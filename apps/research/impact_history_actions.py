"""Use the existing Study and Plan owners for an explicitly selected history."""
from copy import deepcopy

from caelab.impact_history_binding import capsule
from caelab.research_operations import RESULT_REF_KEYS


def prepare_followup(client, packet, kind, command_id):
    if kind not in {'study','numerical'}:raise ValueError('Choose Study or Numerical Plan')
    source={key:packet['source'][key] for key in RESULT_REF_KEYS}
    origin=client.document_read(source['document_id'])
    receipt=client.result_followup(source,'study',session_id=origin['session_id'],
        command_id=command_id+'Study',history_selection=capsule(packet))
    study=receipt['document']
    if kind=='study':return receipt
    expected={'kind':'result',**source,'response':packet['source']['response'],
        'selection':capsule(packet)}
    evidence=next((row for row in study['draft'].get('evidence',[]) if row.get('id')=='Eresult'),None)
    if evidence is None or evidence.get('reference')!=expected:
        raise ValueError('연구 문서의 이력 선택이 바뀌었습니다. 기존 편집을 보존했으니 다시 확인하고 연결하세요.')
    saved=client.document_command(study['id'],'document.save',{},session_id=study['session_id'],
        expected_generation=study['generation'],command_id=command_id+'Save')['document']
    context={'study_id':saved['id'],'saved_revision':saved['saved_revision'],
        'input_revision':saved['input_revision'],'input_sha256':source_hash(saved),
        'selected_kind':'evidence','selected_id':'Eresult'}
    plan=client.study_followup(context,'numerical',session_id=saved['session_id'],command_id=command_id+'Plan')
    return {**plan,'selection_study':deepcopy(context)}


def source_hash(document):
    from caelab.storage import canonical_hash
    return canonical_hash(document['draft'])
