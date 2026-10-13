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
    _,released=render(s);assert released['nodes'][1][2]==20.
    assert released['velocities_mm_s'][1][2]==-100.
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
