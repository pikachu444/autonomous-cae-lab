"""Explicit typed-reference paths shared by connection reading and copy mapping.

Never search arbitrary text, JSON keys, tool IDs or strings for document IDs.
Unknown fields survive untouched. Adding another domain requires an explicit
path adapter here and tests, not an ID-finding heuristic.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class TypedReference:
    path: tuple[str | int, ...]
    role: str
    form: str
    value: dict[str, Any]

    @property
    def document_id(self) -> str | None:
        key = ('discussion_id' if self.value.get('kind') == 'expert_turn' else
               {'proposal': 'discussion_id', 'adoption': 'plan_id', 'pde': 'pde_document_id'}.get(self.form, 'document_id'))
        return self.value.get(key)


def _object(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _rows(value: Any) -> list:
    return value if isinstance(value, list) else []


def draft_references(kind: str, draft: dict) -> Iterator[TypedReference]:
    def ref(path, role, value, form='exact'):
        if isinstance(value, dict):
            return TypedReference(tuple(path), role, form, deepcopy(value))
        return None
    found: list[TypedReference | None] = []
    if kind == 'data':
        found.append(ref(('processing','source'),'처리 원자료',_object(draft.get('processing')).get('source'),'result'))
    elif kind == 'numerical':
        if draft.get('mode') != 'request':
            found.append(ref(('material',), '재료 입력', draft.get('material'), 'material_input'))
            for i, row in enumerate(_rows(draft.get('experiments'))):
                found.append(ref(('experiments', i, 'source'), '시험 관측', _object(row).get('source'), 'observation'))
        else:
            source = draft.get('source')
            form = ('proposal' if 'discussion_id' in _object(source) else
                    'pde' if 'pde_document_id' in _object(source) else 'exact')
            found.append(ref(('source',), '계획의 원본', source, form))
            found.append(ref(('model_source',), '계산 모델', draft.get('model_source')))
            for method, source in _object(draft.get('method_model_sources')).items():
                found.append(ref(('method_model_sources', method), '보존한 방법의 모델', source))
            inputs = _object(_object(draft.get('request')).get('inputs'))
            for role, source in _object(inputs.get('result_refs')).items():
                found.append(ref(('request', 'inputs', 'result_refs', role), '계산 입력 ' + role, source, 'result'))
            for i, experiment in enumerate(_rows(inputs.get('experiments'))):
                source_key='current_data_source' if 'current_data_source' in _object(_object(experiment).get('observation_source')) else 'data_source'
                original_data = _object(_object(experiment).get('observation_source')).get(source_key)
                found.append(ref(('request', 'inputs', 'experiments', i, 'observation_source', source_key),
                                 '보존한 시험 원자료', original_data, 'observation'))
                value = _object(_object(experiment).get('observation_ref')).get('result')
                found.append(ref(('request', 'inputs', 'experiments', i, 'observation_ref', 'result'),
                                 '피팅 관측 결과', value, 'result'))
            for method, inputs in _object(draft.get('method_inputs')).items():
                for i, experiment in enumerate(_rows(_object(inputs).get('experiments'))):
                    source_key='current_data_source' if 'current_data_source' in _object(_object(experiment).get('observation_source')) else 'data_source'
                    original_data = _object(_object(experiment).get('observation_source')).get(source_key)
                    found.append(ref(('method_inputs', method, 'experiments', i, 'observation_source', source_key),
                                     '보존한 방법의 시험 원자료', original_data, 'observation'))
                    value = _object(_object(experiment).get('observation_ref')).get('result')
                    found.append(ref(('method_inputs', method, 'experiments', i, 'observation_ref', 'result'),
                                     '보존한 피팅 관측 결과', value, 'result'))
                for role, source in _object(_object(inputs).get('result_refs')).items():
                    found.append(ref(('method_inputs', method, 'result_refs', role), '보존한 방법 ' + method, source, 'result'))
    elif kind == 'study':
        for i, row in enumerate(_rows(draft.get('evidence'))):
            found.append(ref(('evidence', i, 'reference'), '연구 근거', _object(row).get('reference')))
    elif kind == 'report':
        for i, row in enumerate(_rows(draft.get('sections'))):
            found.append(ref(('sections', i, 'asset', 'reference'), '보고서 근거', _object(_object(row).get('asset')).get('reference')))
    elif kind == 'evaluation':
        for i, row in enumerate(_rows(draft.get('stages'))):
            found.append(ref(('stages', i, 'source'), '단계 모델', _object(row).get('source')))
        found.append(ref(('reuse', 'source'), '재사용 결과', _object(draft.get('reuse')).get('source'), 'result'))
    # Expert composer evidence is an explicit reference-object list. Context is
    # intentionally not crawled: it also holds arbitrary authored notes/tools.
    elif kind == 'expert':
        for i, source in enumerate(_rows(_object(draft.get('composer')).get('evidence'))):
            form='result' if expert_result_reference(source) else 'exact'
            found.append(ref(('composer', 'evidence', i), '질문의 근거', source, form))
        team = _object(_object(draft.get('context')).get('research_team'))
        if team.get('version') == 2:
            for i, assignment in enumerate(_rows(team.get('assignments'))):
                for j, selection in enumerate(_rows(_object(assignment).get('result_refs'))):
                    found.append(ref(('context', 'research_team', 'assignments', i, 'result_refs', j, 'reference'),
                        '담당자가 검토할 계산 결과', _object(selection).get('reference'), 'result'))
    yield from (row for row in found if row is not None)


def expert_result_reference(value):
    """The established untagged result syntax at an explicit Expert evidence path."""
    return (isinstance(value,dict) and value.get('kind') in (None,'result')
            and all(key in value for key in ('document_id','job_id','input_revision','input_sha256','result_sha256')))


def document_references(document: dict, *, include_history: bool = False) -> Iterator[TypedReference]:
    kind = document.get('kind')
    for row in draft_references(kind, _object(document.get('draft'))):
        yield TypedReference(('draft', *row.path), row.role, row.form, row.value)
    for i, adoption in enumerate(_rows(document.get('adoptions'))):
        if isinstance(adoption, dict) and 'plan_id' in adoption:
            yield TypedReference(('adoptions', i), '채택한 후보의 계획', 'adoption', deepcopy(adoption))
            evidence = adoption.get('candidate_evidence')
            if isinstance(evidence, dict):
                yield TypedReference(('adoptions', i, 'candidate_evidence'), '채택한 후보의 보존 증거', 'exact', deepcopy(evidence))
    if include_history:
        for i, run in enumerate(_rows(document.get('runs'))):
            for row in draft_references(kind, _object(_object(run).get('draft'))):
                yield TypedReference(('runs', i, 'draft', *row.path), '원입력: ' + row.role, row.form, row.value)
        for stack in ('_undo', '_redo'):
            for i, draft in enumerate(_rows(document.get(stack))):
                for row in draft_references(kind, _object(draft)):
                    yield TypedReference((stack, i, *row.path), '편집 이력: ' + row.role, row.form, row.value)


def replace_at(value: dict, path: tuple, replacement: dict) -> None:
    parent: Any = value
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = replacement


def comparison_references(document: dict) -> Iterator[TypedReference]:
    for i, comparison in enumerate(_rows(document.get('comparisons'))):
        for key in ('source', 'prediction_source'):
            value = _object(_object(comparison).get('binding')).get(key)
            if isinstance(value, dict):
                yield TypedReference(('comparisons', i, 'binding', key),
                                     '비교 관측' if key == 'source' else '비교 예측', 'curve', deepcopy(value))
