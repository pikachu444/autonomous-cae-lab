"""Retained IP artifact and actual same-mesh receiver gates; no solver runs."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from initial_field_fixture import model
from test_structural_field_ports import saved_source
from caelab.evaluation import file_hash
from caelab.storage import save_json
from caelab.stress_state_transfer import read_saved_stress,verify_stress_source,draft_for_receiver


@pytest.fixture
def source_case(saved_source):
    wb,reference,root,*_=saved_source
    meshpath=root/'calculation/frozen_input/mesh.json'
    old=json.loads(meshpath.read_text(encoding='utf-8'));m=model()
    for row,original in zip(m['nodes'],old['nodes']):
        row['position_mm']=original['position_mm'];row['native_position_mm']=original['position_mm']
    meshpath.write_text(json.dumps(m),encoding='utf-8')
    lines=[' stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set INITIAL_BODY and time 1.000000E+00','']
    for point in range(1,5):
        values=[100.,10.,-20.,1.,2.,3.]
        lines.append('1 '+str(point)+' '+' '.join(format(v,'.6E') for v in values))
    lines+=['',' global coordinates (elem, integ.pnt.,x,y,z) for set INITIAL_BODY and time 1.000000E+00','']
    xyz={r['node_id']:r['position_mm'] for r in m['nodes']}
    for point in range(1,5):
        L=[.1381966011250105]*4;L[point-1]=.5854101966249685
        coordinates=[sum(L[j]*xyz[j+1][k] for j in range(4)) for k in range(3)]
        lines.append('1 '+str(point)+' '+' '.join(format(v,'.6E') for v in coordinates))
    dat=root/'calculation/solver/contact.dat';dat.parent.mkdir(parents=True)
    dat.write_text('\n'.join(lines)+'\n\n',encoding='ascii')
    from caelab.adapters.initial_field_results import read
    rows=read(dat,m,[{'static':{'step':1,'increment':1,'load_parameter':1.}}],require_definition=False)
    path=root/'calculation/initial_fields.json'
    path.write_text(json.dumps({'raw_source':'solver/contact.dat','rows':rows}),encoding='utf-8')
    record=json.loads((root/'result.json').read_text(encoding='utf-8'))
    for artifact in record['artifacts']:
        artifact['sha256']=file_hash(root/artifact['path'])
    record['artifacts'].append({'path':path.relative_to(root).as_posix(),'sha256':file_hash(path)})
    record['artifacts'].append({'path':dat.relative_to(root).as_posix(),'sha256':file_hash(dat)})
    save_json(root/'result.json',record)
    save_json(root/'result.sha256.json',{'sha256':file_hash(root/'result.json')})
    return wb,reference,root,m


def test_same_mesh_renamed_user_model_rotates_physical_tensor_once_and_keeps_steps(source_case):
    wb,reference,root,m=source_case
    before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    field,proof=read_saved_stress(wb,reference,with_proof=True)
    receiver=deepcopy(m)
    receiver['conditions'][0]['label']='사용자 지지'
    receiver['materials'][0]['object_id']='MyMaterial'
    untouched=deepcopy(receiver)
    result=draft_for_receiver(receiver,field,proof,mesh_id='ArbitraryNativeMesh',
        tensor_rotation=[[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    assert result['definition']['stress_rows'][0]['values_MPa']==[10.,100.,-20.,-1.,-3.,2.]
    assert receiver==untouched
    assert result['draft']['mesh_id']=='ArbitraryNativeMesh'
    assert result['provenance']['engineering_release']=='UNKNOWN'
    assert result['draft']['states']==[{'parameter':1.,'label':'첫 평형','load_factor':None},
                                     {'parameter':2.,'label':'후속 하중','load_factor':None}]
    assert {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('fault',['missing_ip','duplicate_ip','nodal','component','tokens','coordinate','ip_order'])
def test_incomplete_or_wrong_native_ip_is_not_reconstructed(source_case,fault):
    wb,reference,root,_=source_case
    path=root/'calculation/initial_fields.json';raw=json.loads(path.read_text(encoding='utf-8'))
    if fault=='missing_ip':raw['rows'].pop()
    elif fault=='duplicate_ip':raw['rows'][-1]['point']=1
    elif fault=='nodal':raw['rows'][0]['basis']='recovered_nodal_STRESS'
    elif fault=='component':raw['rows'][0]['component_names'][4:]=['YZ','XZ']
    elif fault=='tokens':raw['rows'][0]['raw_stress_tokens'][0]='9.000000E+02'
    elif fault=='coordinate':raw['rows'][0]['position_mm'][0]+=.1
    else:raw['rows'][0]['position_mm'],raw['rows'][1]['position_mm']=raw['rows'][1]['position_mm'],raw['rows'][0]['position_mm']
    path.write_text(json.dumps(raw),encoding='utf-8')
    record=json.loads((root/'result.json').read_text(encoding='utf-8'))
    next(a for a in record['artifacts'] if a['path']=='calculation/initial_fields.json')['sha256']=file_hash(path)
    save_json(root/'result.json',record)
    save_json(root/'result.sha256.json',{'sha256':file_hash(root/'result.json')})
    with pytest.raises(ValueError):read_saved_stress(wb,reference)


@pytest.mark.parametrize('fault',['coordinates','connectivity','native_id','plastic','rotation','changed_source'])
def test_changed_source_or_incompatible_receiver_fails_without_mutating_model(source_case,fault):
    wb,reference,root,m=source_case
    field,proof=read_saved_stress(wb,reference,with_proof=True)
    R=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
    if fault=='coordinates':m['nodes'][0]['position_mm'][0]+=.01
    elif fault=='connectivity':m['elements'][0]['node_ids'][4:6]=m['elements'][0]['node_ids'][5:3:-1]
    elif fault=='native_id':m['nodes'][0]['native_node_id']=999
    elif fault=='plastic':m['materials'][0]['plasticity']={'law':'J2'}
    elif fault=='rotation':R[0][0]=-1.
    else:(root/'calculation/initial_fields.json').write_bytes(b'changed after admission')
    before=deepcopy(m)
    with pytest.raises(ValueError):draft_for_receiver(m,field,proof,mesh_id='ChosenMesh',tensor_rotation=R)
    assert m==before
