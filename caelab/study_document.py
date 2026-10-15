"""Independent research questions and explicit judgments, never a solver plan.

The legacy Lab study registry remains separate. This document uses the existing
MaterialDocuments revision/Undo owner; editing and reading cannot execute work.
"""
from copy import deepcopy
import re

from .material_document import MaterialDocuments
from .storage import check_id


HYPOTHESIS_STATUSES = ('UNKNOWN', 'SUPPORTED', 'CONFLICTED', 'REFUTED')
DECISION_STATUSES = ('UNKNOWN', 'PROVISIONAL', 'SUPPORTED', 'CONFLICTED', 'REJECTED', 'NOT_RELEASED')
OBSERVATION_STATUSES = ('UNKNOWN', 'PLANNED', 'OBSERVED')
COLLECTIONS = ('hypotheses', 'evidence', 'decisions', 'next_observations')


def default_draft():
    return {'question': '', 'hypotheses': [], 'evidence': [], 'decisions': [],
            'next_observations': [], 'engineering_release': 'NOT_RELEASED'}


def reference_error(reference):
    """Check explicit immutable identity, without resolving or inferring an owner."""
    try:
        if not isinstance(reference, dict):
            raise ValueError('Choose an exact saved source reference')
        kind = reference.get('kind')
        if kind == 'numerical_candidate_evidence':
            from .numerical_candidate_evidence import validate_evidence_reference
            validate_evidence_reference(reference)
            return None
        if kind == 'comparison':
            required={'kind','document_id','document_kind','saved_revision','comparison_id','result_sha256','start','count'}
            if set(reference)!=required or reference['document_kind'] not in {'data','material','pde','simulation'}:
                raise ValueError('저장된 곡선 비교와 원 문서를 선택하세요.')
            for key in ('document_id','saved_revision','comparison_id'):check_id(reference[key])
            if (not re.fullmatch('[0-9a-f]{64}',str(reference['result_sha256']))
                    or type(reference['start']) is not int or reference['start']<0
                    or type(reference['count']) is not int or not 1<=reference['count']<=4096):
                raise ValueError('정확한 비교와 4096개 이하 표본 구간을 선택하세요.')
            return None
        if kind == 'knowledge':
            required = {'kind', 'document_id', 'revision', 'locator', 'source_sha256', 'content_sha256'}
            if set(reference) != required or type(reference['revision']) is not int or reference['revision'] < 1:
                raise ValueError('문헌의 정확한 저장 개정과 원문 구간을 선택하세요.')
            if not isinstance(reference['document_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', reference['document_id']):
                raise ValueError('문헌 저장소의 정확한 자료 식별자가 필요합니다.')
            if not isinstance(reference['locator'], dict):
                raise ValueError('원문 위치를 명시하세요.')
            for key in ('source_sha256', 'content_sha256'):
                if not re.fullmatch('[0-9a-f]{64}', str(reference[key])):
                    raise ValueError('문헌 원본과 선택 원문의 식별값이 필요합니다.')
            return None
        if kind == 'document':
            required = {'kind', 'document_kind', 'document_id', 'saved_revision', 'input_revision', 'input_sha256'}
            optional = set()
            if not isinstance(reference.get('document_kind'), str) or not reference['document_kind']:
                raise ValueError('Declare the original document kind')
        elif kind == 'result':
            required = {'kind', 'document_id', 'job_id', 'input_revision', 'input_sha256', 'result_sha256'}
            optional = {'response', 'selection'}
            if 'response' in reference and (not isinstance(reference['response'], str) or not reference['response']):
                raise ValueError('Response selection must be an exact nonempty name')
            if 'selection' in reference and not isinstance(reference['selection'], (dict, list)):
                raise ValueError('Result selection must retain its explicit object/list')
        elif kind == 'expert_turn':
            required = {'kind', 'discussion_id', 'saved_revision', 'turn_id', 'turn_sha256'}
            optional = set()
        else:
            raise ValueError('Evidence must reference a saved document, retained result or saved Expert turn')
        if not required <= reference.keys() or reference.keys() - required - optional:
            raise ValueError('Exact ' + kind + ' reference fields are missing or unsupported')
        for key in required - {'kind', 'document_kind', 'input_sha256', 'result_sha256', 'turn_sha256'}:
            check_id(reference[key])
        for key in required & {'input_sha256', 'result_sha256', 'turn_sha256'}:
            if not isinstance(reference[key], str) or not re.fullmatch('[0-9a-f]{64}', reference[key]):
                raise ValueError(key + ' must identify the exact retained content')
    except (ValueError, TypeError, KeyError) as error:
        return str(error)
    return None


def diagnostics(draft):
    """Structural issues remain editable/saveable; no engineering release exists."""
    errors = []
    def error(path, message):
        errors.append({'severity': 'error', 'path': path, 'message': message, 'blocks_decision': True})
    if not isinstance(draft, dict) or set(draft) != set(default_draft()):
        error('draft', 'Study requires question, hypotheses, evidence, decisions, next_observations and engineering_release')
        return errors
    if not isinstance(draft['question'], str):
        error('question', 'Research question must be text')
    if draft['engineering_release'] != 'NOT_RELEASED':
        error('engineering_release', 'Study judgments cannot change engineering release; preserve NOT_RELEASED')
    definitions = {
        'hypotheses': ({'id', 'title', 'statement', 'status'}, HYPOTHESIS_STATUSES),
        'evidence': ({'id', 'label', 'kind', 'reference', 'note'}, None),
        'decisions': ({'id', 'title', 'statement', 'hypothesis_ids', 'supporting', 'conflicting', 'status'}, DECISION_STATUSES),
        'next_observations': ({'id', 'question', 'hypothesis_ids', 'evidence_ids', 'status', 'note'}, OBSERVATION_STATUSES)}
    ids = {}
    for name, (keys, statuses) in definitions.items():
        rows = draft[name]
        ids[name] = set()
        if not isinstance(rows, list):
            error(name, 'Research entries must remain a list')
            continue
        for index, row in enumerate(rows):
            path = name + '/' + str(index)
            if not isinstance(row, dict) or set(row) != keys:
                error(path, 'Unsupported ' + name + ' entry fields; original content is retained')
                continue
            try:
                identifier = check_id(row['id'])
                if identifier in ids[name]:
                    raise ValueError('Research entry IDs must be distinct')
                ids[name].add(identifier)
            except (ValueError, TypeError) as failure:
                error(path + '/id', str(failure))
            for key in keys & {'title', 'statement', 'question', 'label', 'note'}:
                if not isinstance(row[key], str):
                    error(path + '/' + key, 'Research text must remain text')
            if statuses is not None and row['status'] not in statuses:
                error(path + '/status', 'Choose an explicit research status; unknown remains UNKNOWN')
            if name == 'evidence':
                issue = reference_error(row['reference'])
                if issue:
                    error(path + '/reference', issue)
                if row['kind'] != (row['reference'].get('kind') if isinstance(row['reference'], dict) else None):
                    error(path + '/kind', 'Evidence kind differs from its exact source reference')
    for name in ('decisions', 'next_observations'):
        for index, row in enumerate(draft[name] if isinstance(draft[name], list) else []):
            if not isinstance(row, dict):
                continue
            for key, target in (('hypothesis_ids', 'hypotheses'), ('supporting', 'evidence'),
                                ('conflicting', 'evidence'), ('evidence_ids', 'evidence')):
                if key not in row:
                    continue
                values = row[key]
                path = name + '/' + str(index) + '/' + key
                if (not isinstance(values, list) or any(not isinstance(value, str) for value in values)
                        or len(values) != len(set(values))):
                    error(path, 'Linked IDs must be a distinct list of original research entry IDs')
                elif set(values) - ids[target]:
                    error(path, 'Linked ' + target + ' IDs are absent: ' + ', '.join(sorted(set(values) - ids[target])))
            if name == 'decisions' and row.get('status') == 'SUPPORTED' and not row.get('supporting'):
                error(name + '/' + str(index), 'A supported decision requires explicitly selected supporting evidence')
    return errors


class StudyDocuments(MaterialDocuments):
    kind = 'study'
    prefix = 'S'
    update_operation = 'study.update'
    evaluate_operation = None
    default_draft = staticmethod(default_draft)
    diagnostics = staticmethod(diagnostics)

    @property
    def operations(self):
        return {self.update_operation, 'document.undo', 'document.redo', 'document.save'}

    def __init__(self, root, session_id, submit, manager, *, resolve_reference=None):
        super().__init__(root, session_id, submit, manager)
        self.resolve_reference = resolve_reference

    def _retain_inputs(self, saved, folder):
        super()._retain_inputs(saved, folder)
        from .portable_research_owner import retain
        retain(self, saved, folder)

    def _recover_evaluations(self, document):
        # Studies have no calculation/inference operation or execution history.
        return None

    def validate_references(self, draft):
        rows = draft.get('evidence', []) if isinstance(draft, dict) else []
        result = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            reference = row.get('reference')
            issue = reference_error(reference)
            check = {'evidence_id': row.get('id'), 'status': 'UNKNOWN', 'message': 'Exact source has not been resolved'}
            if issue:
                check.update(status='INVALID', message=issue)
            elif self.resolve_reference is not None:
                try:
                    metadata = self.resolve_reference(deepcopy(reference))
                    if not isinstance(metadata, dict):
                        raise ValueError('Reference resolver must return descriptive validation metadata')
                    check.update(deepcopy(metadata))
                    if metadata.get('status') == 'AVAILABLE':
                        check['message'] = metadata.get('message') or 'Exact saved source is available'
                    check['evidence_id'] = row.get('id')
                except (Exception) as failure:
                    check.update(status='UNAVAILABLE', message=str(failure))
            result.append(check)
        return result

    def resolve_references(self, identifier):
        return {'document_id': identifier, 'references': self.validate_references(self.read(identifier)['draft'])}
