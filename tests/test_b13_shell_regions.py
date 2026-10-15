"""Regional shell property/reader/owner regressions, using explicit doubles."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
import pytest
from b13_shell_fixture import model,write_sources
from test_shell_support import snapshot,model as uniform_model
from test_shell_edit import OwnerDouble,EditorDouble
from caelab.shell_model import validate_draft,prepare_mesh,ShellError
from caelab.shell_regions import uniform_region,reverse_region
from caelab.adapters.shell_deck import build
from caelab.adapters.shell_fem import collect,ShellFemCalculixAdapter
from caelab.adapters import shell_fem
from caelab.shell_inspection import explicit_manifest,load,inspect,inspect_internal
from apps.desktop_pre.shell_panel import DraftBuffer


def test_uniform_legacy_is_byte_identical_and_migration_is_explicit():
    m=uniform_model();before=deepcopy(m);expected=build(m)[0]
    r=uniform_region(m['draft'])
    assert m==before and 'regions' not in m['draft']
    assert build(m)[0]==expected and r['elements']==m['draft']['elements']
    m['draft']['geometry_id']=None;m['draft']['pressure_id']=None
    assert uniform_region(m['draft'])['geometry_id']==''


@pytest.mark.parametrize('flipped',[False,True])
def test_curved_regions_native_cards_and_actual_observation_separation(tmp_path,flipped):
    m=model(flipped=flipped);mesh,xyz,exp=write_sources(tmp_path/'solver',m)
    deck,prepared=build(m)
    assert prepared['values_by_element'][m['draft']['elements'][1]]['thickness_mm']==3
    assert len({tuple(n) for n in prepared['normals'].values()})==2
    result=collect(tmp_path,m,mesh,execution_status='SUCCEEDED')
    assert result['execution_status']=='SUCCEEDED'
    # The producer/reopener actually regenerates and checks all regional views.
    portable=tmp_path/'copy';shutil.copytree(tmp_path/'post',portable)
    shutil.rmtree(tmp_path/'solver');shutil.rmtree(tmp_path/'post')
    view,meta=explicit_manifest(portable/'shell_inspection.json')
    checked=load(view);locations=checked['data']['surface']['locations']
    assert {r['region']['id'] for r in locations}=={'R1','R2'}
    location=locations[-1]
    surface=inspect(view,side=location['side'],element_id=location['element_id'],shell_node_id=location['shell_node_id'])
    assert surface['exact_surface_integration_stress']=='UNSUPPORTED'
    ip=inspect_internal(view,element_id=location['element_id'],integration_point=1)
    assert ip['association']=='CELLS' and ip['point_measurement']=='UNSUPPORTED'
    assert ip['position_status']=='OBSERVED' and ip['raw']['source_line']>0
    transformed=inspect_internal(view,element_id=location['element_id'],integration_point=1,basis='element_center_user')
    assert not transformed['basis_transform']['native_IP_material_basis']
    assert transformed['raw']==ip['raw']
    import xml.etree.ElementTree as ET
    tree=ET.parse(portable/'internal_0000.vtu')
    assert not tree.findall('.//PointData/DataArray') and tree.findall('.//CellData/DataArray')


@pytest.mark.parametrize('fault',['overlap','gap','duplicate_native','duplicate_element','zero_thickness','raw','source_normal_ack'])
def test_invalid_region_assignments_are_repairable_not_flattened(fault):
    m=model();d=m['draft'];r=d['regions']
    if fault=='overlap':r[1]['elements'].append(r[0]['elements'][0])
    if fault=='gap':r.pop()
    if fault=='duplicate_native':r[1]['geometry_id']=r[0]['geometry_id']
    if fault=='duplicate_element':r[1]['elements']*=2
    if fault=='zero_thickness':r[1]['thickness_mm']='0'
    if fault=='raw':r[1]['offset']='1e'
    if fault=='source_normal_ack':d['orientation']=''
    errors,_=validate_draft(d)
    assert errors
    original=deepcopy(m['applied'])
    owner=OwnerDouble({'shells':{'ShellAnalysis':{'draft':deepcopy(original['draft']),'applied':original}}})
    ed=EditorDouble(owner,{'applied':original})
    ed.save_draft('ShellAnalysis',{'regions':r,'orientation':d['orientation']})
    fresh=EditorDouble(OwnerDouble(json.loads(json.dumps(owner.data))),{'applied':original})
    assert fresh._record('ShellAnalysis')['draft']['regions']==r
    assert fresh._record('ShellAnalysis')['applied']==original
    with pytest.raises(ShellError):fresh.effective('ShellAnalysis')


def test_cross_region_winding_and_midnode_guard_not_weakened():
    m=model();ns={int(n):p for n,p in m['source_nodes'].items()};es={int(e):c for e,c in m['source_elements'].items()}
    eid=m['draft']['elements'][1];es[eid]=[es[eid][j] for j in (0,3,2,1,7,6,5,4)]
    with pytest.raises(ShellError,match='winding|영역 경계'):prepare_mesh(ns,es,m['draft'])


def test_reversal_couples_offset_pressure_and_does_not_touch_old_result():
    m=model(flipped=False);d=m['draft'];before=deepcopy(d)
    out=reverse_region(d,'R2');a=d['regions'][1];b=out['regions'][1]
    assert float(b['offset'])==-float(a['offset']) and float(b['pressure_MPa'])==-float(a['pressure_MPa'])
    assert d==before and out['regions'][0]==d['regions'][0]
    owner=OwnerDouble({'shells':{'ShellAnalysis':{'draft':d,'applied':m['applied']}}})
    ed=EditorDouble(owner,m)
    wrong=deepcopy(d['regions']);wrong[1]['orientation']='reversed'
    with pytest.raises(ValueError,match='offset'):ed.save_draft('ShellAnalysis',{'regions':wrong})


def test_raw_region_buffer_late_receipt_does_not_erase_new_input():
    d=model()['draft'];buffer=DraftBuffer();buffer.read('A',d)
    buffer.fields['regions'][0]['thickness_mm']='1e';snap=buffer.snapshot()
    buffer.fields['regions'][0]['thickness_mm']='2e';buffer.acknowledge(snap)
    assert buffer.pending_changes() and buffer.fields['regions'][0]['thickness_mm']=='2e'
    before=deepcopy(buffer.base);buffer.acknowledge({'analysis_id':'other','fields':{}})
    assert buffer.base==before


def test_rebind_preserves_newer_region_edits_without_auto_ready():
    m=model();owner=OwnerDouble({'shells':{'ShellAnalysis':{'draft':m['draft'],'applied':m['applied']}}})
    ed=EditorDouble(owner,m);ed._stamp=lambda d:{}
    old=deepcopy(m['draft']);old['orientation']='';ed._pending['token']=('ShellAnalysis',old)
    latest=deepcopy(m['draft']['regions']);latest[0]['thickness_mm']='2e'
    ed.save_draft('ShellAnalysis',{'regions':latest});ed.apply_rebind('token')
    assert ed._record('ShellAnalysis')['draft']['regions']==latest
    assert ed._record('ShellAnalysis')['draft']['orientation']==''


def test_existing_owned_adapter_executes_only_the_selected_regional_snapshot(monkeypatch,tmp_path):
    import subprocess
    m=model();source=snapshot(tmp_path/'input',m);binary=tmp_path/'NOT_A_SOLVER';binary.write_bytes(b'process double')
    monkeypatch.setattr(shell_fem.shutil,'which',lambda _:str(binary));calls=[]
    def command(argv,cwd,label,**kw):
        calls.append(argv);assert kw['owned_tree'] is True
        write_sources(cwd,m)
        return subprocess.CompletedProcess(argv,0,'SYNTHETIC TEST DOUBLE','')
    monkeypatch.setattr(shell_fem,'run_owned_command',command)
    result=ShellFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert result['execution_status']=='SUCCEEDED',result
    assert len(calls)==1 and result['engineering_valid'] is False
