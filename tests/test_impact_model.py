"""Changed-path checks: real converter, retained owner, exact source semantics."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import pytest
from caelab.impact_model import parse_inp,render,validate_settings,engine_deck,BACKEND
from caelab.adapters.impact import ImpactAdapter,converted_mesh
from examples.impact.user_model import settings
from caelab.storage import canonical_hash
from test_connected_evaluation_study import service,change


def test_actual_pinned_conversion_and_spin_keep_original_mesh(tmp_path):
    original=settings(); source=canonical_hash(original)
    original['motions'][0]['omega_rad_s']=[0.,0.,2.]
    text,projection=render(original)
    assert projection['velocities_mm_s'][2]==[0.,20.,-100.]
    assert projection['velocities_mm_s'][3]==[-20.,0.,-100.]
    assert canonical_hash(settings())==source
    path=tmp_path/'impact.inp';path.write_text(text,encoding='ascii',newline='\n')
    import caelab.adapters.inp2rad_worker as worker
    process=subprocess.run([sys.executable,worker.__file__,str(path)],capture_output=True,text=True,timeout=30)
    assert process.returncode==0,process.stdout+'\n'+process.stderr
    assert 'Press Enter' not in process.stdout
    admission=converted_mesh(tmp_path/'impact_0000.rad',parse_inp(original['source']['text']),projection['nodes'])
    assert admission['node_count']==4 and admission['element_count']==1
    # Converter defaults retained separately; effective controls are explicit.
    native=engine_deck(original)
    assert '/DT/NODA/CST' not in native and '/TFILE/4' in native
    assert str(original['time']['end_s']) in native


def test_height_modes_and_converter_omissions_blocked():
    s=settings();s['gravity_mm_s2']=[0.,0.,-10000.]
    m=s['motions'][0];m.update(mode='release_height',height_mm=20.)
    with pytest.raises(ValueError,match='병진 속도'):render(s)
    m['velocity_mm_s']=[0.,0.,0.]
    _,released=render(s);assert released['nodes'][1][2]==20.
    assert released['velocities_mm_s'][1][2]==0.
    m.update(mode='impact_height',velocity_mm_s=[0.,0.,0.])
    _,impact=render(s)
    assert impact['nodes'][1][2]==0 and impact['velocities_mm_s'][1][2]==pytest.approx(-632.4555320336759)
    bad=deepcopy(s);bad['source']['text']+='*INCLUDE,INPUT=outside.inp\n'
    with pytest.raises(ValueError,match='INCLUDE'):validate_settings(bad)
    bad=deepcopy(s);bad['time']['target_step_s']=1e-7
    with pytest.raises(ValueError):validate_settings(bad)
    bad=deepcopy(s);bad['motions'].append(deepcopy(m))
    with pytest.raises(ValueError):validate_settings(bad)


def test_real_owner_invalid_save_cold_reopen_repair_no_solver(service):
    wb,client=service
    s=settings();s['motions'][0]['velocity_mm_s'][2]='1e'
    doc=client.document_open(kind='simulation',title='내 충격 입력',draft={'backend':BACKEND,'settings':s})
    saved=change(client,doc,'document.save')['document']
    assert saved['diagnostics']
    with pytest.raises(Exception):change(client,saved,'simulation.evaluate')
    from caelab.workbench import Workbench
    workspace=wb.workspace
    assert wb.shutdown()['joined']
    fresh=Workbench(workspace)
    try:
        reopened=fresh.document_open(kind='simulation',document_id=saved['id'])
        assert reopened['draft']['settings']==s and len(fresh.manager.list())==0
    finally:fresh.shutdown()


def test_native_numerical_binding_keeps_mesh_source():
    from caelab.model_parameters import bind
    s=settings();adapter=ImpactAdapter()
    bound=bind(adapter,s,{'motion_0_velocity_mm_s_2':-125.})
    assert bound['motions'][0]['velocity_mm_s'][2]==-125.
    assert bound['source']==s['source'] and s['motions'][0]['velocity_mm_s'][2]==-100.


@pytest.mark.skipif(os.environ.get('CAELAB_RUN_USER_IMPACT')!='1',reason='explicit installed native OpenCourant run')
def test_installed_user_fe_starter_engine_post_and_saved_result(tmp_path):
    from caelab.evaluation import run,read_result
    from caelab.research_execution import publish_fields
    from caelab.workbench import Workbench
    s=settings()
    result=run(BACKEND,s,output=tmp_path/'attempt'/'calculation')
    assert result['execution_status']=='SUCCEEDED',result
    assert result['responses']['global_2']['unit']=='J'
    assert result['post_artifacts'] and result['diagnostics']['frame_count']>0
    saved=read_result(tmp_path/'attempt'/'calculation',verify='all')
    assert saved['settings']==s
    wb=Workbench(tmp_path/'store')
    try:
        publish_fields(wb,result,tmp_path/'attempt')
        assert result['post_input']['format']=='pvd'
    finally:wb.shutdown()


def test_starter_actual_declared_units_and_scale_both_required(tmp_path):
    from caelab.adapters.impact import starter_admission
    model=parse_inp(settings()['source']['text'])
    text=('NORMAL TERMINATION\nNO SYNTAX ERROR DETECTED\n0 ERROR(S)\n0 WARNING(S)\nNUMNOD: 4\n'
          'WORK UNIT SYSTEM . . . ( Mg , mm , s   ) 1.0000000000000E+03 1.0000000000000E-03 1.0000000000000E+00\n'
          'INPUT UNIT SYSTEM . . ( Mg , mm , s   ) 1.0000000000000E+03 1.0000000000000E-03 1.0000000000000E+00\n')
    path=tmp_path/'starter.out';path.write_text(text,encoding='ascii')
    assert starter_admission(path,model)['status']=='PASS'
    for changed in (text.replace('Mg','kg'),text.replace('1.0000000000000E-03','1.0000000000000E+00')):
        path.write_text(changed,encoding='ascii')
        with pytest.raises(ValueError,match='units'):starter_admission(path,model)


def test_two_sections_oblique_gravity_and_physical_postflight(tmp_path):
    from caelab.adapters.impact_admission import global_gravity,normalize_surfaces,validate_physics,cards
    import caelab.adapters.inp2rad_worker as worker
    s=settings()
    # Two nonintersecting tetrahedra with different material properties.
    s['source']['text']+='\n*NODE\n5,20,0,0\n6,30,0,0\n7,20,10,0\n8,20,0,10\n'
    s['source']['text']+='*ELEMENT,TYPE=C3D4,ELSET=SECOND\n2,5,6,7,8\n*MATERIAL,NAME=SECOND_MAT\n*DENSITY\n2.7e-9\n*ELASTIC\n70000,.3\n*SOLID SECTION,ELSET=SECOND,MATERIAL=SECOND_MAT\n'
    s['gravity_mm_s2']=[1000.,2000.,-3000.]
    text,initial=render(s)
    assert text.count(',GRAV,')==1
    path=tmp_path/'impact.inp';path.write_text(text,encoding='ascii',newline='\n')
    proc=subprocess.run([sys.executable,worker.__file__,str(path)],capture_output=True,text=True,timeout=30)
    assert proc.returncode==0,proc.stdout+proc.stderr
    original=(tmp_path/'impact_0000.rad').read_text(encoding='ascii')
    fixed,receipt=global_gravity(original,s['gravity_mm_s2'])
    fixed,_=normalize_surfaces(fixed,parse_inp(s['source']['text']))
    admission=validate_physics(fixed,parse_inp(s['source']['text']),initial,s)
    assert admission['global_gravity_mm_s2']==s['gravity_mm_s2']
    assert len(admission['material_by_element'])==2
    assert len([k for k in cards(fixed) if k.startswith('/GRAV/')])==3
    # Changing only physics while keeping valid geometry must be rejected.
    blocks=cards(fixed)
    key=next(k for k,v in blocks.items() if k.startswith('/MAT/ELAST/') and v[0].strip()=='SECOND_MAT')
    blocks[key][2]=f'{71000:20.8e}'+blocks[key][2][20:]
    corrupt='\n'.join(line for key,rows in blocks.items() for line in [key,*rows])
    with pytest.raises(ValueError,match='physical value'):validate_physics(corrupt,parse_inp(s['source']['text']),initial,s)


def test_repeated_lowercase_sets_preserve_full_fixed_union_in_native_cards(tmp_path):
    from caelab.adapters.impact_admission import global_gravity,normalize_surfaces,validate_physics
    import caelab.adapters.inp2rad_worker as worker
    s=settings()
    s['source']['text']+='\n*NSET,NSET=fixed\n1\n*NSET,NSET=fixed\n2\n*BOUNDARY\nfixed,1,3\n'
    text,initial=render(s)
    assert text.count('*NSET,NSET=FIXED')==1 and 'fixed' not in text
    path=tmp_path/'impact.inp';path.write_text(text,encoding='ascii',newline='\n')
    proc=subprocess.run([sys.executable,worker.__file__,str(path)],capture_output=True,text=True,timeout=30)
    assert proc.returncode==0,proc.stdout+proc.stderr
    native,_=global_gravity((tmp_path/'impact_0000.rad').read_text(encoding='ascii'),s['gravity_mm_s2'])
    native,_=normalize_surfaces(native,parse_inp(s['source']['text']))
    assert validate_physics(native,parse_inp(s['source']['text']),initial,s)['fixed_dof_count']==6


def test_contact_converter_admission_preserves_starter_header_and_precision(tmp_path):
    from caelab.adapters.impact_admission import global_gravity,normalize_surfaces,normalize_contact_friction,validate_physics
    import caelab.adapters.inp2rad_worker as worker
    s=settings()
    s['source']['text']+='\n*SURFACE,NAME=SECOND_FACE,TYPE=ELEMENT\n1,S2\n'
    model=parse_inp(s['source']['text'])
    first=next(name for name in model['surfaces'] if name!='SECOND_FACE')
    s['contacts']=[{'a':first,'b':'SECOND_FACE','law':'TYPE24','friction':.1234567890123}]
    effective,initial=render(s)
    path=tmp_path/'impact.inp';path.write_text(effective,encoding='ascii',newline='\n')
    process=subprocess.run([sys.executable,worker.__file__,str(path)],capture_output=True,text=True,timeout=30)
    assert process.returncode==0,process.stdout+process.stderr
    raw=(tmp_path/'impact_0000.rad').read_text(encoding='ascii')
    assert raw.startswith('#RADIOSS STARTER')
    fixed,_=global_gravity(raw,s['gravity_mm_s2'])
    fixed=normalize_contact_friction(fixed,s)
    fixed,_=normalize_surfaces(fixed,model)
    assert fixed.startswith('#RADIOSS STARTER')
    assert validate_physics(fixed,model,initial,s)['contact_count']==1
    # A no-gravity/no-contact edit preserves every non-GRAV source card.
    assert '/BEGIN' in fixed and '/END' in fixed


def test_surface_fixed_slots_preserve_orientation_and_reject_blank_or_shifted_nodes(tmp_path):
    from caelab.adapters.impact_admission import normalize_surfaces,_segment_nodes,global_gravity,validate_physics,cards
    import caelab.adapters.inp2rad_worker as worker
    s=settings();model=parse_inp(s['source']['text']);text,initial=render(s)
    path=tmp_path/'impact.inp';path.write_text(text,encoding='ascii',newline='\n')
    process=subprocess.run([sys.executable,worker.__file__,str(path)],capture_output=True,text=True,timeout=30)
    assert process.returncode==0,process.stdout+process.stderr
    raw=(tmp_path/'impact_0000.rad').read_text(encoding='ascii')
    fixed,receipt=normalize_surfaces(raw,model)
    assert fixed.startswith('#RADIOSS STARTER') and receipt
    before,after=cards(raw),cards(fixed)
    assert {k:v for k,v in before.items() if not k.startswith('/SURF/SEG/')}=={
        k:v for k,v in after.items() if not k.startswith('/SURF/SEG/')}
    row=next(rows[1] for key,rows in after.items() if key.startswith('/SURF/SEG/'))
    ordinal,nodes=_segment_nodes(row)
    assert ordinal==1 and nodes==(1,3,2)
    assert row==f'{1:10d}{1:10d}{3:10d}{2:10d}{2:10d}'
    effective,_=global_gravity(fixed,s['gravity_mm_s2'])
    assert validate_physics(effective,model,initial,s)['fixed_dof_count']==0
    for malformed in (' '*10+row[10:],row[:10]+' '*10+row[20:],row[10:],row+'         4',
                      f'{1:10d}{1:10d}{3:10d}{2:10d}{1:10d}'):
        with pytest.raises(ValueError,match='[Ss]urface'):
            validate_physics(effective.replace(row,malformed),model,initial,s)
    # A semantic corner change is rejected before reformatting, not repaired.
    original=next(rows[1] for key,rows in before.items() if key.startswith('/SURF/SEG/'))
    with pytest.raises(ValueError,match='surface'):
        normalize_surfaces(raw.replace(original,f'{"":10}{1:10d}{2:10d}{3:10d}'),model)
