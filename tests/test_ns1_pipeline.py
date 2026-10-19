"""Native-format/process doubles. None of these tests claims a physical solve."""
from copy import deepcopy
import hashlib
import base64
import struct
import math
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS
from xml.etree import ElementTree as ET
import pytest

from test_contact_execution import model, native_outputs
from test_contact_steps import write_snapshot
from caelab.calculix_material import J2, default_plasticity
from caelab.contact_deck import render, validate_model
from caelab.adapters import contact_fem
from caelab.adapters.frozen_fem import read_frd
from caelab.adapters.contact_results import write_post
from caelab.contact_status import read_status
from caelab.execution_control import ExecutionCancelled
from caelab.evaluation import normalize_evaluation


def nonlinear_model(original, *, single=False, nlgeom=True):
    value=deepcopy(original)
    curve=default_plasticity(); curve['yield_points']=[[250,0],[270,1.234567891234567e-5],[300,.02]]
    for material in value['materials']:
        if material['body_id']=='Pad':
            material.update(law=J2,plasticity=deepcopy(curve),source_curve=deepcopy(curve))
    if single:
        value['analysis_scope']='single_solid_static'
        for key in ('nodes','elements','materials'):
            value[key]=[row for row in value[key] if row['body_id']=='Pad']
        value['body_maps']={'Pad':value['body_maps']['Pad']}
        value['contacts']=[]
        value['boundary_dofs']=[dict(node_id=value['body_maps']['Pad']['nodes'][n],component=d,value_mm=0.)
                                for n in (1,2,3) for d in (1,2,3)]
    value['step']['geometry']='nonlinear' if nlgeom else 'linear'
    return value


def outputs(model, *, omit=()):
    """Fixed-column 2.22 format from public frd.c labels; numerical values are artificial."""
    base,dat,materials=native_outputs(model)
    lines=base.split('    1PSTEP',1)[0].splitlines()
    nodes,elements,bodies=validate_model(model)
    labels={
      'DISP':['D1 1 2 1 0','D2 1 2 2 0','D3 1 2 3 0','ALL 1 2 0 0 1ALL'],
      'STRESS':['SXX 1 4 1 1','SYY 1 4 2 2','SZZ 1 4 3 3','SXY 1 4 1 2','SYZ 1 4 2 3','SZX 1 4 3 1'],
      'TOSTRAIN':['EXX 1 4 1 1','EYY 1 4 2 2','EZZ 1 4 3 3','EXY 1 4 1 2','EYZ 1 4 2 3','EZX 1 4 3 1'],
      'FORC':['F1 1 2 1 0','F2 1 2 2 0','F3 1 2 3 0','ALL 1 2 0 0 1ALL'],
      'PE':['PE 1 1 0 0'],
      'CONTACT':['COPEN 1 1 0 0','CSLIP1 1 1 0 0','CSLIP2 1 1 0 0','CPRESS 1 1 0 0','CSHEAR1 1 1 0 0','CSHEAR2 1 1 0 0']}
    values={'DISP':[0.,0.,.02],'STRESS':[275.,1.,2.,3.,4.,5.],
            'TOSTRAIN':[.01,.02,.03,.004,.005,.006],'FORC':[1.,2.,3.],'PE':[.0123],
            'CONTACT':[-.001,0.,0.,1.,0.,0.]}
    names=['DISP','STRESS','TOSTRAIN','FORC','PE']+(['CONTACT'] if model['contacts'] else [])
    counter=0
    for inc,time in [(1,.5),(2,1.)]:
        for name in names:
            if (inc,name) in omit: continue
            counter+=1
            lines += ['    1PSTEP'+' '*14+f'{counter:12d}{inc:12d}{1:12d}'+' '*10,
                      '  100CL'+f'{100+inc:5d}{time:12.9f}{len(nodes):12d}'+' '*21+'0'+f'{inc:5d}'+' '*11+'1',
                      f' -4  {name:<12}{len(labels[name])}    1']
            lines += [' -5  '+label for label in labels[name]]
            for n in nodes:
                lines.append(' -1'+f'{n:10d}'+''.join(f'{v*time:12.5E}' for v in values[name]))
            lines.append(' -3')
    return '\n'.join(lines+[' 9999','']),dat,materials


def status_text(*, failed=False):
    if failed:
        return '1 1 1 3 0.5 0.5 0.5\n1 2 1U 10 0.5 0.5 0.5\n1 2 2U 12 0.5 0.5 0.25\n'
    return '1 1 1 3 0.5 0.5 0.5\n1 2 1 4 1.0 1.0 0.5\n'


def snapshot_of(model, folder):
    path=write_snapshot(model,folder)
    data=json.loads(path.read_text()); data['bodies']=[{'body_id':key} for key in model['body_maps']]
    path.write_text(json.dumps(data),encoding='utf-8')
    return path


@pytest.mark.parametrize('single,nlgeom',[(False,False),(False,True),(True,False),(True,True)])
def test_real_material_sets_output_cards_and_twenty_character_deck_fields(model,single,nlgeom,tmp_path):
    model=nonlinear_model(model,single=single,nlgeom=nlgeom)
    deck=render(model)
    assert deck.count('*PLASTIC')==1
    assert ('NLGEOM' in deck) is nlgeom
    assert '*EL FILE\nS,E,PEEQ' in deck and '*NODE FILE,GLOBAL=YES\nU,RF' in deck
    assert ('*CONTACT PAIR' in deck) is not single
    assert 'STABILIZE' not in deck and 'LINE SEARCH' not in deck
    curve=deck.split('*PLASTIC,HARDENING=ISOTROPIC\n',1)[1].split('*SOLID SECTION',1)[0]
    assert float(curve.splitlines()[1].split(',')[1].strip()[:20])==pytest.approx(1.234567891234567e-5,rel=5e-13)
    path=snapshot_of(model,tmp_path/'input')
    _,actual,_,gates=contact_fem.validate_snapshot(path)
    assert actual==json.loads(json.dumps(model)) and gates['mesh_components']==(1 if single else 2)


@pytest.mark.parametrize('single',[False,True])
def test_201_points_block_both_model_and_re_pinned_deck(model,single,tmp_path):
    value=nonlinear_model(model,single=single)
    path=snapshot_of(value,tmp_path/'input')
    plastic=next(row for row in value['materials'] if row['law']==J2)['plasticity']
    plastic['yield_points']=[[250+i,i*.001] for i in range(201)]
    with pytest.raises(ValueError,match='200'): render(value)
    mesh=path.parent/'mesh.json'; mesh.write_text(json.dumps(value))
    manifest=json.loads(path.read_text()); pin=next(p for p in manifest['files'] if p['relative']=='mesh.json')
    pin.update(bytes=mesh.stat().st_size,sha256=hashlib.sha256(mesh.read_bytes()).hexdigest())
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='200'): contact_fem.validate_snapshot(path)


def test_pe_scalar_and_missing_is_nan_with_explicit_unavailable_metadata(model,tmp_path):
    value=nonlinear_model(model,single=True,nlgeom=False)
    text,_,materials=outputs(value,omit={(1,'PE')})
    file=tmp_path/'result.frd'; file.write_text(text)
    nodes,elements,_=validate_model(value)
    observed=read_frd(file,nodes,elements,contact_materials=materials,require_contact=False)
    assert 'PE' not in observed['frames'][0]['fields']
    assert observed['frames'][1]['fields']['PE'][next(iter(nodes))]==[.0123]
    metadata=write_post(tmp_path/'post',value,observed['frames'],[])
    assert metadata['field_meanings']['TOSTRAIN']['measure']=='infinitesimal'
    assert metadata['field_availability']['PE']['present_frames']==1
    tree=ET.parse(tmp_path/'post/frame0001.vtu')
    pe=tree.find('.//PointData/DataArray[@Name="PEEQ_1"]')
    assert pe is not None and pe.get('format') == 'binary'
    raw=base64.b64decode(pe.text); size,=struct.unpack('<I',raw[:4])
    assert size==len(nodes)*8 and all(math.isnan(v) for v in struct.unpack('<'+str(len(nodes))+'d',raw[4:]))
    valid=tree.find('.//PointData/DataArray[@Name="PE_valid"]')
    assert all(float(v)==0 for v in valid.text.split())
    assert any(a['name']=='PEEQ_1' and a['units']=='1' and a['measure']=='equivalent_plastic_strain' for a in metadata['arrays'])


@pytest.mark.parametrize('single',[False,True])
def test_run_failure_cancel_new_attempt_and_fresh_process_reopen_without_runtime(model,single,tmp_path,monkeypatch):
    value=nonlinear_model(model,single=single)
    snapshot=snapshot_of(value,tmp_path/'input')
    executable=tmp_path/'ccx'; executable.write_bytes(b'EXPLICIT_PROCESS_DOUBLE_NOT_A_SOLVER')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda name:str(executable))
    frd,dat,_=outputs(value); state={'fail':True,'calls':0,'cancel':False}
    def command(argv,cwd,label):
        state['calls']+=1
        (cwd/'contact.frd').write_text(frd); (cwd/'contact.dat').write_text(dat)
        (cwd/'contact.sta').write_text(status_text(failed=state['fail']))
        if state['cancel']: raise ExecutionCancelled('explicit owned process cancellation double')
        return NS(returncode=2 if state['fail'] else 0)
    monkeypatch.setattr(contact_fem,'run_owned_command',command)
    adapter=contact_fem.ContactFemCalculixAdapter()
    failed=adapter.run({'snapshot_path':str(snapshot)},output=tmp_path/'failed')
    assert failed['execution_status']=='FAILED',failed
    assert failed['partial_result']['frame_count']==1,failed['diagnostics']
    assert failed['increment_history']['rejected_attempt_count']==2
    assert len(failed['increment_history']['observed_cutbacks'])==1
    assert failed['increment_history']['residual']['status']=='unavailable'
    old={p.relative_to(tmp_path/'failed'):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in (tmp_path/'failed').rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='overwrite'): adapter.run({'snapshot_path':str(snapshot)},output=tmp_path/'failed')
    # Repair/load configuration produces a new snapshot and separate attempt.
    repaired=deepcopy(value); repaired['step']['increments']=200
    retry=snapshot_of(repaired,tmp_path/'retry-input')
    state['fail']=False
    success=normalize_evaluation(adapter.run({'snapshot_path':str(retry)},output=tmp_path/'success'))
    assert success['execution_status']=='SUCCEEDED',success['diagnostics']
    assert success['responses']['PEEQ']['component']=='SCALAR'
    assert success['responses']['PEEQ']['value'][0]==.0123
    assert success['responses']['total_strain']['metadata']['measure']=='green_lagrange'
    assert success['responses']['nodal_force']['metadata']['measure']=='nodal_force'
    state.update(fail=True,cancel=True)
    cancelled=adapter.run({'snapshot_path':str(snapshot)},output=tmp_path/'cancelled')
    assert cancelled['execution_status']=='CANCELLED' and cancelled['partial_result']['frame_count']==1
    # A new OS process rebuilds from source pins while the solver executable is absent.
    executable.unlink()
    process=subprocess.run([sys.executable,'-m','caelab.adapters.contact_fem','--rebuild-post-from',str(tmp_path/'success'),
        '--output',str(tmp_path/'reopened')],text=True,capture_output=True,timeout=20)
    assert process.returncode==0,process.stderr
    assert json.loads(process.stdout)['solver_execution']=='NOT_PERFORMED' and state['calls']==3
    assert all(hashlib.sha256((tmp_path/'failed'/p).read_bytes()).hexdigest()==digest for p,digest in old.items())
    receipt=json.loads((tmp_path/'reopened/post_regeneration.json').read_text())
    assert receipt['post_artifact']['native_metadata']['field_meanings']['PE']['quantity']=='equivalent_plastic_strain'
