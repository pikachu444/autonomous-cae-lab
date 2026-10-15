"""Connections between existing native owners, retained inputs and JobManager.

No executable paths or arbitrary source roots are accepted from a client.
Native exporters write into this workspace's private exchange directory.
"""
from copy import deepcopy
from pathlib import Path
import os
import shutil
import sys
import threading
import uuid

from .native_inputs import register_frozen_input
from .storage import canonical_hash, check_id, load_json, save_json


class DesktopLinks:
    def __init__(self, workbench):
        self.workbench = workbench
        self.root = workbench.root / 'native_exchange'
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def context(self):
        config = self.workbench.config.get('desktop', {})
        return {'service_session_id': self.workbench.session_id,
                'export_root': str(self.root), 'python': sys.executable,
                'repo_root': str(Path(__file__).resolve().parents[1]),
                'freecad_executable': config.get('freecad_executable') or os.getenv('CAELAB_FREECAD_EXE') or shutil.which('FreeCAD') or shutil.which('freecad'),
                'paraview_executable': config.get('paraview_executable') or os.getenv('CAELAB_PARAVIEW_EXE') or shutil.which('paraview')}

    def submit_frozen(self, command_id):
        """Retry one completed export without registering/submitting it twice."""
        wb = self.workbench
        command_id = check_id(command_id)
        exports = {'pre.freeze': ('frozen_fem', 'structure.calculix.frozen'),
            'pre.contact.freeze': ('frozen_contact', 'structure.calculix.contact'),
            'pre.shell.freeze': ('frozen_shell', 'structure.calculix.shell'),
            'pre.beam.freeze': ('frozen_beam', 'structure.calculix.beam'),
            'pre.dynamic.freeze': ('frozen_contact', 'structure.calculix.contact'),
            'pre.dynamic.restart': ('frozen_contact', 'structure.calculix.contact')}
        with self._lock:
            command = wb.native_commands.status(command_id)
            if command['operation'] not in exports or command['state'] != 'SUCCEEDED':
                raise ValueError('A completed native FEM/contact/dynamic export command is required')
            envelope = command.get('outcome', {}).get('result', {})
            result = envelope.get('result', {})
            if envelope.get('status') != 'COMPLETED':
                raise ValueError('Native export has no completed outcome')
            relative = result.get('snapshot_relative')
            from .workbench import contained
            manifest = contained(self.root, relative)
            if manifest.name != 'snapshot.json' or manifest.parent.parent.name != command['document_id']:
                raise ValueError('Export must belong to this exact native document exchange folder')
            record = self.root / 'submissions' / (command_id + '.json')
            if record.exists():
                previous = load_json(record)
                if previous['command_hash'] != command['request_hash']:
                    raise ValueError('Native submission command changed')
                receipt = previous['input']
                wb.input_path(receipt['id'])
            else:
                receipt = register_frozen_input(wb.root, self.root, manifest, 'D' + uuid.uuid4().hex,
                    root_id='native-owner:' + command['document_id'], relative=relative,
                    limit=wb.config.get('local_input_max_bytes', 2 * 1024 ** 3))
                save_json(record, {'command_hash': command['request_hash'], 'input': receipt})
            receipt_kind, backend = exports[command['operation']]
            if receipt.get('kind') != receipt_kind:
                raise ValueError('Registered snapshot kind differs from the completed export operation')
            if command['operation'] in {'pre.dynamic.freeze', 'pre.dynamic.restart'}:
                from .adapters.contact_fem import validate_snapshot
                from .dynamic_model import enabled, has_dynamic
                _, model, _, _ = validate_snapshot(wb.input_path(receipt['id']))
                if (not enabled(model) or not has_dynamic(model['analysis_steps']) or
                        bool(model.get('restart')) != (command['operation'] == 'pre.dynamic.restart')):
                    raise ValueError('Dynamic export operation differs from its admitted new-run/READ input')
            origin = {'kind': 'pre', 'document_id': command['document_id'],
                      'session_id': command['session_id'], 'generation': command.get('final_generation', command['expected_generation']),
                      'command_id': command_id, 'input_id': receipt['id']}
            job = wb.submit('run', {'backend': backend,
                'settings': {'data_id': receipt['id']}, 'origin': origin,
                'label': result.get('label', 'FreeCAD FEM analysis')[:160]},
                request_id='native-frozen:' + command_id)
            return {'job': job, 'input': receipt, 'origin': origin}

    def research_job(self, job_id):
        """Find the exact saved owner record, without recreating a controller job."""
        job_id = check_id(job_id)
        for owner in self.workbench.research_owners():
            for document in owner.list():
                run = next((row for row in document['runs'] if row['job_id'] == job_id), None)
                if run is not None:
                    return owner, document, run
        return None

    @staticmethod
    def _retained_job(match):
        owner, document, run = match
        reference = run.get('retained_record')
        if not reference:
            raise ValueError('The original job is unavailable and no saved job record exists')
        owner._verify_revision(document['id'],reference['revision'])
        job = load_json(owner._folder(document['id']) / 'revisions' / reference['revision'] / 'jobs' / (run['job_id']+'.json'))
        if job['id'] != run['job_id'] or job['operation'] != run['operation'] or job['arguments'] != run['arguments']:
            raise ValueError('Saved job record differs from this document input')
        from .jobs import TERMINAL
        if job['state'] not in TERMINAL:
            job.update(state='INTERRUPTED', recorded_state=job['state'],
                message='Historical job snapshot; original controller record is unavailable')
        job['retained_owner_document_id'] = document['id']
        job['live_controller_record'] = False
        return job

    def job_record(self, job_id):
        try:
            return self.workbench.manager.status(check_id(job_id))
        except (KeyError, FileNotFoundError):
            match = self.research_job(job_id)
            if match is None:
                raise ValueError('No current or owner-retained job record is available')
            return self._retained_job(match)

    def navigation(self, job_id):
        wb = self.workbench
        job = self.job_record(job_id)
        result = {'job_id': job_id, 'origin_document': None, 'post_input': None, 'post_inputs': [],
                  'retained_design_input_id': None}
        origin = job['arguments'].get('origin', {})
        match = None
        if job['arguments'].get('backend') in {'structure.calculix.frozen', 'structure.calculix.contact', 'structure.calculix.shell', 'structure.calculix.beam'}:
            result['retained_design_input_id'] = job['arguments']['settings']['data_id']
        if origin.get('kind') == 'pre':
            try:
                current = wb.native_commands.read(origin['document_id'])
                result['origin_document'] = {key: current.get(key) for key in
                    ('id', 'kind', 'title', 'session_id', 'generation', 'connected')}
            except KeyError:
                pass
            result['frozen_origin'] = deepcopy(origin)
        else:
            match = self.research_job(job_id)
            if match:
                _, document, _ = match
                result['origin_document'] = {key: document.get(key) for key in ('id','kind','title','session_id','generation')}
                result['origin_document']['connected'] = True
        if job.get('result_refs'):
            summary = (match[0].result(match[1]['id'],job_id,selection={'responses': []}) if match
                       else wb.result(job_id,selection={'responses': []}))
            for item in summary.get('post_inputs', []):
                native = wb.native_input(item['id'])
                if native['sha256'] != item['sha256']:
                    raise ValueError('Registered Post input differs from this saved result')
                result['post_inputs'].append(deepcopy(item))
            post = summary.get('post_input')
            if post:
                native = wb.native_input(post['id'])
                if native['sha256'] != post['sha256']:
                    raise ValueError('Registered Post input differs from this saved result')
                result['post_input'] = deepcopy(post)
        return result

    def adopt(self, plan_id, job_id, candidate_id, *, material_document_id,
              session_id, expected_generation, command_id, detail_evidence=None):
        """The Plan owns the search; only its selected coefficients edit Material."""
        from .numerical_document import adopted_draft
        wb = self.workbench
        plan = wb.numerical_documents.read(check_id(plan_id))
        run = next((row for row in plan['runs'] if row['job_id'] == job_id), None)
        if run is None:
            raise ValueError('Selected run does not belong to this Numerical Plan')
        if run['draft'].get('mode') == 'request':
            raise ValueError('This request has no bound Material target; do not infer coefficient adoption')
        frozen = run['draft']['material']
        if frozen['document_id'] != material_document_id:
            raise ValueError('Candidate belongs to a different Material document')
        result = wb.numerical_documents.result(plan_id, check_id(job_id))
        draft = adopted_draft(run, result, candidate_id, evidence_owner=wb.numerical_documents,
                              detail_evidence=detail_evidence)
        # Reuse the exact verified retained run on retries. A result read above
        # already verified its immutable revision; adoption does not need to
        # copy every Plan result to another revision on each lost HTTP response.
        retained = run.get('retained_result')
        if retained and run.get('retention_complete'):
            revision = retained['revision']
        else:
            saved = wb.numerical_documents.command(plan_id, 'document.save', {},
                session_id=plan['session_id'], expected_generation=plan['generation'])['document']
            revision = saved['saved_revision']
        source = {'plan_id': plan_id, 'plan_revision': revision, 'job_id': job_id,
                  'candidate_id': candidate_id, 'input_sha256': run['input_sha256'],
                  'coefficient_sha256': canonical_hash(draft['settings']['parameters'])}
        if result.get('kind') == 'fit':
            source['candidate_evidence'] = deepcopy(detail_evidence)
        return wb.material_documents.adopt(material_document_id, draft, source,
            expected_input_revision=frozen['input_revision'], expected_input_hash=canonical_hash(frozen['draft']),
            session_id=session_id, expected_generation=expected_generation, command_id=command_id)

    def _pde_candidate(self, plan_id, job_id, candidate_id):
        """Resolve a retained candidate and its explicitly bound original PDE."""
        from .pde_candidate import prepare_candidate
        wb = self.workbench
        plan = wb.numerical_documents.read(check_id(plan_id))
        run = next((row for row in plan.get('runs', []) if row['job_id'] == check_id(job_id)), None)
        if run is None:
            raise ValueError('The selected result does not belong to this Numerical Plan')
        source = run.get('draft', {}).get('model_source') or run.get('draft', {}).get('source')
        if not isinstance(source, dict):
            raise ValueError('This Plan has no explicitly bound original PDE document')
        target = source.get('pde_document_id') or (source.get('document_id') if source.get('kind') == 'pde' else None)
        if not isinstance(target, str) or not target.startswith('Q'):
            raise ValueError('This Plan does not declare a PDE adoption target')
        original = wb.pde_documents._verify_revision(check_id(target), check_id(source['saved_revision']))
        if (original.get('kind') != 'pde' or original['input_revision'] != source.get('input_revision')
                or canonical_hash(original['draft']) != source.get('input_sha256')):
            raise ValueError('Saved PDE input differs from the Plan source')
        result = wb.numerical_documents.result(plan_id, job_id)
        prepared = prepare_candidate(run, result, candidate_id, original)
        return plan, run, result, source, target, original, prepared

    @staticmethod
    def _draft_changes(before, after):
        changes = []
        missing = object()
        def bounded(value):
            if value is missing:
                return {'present': False}
            if isinstance(value, (dict, list)):
                return {'type': type(value).__name__, 'count': len(value), 'sha256': canonical_hash(value)}
            return value
        def visit(left, right, path):
            if type(left) is type(right) and left == right:
                return
            if isinstance(left, dict) and isinstance(right, dict):
                for key in sorted(left.keys() | right.keys()):
                    visit(left.get(key, missing), right.get(key, missing), path + [key])
            elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right) and len(left) <= 32:
                for i, (a, b) in enumerate(zip(left, right)):
                    visit(a, b, path + [i])
            else:
                changes.append({'path': path, 'before': bounded(left), 'after': bounded(right)})
        visit(before, after, [])
        return changes

    def pde_candidate_preview(self, plan_id, job_id, candidate_id):
        _, run, result, source, target, original, prepared = self._pde_candidate(plan_id, job_id, candidate_id)
        return {'target_document_id': target, 'candidate_id': candidate_id,
                'draft': deepcopy(prepared['draft']), 'source': deepcopy(source),
                'changes': self._draft_changes(original['draft'], prepared['draft']),
                'candidate_source': deepcopy(prepared['source']),
                'result_sha256': canonical_hash(result), 'plan_input_sha256': run['input_sha256'],
                'executed': False, 'engineering_release': 'NOT_RELEASED'}

    def pde_adopt(self, plan_id, job_id, candidate_id, *, pde_document_id,
                  session_id, expected_generation, command_id, detail_evidence=None):
        wb = self.workbench
        if session_id != wb.session_id:
            raise ValueError('PDE adoption requires the current service session')
        plan, run, result, frozen, target, original, prepared = self._pde_candidate(plan_id, job_id, candidate_id)
        if result.get('kind') == 'fit':
            from .numerical_candidate_evidence import require_adoption_evidence
            require_adoption_evidence(wb.numerical_documents, detail_evidence, run, result, candidate_id)
        if target != check_id(pde_document_id):
            raise ValueError('The selected candidate belongs to another PDE document')
        retained = run.get('retained_result')
        if retained and run.get('retention_complete'):
            revision = retained['revision']
        else:
            saved = wb.numerical_documents.command(plan_id, 'document.save', {},
                session_id=session_id, expected_generation=plan['generation'])['document']
            revision = saved['saved_revision']
        source = {**deepcopy(prepared['source']), 'plan_id': plan_id, 'plan_revision': revision,
                  'job_id': job_id, 'candidate_id': candidate_id, 'input_sha256': run['input_sha256'],
                  'result_sha256': canonical_hash(result), 'engineering_release': 'NOT_RELEASED'}
        if result.get('kind') == 'fit':
            source['candidate_evidence'] = deepcopy(detail_evidence)
        return wb.pde_documents.adopt(target, prepared['draft'], source,
            expected_input_revision=frozen['input_revision'], expected_input_hash=frozen['input_sha256'],
            session_id=session_id, expected_generation=expected_generation, command_id=command_id)

    def discussion_plan(self, discussion_id, turn_id, proposal_index, *, session_id, command_id):
        """Open one actual, retained Expert proposal as a Numerical request draft.

        Creating the document cannot submit a calculation. A deterministic
        document identity and receipt recover a lost creation response without
        replacing edits or creating duplicate Plans.
        """
        from .numerical_document import request_draft
        from .assist.experts import validate_plan_request
        wb = self.workbench
        discussion_id, turn_id, command_id = map(check_id, (discussion_id, turn_id, command_id))
        if session_id != wb.session_id:
            raise ValueError('Document session is stale; reread after service restart')
        if type(proposal_index) is not int or proposal_index < 0:
            raise ValueError('Select an exact nonnegative proposal index')
        with self._lock:
            with wb.discussion_documents._lock(discussion_id):
                discussion = wb.discussion_documents.read(discussion_id)
                turn = next((row for row in discussion.get('turns', []) if row['id'] == turn_id), None)
                if turn is None or not turn.get('job_id') or turn.get('job_state') != 'SUCCEEDED':
                    raise ValueError('Select an actual successful Expert reply with a managed job')
                run = next((row for row in discussion['runs'] if row['job_id'] == turn['job_id']), None)
                if run is None or any(run.get(key) != turn.get(key) for key in ('input_revision', 'input_sha256')):
                    raise ValueError('Expert reply and submitted input identity disagree')
                actual = wb.discussion_documents.result(discussion_id, turn['job_id'])
                actions = actual.get('proposed_actions', [])
                if proposal_index >= len(actions):
                    raise ValueError('Proposal is not present in the actual retained reply')
                action = actions[proposal_index]
                if not isinstance(action, dict) or action.get('status') != 'PLANNED' or action.get('executed') is not False:
                    raise ValueError('Only an actual editable, unexecuted Plan proposal can be opened')
                request = validate_plan_request(action.get('plan'))['plan']
                source = {key: run[key] for key in ('job_id','input_revision','input_sha256')}
                source.update(discussion_id=discussion_id, turn_id=turn_id, proposal_index=proposal_index,
                              proposal_sha256=canonical_hash(request))
                signature = canonical_hash(source)
                record = self.root / 'discussion_plans' / (command_id + '.json')
                if record.exists():
                    prior = load_json(record)
                    if prior['request_hash'] != signature:
                        raise ValueError('Plan creation command_id conflicts with another proposal')
                    target = prior['document_id']
                else:
                    # The selected reply/result is retained before publishing its use.
                    wb.discussion_documents.command(discussion_id, 'document.save', {},
                        session_id=session_id, expected_generation=discussion['generation'])
                    target = 'N' + canonical_hash({'command_id':command_id, 'source':source})[:32]
                    save_json(record, {'request_hash':signature, 'document_id':target, 'state':'APPLYING', 'source':source})
            owner = wb.numerical_documents
            with owner._lock(target):
                if (owner._folder(target) / 'working.json').exists() or owner._manifest(target):
                    document = owner.read(target)
                else:
                    document = owner.open(_new_id=target, title=('Plan — ' + request['purpose'])[:160],
                        draft=request_draft(request,source=source))
                save_json(record, {'request_hash':signature, 'document_id':target, 'state':'SUCCEEDED', 'source':source})
            return {'document':document, 'command_id':command_id, 'source':source,
                    'status':'DRAFT_OPENED', 'executed':False}

    def pde_plan(self, document_id, *, session_id, expected_generation, command_id):
        """Retain the chosen PDE input and open an independent editable request."""
        from .numerical_document import request_draft
        wb = self.workbench
        document_id, command_id = map(check_id,(document_id,command_id))
        if session_id != wb.session_id:
            raise ValueError('Document session is stale; reread after service restart')
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError('An exact input generation is required')
        signature = canonical_hash({'document_id':document_id,'session_id':session_id,
                                    'expected_generation':expected_generation})
        record = self.root / 'pde_plans' / (command_id+'.json')
        with self._lock:
            if record.exists():
                prepared = load_json(record)
                if prepared['request_hash'] != signature:
                    raise ValueError('Plan creation command_id conflicts with another input')
            else:
                with wb.pde_documents._lock(document_id):
                    source = wb.pde_documents.read(document_id)
                    if source['generation'] != expected_generation:
                        raise ValueError('PDE input changed; reread before creating its Plan')
                    if source['diagnostics']:
                        raise ValueError('Fix the selected PDE declaration before using it in a Plan')
                    saved = wb.pde_documents.command(document_id,'document.save',{},
                        session_id=session_id,expected_generation=expected_generation)['document']
                    reference = {'pde_document_id':document_id,'saved_revision':saved['saved_revision'],
                                 'input_revision':saved['input_revision'],'input_sha256':canonical_hash(saved['draft'])}
                    request = {'purpose':saved['title'],'operation':'evaluate',
                               'inputs':deepcopy(saved['draft']),'budget':{'evaluations':1}}
                    prepared = {'request_hash':signature,'document_id':'N'+canonical_hash({'command_id':command_id,'source':reference})[:32],
                                'source':reference,'request':request,'state':'APPLYING'}
                    save_json(record,prepared)
            # Do not hold the source Q lock while entering the Numerical owner.
            owner, target = wb.numerical_documents, prepared['document_id']
            with owner._lock(target):
                if (owner._folder(target)/'working.json').exists() or owner._manifest(target):
                    document = owner.read(target)
                else:
                    document = owner.open(_new_id=target,title=('Plan — '+prepared['request']['purpose'])[:160],
                        draft=request_draft(prepared['request'],source=prepared['source']))
                save_json(record,{**prepared,'state':'SUCCEEDED'})
            return {'document':document,'source':prepared['source'],'command_id':command_id,
                    'status':'DRAFT_OPENED','executed':False}

    def data_followup(self, source, kind, *, session_id, command_id, material_document_id=None):
        """Open an actual unexecuted Plan/discussion from the selected Data run."""
        from .numerical_document import from_material_document
        from .discussion_document import default_draft as discussion_draft
        wb=self.workbench
        command_id=check_id(command_id)
        if session_id!=wb.session_id or kind not in {'numerical','expert'}:
            raise ValueError('Select Numerical or Expert in the current service session')
        signature=canonical_hash(dict(source=source,kind=kind,session_id=session_id,material=material_document_id))
        path=self.root/'data_followups'/(command_id+'.json')
        with self._lock:
            if path.exists():
                prepared=load_json(path)
                if prepared['request_hash']!=signature:
                    raise ValueError('Follow-up command conflicts with another source')
            else:
                document,run,observation,binding=wb._curve_reference(source)
                if document['kind']!='data':
                    raise ValueError('Choose a retained Data import')
                # The handoff retains the actual source before opening a target;
                # neither target creation nor later edits reimport/recalculate it.
                saved=wb.data_documents.command(document['id'],'document.save',{},
                    session_id=session_id,expected_generation=document['generation'])['document']
                exact={key:binding[key] for key in ('document_id','job_id','response','input_revision','input_sha256')}
                metadata=deepcopy(run.get('draft',{}).get('test_metadata',{}))
                if kind=='numerical':
                    material=wb.document_read(check_id(material_document_id))
                    if material.get('kind')!='material':
                        raise ValueError('Choose an explicit Material model and protocol for identification')
                    draft=from_material_document(material)
                    response='stress_'+str(observation.get('component'))
                    if response not in {'stress_xx','stress_yy','stress_zz','stress_xy','stress_xz','stress_yz'}:
                        raise ValueError('This Material fit path needs a declared stress component; other channels remain independent Data')
                    draft['experiments']=[{'id': 'E'+canonical_hash(exact)[:16], 'role':'fit', 'source':exact,
                        'response':response,'settings':deepcopy(material['draft']['settings']),'weight':1.0,'scale':1.0}]
                    title='Identify from '+document['title']
                else:
                    draft=discussion_draft()
                    draft['topics'][0]['title']='Observed '+source['response']
                    draft['composer'].update(text='Explain the retained observation and identify the next distinguishing measurement.',
                        evidence=[{key:exact[key] for key in exact if key!='response'} | {'selection':[exact['response']]}])
                    draft['context']={'test_metadata':metadata,'data_comparisons':deepcopy(document.get('comparisons',[]))}
                    title='Discuss '+document['title']
                prepared={'request_hash':signature,'document_id':('N' if kind=='numerical' else 'X')+canonical_hash({'command_id':command_id,'signature':signature})[:32],
                    'draft':draft,'title':title[:160],'source':exact,'saved_source_revision':saved['saved_revision'],'state':'APPLYING'}
                save_json(path,prepared)
            owner=wb.numerical_documents if kind=='numerical' else wb.discussion_documents
            target=prepared['document_id']
            with owner._lock(target):
                if (owner._folder(target)/'working.json').exists() or owner._manifest(target):
                    result=owner.read(target)
                else:
                    result=owner.open(_new_id=target,title=prepared['title'],draft=prepared['draft'])
                save_json(path,{**prepared,'state':'SUCCEEDED'})
            return {'document':result,'source':prepared['source'],'command_id':command_id,
                    'status':'DRAFT_OPENED','executed':False}

    def result_followup(self, source_ref, kind='expert', *, session_id, command_id, request=None):
        from .research_operations import _resolve
        from .discussion_document import default_draft as discussion_draft
        from .numerical_document import request_draft
        wb=self.workbench
        if session_id!=wb.session_id or kind not in {'expert','numerical','study'}:
            raise ValueError('Follow-up requires the current service session and an explicit workspace')
        command_id=check_id(command_id)
        signature=canonical_hash(dict(source=source_ref,kind=kind,session_id=session_id,request=request))
        path=self.root/'result_followups'/(command_id+'.json')
        with self._lock:
            if path.exists():
                prepared=load_json(path)
                if prepared['request_hash']!=signature:
                    raise ValueError('Follow-up command conflicts with an earlier request')
            else:
                result=_resolve(source_ref,wb.document_read,wb.document_result)
                if kind=='expert':
                    draft=discussion_draft()
                    draft['composer'].update(text='Interpret this retained research result, its failed cases and the next distinguishing study.',
                        evidence=[{key:source_ref[key] for key in ('document_id','job_id','input_revision','input_sha256')} | {'selection':[]}])
                    from .research_operations import result_metadata
                    draft['context']={'selected_result_ids':[source_ref['job_id']], 'result_summary':result_metadata(result)}
                elif kind=='study':
                    from .study_document import default_draft as study_draft
                    draft=study_draft()
                    draft['question']='이 결과가 뒷받침하는 판단은 무엇이며, 다음 시험에서 무엇을 확인할까요?'
                    draft['evidence']=[{'id':'Eresult','label':'보존한 계산 결과','kind':'result',
                        'reference':{'kind':'result',**deepcopy(source_ref)},'note':'원 입력과 계산 결과를 보존했습니다. 공학적 승인을 뜻하지 않습니다.'}]
                else:
                    if not isinstance(request,dict):
                        raise ValueError('A Numerical follow-up needs an explicitly edited request; nothing is inferred or submitted')
                    wb._request_plan_arguments(request)
                    # Each result-consuming request owns its exact result_refs.
                    from .experiment_analysis_service import matches_followup_source
                    if (source_ref not in request.get('inputs',{}).get('result_refs',{}).values()
                            and not matches_followup_source(request, source_ref, workbench=wb)):
                        raise ValueError('The request must retain the selected result reference in an explicit input role')
                    draft=request_draft(request)
                prepared={'request_hash':signature,'document_id':{'expert':'X','numerical':'N','study':'S'}[kind]+signature[:32],
                          'draft':draft,'state':'APPLYING'}
                save_json(path,prepared)
            owner={'expert':wb.discussion_documents,'numerical':wb.numerical_documents,'study':wb.study_documents}[kind]
            target=prepared['document_id']
            with owner._lock(target):
                document=(owner.read(target) if (owner._folder(target)/'working.json').exists() or owner._manifest(target) else
                    owner.open(_new_id=target,title='계산 결과 검토' if kind=='study' else 'Follow-up — '+source_ref['job_id'],draft=prepared['draft']))
                save_json(path,{**prepared,'state':'SUCCEEDED'})
            return {'document':document,'source':deepcopy(source_ref),'command_id':command_id,'executed':False}

    def domain_plan(self, document_id, *, session_id, expected_generation, command_id):
        """Save one actual source and open its unexecuted numerical request."""
        from .evaluation_definition import document_reference
        from .numerical_document import request_draft
        wb = self.workbench
        document_id, command_id = map(check_id, (document_id, command_id))
        if session_id != wb.session_id or type(expected_generation) is not int or expected_generation < 0:
            raise ValueError('Select the current owner session and exact input generation')
        owner = wb._document_owner(document_id)
        if owner not in (wb.simulation_documents, wb.evaluation_documents, wb.material_documents):
            raise ValueError('This handoff requires a Material, Simulation or EvaluationDefinition document')
        signature = canonical_hash(dict(document_id=document_id,session_id=session_id,generation=expected_generation))
        path = self.root / 'domain_plans' / (command_id + '.json')
        with self._lock:
            if path.exists():
                prepared = load_json(path)
                if prepared['request_hash'] != signature:
                    raise ValueError('Plan command conflicts with another source')
            else:
                with owner._lock(document_id):
                    document = owner.read(document_id)
                    if document['generation'] != expected_generation or document['diagnostics']:
                        raise ValueError('Reread the exact valid domain input before creating its Plan')
                    if owner is wb.evaluation_documents:
                        errors = owner.inspect_definition(document_id)['diagnostics']
                        if errors: raise ValueError(errors[0]['message'])
                    saved = owner.command(document_id,'document.save',{},session_id=session_id,
                        expected_generation=expected_generation)['document']
                    reference = document_reference(saved)
                    inputs = ({'backend':'evaluation.definition','settings':{'definition_ref':reference}}
                              if owner is wb.evaluation_documents else deepcopy(saved['draft']))
                    prepared = {'request_hash':signature,'source':reference,
                        'request':{'purpose':saved['title'],'operation':'evaluate','inputs':inputs,'budget':{'evaluations':1}},
                        'document_id':'N'+canonical_hash({'command_id':command_id,'source':reference})[:32],'state':'APPLYING'}
                    save_json(path,prepared)
            target, owner = prepared['document_id'], wb.numerical_documents
            with owner._lock(target):
                document = (owner.read(target) if (owner._folder(target)/'working.json').exists() or owner._manifest(target)
                    else owner.open(_new_id=target,title=('Plan — '+prepared['request']['purpose'])[:160],
                                    draft=request_draft(prepared['request'],source=prepared['source'])))
                save_json(path,{**prepared,'state':'SUCCEEDED'})
            return {'document':document,'source':prepared['source'],'command_id':command_id,'executed':False}

    def study_followup(self, context, kind, *, session_id, command_id):
        """Open a discussion/Plan from the saved selected issue, without execution."""
        from .evaluation_definition import document_reference
        from .numerical_document import request_draft
        from .discussion_document import default_draft as discussion_draft
        wb = self.workbench
        command_id = check_id(command_id)
        if session_id != wb.session_id or kind not in {'expert','numerical'} or not isinstance(context,dict):
            raise ValueError('Choose an exact saved Study issue and target editor in this service')
        identifier = check_id(context.get('study_id'))
        saved = wb.study_documents._verify_revision(identifier,check_id(context.get('saved_revision')))
        if saved['input_revision'] != context.get('input_revision') or canonical_hash(saved['draft']) != context.get('input_sha256'):
            raise ValueError('Study source differs from the selected saved input')
        category, item_id = context.get('selected_kind'), context.get('selected_id')
        row = None
        if category is not None:
            if category not in ('hypotheses','evidence','decisions','next_observations'):
                raise ValueError('Select an existing Study issue')
            row = next((row for row in saved['draft'][category] if row['id']==item_id),None)
            if row is None: raise ValueError('Selected Study issue is absent from the saved revision')
        ids = ({row['id']} if row and category=='evidence' else
               set(row.get('supporting',[])+row.get('conflicting',[])+row.get('evidence_ids',[])) if row else
               set())
        if row and category == 'hypotheses':
            for decision in saved['draft']['decisions']:
                if row['id'] in decision['hypothesis_ids']:
                    ids.update(decision['supporting'] + decision['conflicting'])
        evidence = [deepcopy(item['reference']) for item in saved['draft']['evidence'] if item['id'] in ids]
        question = (row.get('question') or row.get('statement') or row.get('title')) if row else saved['draft']['question']
        question = question or saved['draft']['question']
        reference = {'document_id':identifier,'kind':'study','saved_revision':context['saved_revision'],
                     'input_revision':saved['input_revision'],'input_sha256':canonical_hash(saved['draft'])}
        exact_context = {'study':reference,'question':question,'selected_kind':category,'selected_id':item_id,
                         'evidence':evidence,'engineering_release':'NOT_RELEASED'}
        signature = canonical_hash({'context':exact_context,'kind':kind,'session':session_id})
        path = self.root / 'study_followups' / (command_id + '.json')
        with self._lock:
            if path.exists():
                prepared = load_json(path)
                if prepared['request_hash'] != signature: raise ValueError('Follow-up command conflicts with another Study selection')
            else:
                if kind=='expert':
                    draft=discussion_draft()
                    draft['composer'].update(text=question,evidence=[
                        {k:v for k,v in ref.items() if k!='kind'} | {'selection':[]} for ref in evidence if ref['kind']=='result'])
                    draft['context']=exact_context
                    prefix='X'
                else:
                    inputs={'backend':'','settings':{}}
                    model_refs=[ref for ref in evidence if ref['kind']=='document' and ref['document_kind'] in {'material','pde','simulation','evaluation'}]
                    if len(model_refs)==1:
                        actual=wb.research_reference(model_refs[0])['document']
                        if actual['kind']=='evaluation':
                            ref=model_refs[0]
                            inputs={'backend':'evaluation.definition','settings':{'definition_ref':{
                                'document_id':ref['document_id'],'kind':'evaluation','saved_revision':ref['saved_revision'],
                                'input_revision':ref['input_revision'],'input_sha256':ref['input_sha256']}}}
                        else: inputs=deepcopy(actual['draft'])
                    draft=request_draft({'purpose':question,'operation':'evaluate','inputs':inputs,'budget':{'evaluations':1}},source=reference)
                    prefix='N'
                prepared={'request_hash':signature,'document_id':prefix+signature[:32],'draft':draft,'state':'APPLYING'}
                save_json(path,prepared)
            target=prepared['document_id']
            owner=wb.discussion_documents if kind=='expert' else wb.numerical_documents
            with owner._lock(target):
                document=(owner.read(target) if (owner._folder(target)/'working.json').exists() or owner._manifest(target) else
                    owner.open(_new_id=target,title=('Study follow-up — '+saved['title'])[:160],draft=prepared['draft']))
                save_json(path,{**prepared,'state':'SUCCEEDED'})
            return {'document':document,'source':reference,'command_id':command_id,'executed':False}
