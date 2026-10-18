"""Common admission and partial readback edges; no native solver execution."""
from copy import deepcopy

import pytest

from test_impact_interface_history import definition
from test_impact_damage import converted, frames
from caelab.impact_model import model_from_settings, validate_settings


@pytest.mark.parametrize('malformed',[None,{},'',0,False])
@pytest.mark.parametrize('bound',[False,True])
def test_present_history_field_cannot_silently_become_no_load(malformed,bound):
    value=definition()
    if bound:
        from caelab.impact_reference_bindings import snapshot
        value['source_reference_bindings']=snapshot(value)
    value['interface_histories']=malformed
    with pytest.raises(ValueError,match='명시 계면 하중 이력'):
        validate_settings(value)


def test_unavailable_frame_preserves_raw_samples_and_marks_partial_observation(tmp_path):
    from caelab.impact_damage import apply_laws
    from caelab.impact_b import compile,append_readback
    from caelab.impact_retained import artifact_receipt
    from caelab.dynamic_result_store import file_pin
    from caelab.storage import save_json

    value=definition();raw,initial=converted(tmp_path,value)
    model={**model_from_settings(value),'nodes':initial['nodes']}
    native,cohesive=apply_laws(raw,model,value['cohesive'])
    effective,receipt=compile(native,model,value,cohesive)
    root=tmp_path/'retained';(root/'native').mkdir(parents=True)
    (root/'native/impact_0000.rad').write_text(effective,encoding='ascii')
    save_json(root/'b_definition.json',receipt);save_json(root/'input.json',value)
    save_json(root/'original_execution.json',{'execution_status':'FAILED','retained_native':artifact_receipt(root)})
    result={'execution_status':'FAILED','source_execution_status':'FAILED','responses':{},'diagnostics':{
        'original_execution_record':file_pin(root,root/'original_execution.json')}}
    _,samples,_=frames(tmp_path);before=deepcopy(samples)

    class PartialFrames:
        frames=[{'available':True},{'available':False,'time_s':.2,'reason':'missing original frame'},
                {'available':True},{'available':True}]
        def __getitem__(self,index):return samples[{0:0,2:1,3:2}[index]]

    append_readback(root,model,value,result,PartialFrames(),partial=True)
    record=result['diagnostics']['b_observations'];audit=record['interface_history']
    assert record['scopes']['interface_history']['status']=='PARTIAL'
    assert result['diagnostics']['readback_scopes']['b_interface_history']['status']=='PARTIAL'
    assert audit['unavailable_frames']==[{'frame_index':1,'time_s':.2,'reason':'missing original frame'}]
    assert audit['elements'][0]['sampled_damage_nondecrease']=='UNKNOWN'
    assert [s['time_s'] for s in audit['elements'][0]['samples']]==[s['time'] for _,s in samples]
    assert samples==before and result['execution_status']=='FAILED'
