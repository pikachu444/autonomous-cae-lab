"""Service-owned Material drafts, shared Undo and append-only saved revisions."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
import threading
import uuid

from .adapters.felupe_material import validate_settings
from .evaluation import file_hash, read_result
from .jobs import TERMINAL
from .storage import canonical_hash, check_id, load_json, save_json, utc_now


OPERATIONS = {'material.update', 'material.evaluate', 'document.undo', 'document.redo', 'document.save'}
NATIVE_LAWS = ('material.mfront', 'material.mfront.hyperelastic', 'material.mfront.viscoelastic', 'material.mfront.user')


def default_draft():
    return {'backend': 'material.felupe', 'settings': {
        'model': 'linear_elastic', 'stress_unit': 'MPa', 'time_unit': 's',
        'parameters': {'E': 1000, 'nu': .25}, 'time': [0, 1, 2],
        'deformation_gradient': [[[1 + strain, 0, 0], [0, 1, 0], [0, 0, 1]] for strain in [0, .001, .002]]}}


def diagnostics(draft):
    try:
        if set(draft) != {'backend', 'settings'}:
            raise ValueError('Material draft requires only backend and settings; hidden execution overrides are not allowed')
        if draft.get('backend') == 'material.law_native':
            from plugins.material_point.law_native import validate_settings as validate_law_native
            validate_law_native(draft['settings'])
            return []
        if draft.get('backend') in NATIVE_LAWS:
            from .simulation_document import validate_draft
            validate_draft(draft)
            return []
        if draft.get('backend') != 'material.felupe':
            raise ValueError('This editor supports the registered FELUPE material-point adapter')
        if not isinstance(draft.get('settings'), dict):
            raise ValueError('Material settings must be an object')
        if set(draft['settings']) - {'tangent_probe', 'boundary_control'} != {'model', 'stress_unit', 'time_unit', 'parameters', 'time', 'deformation_gradient'}:
            raise ValueError('Material settings require model, parameters, time, deformation_gradient and both units')
        validate_settings(draft['settings'])
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return [{'severity': 'error', 'path': getattr(error,'path','settings'), 'line':getattr(error,'line',None), 'column':getattr(error,'column',None), 'message': str(error), 'blocks_evaluation': True}]
    return []


from .retained_comparisons import RetainedComparisons


class MaterialDocuments(RetainedComparisons):
    kind = 'material'
    prefix = 'M'
    update_operation = 'material.update'
    evaluate_operation = 'material.evaluate'
    evaluation_operation = 'evaluate'

    @property
    def evaluation_commands(self):
        return {self.evaluate_operation}

    @property
    def operations(self):
        return {self.update_operation, 'document.undo', 'document.redo', 'document.save'} | self.evaluation_commands

    def prepare_command_job(self, operation, arguments, document):
        if arguments:
            raise ValueError('Evaluate requires empty arguments')
        errors = self.diagnostics(document['draft'])
        if errors:
            raise ValueError('Invalid draft blocks evaluation: ' + errors[0]['message'])
        snapshot = deepcopy(document['draft'])
        return snapshot, self.evaluation_for(snapshot), self.prepare_job_arguments(snapshot, document)

    def command_input_context(self, operation, arguments, document, snapshot):
        """Identity of the frozen input; command authority still uses the open draft."""
        return {'input_generation': document['generation'], 'input_revision': document['input_revision']}

    @staticmethod
    def default_draft():
        return default_draft()

    @staticmethod
    def diagnostics(draft):
        return diagnostics(draft)

    @staticmethod
    def job_arguments(draft):
        return deepcopy(draft)

    def prepare_job_arguments(self, draft, document):
        """Resolve owner-specific inputs before the command publishes its submission."""
        return self.job_arguments(draft)

    def evaluation_for(self, draft):
        if self.kind == 'material' and draft.get('backend') in NATIVE_LAWS:
            return 'simulation.run'  # Existing file-backed run/domain retention, no new runner.
        return self.evaluation_operation

    def _retain_inputs(self, saved, folder):
        """Concrete document owners retain external inputs before publication."""
        self._retain_comparisons(saved, folder)
        if self.kind == 'material':
            from .material_fe_transfer import retain_inputs
            retain_inputs(saved, folder)

    def __init__(self, root, session_id, submit, manager):
        self.root = Path(root) / 'documents'
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_id, self.submit, self.manager = session_id, submit, manager
        self._documents, self._locks = {}, {}
        self._catalog_lock = threading.RLock()

    def _folder(self, identifier):
        return self.root / check_id(identifier)

    @staticmethod
    def _draft(value):
        if not isinstance(value, dict) or len(json.dumps(value, allow_nan=False).encode()) > 96 * 1024:
            raise ValueError('A Material draft must be a JSON object of at most 96 KiB')
        return deepcopy(value)

    def _lock(self, identifier):
        with self._catalog_lock:
            return self._locks.setdefault(check_id(identifier), threading.RLock())

    def _persist_draft(self, document):
        save_json(self._folder(document['id']) / 'working.json', document)

    def acknowledged_state(self, identifier):
        """Exact owner/durable state for read-only recovery; never a UI projection.

        Working persistence acknowledges the entire internal document, including
        run/reference/Undo metadata. A published saved pointer is independently
        verified. An unresolved write cannot be healed by a Keep operation.
        """
        with self._lock(identifier):
            if identifier not in self._documents:
                self.read(identifier)
            document = deepcopy(self._documents[identifier])
            path = self._folder(identifier) / 'working.json'
            before = file_hash(path)
            durable = load_json(path)
            if file_hash(path) != before or canonical_hash(durable) != canonical_hash(document):
                raise ValueError('Acknowledged owner and durable working content differ')
            manifest = self._manifest(identifier)
            revision = (manifest or {}).get('revision')
            if revision != document.get('saved_revision') or revision != document.get('_disk_revision'):
                raise ValueError('Published saved pointer and acknowledged owner differ')
            if manifest:
                folder = self._folder(identifier) / 'revisions' / check_id(revision)
                if file_hash(folder / 'revision.json') != manifest['revision_sha256']:
                    raise ValueError('Acknowledged saved revision manifest changed')
                saved = self._verify_revision(identifier, revision)
                if (saved.get('id') != identifier or saved.get('saved_revision') != revision
                        or self._fingerprint(saved) != manifest['fingerprint']
                        or document.get('_saved_fingerprint') != manifest['fingerprint']):
                    raise ValueError('Acknowledged saved reference content differs')
            return {'document': document, 'durability': {'working_sha256': before,
                    'working_content_sha256': canonical_hash(durable),
                    'published_manifest': deepcopy(manifest)}}

    def _manifest(self, identifier):
        path = self._folder(identifier) / 'document.json'
        return load_json(path) if path.exists() else None

    def _verify_revision(self, identifier, revision):
        from .storage import revision_read_cache
        cache = revision_read_cache()
        key = (id(self), check_id(identifier), check_id(revision))
        if cache is not None and key in cache:
            return deepcopy(cache[key])
        folder = (self._folder(identifier) / 'revisions' / revision).resolve()
        manifest = load_json(folder / 'revision.json')
        for item in manifest['files']:
            path = (folder / item['path']).resolve()
            if not path.is_relative_to(folder) or not path.is_file() or file_hash(path) != item['sha256']:
                raise ValueError('A retained Material revision asset changed or is missing')
        document = load_json(folder / 'document.json')
        if cache is not None:
            cache[key] = deepcopy(document)
        return document

    def open(self, *, title='Material research', draft=None, document_id=None, _new_id=None):
        # Internal, deterministic creation identity supports cross-owner handoff
        # recovery. Public HTTP/MCP open still accepts only document_id for reopen.
        if _new_id is not None and document_id is not None:
            raise ValueError('Choose new creation or reopen, not both')
        identifier = check_id(document_id or _new_id or self.prefix + uuid.uuid4().hex)
        if not identifier.startswith(self.prefix):
            raise ValueError(f'{self.kind} document identities must start with {self.prefix}')
        if not isinstance(title, str) or not title.strip() or len(title) > 160:
            raise ValueError('Document title must contain 1 to 160 characters')
        with self._lock(identifier):
            if identifier in self._documents:
                if draft is not None:
                    raise ValueError('Use a generation-checked command to edit an open document')
                return self.read(identifier)
            manifest = self._manifest(identifier)
            working = self._folder(identifier) / 'working.json'
            if manifest:
                if draft is not None:
                    raise ValueError('Opening a saved document does not replace its draft')
                saved = self._verify_revision(identifier, manifest['revision'])
                if file_hash(self._folder(identifier) / 'revisions' / manifest['revision'] / 'revision.json') != manifest['revision_sha256']:
                    raise ValueError('Material revision manifest changed')
                document = load_json(working) if working.exists() else saved
                if document.get('saved_revision') != manifest['revision']:
                    document = saved
                document['_saved_fingerprint'] = manifest['fingerprint']
                document['_disk_revision'] = manifest['revision']
                document['saved_revision'] = manifest['revision']
            elif working.exists():
                if draft is not None:
                    raise ValueError('A recoverable draft already exists')
                document = load_json(working)
            elif document_id:
                raise FileNotFoundError('Material document does not exist')
            else:
                document = {'id': identifier, 'kind': self.kind, 'title': title, 'generation': 0,
                            'input_revision': 'I' + uuid.uuid4().hex, 'saved_revision': None,
                            'draft': self._draft(self.default_draft() if draft is None else draft), 'runs': [],
                            '_undo': [], '_redo': [], '_saved_fingerprint': None, '_disk_revision': None}
            document['session_id'] = self.session_id
            self._documents[identifier] = document
            self._persist_draft(document)
            return self.read(identifier)

    @staticmethod
    def _fingerprint(document):
        values = {key: document[key] for key in ('title', 'draft', 'runs')}
        if document.get('adoptions'):
            values['adoptions'] = document['adoptions']
        if document.get('kind') != 'data' and document.get('comparisons'):
            # Data retains its existing outer comparison fingerprint. Older
            # documents without comparisons keep their original fingerprint.
            values['comparisons'] = document['comparisons']
        return canonical_hash(values)

    def adopt(self, identifier, draft, source, *, expected_input_revision, expected_input_hash,
              session_id, expected_generation, command_id):
        """Atomic target-owner edit after the Workbench validates a retained candidate."""
        if self.kind not in {'material', 'pde', 'simulation', 'evaluation'} or session_id != self.session_id:
            raise ValueError('Adoption requires the current target domain owner session')
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError('Adoption requires an exact ' + self.kind + ' generation')
        command_id = check_id(command_id)
        # A Plan save may copy the same immutable run to another retained folder.
        # That storage location is not a different adoption request.
        source_identity = {key:value for key,value in source.items() if key != 'plan_revision'}
        signature = canonical_hash(dict(draft=draft, source=source_identity, generation=expected_generation,
            session_id=session_id, expected_input_revision=expected_input_revision, expected_input_hash=expected_input_hash))
        with self._lock(identifier):
            self.read(identifier)
            current = self._documents[identifier]
            receipt = self._folder(identifier) / 'commands' / (command_id + '.json')
            if receipt.exists():
                prior = load_json(receipt)
                if prior['request_hash'] != signature:
                    raise ValueError('Adoption command_id conflicts with another request')
                if 'response' in prior:
                    return prior['response']
                if any(row.get('command_id') == command_id for row in current.get('adoptions', [])):
                    return {'document': self._public(current), 'command_id': command_id}
            if (current['generation'] != expected_generation or current['input_revision'] != expected_input_revision
                    or canonical_hash(current['draft']) != expected_input_hash):
                raise ValueError(self.kind.title() + ' changed after this Plan was bound; rebind explicitly before adoption')
            draft = self._draft(draft)
            if self.diagnostics(draft):
                raise ValueError('Candidate is not a valid ' + self.kind.title() + ' input')
            updated = deepcopy(current)
            updated['_undo'].append(deepcopy(current['draft']))
            updated['_redo'] = []
            updated['draft'] = draft
            self._changed(updated)
            updated.setdefault('adoptions', []).append({**deepcopy(source), 'command_id': command_id,
                'input_revision': updated['input_revision'], 'created_utc': utc_now()})
            save_json(receipt, {'request_hash': signature, 'operation': self.kind + '.adopt', 'state': 'APPLYING'})
            self._persist_draft(updated)
            self._documents[identifier] = updated
            response = {'document': self._public(updated), 'command_id': command_id}
            save_json(receipt, {'request_hash': signature, 'response': response})
            return response

    def _public(self, document):
        result = {key: deepcopy(value) for key, value in document.items() if not key.startswith('_')}
        result.update(diagnostics=self.diagnostics(document['draft']), can_undo=bool(document['_undo']),
                      can_redo=bool(document['_redo']), dirty=self._fingerprint(document) != document['_saved_fingerprint'],
                      capabilities=sorted(self.operations))
        from .adapters.native_doctor import service_platform
        # Public, live service context; never part of draft/revision fingerprints.
        result['service_platform'] = service_platform()
        for run in result['runs']:
            run['is_current_input'] = run['input_sha256'] == canonical_hash(document['draft'])
        if self.kind == 'material' and document['draft'].get('backend') in NATIVE_LAWS:
            from .simulation_document import support_details
            result['material_support'] = support_details(document['draft'])
        if self.kind == 'material' and document['draft'].get('backend') == 'material.law_native':
            from plugins.material_point.law_native import declaration
            try:
                result['material_support'] = declaration(document['draft']['settings'])
            except (ValueError, TypeError, KeyError):
                result['material_support'] = {'status':'INVALID_DRAFT', 'evidence':'NOT_RUN'}
        return result

    def read(self, identifier):
        with self._lock(identifier):
            if identifier not in self._documents:
                return self.open(document_id=identifier)
            self._recover_evaluations(self._documents[identifier])
            return self._public(self._documents[identifier])

    def _run_record(self, job, draft, generation, revision, session_id):
        record = {'job_id': job['id'], 'input_generation': generation, 'input_revision': revision,
                  'input_sha256': canonical_hash(draft), 'operation': job['operation'],
                  'arguments': deepcopy(job['arguments']), 'draft': deepcopy(draft),
                  'service_session_id': session_id, 'created_utc': job['created_utc']}
        if 'backend' in draft and 'settings' in draft:
            record.update(backend=draft['backend'], settings=deepcopy(draft['settings']))
        return record

    def _recover_evaluations(self, document):
        """A submitted job survives a lost document write; attach it without resubmitting."""
        for path in (self._folder(document['id']) / 'commands').glob('*.json'):
            prior = load_json(path)
            if 'response' in prior or prior.get('operation') not in self.evaluation_commands:
                continue
            request_id = self.kind + ':' + document['id'] + ':' + path.stem
            job = next((job for job in self.manager.list() if job.get('request_id') == request_id), None)
            if job is None:
                continue
            # Resolve document/file bindings once, before submit. A lost response
            # must recover that exact submission, even after a source owner edits.
            operation = prior.get('submitted_operation', self.evaluation_for(prior['input']))
            arguments = prior.get('submitted_arguments')
            if arguments is None:  # Read pre-hook Material command receipts.
                arguments = self.job_arguments(prior['input'])
            if job['operation'] != operation or canonical_hash(job['arguments']) != canonical_hash(arguments):
                raise ValueError('Interrupted Material command and retained job input disagree')
            snapshot = prior.get('submitted_input', prior['input'])
            input_document = dict(document, generation=prior['input_generation'],
                                  input_revision=prior.get('input_revision'))
            expected_context = self.command_input_context(prior['operation'], arguments, input_document, snapshot)
            context = prior.get('submitted_input_context', expected_context)
            if context != expected_context:
                raise ValueError('Interrupted command and retained input identity disagree')
            if not any(run['job_id'] == job['id'] for run in document['runs']):
                run = self._run_record(job, snapshot, context['input_generation'], context['input_revision'], prior.get('session_id'))
                run['recovered_after_response_loss'] = True
                document['runs'].append(run)
            self._persist_draft(document)
            prior['response'] = {'document': self._public(document), 'command_id': path.stem, 'job': job,
                                 'recovered_after_response_loss': True}
            save_json(path, prior)

    def list(self):
        identifiers = {path.parent.name for path in self.root.glob('*/working.json')}
        identifiers.update(path.parent.name for path in self.root.glob('*/document.json'))
        identifiers.update(self._documents)
        return [self.read(identifier) for identifier in sorted(identifiers) if identifier.startswith(self.prefix)]

    def command(self, identifier, operation, arguments, *, session_id, expected_generation, command_id=None):
        if operation not in self.operations or not isinstance(arguments, dict):
            raise ValueError('Unsupported Material command')
        if session_id != self.session_id:
            raise ValueError('Document session is stale; reopen after service restart')
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError('An exact input generation is required')
        command_id = check_id(command_id or 'C' + uuid.uuid4().hex)
        signature = canonical_hash(dict(document_id=identifier, operation=operation, arguments=arguments,
                                        session_id=session_id, expected_generation=expected_generation))
        with self._lock(identifier):
            self.read(identifier)
            from .related_save import recover_saved_commands
            from .related_save_edits import recover_mutation
            recover_saved_commands(self, identifier)
            recover_mutation(self, identifier, command_id)
            if self.kind == 'data':
                from .data_processing_document import recover_apply
                recover_apply(self, identifier)
            document = deepcopy(self._documents[identifier])
            receipt = self._folder(identifier) / 'commands' / (command_id + '.json')
            if receipt.exists():
                prior = load_json(receipt)
                if prior['request_hash'] != signature:
                    raise ValueError('command_id conflicts with an earlier request')
                if 'response' not in prior:
                    raise ValueError('Previous command outcome is unconfirmed; reread the document before a new command')
                return prior['response']
            if document['generation'] != expected_generation:
                raise ValueError('Document generation changed; reread before applying')
            save_json(receipt, {'request_hash': signature, 'state': 'APPLYING', 'operation': operation,
                               'input_generation': expected_generation, 'input': document['draft'],
                               'input_revision': document['input_revision'], 'session_id': self.session_id})
            if operation == self.update_operation:
                allowed = {'draft', 'portable_recovery_inputs'} if self.kind == 'data' else {'draft'}
                if 'draft' not in arguments or set(arguments) - allowed:
                    raise ValueError('Material update requires only draft; Data may carry an explicit portable source review')
                draft = self._draft(arguments['draft'])
                if canonical_hash(draft) != canonical_hash(document['draft']):
                    document['_undo'].append(deepcopy(document['draft']))
                    document['_redo'] = []
                    document['draft'] = draft
                    self._changed(document)
                if self.kind == 'data' and 'portable_recovery_inputs' in arguments:
                    from .portable_recovery_data_inputs import retain_for_resume
                    retain_for_resume(self, document, arguments['portable_recovery_inputs'], command_id=command_id)
            elif operation in {'document.undo', 'document.redo'}:
                if arguments:
                    raise ValueError('Undo/Redo requires empty arguments')
                source, destination = ('_undo', '_redo') if operation == 'document.undo' else ('_redo', '_undo')
                if not document[source]:
                    raise ValueError('No edit is available to ' + operation.split('.')[1])
                document[destination].append(deepcopy(document['draft']))
                document['draft'] = document[source].pop()
                self._changed(document)
            elif operation == 'data.processing.apply' and self.kind == 'data':
                from .data_processing_document import apply
                processing = apply(self, document, arguments, command_id)
            elif arguments and operation not in self.evaluation_commands:
                raise ValueError('Save/evaluate requires empty arguments')
            job = None
            if operation in self.evaluation_commands:
                snapshot, operation_to_run, arguments_to_run = self.prepare_command_job(operation, arguments, document)
                input_context = self.command_input_context(operation, arguments_to_run, document, snapshot)
                prepared = load_json(receipt)
                prepared.update(submitted_operation=operation_to_run, submitted_arguments=arguments_to_run,
                                submitted_input=deepcopy(snapshot), submitted_input_context=deepcopy(input_context))
                save_json(receipt, prepared)
                job = self.submit(operation_to_run, arguments_to_run, request_id=self.kind + ':' + identifier + ':' + command_id)
                document['runs'].append(self._run_record(job, snapshot, input_context['input_generation'],
                                                        input_context['input_revision'], self.session_id))
            if operation == 'document.save':
                from .related_save import save_marker
                document['_save_command'] = save_marker(document, command_id, signature)
                document['_save_command']['content_sha256'] = self._fingerprint(document)
                self._save(document)
                self._persist_draft(document)  # acknowledge the published saved pointer too
            else:
                if operation in {self.update_operation, 'document.undo', 'document.redo'}:
                    from .related_save_edits import mutation_marker
                    document['_mutation_command'] = mutation_marker(document, operation=operation,
                        command_id=command_id, request_hash=signature)
                self._persist_draft(document)
            self._documents[identifier] = document
            response = {'document': self._public(document), 'command_id': command_id}
            if operation in {self.update_operation, 'document.undo', 'document.redo'}:
                # Existing receipt binds the FULL acknowledged post-state, not
                # only input identity (evaluate/comparison can keep that identity).
                response['acknowledged_document_sha256'] = canonical_hash(document)
            if job is not None:
                response['job'] = job
            if operation == 'data.processing.apply':
                response['processing'] = processing
            save_json(receipt, {'request_hash': signature, 'response': response})
            return response

    @staticmethod
    def _changed(document):
        document['generation'] += 1
        document['input_revision'] = 'I' + uuid.uuid4().hex

    def _save(self, document):
        identifier = document['id']
        previous = self._manifest(identifier)
        if (previous or {}).get('revision') != document['_disk_revision']:
            raise ValueError('Saved document changed outside this owner; reopen before saving')
        revision = 'R' + uuid.uuid4().hex
        folder = self._folder(identifier) / 'revisions' / revision
        folder.mkdir(parents=True)
        saved = deepcopy(document)
        self._retain_inputs(saved, folder)
        for run in saved['runs']:
            if self.kind == 'expert' and run.get('portable_history_only'):
                from .portable_research_owner import retain_job
                retain_job(self, saved, folder, run, revision)
                continue
            retained = run.get('retained_record') or run.get('retained_result')
            if retained and run.get('retention_complete'):
                self._verify_revision(identifier, retained['revision'])
                previous_folder = self._folder(identifier) / 'revisions' / retained['revision']
                job = load_json(previous_folder / 'jobs' / (check_id(run['job_id']) + '.json'))
                source = previous_folder / 'results' / run['job_id']
            else:
                job = self.manager.status(run['job_id'])
                source = self.manager.root / 'results' / check_id(run['job_id'])
            expected = run.get('arguments')
            if expected is None:
                expected = {'backend': run['backend'], 'settings': run['settings']}
            if job['arguments'] != expected or job['operation'] != run.get('operation', 'evaluate'):
                raise ValueError('Retained job inputs differ from the Material run')
            save_json(folder / 'inputs' / (run['job_id'] + '.json'), run)
            save_json(folder / 'jobs' / (run['job_id'] + '.json'), job)
            if job['result_refs']:
                read_result(source, verify='all', selection={'metadata_only': True})
                before = {path.relative_to(source).as_posix(): file_hash(path) for path in source.rglob('*') if path.is_file()}
                destination = folder / 'results' / run['job_id']
                shutil.copytree(source, destination)
                if {path.relative_to(destination).as_posix() for path in destination.rglob('*') if path.is_file()} != set(before):
                    raise ValueError('Result file set changed during Material save')
                for relative, digest in before.items():
                    if file_hash(source / relative) != digest or file_hash(destination / relative) != digest:
                        raise ValueError('Result changed during Material save; previous revision preserved')
                read_result(destination, verify='all', selection={'metadata_only': True})
                run['retained_result'] = {'revision': revision, 'job_id': run['job_id']}
            elif self.kind == 'evaluation':
                from .portable_project_evaluation import retain_partial_inputs
                retain_partial_inputs(self, saved, folder, run, job, source)
            run['retained_state'] = job['state']
            run['retained_error'] = deepcopy(job.get('error'))
            run['retention_complete'] = job['state'] in TERMINAL
            run['retained_record'] = {'revision': revision, 'job_id': run['job_id']}
        saved.update(saved_revision=revision, _disk_revision=revision)
        saved['_saved_fingerprint'] = self._fingerprint(saved)
        save_json(folder / 'document.json', saved)
        files = [{'path': path.relative_to(folder).as_posix(), 'sha256': file_hash(path)}
                 for path in sorted(folder.rglob('*')) if path.is_file()]
        save_json(folder / 'revision.json', {'id': identifier, 'revision': revision, 'files': files})
        self._verify_revision(identifier, revision)
        if self._manifest(identifier) != previous:
            raise ValueError('Saved document changed during save; previous revision preserved')
        # Publication is the only mutable pointer; every required asset precedes it.
        save_json(self._folder(identifier) / 'document.json', {'id': identifier, 'revision': revision,
                  'revision_sha256': file_hash(folder / 'revision.json'), 'fingerprint': saved['_saved_fingerprint']})
        document.clear()
        document.update(saved)

    def result(self, identifier, job_id, *, selection=None):
        with self._lock(identifier):
            document = self.read(identifier)
            run = next((run for run in document['runs'] if run['job_id'] == job_id), None)
            if run is None:
                raise ValueError('Job does not belong to this Material document')
            if run.get('retained_result'):
                revision = run['retained_result']['revision']
                self._verify_revision(identifier, revision)
                return read_result(self._folder(identifier) / 'revisions' / revision / 'results' / check_id(job_id),
                                   verify='all', selection=selection)
            if run.get('retention_complete'):
                error = run.get('retained_error') or {}
                raise ValueError('Retained run has no response: ' + run['retained_state'] + '; ' + error.get('message', ''))
            return self.manager.result(job_id, selection=selection)
