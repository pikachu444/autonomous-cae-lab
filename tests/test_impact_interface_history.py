"""Existing material/mesh with explicit history admission; no native solver."""
from copy import deepcopy
import pytest
from examples.impact.cohesive_model import settings as coupon
from caelab.impact_model import model_from_settings
from caelab.impact_interface_history import validate


def definition():
    value=coupon();value['motions']=[]
    value['interface_histories']=[{'name':'normal','material':'BOND','node_set':'MOVING','component':'Z',
        'time_s':[0.,.00025,.0005,.00075,.001], 'displacement_mm':[0.,.008,0.,-.002,.008],'frame':'MODEL_GLOBAL'}]
    return value


def test_explicit_history_preserves_original_settings_and_material():
    value=definition();before=deepcopy(value);rows=validate(model_from_settings(value),value)
    assert rows==value['interface_histories'] and value==before
    rows[0]['displacement_mm'][1]=.1
    assert value==before


@pytest.mark.parametrize('change',['time','endpoint','jump','nonfinite','unknown_set','lower_set','partial_set','duplicate','fixed','velocity'])
def test_invalid_or_conflicting_history_blocks_before_native(change):
    value=definition();model=model_from_settings(value);row=value['interface_histories'][0]
    if change=='time':row['time_s'][2]=row['time_s'][1]
    elif change=='endpoint':row['time_s'][-1]=.002
    elif change=='jump':row['displacement_mm'][0]=.001
    elif change=='nonfinite':row['displacement_mm'][1]=float('nan')
    elif change=='unknown_set':row['node_set']='MISSING'
    elif change=='lower_set':row['node_set']='FIXED'
    elif change=='partial_set':model['nsets']['MOVING']={9}
    elif change=='duplicate':value['interface_histories'].append({**deepcopy(row),'name':'second'})
    elif change=='fixed':model['blocks'].append({'card':'BOUNDARY','options':{},'rows':[(1,'MOVING,3,3,0')],'line':1})
    else:value['motions']=coupon()['motions']
    with pytest.raises(ValueError):validate(model,value)


def test_two_axes_are_explicit_not_unmentioned_zero_axis_constraints():
    value=definition();normal=value['interface_histories'][0]
    value['interface_histories'].append({**deepcopy(normal),'name':'shear','component':'X','displacement_mm':[0.,.004,0.,0.,.004]})
    assert {row['component'] for row in validate(model_from_settings(value),value)}=={'X','Z'}



def test_native_history_cards_reuse_converter_and_preserve_materials(tmp_path):
    from test_impact_damage import converted
    from caelab.impact_bulk_deck import cards,integer,real
    from caelab.impact_damage import apply_laws
    from caelab.impact_interface_history import apply,verify
    value=definition();convert=deepcopy(value);convert.pop('interface_histories')
    raw,initial=converted(tmp_path,convert);model=model_from_settings(value)
    model={**model,'nodes':initial['nodes']}
    native,law=apply_laws(raw,model,value['cohesive'])
    before=cards(native);after,receipt=apply(native,model,value)
    blocks=cards(after)
    assert all(blocks[key]==rows for key,rows in before.items())
    entry=receipt['histories'][0];fid=entry['native_function_id'];gid=entry['native_group_id']
    imposed=blocks['/IMPDISP/'+str(entry['native_imposed_id'])]
    assert imposed[1]==integer(fid)+'         Z'+' '*10+integer(0)+integer(gid)+' '*10+integer(0)
    assert imposed[2]==real(1)+real(1)+real(0)+real(.001)
    assert blocks['/FUNCT/'+str(fid)][1:]==[real(t)+real(u) for t,u in zip(value['interface_histories'][0]['time_s'],value['interface_histories'][0]['displacement_mm'])]
    verify(after,model,value,receipt)
    changed=after.replace(imposed[2],real(2)+imposed[2][20:])
    with pytest.raises(ValueError,match='변경'):verify(changed,model,value,receipt)
    with pytest.raises(ValueError,match='이중'):apply(after,model,value)
    with pytest.raises(ValueError,match='중복'):verify(after.replace('/END','/IMPVEL/99999\nx\n/END'),model,value,receipt)
    stale=deepcopy(value);stale['interface_histories'][0]['node_set']='MISSING'
    with pytest.raises(ValueError):verify(after,model,stale,receipt)
    changed_model=deepcopy(model);changed_model['nodes'][1][0]+=.1
    with pytest.raises(ValueError,match='변경'):verify(after,changed_model,value,receipt)


def test_observer_preserves_missing_and_inactive_and_raw_compression(tmp_path):
    from test_impact_damage import frames
    from caelab.impact_interface_history import observe
    from caelab.impact_b import model_identity
    from caelab.storage import canonical_hash
    value=definition();model,raw,cohesive=frames(tmp_path)
    receipt={'model_identity':model_identity(model),'definition_sha256':canonical_hash(value['interface_histories']),'histories':deepcopy(value['interface_histories'])}
    # Explicit synthetic reader contract double: not a native physics result.
    for _,sample in raw:
        for point,node in zip(sample['points'],sample['POINTS']['NODE_ID']['values']):
            if node>=9:point[2]-=.03
        sample['CELLS']['3DELEM_Stress']['values'][17]=-1.
    report=observe(raw,model,value,cohesive,receipt);element=report['elements'][0]
    assert element['strict_partial_times_s']==[.1,.3]
    assert element['sampled_damage_nondecrease']=='OBSERVED'
    assert element['sampled_initial_basis_compressive_sign']=='OBSERVED'
    first=element['samples'][0]
    assert first['paired_change_mm']['normal']==pytest.approx(-.03)
    assert first['native_global_mean_traction_tensor_mpa'][-1]==-1.
    assert first['paired_separation_mm']['normal']<0
    assert first['adjacent_bulk_activity']=={'1':[1],'3':[1]}
    assert first['derived_initial_basis_traction_mpa']['normal']==-1.
    assert report['constitutive_numerical_criterion']=='UNKNOWN'
    # Compression does not require raw separation to cross zero.
    raw[0][1]['points'][8][2]+=.02
    raw[0][1]['points'][9][2]+=.02
    raw[0][1]['points'][10][2]+=.02
    raw[0][1]['points'][11][2]+=.02
    report=observe(raw,model,value,cohesive,receipt)
    assert report['elements'][0]['samples'][0]['paired_change_mm']['normal']<0
    assert report['elements'][0]['samples'][0]['paired_separation_mm']['normal']>0
    del raw[1][1]['CELLS']['3DELEM_Damage']
    raw[2][1]['CELLS']['EROSION_STATUS']['values'][1]=0
    report=observe(raw,model,value,cohesive,receipt);element=report['elements'][0]
    assert element['sampled_damage_nondecrease']=='UNKNOWN'
    assert element['samples'][1]['native_mean_damage'] is None
    assert element['samples'][2]['native_mean_damage'] is None
    assert element['samples'][2]['active']==0
    assert element['samples'][2]['reasons']



def test_common_compile_and_retained_partial_observer_keep_failed_verdict(tmp_path):
    from test_impact_damage import converted,frames
    from caelab.impact_model import validate_settings
    from caelab.impact_damage import apply_laws
    from caelab.impact_b import compile,verify,append_readback
    from caelab.impact_retained import artifact_receipt
    from caelab.dynamic_result_store import file_pin
    from caelab.storage import save_json
    value=definition();validate_settings(value)
    raw,initial=converted(tmp_path,value);model=model_from_settings(value)
    model={**model,'nodes':initial['nodes']}
    native,cohesive=apply_laws(raw,model,value['cohesive'])
    effective,definition_receipt=compile(native,model,value,cohesive)
    assert definition_receipt['interface_history']['histories'][0]['component']=='Z'
    verify(effective,model,value,definition_receipt)
    root=tmp_path/'retained';(root/'native').mkdir(parents=True)
    (root/'native/impact_0000.rad').write_text(effective,encoding='ascii')
    save_json(root/'b_definition.json',definition_receipt)
    save_json(root/'input.json',value)
    _,synthetic,_=frames(tmp_path)
    original={'execution_status':'FAILED','retained_native':artifact_receipt(root)}
    save_json(root/'original_execution.json',original)
    result={'execution_status':'FAILED','source_execution_status':'FAILED','responses':{},'diagnostics':{
        'original_execution_record':file_pin(root,root/'original_execution.json')}}
    append_readback(root,model,value,result,synthetic,partial=True)
    audit=result['diagnostics']['b_observations']['interface_history']
    assert audit['reader_operation']=='READBACK_ONLY' and audit['source_execution_status']=='FAILED'
    assert audit['elements'][0]['strict_partial_times_s']==[.1,.3]
    assert (root/'interface_history_observations.json').is_file()
    assert result['execution_status']=='FAILED' and audit['qualification']=='UNKNOWN'
    # Historical receipt does not admit a changed IMPDISP definition.
    path=root/'native/impact_0000.rad';path.write_bytes(path.read_bytes().replace(b'HISTORY_normal',b'HISTORY_edited',1))
    changed={'execution_status':'FAILED','responses':{},'diagnostics':{
        'original_execution_record':file_pin(root,root/'original_execution.json')}}
    append_readback(root,model,value,changed,synthetic,partial=True)
    assert changed['diagnostics']['b_observations']['scopes']['definition']['status']=='UNKNOWN'
    assert 'interface_history' not in changed['diagnostics']['b_observations']


@pytest.mark.parametrize('change',['contact','late_contact','raw_rad','boolean_time','bad_name'])
def test_history_admission_does_not_silently_add_double_support_or_change_source(change):
    value=definition();model=model_from_settings(value)
    if change=='contact':value['contacts']=[{'a':'LOWER_TOP','b':'UPPER_BOTTOM','friction':0.}]
    elif change=='late_contact':
        from caelab.impact_interface import default_control
        value['interface_controls']=[{**default_control('BOND'),'reclosure':'DELAYED_TYPE24_REQUIRE_DELETION'}]
    elif change=='raw_rad':value['source']['format']='RAD'
    elif change=='boolean_time':value['interface_histories'][0]['time_s'][0]=False
    else:value['interface_histories'][0]['node_set']=[]
    with pytest.raises(ValueError):validate(model,value)



def test_partial_observation_requires_both_live_adjacent_bulk_cells(tmp_path):
    from test_impact_damage import frames
    from caelab.impact_interface_history import observe
    from caelab.impact_b import model_identity
    from caelab.storage import canonical_hash
    value=definition();model,raw,cohesive=frames(tmp_path)
    receipt={'model_identity':model_identity(model),'definition_sha256':canonical_hash(value['interface_histories']),
             'histories':deepcopy(value['interface_histories'])}
    for _,sample in raw:sample['CELLS']['EROSION_STATUS']['values'][0]=0
    report=observe(raw,model,value,cohesive,receipt);element=report['elements'][0]
    assert element['strict_partial_times_s']==[] and element['partial_state']=='NOT_OBSERVED'
    assert element['sampled_damage_nondecrease']=='UNKNOWN'
    assert element['samples'][1]['native_mean_damage']==.2
    assert element['samples'][1]['adjacent_bulk_activity']=={'1':[0],'3':[1]}
    assert element['samples'][1]['paired_change_mm']['normal'] is None



def test_observer_preserves_damage_decrease_and_rejects_time_reordering(tmp_path):
    from test_impact_damage import frames
    from caelab.impact_interface_history import observe
    from caelab.impact_b import model_identity
    from caelab.storage import canonical_hash
    value=definition();model,raw,cohesive=frames(tmp_path)
    receipt={'model_identity':model_identity(model),'definition_sha256':canonical_hash(value['interface_histories']),
             'histories':deepcopy(value['interface_histories'])}
    raw[1][1]['CELLS']['3DELEM_Damage']['values'][1]=.5
    raw[2][1]['CELLS']['3DELEM_Damage']['values'][1]=.25
    report=observe(raw,model,value,cohesive,receipt);element=report['elements'][0]
    assert element['sampled_damage_nondecrease']=='VIOLATED'
    assert element['damage_decrease_steps']==[{'before_time_s':.1,'after_time_s':.3,'before':.5,'after':.25}]
    assert element['samples'][2]['native_mean_damage']==.25
    raw[2][1]['time']=.1
    with pytest.raises(ValueError,match='증가'):observe(raw,model,value,cohesive,receipt)



def test_zero_later_motion_does_not_hide_nonzero_initial_velocity_conflict():
    value=definition();motion=deepcopy(coupon()['motions'][0]);zero=deepcopy(motion);zero['velocity_mm_s']=[0.,0.,0.]
    value['motions']=[motion,zero]
    with pytest.raises(ValueError,match='초기 속도'):validate(model_from_settings(value),value)
