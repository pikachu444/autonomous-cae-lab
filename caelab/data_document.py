"""Data drafts reuse the shared document owner and the registered table reader."""
from copy import deepcopy
import math
from pathlib import Path
import shutil

from .adapters.file_table import preview_table, validate_row_selection
from .evaluation import file_hash, save_evaluation, read_result
from .material_document import MaterialDocuments
from .storage import canonical_hash, check_id, load_json, save_json


def default_draft():
    return {'data_id': '', 'mapping': {'delimiter': ',', 'skip_header': 0,
        'columns': {'response': {'column': 1, 'unit': '', 'component': '',
            'location': '', 'measure': '', 'frame': '',
            'axis': {'column': 0, 'name': '', 'unit': ''}}}}}


def diagnostics(draft):
    """Preserve invalid drafts; import requires explicit meaning for every channel."""
    try:
        if not isinstance(draft, dict) or not {'data_id', 'mapping'} <= set(draft) or set(draft) - {'data_id', 'mapping', 'test_metadata', 'acquisition', 'processing', 'sheet_group'}:
            raise ValueError('Data draft requires data_id and mapping; only explicit test_metadata may be added')
        check_id(draft['data_id'])
        if not draft['data_id'].startswith('D'):
            raise ValueError('Choose a registered data input')
        metadata = draft.get('test_metadata', {})
        if not isinstance(metadata, dict) or set(metadata) - {'test_id', 'specimen', 'protocol', 'temperature'} or any(not isinstance(value, str) for value in metadata.values()):
            raise ValueError('Test metadata uses explicitly supplied test_id, specimen, protocol and temperature text')
        mapping = draft['mapping']
        allowed = {'delimiter', 'skip_header', 'columns', 'candidate_id', 'case_id'}
        if not isinstance(mapping, dict) or set(mapping) - allowed or 'columns' not in mapping:
            raise ValueError('Mapping requires columns and only supported delimiter/header/provenance fields')
        delimiter = mapping.get('delimiter', ',')
        if not (delimiter is None or isinstance(delimiter, str) and len(delimiter) == 1
                or type(delimiter) is int and delimiter > 0
                or isinstance(delimiter, list) and delimiter and all(type(width) is int and width > 0 for width in delimiter)):
            raise ValueError('Delimiter must be one character, whitespace (null), or positive fixed widths')
        if type(mapping.get('skip_header', 0)) is not int or mapping.get('skip_header', 0) < 0:
            raise ValueError('Skipped header rows must be a nonnegative integer')
        columns = mapping['columns']
        if not isinstance(columns, dict) or not columns:
            raise ValueError('Declare at least one scalar channel and its explicit axis')
        for name, response in columns.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError('Every response needs a channel name')
            required = {'column', 'unit', 'component', 'location', 'measure', 'frame', 'axis'}
            optional = {'scale', 'offset', 'reduction', 'coordinate_system', 'row_selection', 'calibration'}
            if not isinstance(response, dict) or not required <= set(response) or set(response) - required - optional:
                raise ValueError(f'{name}: response requires column, unit, component, location, measure, frame and axis')
            axis = response['axis']
            if not isinstance(axis, dict) or not {'column', 'name', 'unit'} <= set(axis) or set(axis) - {'column', 'name', 'unit', 'scale', 'offset'}:
                raise ValueError(f'{name}: axis requires its source column, name and unit')
            for label, spec, labels in (('Response', response, ('unit', 'component', 'location', 'measure', 'frame')),
                                        ('Axis', axis, ('name', 'unit'))):
                for key in labels:
                    if not isinstance(spec[key], str) or not spec[key].strip():
                        raise ValueError(f'{name}: {label} {key} must be explicitly declared; labels do not convert units or frames')
                column = spec['column']
                if not (type(column) is int and column >= 0 or isinstance(column, str) and column.strip()):
                    raise ValueError(f'{name}: {label} column must be a zero-based index or an exact named column')
                for key in ('scale', 'offset'):
                    if key in spec and (type(spec[key]) not in (int, float) or not math.isfinite(spec[key])):
                        raise ValueError(f'{name}: {label} {key} must be a finite number')
            if isinstance(response['column'], str) != isinstance(axis['column'], str):
                raise ValueError(f'{name}: use either numeric indexes for both columns or named columns for both')
            if 'calibration' in response:
                from .experiment_calibration import validate_calibration
                validate_calibration(response['calibration'], response['unit'])
                if response.get('scale', 1) != 1 or response.get('offset', 0) != 0:
                    raise ValueError(name + ': 교정과 기존 배율/오프셋을 중복 적용할 수 없습니다.')
            validate_row_selection(response.get('row_selection', {}))
    except (ValueError, TypeError, KeyError) as error:
        return [{'severity': 'error', 'path': 'mapping', 'message': str(error), 'blocks_evaluation': True}]
    return []


class DataDocuments(MaterialDocuments):
    kind = 'data'
    prefix = 'T'
    update_operation = 'data.update'
    evaluate_operation = 'data.import'
    evaluation_operation = 'import_table'
    default_draft = staticmethod(default_draft)
    diagnostics = staticmethod(diagnostics)

    @property
    def operations(self):
        return super().operations | {'data.processing.apply'}

    def processing_preview(self, identifier):
        from .data_processing_document import preview
        return preview(self, identifier)

    def processing_result(self, identifier, revision, *, selection=None):
        from .data_processing_document import result
        return result(self, identifier, revision, selection=selection)

    def __init__(self, root, session_id, submit, manager, *, resolve_input):
        super().__init__(root, session_id, submit, manager)
        self.resolve_input = resolve_input

    @staticmethod
    def _fingerprint(document):
        content = {'input': MaterialDocuments._fingerprint(document),
                   'comparisons': document.get('comparisons', [])}
        if document.get('processing_revisions'):
            content['processing_revisions'] = document['processing_revisions']
        return canonical_hash(content)

    @staticmethod
    def job_arguments(draft):
        return {'data_id': draft['data_id'], 'mapping': deepcopy(draft['mapping']),
                'test_metadata': deepcopy(draft.get('test_metadata', {}))}

    def prepare_job_arguments(self, draft, document):
        """Freeze the exact registered or document-retained source before submit."""
        identifier = draft['data_id']
        retained = document.get('retained_inputs', {}).get(identifier)
        reference = {'kind': 'registered_input', 'document_id': document['id'], 'data_id': identifier}
        if retained is not None:
            revision = check_id(retained['revision'])
            manifest = self._folder(document['id']) / 'revisions' / revision / 'revision.json'
            reference.update(kind='retained_data_input', revision=revision,
                             revision_sha256=file_hash(manifest))
            source, receipt = self._retained_source(document, identifier)
            if file_hash(manifest) != reference['revision_sha256']:
                raise ValueError('Retained Data revision changed while preparing the import')
        else:
            source, receipt = self.resolve_input(identifier)
        source = Path(source)
        self._check_source(identifier, source, receipt)
        reference.update(sha256=receipt['sha256'], bytes=receipt['bytes'],
                         receipt_sha256=canonical_hash(receipt))
        certificates = []
        for spec in draft['mapping']['columns'].values():
            if 'calibration' not in spec:
                continue
            cert = spec['calibration']['source']
            # Reuse the same frozen source contract for certificates.
            prepared = self.prepare_job_arguments({'data_id': cert['data_id'],
                'mapping': {'columns': {}}}, document)['source_ref']
            if prepared['sha256'] != cert['sha256']:
                raise ValueError('교정 원본이 변경되었습니다. 새 버전을 명시적으로 선택하세요.')
            certificates.append(prepared)
        # The command receipt must freeze exactly the arguments that admission stores.
        certificates = self.calibration_sources(draft['mapping'], certificates)
        return {**self.job_arguments(draft), 'source_ref': reference,
                **({'calibration_sources': certificates} if certificates else {})}

    def calibration_sources(self, mapping, supplied=None, *, require_frozen=False):
        """Derive the entire certificate closure from the actual submitted mapping."""
        from .experiment_calibration import validate_calibration
        required = {}
        columns = mapping.get('columns', {}) if isinstance(mapping, dict) else {}
        for spec in (columns.values() if isinstance(columns, dict) else []):
            if not isinstance(spec, dict) or 'calibration' not in spec:
                continue
            recipe = spec['calibration']
            validate_calibration(recipe, spec.get('unit'))
            source = recipe['source']
            identifier = source['data_id']
            if identifier in required and required[identifier] != source['sha256']:
                raise ValueError('한 교정 원본에 서로 다른 버전이 지정되었습니다.')
            required[identifier] = source['sha256']
        if supplied is None:
            if required and require_frozen:
                raise ValueError('교정 원본의 제출 당시 기록이 없습니다.')
            supplied = []
            for identifier in sorted(required):
                path, receipt = self.resolve_input(identifier)
                self._check_source(identifier, Path(path), receipt)
                supplied.append({'kind': 'registered_calibration', 'data_id': identifier,
                    'sha256': receipt['sha256'], 'bytes': receipt['bytes'],
                    'receipt_sha256': canonical_hash(receipt)})
        if not isinstance(supplied, list):
            raise ValueError('교정 원본 목록이 잘못되었습니다.')
        verified = {}
        for reference in supplied:
            if not isinstance(reference, dict):
                raise ValueError('교정 원본 기록이 잘못되었습니다.')
            identifier = reference.get('data_id')
            if identifier not in required or reference.get('sha256') != required[identifier]:
                raise ValueError('교정식의 원본과 제출한 증빙이 다릅니다.')
            if identifier in verified and verified[identifier] != reference:
                raise ValueError('한 교정 원본에 서로 다른 보존 기록이 있습니다.')
            if reference.get('kind') == 'registered_calibration':
                if set(reference) != {'kind','data_id','sha256','bytes','receipt_sha256'}:
                    raise ValueError('등록 교정 원본의 필드가 잘못되었습니다.')
                path, receipt = self.resolve_input(identifier)
                self._check_source(identifier, Path(path), receipt)
                if (receipt['sha256'] != reference['sha256'] or receipt['bytes'] != reference['bytes']
                        or canonical_hash(receipt) != reference['receipt_sha256']):
                    raise ValueError('교정 원본 또는 등록 기록이 변경되었습니다.')
            else:
                self.resolve_job_source(identifier, reference)
            verified[identifier] = deepcopy(reference)
        if set(verified) != set(required):
            raise ValueError('교정식에 필요한 원본 증빙이 빠졌습니다.')
        return [verified[key] for key in sorted(verified)]

    def resolve_job_source(self, identifier, reference):
        """Resolve only a frozen service-owned reference, never a supplied file path."""
        required = {'kind', 'document_id', 'data_id', 'sha256', 'bytes', 'receipt_sha256'}
        if not isinstance(reference, dict):
            raise ValueError('Data import requires its frozen source reference')
        retained = reference.get('kind') == 'retained_data_input'
        if set(reference) != required | ({'revision', 'revision_sha256'} if retained else set()):
            raise ValueError('Unsupported Data source reference fields')
        if reference.get('kind') not in {'registered_input', 'retained_data_input'}:
            raise ValueError('Unsupported Data source reference kind')
        document_id = check_id(reference['document_id'])
        if not document_id.startswith(self.prefix) or reference['data_id'] != check_id(identifier):
            raise ValueError('Data source reference does not match the submitted owner/input')
        if retained:
            revision = check_id(reference['revision'])
            folder = self._folder(document_id) / 'revisions' / revision
            manifest = folder / 'revision.json'
            if file_hash(manifest) != reference['revision_sha256']:
                raise ValueError('Frozen Data revision manifest changed')
            document = load_json(folder / 'document.json')
            binding = document.get('retained_inputs', {}).get(identifier)
            if document.get('id') != document_id or not binding or binding.get('revision') != revision:
                raise ValueError('Saved Data document does not own this source revision')
            source, receipt = self._retained_source(document, identifier)
            if file_hash(manifest) != reference['revision_sha256']:
                raise ValueError('Frozen Data revision changed while resolving the import')
        else:
            source, receipt = self.resolve_input(identifier)
        source = Path(source)
        self._check_source(identifier, source, receipt)
        if (receipt['sha256'] != reference['sha256'] or receipt['bytes'] != reference['bytes']
                or canonical_hash(receipt) != reference['receipt_sha256']):
            raise ValueError('Frozen Data source bytes or registration receipt changed')
        return source, receipt

    def _retained_source(self, document, identifier):
        retained = document.get('retained_inputs', {}).get(identifier)
        if retained is None:
            return None
        self._verify_revision(document['id'], retained['revision'])
        folder = self._folder(document['id']) / 'revisions' / check_id(retained['revision'])
        source = (folder / retained['file']).resolve()
        metadata = (folder / retained['metadata']).resolve()
        if not source.is_relative_to(folder.resolve()) or not metadata.is_relative_to(folder.resolve()):
            raise ValueError('Retained Data input reference escapes its revision')
        receipt = load_json(metadata)
        self._check_source(identifier, source, receipt)
        if receipt['sha256'] != retained['sha256']:
            raise ValueError('Retained Data input identity changed')
        return source, receipt

    @staticmethod
    def _check_source(identifier, source, receipt):
        if (not isinstance(receipt, dict) or receipt.get('id') != identifier or not source.is_file()
                or source.stat().st_size != receipt.get('bytes') or file_hash(source) != receipt.get('sha256')):
            raise ValueError('Registered Data input bytes or metadata changed; previous revision is preserved')

    def _retain_inputs(self, saved, folder, *, recovery_inputs=None):
        from .portable_data_execution import retain
        retain(self, saved, folder)
        drafts = [saved['draft'], *saved.get('_undo', []), *saved.get('_redo', [])]
        drafts.extend(run.get('draft', {}) for run in saved['runs'])
        # Internal verified Q sources only; never a raw editor or input registry.
        identifiers = set(recovery_inputs or {})
        for draft in drafts:
            if not isinstance(draft, dict):
                continue
            mapping = draft.get('mapping')
            columns = mapping.get('columns', {}) if isinstance(mapping, dict) else {}
            specs = list(columns.values()) if isinstance(columns, dict) else []
            acquisition = draft.get('acquisition')
            if isinstance(acquisition, dict) and isinstance(acquisition.get('channels'), list):
                specs += acquisition['channels']
            for spec in specs:
                calibration = spec.get('calibration') if isinstance(spec, dict) else None
                source = calibration.get('source') if isinstance(calibration, dict) else None
                if isinstance(source, dict):
                    try:
                        identifier = check_id(source.get('data_id'))
                        if identifier.startswith('D'):
                            identifiers.add(identifier)
                    except ValueError:
                        pass
        for draft in drafts:
            identifier = draft.get('data_id') if isinstance(draft, dict) else None
            try:
                check_id(identifier)
            except ValueError:
                continue  # Raw invalid/empty identities remain saveable, with blocking diagnostics.
            if identifier.startswith('D'):
                identifiers.add(identifier)
        retained = {}
        unresolved = []
        used = {run.get('draft', {}).get('data_id') for run in saved['runs']}
        for run in saved['runs']:
            mapping = run.get('draft', {}).get('mapping')
            columns = mapping.get('columns', {}) if isinstance(mapping, dict) else {}
            for spec in (columns.values() if isinstance(columns, dict) else []):
                if isinstance(spec, dict) and isinstance(spec.get('calibration'), dict):
                    used.add((spec['calibration'].get('source') or {}).get('data_id'))
        for identifier in sorted(identifiers):
            original = self._retained_source(saved, identifier)
            try:
                source, receipt = original if original is not None else (
                    recovery_inputs[identifier][:2] if recovery_inputs and identifier in recovery_inputs
                    else self.resolve_input(identifier))
            except FileNotFoundError:
                if identifier in used:
                    raise  # A submitted import must not lose its declared raw source.
                unresolved.append(identifier)
                continue  # Preserve an unfinished source identity without inventing bytes.
            source, receipt = Path(source), deepcopy(receipt)
            self._check_source(identifier, source, receipt)
            destination = folder / 'sources' / identifier / ('source' + source.suffix)
            destination.parent.mkdir(parents=True)
            with source.open('rb') as incoming, destination.open('xb') as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            self._check_source(identifier, source, receipt)
            self._check_source(identifier, destination, receipt)
            metadata = destination.parent / 'input.json'
            original_metadata = None
            if recovery_inputs and identifier in recovery_inputs:
                original_metadata = recovery_inputs[identifier][2]
            elif original is not None:
                binding = saved['retained_inputs'][identifier]
                original_metadata = self._folder(saved['id']) / 'revisions' / check_id(binding['revision']) / binding['metadata']
            if original_metadata is not None:
                digest = file_hash(original_metadata)
                if load_json(original_metadata) != receipt:
                    raise ValueError('Retained input.json differs from the verified original receipt')
                shutil.copyfile(original_metadata, metadata)
                if file_hash(original_metadata) != digest or file_hash(metadata) != digest:
                    raise ValueError('Retained input.json changed during retention')
            else:
                save_json(metadata, receipt)
            retained[identifier] = {'revision': folder.name, 'file': destination.relative_to(folder).as_posix(),
                'metadata': metadata.relative_to(folder).as_posix(), 'sha256': receipt['sha256'], 'bytes': receipt['bytes']}
        saved['retained_inputs'] = retained
        saved['unresolved_inputs'] = unresolved
        self._retain_comparisons(saved, folder)
        from .data_processing_document import retain
        retain(self, saved, folder)

    def source_preview(self, identifier):
        """Read bounded original bytes, including after the registration is unavailable."""
        with self._lock(identifier):
            document = self.read(identifier)
            data_id = document['draft'].get('data_id')
            check_id(data_id)
            retained = self._retained_source(document, data_id)
            source, receipt = retained if retained is not None else self.resolve_input(data_id)
            source = Path(source)
            self._check_source(data_id, source, receipt)
            result = {'id': data_id, 'name': receipt['name'], 'sha256': receipt['sha256'],
                      'retained': retained is not None}
            if source.suffix.lower() == '.npz':
                return {**result, 'preview': 'Numeric archive; enter exact array keys for axis and response.'}
            with source.open(encoding='utf-8-sig') as stream:
                sample = stream.read(16385)
            self._check_source(data_id, source, receipt)
            result.update(text=sample[:16384], truncated=len(sample) > 16384)
            table = preview_table(result['text'], truncated=result['truncated'])
            if table is not None:
                result['table_preview'] = table
            return result
