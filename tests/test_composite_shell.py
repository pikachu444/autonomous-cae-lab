"""Laminate admission/deck/basis checks; no solver is simulated as native success."""
from copy import deepcopy
import pytest
from examples.composite.generate_laminate import model
from caelab.composite_shell import material_values,validate,move_ply,reverse_region,ply_axes
from caelab.adapters.composite_shell_deck import build
from caelab.adapters.composite_shell_fem import CompositeShellCalculixAdapter
from caelab.composite_shell_results import selected_tensor


def test_original_layers_reverse_only_at_native_boundary():
    data=model();before=deepcopy(data);text,mesh=build(data)
    assert data==before
    assert '*ELEMENT, TYPE=S8R' in text and 'COMPOSITE' in text
    assert 'COORD' not in text and '\nRF' not in text
    assert '*ELASTIC, TYPE=ENGINEERING CONSTANTS' in text
    for rows in mesh['native_layers'].values():
        assert [(r['native_layer'],r['ply_id'],r['ui_position'],r['thickness_mm']) for r in rows]==[(1,'LowerPly',2,1.3),(2,'UpperPly',1,.7)]
    swapped=move_ply(data['draft'],'PlateRegion','UpperPly',1);data['draft']=swapped;data['applied']['draft']=deepcopy(swapped)
    _,changed=build(data)
    assert changed['native_layers'][1][0]['ply_id']=='UpperPly'


@pytest.mark.parametrize('change',[('thickness_mm','0'),('thickness_mm','1e'),('thickness_mm','NaN'),('material_id','missing')])
def test_invalid_edit_remains_raw_but_cannot_export(change):
    data=model();data['draft']['regions'][0]['plies'][0][change[0]]=change[1];data['applied']['draft']=deepcopy(data['draft'])
    before=deepcopy(data)
    with pytest.raises(ValueError):build(data)
    assert data==before


def test_orthotropic_reciprocity_spd_not_isotropic_poisson_bound():
    original=model()['draft']['materials']['Orthotropic'];record=deepcopy(original)
    record['constants'].update(E1_MPa='100',E2_MPa='10',E3_MPa='10',nu12='.6',nu13='.6',nu23='.2')
    assert material_values(record)['constants']['nu12']==.6
    record['constants'].update(E2_MPa='100',E3_MPa='100',nu23='.6')
    with pytest.raises(ValueError,match='정부호'):material_values(record)
    record=deepcopy(original);record['constants'].pop('G23_MPa')
    with pytest.raises(ValueError):material_values(record)


def test_normal_reversal_preserves_occupied_stack_and_declared_axes():
    draft=model()['draft'];reversed=reverse_region(draft,'PlateRegion');a=draft['regions'][0];b=reversed['regions'][0]
    assert [p['id'] for p in b['plies']]==[p['id'] for p in a['plies'][::-1]]
    assert float(b['offset'])==-float(a['offset']) and float(b['pressure_MPa'])==-float(a['pressure_MPa'])
    assert [float(p['angle_deg']) for p in b['plies']]==[-float(p['angle_deg']) for p in a['plies'][::-1]]
    transformed=reverse_region(reversed,'PlateRegion')
    for p,q in zip(transformed['regions'][0]['plies'],a['plies']):assert p['id']==q['id'] and float(p['angle_deg'])==float(q['angle_deg'])


def test_declared_basis_transform_preserves_raw_tensor_trace_and_norm():
    row={'ply_id':'P','S':{'values':[10.,20.,30.,2.,3.,4.]}};before=deepcopy(row)
    layer={'ply_id':'P','axes_global':ply_axes(([1,0,0],[0,1,0],[0,0,1]),90)}
    actual=selected_tensor(row,'S',basis='DECLARED_PLY',layer=layer)
    assert actual==pytest.approx([20,10,30,-2,-4,3])
    assert sum(actual[:3])==pytest.approx(sum(row['S']['values'][:3]))
    assert row==before


def test_public_diagnostics_never_resolve_server_path(monkeypatch):
    adapter=CompositeShellCalculixAdapter()
    monkeypatch.setattr('caelab.adapters.composite_shell_fem.validate_snapshot',lambda *_:pytest.fail('server path read'))
    assert adapter.validate_settings({'data_id':'D'+'a'*32})['data_id'].startswith('D')
    for settings in ({'snapshot_path':'C:/private/snapshot.json'},{'data_id':'D'+'a'*32,'snapshot_path':'C:/private/snapshot.json'}):
        with pytest.raises(ValueError):adapter.describe_ports(settings)


def test_layer_count_and_disjoint_regions_are_explicit():
    draft=model()['draft'];draft['regions'][0]['plies']=draft['regions'][0]['plies'][:1]
    assert validate(draft)[0]
    draft=model()['draft'];draft['regions'].append(deepcopy(draft['regions'][0]));draft['regions'][1]['id']='overlap'
    assert validate(draft)[0]
