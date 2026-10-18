"""A stored selection cannot silently acquire different masks or source bytes."""
from copy import deepcopy
import pytest

from caelab.impact_bulk_results import response
from caelab.impact_responses import select_history
from caelab.impact_history_binding import capsule, replay, selected_result
from caelab.storage import canonical_hash


def retained():
    channel=response([0.,.1,.2],[1.,None,-2.],unit='N s',label='원 충격량',
        measure='native_cumulative_contact_impulse',
        selection={'scope':'pair','identity':0,'quantity':'impulse','component':'FNZ'})
    result={'execution_status':'FAILED','responses':{'impulse':channel}}
    source={'document_id':'Vtest','job_id':'Jtest','input_revision':'Itest',
        'input_sha256':'1'*64,'result_sha256':canonical_hash(result)}
    packet=select_history({'source':source,'result':result},
        dict(response='impulse',start_s=0.,end_s=.2,side='native',transform='identity'))
    return source,result,packet


def test_stored_selection_preserves_missing_signed_original_and_failed_status():
    source,result,packet=retained();before=deepcopy(result)
    assert replay(source,result,capsule(packet))==packet
    actual=selected_result(source,result,capsule(packet))
    assert actual['execution_status']=='FAILED'
    assert actual['responses']['impulse']['raw_samples']['transformed_values']==[1.,None,-2.]
    assert result==before


@pytest.mark.parametrize('changed',['mask','request','hash','result'])
def test_changed_mask_request_binding_or_result_is_rejected(changed):
    source,result,packet=retained();selection=capsule(packet)
    if changed=='mask':selection['selection']['calculation_valid'][1]=True
    elif changed=='request':selection['selection']['request']['end_s']=.1
    elif changed=='hash':selection['selection_sha256']='0'*64
    else:result['responses']['impulse']['raw_samples']['transformed_values'][0]=2.
    with pytest.raises(ValueError):replay(source,result,selection)


def test_study_reference_cannot_relabel_the_selected_response():
    from caelab.study_document import reference_error
    source,result,packet=retained()
    reference={'kind':'result',**source,'response':'impulse','selection':capsule(packet)}
    assert reference_error(reference) is None
    reference['response']='other_body_force'
    assert '응답이 다릅니다' in reference_error(reference)
