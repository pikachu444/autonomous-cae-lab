"""E1 numeric/selection/deck regressions, no native solver assertions."""
from copy import deepcopy
import json
import pytest

from caelab.shell_model import (validate_draft,reverse,prepare_mesh,derivatives8,shape8,
                               ShellError,DEFAULTS,REVERSE_S8)
from caelab.adapters.shell_deck import build,native_mesh,validate_snapshot
from apps.desktop_pre.shell_panel import DraftBuffer
if __package__:
    from .test_shell_support import model,mesh_text,snapshot
else:
    from test_shell_support import model,mesh_text,snapshot

@pytest.mark.parametrize('value',['0','-2','1e','NaN','Inf','1e10000'])
def test_invalid_raw_thickness_has_addressed_error_and_roundtrips(value):
    draft=model()['draft'];draft['thickness_mm']=value
    restored=json.loads(json.dumps(draft))
    assert restored['thickness_mm']==value
    errors,_=validate_draft(restored)
    assert any(e['path']=='thickness_mm' for e in errors)

@pytest.mark.parametrize('thickness',['2','3','2.345678901234567'])
def test_native_card_retains_actual_serialized_thickness(thickness):
    text,mesh=build(model(thickness=thickness,offset='0.25'))
    assert mesh['section_values']=={'thickness_mm':float(f'{float(thickness):.13G}'),'offset':.25}
    assert text.count('*SHELL SECTION')==2
    assert '*ELEMENT, TYPE=S8' in text and 'C3D10' not in text
    assert f'\n{float(thickness):.13G}\n' in text
    assert 'OUTPUT=3D' in text and 'S, E, COORD' in text

@pytest.mark.parametrize('family',['S8R','M3D8','C3D10','S4','S6'])
def test_solid_membrane_reduced_other_families_are_not_admitted(family):
    with pytest.raises(ValueError):native_mesh(mesh_text(model()).replace('TYPE=S8','TYPE='+family))

@pytest.mark.parametrize('target',['native_sections','native_pressure','native_material','applied'])
def test_stale_native_or_applied_state_cannot_silently_replace_draft(target):
    data=model()
    if target=='native_sections':data[target]=data[target].replace('\n2\n','\n3\n')
    elif target=='native_pressure':data[target]=data[target].replace('-0.001','0.001')
    elif target=='native_material':data[target]=data[target].replace('210000','110000')
    else:data[target]['draft']['thickness_mm']='3'
    with pytest.raises(ValueError):build(data)

def test_reversal_exchanges_sides_without_moving_occupied_geometry():
    a=model(offset='.3'); b=model(offset='.3',flipped=True)
    _,ma=build(a);_,mb=build(b)
    assert mb['elements'][1]==tuple(ma['elements'][1][i] for i in REVERSE_S8)
    assert mb['values']['offset']==-.3 and mb['values']['pressure_MPa']==-.001
    assert mb['normals'][1]==tuple(-x for x in ma['normals'][1])
    for old_side,new_side in ((1,-1),(-1,1)):
        pa=[a['draft']['thickness_mm'],b['draft']['thickness_mm']]
        va=[2*(old_side/2-.3)*n for n in ma['normals'][1]]
        vb=[2*(new_side/2+.3)*n for n in mb['normals'][1]]
        assert vb==pytest.approx(va)
    keep_normal_pressure=reverse(a['draft'],keep_physical_load=False)
    assert keep_normal_pressure['pressure_MPa']==a['draft']['pressure_MPa']
    invalid=deepcopy(a['draft']);invalid['offset']='1e';original=deepcopy(invalid)
    with pytest.raises(ShellError):reverse(invalid)
    assert invalid==original

def test_missing_direction_axis_parallel_lost_selection_block():
    for edit,path in [({'orientation':''},'orientation'),({'axis_x':'0','axis_z':'1'},'elements/1'),({'elements':[999]},'elements')]:
        data=model();data['draft'].update(edit);data['applied']['draft']=deepcopy(data['draft'])
        with pytest.raises(ShellError) as exc:build(data)
        assert any(e['path']==path for e in exc.value.errors)

def test_only_selected_user_elements_are_exported():
    data=model();data['draft']['elements']=[1];data['applied']['draft']=deepcopy(data['draft'])
    data['native_sections']=data['native_sections'].split('*SHELL SECTION')[0]+'*SHELL SECTION'+data['native_sections'].split('*SHELL SECTION')[1]
    data['native_pressure']='*DLOAD\n1,P,-0.001\n'
    text,mesh=build(data)
    assert set(mesh['elements'])=={1}
    assert '*ELEMENT, TYPE=S8' in text and 'ES2' not in text

def test_numeric_shape_derivatives_against_finite_difference():
    h=1e-6
    for r,s in [(0.,0.),(.13,-.47),(-.9,.8)]:
        dr,ds=derivatives8(r,s)
        assert sum(shape8(r,s))==pytest.approx(1.)
        assert dr==pytest.approx([(a-b)/(2*h) for a,b in zip(shape8(r+h,s),shape8(r-h,s))],abs=1e-9)
        assert ds==pytest.approx([(a-b)/(2*h) for a,b in zip(shape8(r,s+h),shape8(r,s-h))],abs=1e-9)

def test_snapshot_reopen_verifies_every_native_source_and_no_overwrite(tmp_path):
    path=snapshot(tmp_path/'snapshot')
    validate_snapshot(path)
    native=path.parent/'native_mesh.inp';native.write_text(native.read_text()+'** changed\n')
    with pytest.raises(ValueError):validate_snapshot(path)

def test_draft_buffer_ack_does_not_overwrite_newer_edit():
    b=DraftBuffer();b.read('A',model()['draft']);b.fields['thickness_mm']='1e'
    frozen=b.snapshot();b.fields['thickness_mm']='3'
    b.acknowledge(frozen)
    assert b.fields['thickness_mm']=='3' and b.pending_changes()
