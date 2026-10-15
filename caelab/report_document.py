"""Nonexecuting report sections on the existing revision/Undo owner.

Large frozen payloads are immutable report assets, not an inline draft or another
result store. Sources are verified on capture; later availability is separate.
"""
from copy import deepcopy
import json
import shutil

from .material_document import MaterialDocuments
from .storage import canonical_hash, check_id, load_json, save_json
from .evaluation import file_hash
from .study_document import reference_error as study_reference_error
from . import report_image


def reference_error(reference):
    if isinstance(reference, dict) and reference.get('kind') == 'post_image':
        return report_image.reference_error(reference)
    return study_reference_error(reference)


def default_draft():
    return {'title': '연구 보고서', 'sections': [], 'engineering_release': 'NOT_RELEASED'}


def diagnostics(draft):
    errors = []
    def error(path, message):
        errors.append({'severity': 'error', 'path': path, 'message': message, 'blocks_export': True})
    if not isinstance(draft, dict) or set(draft) != set(default_draft()):
        error('draft', '제목과 섹션을 확인하세요.')
        return errors
    if not isinstance(draft['title'], str) or not draft['title'].strip():
        error('title', '보고서 제목을 입력하세요.')
    if draft['engineering_release'] != 'NOT_RELEASED':
        error('engineering_release', '보고서 작성은 공학적 승인을 변경하지 않습니다.')
    if not isinstance(draft['sections'], list) or len(draft['sections']) > 100:
        error('sections', '섹션은 100개 이하로 구성하세요.')
        return errors
    seen = set()
    for i, row in enumerate(draft['sections']):
        path = 'sections/' + str(i)
        if (not isinstance(row, dict) or set(row) - {'image'} !=
                {'id', 'title', 'text', 'include', 'table', 'curve', 'asset'}):
            error(path, '섹션 제목, 설명, 표와 곡선 선택을 확인하세요.')
            continue
        try:
            check_id(row['id'])
            if row['id'] in seen:
                raise ValueError('중복 섹션')
            seen.add(row['id'])
        except ValueError:
            error(path, '섹션의 저장 식별자가 잘못되었습니다.')
        if not all(isinstance(row[k], str) for k in ('title', 'text')):
            error(path, '제목과 설명은 텍스트여야 합니다.')
        if not all(type(row[k]) is bool for k in ('include', 'table', 'curve')):
            error(path, '섹션 포함과 표시 선택을 확인하세요.')
        if 'image' in row:
            try:
                report_image.image_options(row)
            except ValueError as exc:
                error(path + '/image', str(exc))
        asset = row['asset']
        if asset is not None:
            if not isinstance(asset, dict) or set(asset) != {'id', 'sha256', 'reference'}:
                error(path, '원자료를 다시 선택하세요.')
            else:
                issue = reference_error(asset['reference'])
                if issue:
                    error(path, issue)
    return errors


def snapshot_value(value):
    """JSON-safe exact real values; match file_table's retained nonfinite tokens."""
    import math
    import numpy as np
    if isinstance(value, np.ndarray):
        return snapshot_value(value.tolist())
    if isinstance(value, np.generic):
        return snapshot_value(value.item())
    if isinstance(value, dict):
        return {key: snapshot_value(item) for key,item in value.items()}
    if isinstance(value, (list,tuple)):
        return [snapshot_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)  # nan/inf/-inf stay distinct, never 0 or null.
    return value


def effective_selection(reference):
    selection = reference.get('selection')
    if selection is None:
        return {'responses': [reference['response']]} if reference.get('response') else {'metadata_only': True}
    return {'responses': selection} if isinstance(selection, list) else selection


def compact_payload(payload):
    """Keep verified selected numeric/text content, never paths to mutable views."""
    result = {'kind': payload['kind']}
    if payload['kind'] == 'numerical_candidate_evidence':
        result['candidate_evidence'] = deepcopy(payload['candidate_evidence'])
        result['report_intent'] = payload['report_intent']
    elif payload['kind'] == 'comparison':
        result['comparison'] = deepcopy(payload['comparison'])
    elif payload['kind'] == 'result':
        source = payload['result']
        result['result'] = {k: deepcopy(source[k]) for k in
            ('kind', 'execution_status', 'responses', 'checks', 'identification', 'parameters',
             'parameter_units', 'experiment_analysis', 'curves', 'converged', 'termination_reason', 'failure_reason') if k in source}
        result['result']['qualification'] = deepcopy(source.get('diagnostics', {}).get('qualification', 'UNKNOWN'))
        result['result'].pop('curves', None)  # Curves are read through selected response views.
        metadata_only = effective_selection(payload.get('reference', {})).get('metadata_only', False)
        if metadata_only:
            result['result'].pop('responses', None)
            if source.get('kind') == 'fit':
                result['report_intent'] = 'METADATA_ONLY_NOT_A_SUCCESS_JUDGMENT'
                result['success_judgment_permitted'] = False
        for key in ('candidates', 'predictions'):
            if isinstance(source.get(key), list):
                result['result'][key] = [{k: deepcopy(v) for k, v in row.items()
                    if k in {'candidate_id','values','execution_status','prediction_status','responses',
                        'checks','failure_reason','error','feasible','objective','objectives','penalty','constraints',
                        'constraint_residuals','response_reductions','selected_reduction_index','converged','termination_reason'}
                    and (k != 'responses' or not metadata_only)} for row in source[key]]
    elif payload['kind'] == 'document':
        result['document'] = deepcopy(payload['document'])
    elif payload['kind'] == 'knowledge':
        result['source'] = deepcopy(payload['source'])
    else:
        result['turn'] = deepcopy(payload['turn'])
    return snapshot_value(result)


def check_selection(reference, payload):
    if reference['kind'] == 'numerical_candidate_evidence':
        from .numerical_candidate_evidence import SUCCESS, FAILURE, validate_evidence_reference
        validate_evidence_reference(reference)
        evidence = payload.get('candidate_evidence', {})
        readiness = evidence.get('readiness', {})
        if (evidence.get('reference') != reference or
                readiness.get('preservation') != 'IMMUTABLE_REVISION_VERIFIED' or
                reference['purpose'] == SUCCESS and not readiness.get('success_judgment_permitted') or
                reference['purpose'] == FAILURE and not readiness.get('failure_diagnostic_permitted')):
            raise ValueError('보고서의 정확한 후보/선택 상세 근거가 보존·검증되지 않았습니다.')
        return
    if reference['kind'] != 'result':
        return
    selection = effective_selection(reference)
    if not isinstance(selection, dict) or set(selection) - {'responses', 'rows', 'time_range', 'component', 'location', 'metadata_only', 'source_rows', 'candidate_ids', 'reduction_index'}:
        raise ValueError('보고서에 고정할 응답과 행/시각을 명시하세요.')
    source = snapshot_value(payload.get('result', {}))
    nested = source.get('candidates', source.get('predictions'))
    sources = nested if isinstance(nested, list) else [source]
    if selection.get('candidate_ids') is not None:
        if not isinstance(nested, list) or {r.get('candidate_id') for r in nested} != set(selection['candidate_ids']):
            raise ValueError('선택한 후보와 읽은 결과가 다릅니다.')
    if selection.get('metadata_only'):
        return
    if source.get('kind') == 'fit' and isinstance(nested, list):
        raise ValueError('Fit 성공/실패 판단 보고는 선택 후보의 numerical_candidate_evidence 참조를 보존하세요. 요약 읽기는 허용됩니다.')
    if 'reduction_index' in selection:
        if (not isinstance(nested,list) or len(nested)!=1 or
                nested[0].get('selected_reduction_index')!=selection['reduction_index'] or
                len(nested[0].get('response_reductions',[]))!=1 or
                [nested[0]['response_reductions'][0]['response']]!=selection.get('responses')):
            raise ValueError('선택한 후보의 정확한 축약값이 없습니다.')
        return
    names = selection.get('responses')
    if not isinstance(names, list) or not names or not sources:
        raise ValueError('보고서에 포함할 실제 응답을 선택하세요.')
    for source in sources:
        responses = source.get('responses', {})
        for name in names:
            response = responses.get(name)
            if not isinstance(response, dict):
                raise ValueError('요청한 응답/위치를 찾지 못했습니다: ' + name)
            if response.get('kind') == 'series' and not len(response.get('value', [])) and not (response.get('raw_samples') or {}).get('source_rows'):
                raise ValueError('선택한 시각/행에 원값이 없습니다. 인접 시각으로 대체하지 않습니다.')
            if 'time_range' in selection and selection['time_range'][0] == selection['time_range'][1]:
                axis = next((a for a in response.get('axes', []) if a.get('name') == 'time'), None)
                if not axis or not axis.get('values') or any(t != selection['time_range'][0] for t in axis['values']):
                    raise ValueError('선택한 정확한 시각이 없습니다.')


class ReportDocuments(MaterialDocuments):
    kind, prefix = 'report', 'B'
    update_operation, evaluate_operation = 'report.update', None
    default_draft = staticmethod(default_draft)
    diagnostics = staticmethod(diagnostics)

    @property
    def operations(self):
        return {self.update_operation, 'document.undo', 'document.redo', 'document.save'}

    def __init__(self, *args, resolve_reference, **kwargs):
        super().__init__(*args, **kwargs)
        self.resolve_reference = resolve_reference

    @staticmethod
    def _changed(document):
        MaterialDocuments._changed(document)
        title = document.get('draft', {}).get('title')
        if isinstance(title, str) and title.strip():
            document['title'] = title[:160]

    def _recover_evaluations(self, document):
        return None

    def _verify_revision(self, identifier, revision):
        try:
            result = super()._verify_revision(identifier, revision)
            getattr(self, '_image_revision_issues', {}).pop(identifier, None)
            return result
        except (ValueError, OSError):
            folder = self._folder(identifier) / 'revisions' / check_id(revision)
            document, issues = report_image.read_degraded_revision(
                folder, self._manifest(identifier), identifier, revision)
            if not hasattr(self, '_image_revision_issues'):
                self._image_revision_issues = {}
            self._image_revision_issues[identifier] = issues
            return document

    def capture(self, identifier, reference):
        with self._lock(identifier):
            self.read(identifier)
            reference = deepcopy(reference)
            payload = self.resolve_reference(reference)
            check_selection(reference, payload)
            frozen = {'reference': reference, 'content': compact_payload(payload)}
            return self._retain_asset(identifier, frozen)

    def capture_image(self, identifier, command):
        """command must come from the stored native broker, never client JSON."""
        with self._lock(identifier):
            self.read(identifier)
            reference, content = report_image.completed_content(command)
            return self._retain_asset(identifier, {'reference': reference, 'content': content})

    def _retain_asset(self, identifier, frozen):
        # Caller holds the report owner lock; keep the one existing asset store.
        reference = frozen['reference']
        encoded = json.dumps(frozen, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(encoded) > 8 * 1024 * 1024:
            raise ValueError('자료가 큽니다. 필요한 응답과 원행 구간을 선택하세요.')
        digest = canonical_hash(frozen)
        asset_id = 'A' + digest
        path = self._folder(identifier) / 'assets' / (asset_id + '.json')
        if not path.exists():
            save_json(path, frozen)
        elif canonical_hash(load_json(path)) != digest:
            raise ValueError('보존된 보고서 자료가 변경되었습니다.')
        return {'id': asset_id, 'sha256': digest, 'reference': reference}

    def asset(self, identifier, binding):
        asset_id = check_id(binding['id'])
        if not asset_id.startswith('A') or asset_id[1:] != binding['sha256']:
            raise ValueError('잘못된 보고서 자료 식별자')
        document = self.read(identifier)
        path = self._folder(identifier) / 'assets' / (asset_id + '.json')
        if not path.exists() and document.get('saved_revision'):
            path = self._folder(identifier) / 'revisions' / check_id(document['saved_revision']) / 'assets' / (asset_id + '.json')
        frozen = load_json(path)
        if canonical_hash(frozen) != binding['sha256'] or frozen['reference'] != binding['reference']:
            raise ValueError('보고서 자료의 원값 또는 참조가 변경되었습니다.')
        if frozen['content'].get('kind') == 'post_image':
            report_image.validate_content(frozen['content'], binding['reference'])
        return frozen

    def content(self, identifier, bindings):
        if not isinstance(bindings, list) or len(bindings) > 100:
            raise ValueError('보고서의 섹션 자료를 선택하세요.')
        rows = []
        for binding in bindings:
            try:
                frozen = self.asset(identifier, binding)
                try:
                    if frozen['content'].get('kind') == 'post_image':
                        report_image.verify_origin(frozen['content']['snapshot']['origin'])
                    else:
                        current = self.resolve_reference(binding['reference'])
                        check_selection(binding['reference'], current)
                        # The report always reads its snapshot; availability cannot replace it.
                        if canonical_hash(compact_payload(current)) != canonical_hash(frozen['content']):
                            raise ValueError('원자료 내용이 고정한 자료와 다릅니다.')
                    state, message = 'AVAILABLE', ''
                except Exception as error:
                    state, message = 'UNAVAILABLE', str(error)
                issues = [row for row in getattr(self, '_image_revision_issues', {}).get(identifier, [])
                          if row['asset_id'] == binding['id']]
                if issues:
                    state, message = 'UNAVAILABLE', issues[0]['message'] + ' 확인된 작업 사본은 유지합니다.'
                rows.append({'id': binding['id'], **frozen, 'source_status': state, 'message': message})
            except Exception as error:
                rows.append({'id': binding.get('id'), 'source_status': 'SNAPSHOT_UNAVAILABLE', 'message': str(error)})
        return {'document_id': identifier, 'assets': rows}

    def _retain_inputs(self, saved, folder):
        bindings = {}
        for draft in [saved['draft'], *saved.get('_undo', []), *saved.get('_redo', [])]:
            if not isinstance(draft, dict):
                continue
            for row in draft.get('sections', []) if isinstance(draft.get('sections'), list) else []:
                binding = row.get('asset') if isinstance(row, dict) else None
                if isinstance(binding, dict) and {'id', 'sha256', 'reference'} <= binding.keys():
                    bindings[binding['id']] = binding
        for binding in bindings.values():
            frozen = self.asset(saved['id'], binding)
            save_json(folder / 'assets' / (check_id(binding['id']) + '.json'), frozen)
        self._retain_comparisons(saved, folder)
