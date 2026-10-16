"""Preserved actual CCX 2.22 public output; these tests never execute a solver."""
from pathlib import Path
from copy import deepcopy
import json
import shutil
import pytest
from caelab.composite_shell_results import read_native,selected_tensor,retain,load

FIXTURE=Path(__file__).parent/'fixtures/composite_shell_ccx222'


def test_actual_layer_topology_material_and_all_native_dat_tuples():
    model=json.loads((FIXTURE/'mesh.json').read_text(encoding='utf-8'))
    observed=read_native(FIXTURE,model)
    assert len(observed['mother_expansion'])==8 and len(observed['layer_solids'])==16
    assert observed['dat']['status']=='COMPLETE' and observed['frd']['status']=='COMPLETE'
    rows=observed['dat']['frames'][-1]['rows'];assert len(rows)==128
    lines=(FIXTURE/'composite.dat').read_text(encoding='ascii').splitlines()
    for row in rows:
        assert row['native_layer']==(row['integration_point']-1)//8+1
        assert row['ui_position']==3-row['native_layer']
        assert row['thickness_ip']==((row['integration_point']-1)%8)//4+1
        for field in ('S','E'):
            source=lines[row[field]['source_line']-1].split()
            assert source[:2]==[str(row['element_id']),str(row['integration_point'])]
            assert source[2:]==row[field]['raw_tokens']
            assert row[field]['values']==[float(source[k]) for k in (2,3,4,5,7,6)]
        assert row['position_provenance'].startswith('Calculated')
    lower=[r for r in rows if r['native_layer']==1];upper=[r for r in rows if r['native_layer']==2]
    assert max(r['position_derived_mm'][2] for r in lower)<0<min(r['position_derived_mm'][2] for r in upper)
    assert {r['material_id'] for r in lower}=={'Isotropic'}
    assert {r['material_id'] for r in upper}=={'Orthotropic'}


def test_missing_duplicate_and_inconsistent_layers_are_not_relabelled(tmp_path):
    root=tmp_path/'native';shutil.copytree(FIXTURE,root)
    model=json.loads((root/'mesh.json').read_text(encoding='utf-8'))
    path=root/'composite.dat';original=path.read_bytes();lines=original.decode('ascii').splitlines()
    index=next(i for i,line in enumerate(lines) if len(line.split())==8 and line.split()[:2]==['1','1'])
    lines.insert(index,lines[index]);path.write_text('\n'.join(lines),encoding='ascii')
    with pytest.raises(ValueError,match='Repeated'):read_native(root,model)
    path.write_bytes(original);lines=original.decode('ascii').splitlines();lines.pop(index)
    path.write_text('\n'.join(lines),encoding='ascii')
    with pytest.raises(ValueError,match='Incomplete'):read_native(root,model)
    path.write_bytes(original)
    model['draft']['regions'][0]['plies'][0]['thickness_mm']='.8';model['applied']['draft']=deepcopy(model['draft'])
    with pytest.raises(ValueError,match='thickness|position|offset'):read_native(root,model)


def test_saved_native_tuple_bundle_reopens_without_calculation_and_detects_changed_view(tmp_path):
    model=json.loads((FIXTURE/'mesh.json').read_text(encoding='utf-8'));observed=read_native(FIXTURE,model)
    post=tmp_path/'post';post.mkdir();shutil.copytree(FIXTURE,post/'source')
    primary,metadata=retain(post,model,observed,execution_status='FAILED')
    restored=load(post/primary,metadata['composite_inspection'])
    assert restored['data']['execution_status']=='FAILED'
    assert len(restored['data']['observed']['dat']['frames'][-1]['rows'])==128
    (post/primary).write_bytes((post/primary).read_bytes()+b' ')
    with pytest.raises(ValueError,match='changed'):load(post/primary,metadata['composite_inspection'])


def test_simulation_registers_the_retained_failed_native_result_without_rerunning(tmp_path):
    from caelab.adapters.composite_shell_fem import collect
    from caelab.research_execution import publish_fields
    from caelab.workbench import Workbench
    model=json.loads((FIXTURE/'mesh.json').read_text(encoding='utf-8'))
    output=tmp_path/'result';calculation=output/'calculation'
    shutil.copytree(FIXTURE,calculation/'solver')
    result=collect(calculation,model,execution_status='FAILED')
    wb=Workbench(tmp_path/'workspace')
    try:
        publish_fields(wb,result,output)
        assert result['execution_status']=='FAILED'
        saved=load(wb.input_path(result['post_input']['id']))
        assert saved['data']['execution_status']=='FAILED'
        assert len(saved['data']['observed']['dat']['frames'][-1]['rows'])==128
        assert not wb.manager.list()
        primary=calculation/result['post_artifact']['relative']
        primary.write_bytes(primary.read_bytes()+b' ')
        with pytest.raises(ValueError,match='changed'):
            publish_fields(wb,result,output)
        assert len(list((wb.root/'inputs').iterdir()))==1
    finally:
        assert wb.shutdown()['joined']
