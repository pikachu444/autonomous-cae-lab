"""Actual native-command -> Connection -> JobManager -> adapter -> Post service.

Only native document bytes and CalculiX's process/output are synthetic. No
monkeypatch of Workbench.run, submit_frozen, JobManager or the compiler is used.
"""
import json
from pathlib import Path
import time
from types import SimpleNamespace as NS
import pytest

from apps.desktop_pre.connection import Connection
from caelab.adapters import contact_fem
from caelab.contact_steps import compile_program
from caelab.dynamic_locations import KEY, load, select
from caelab.dynamic_restart import prepare
from caelab.dynamic_results import read_attempt
from caelab.workbench import Workbench
from test_dynamic_support import dynamic_model, outputs, snapshot, synthetic_rout


def completed_export(wb, auth, descriptor, command_id, operation, manifest):
    wb.document_command('Pdesign', operation, {}, session_id='Snative',
        expected_generation=3, command_id=command_id)
    dispatched = wb.native_commands.next('Hpre', session_id='Snative',
        host_token=auth['host_token'])['command']
    assert dispatched['command_id'] == command_id
    outcome = {'state':'SUCCEEDED', 'result':{'status':'COMPLETED',
        'result':{'snapshot_relative':manifest.relative_to(wb.desktop.root).as_posix(),
                  'label':'동해석 서비스 시험 (수치 검증 아님)'},
        'generation':3, 'view_generation':0}}
    wb.native_commands.event('Hpre', session_id='Snative', host_token=auth['host_token'],
        event='finished', command_id=command_id, outcome=outcome, documents=[descriptor])
    return wb.native_commands.status(command_id)


def host(wb):
    descriptor = {'id':'Pdesign','kind':'pre','generation':3,'view_generation':0,
        'title':'편집 가능한 동해석', 'capabilities':['pre.dynamic.freeze','pre.dynamic.restart','document.activate']}
    auth = wb.native_commands.register(host_id='Hpre',session_id='Snative', application='freecad',
        version='TEST_ONLY',execution_mode='headless',documents=[descriptor],registration_nonce='n'*32)
    return auth, descriptor


def wait(wb, identifier):
    deadline = time.monotonic()+10
    while time.monotonic()<deadline:
        state = wb.manager.status(identifier)
        if state['state'] in ('SUCCEEDED','FAILED','CANCELLED','INTERRUPTED'):
            return state
        time.sleep(.01)
    pytest.fail('The bounded synthetic native process did not terminate')


def install_process(monkeypatch, tmp_path):
    executable = tmp_path/'ccx'; executable.write_bytes(b'EXPLICIT_PROCESS_DOUBLE_NOT_CALCULIX')
    monkeypatch.setattr(contact_fem.shutil,'which',lambda _:str(executable))
    calls = []
    def process(args, cwd, label):
        model = json.loads((cwd.parent/'frozen_input/mesh.json').read_text(encoding='utf-8'))
        calls.append({'directory':str(cwd), 'restart':bool(model.get('restart'))})
        if model.get('restart'):
            assert (cwd/'contact.rin').read_bytes() == (cwd.parent/'frozen_input/contact.rin').read_bytes()
            assert (cwd/'contact.inp').read_text(encoding='utf-8').startswith('*RESTART,READ,STEP=1\n')
        for suffix,text in zip(('frd','dat','sta'),outputs(model)):
            (cwd/('contact.'+suffix)).write_text(text,encoding='utf-8')
        steps = [s['index'] for s in compile_program(
            model['analysis_steps'],model['conditions']) if s['index']>model.get('restart',{}).get('checkpoint',{}).get('step',0)]
        (cwd/'contact.rout').write_bytes(synthetic_rout(model,steps=steps))
        return NS(returncode=0)
    monkeypatch.setattr(contact_fem,'run_owned_command',process)
    return calls


def through_connection(wb, status, *, export_only=False):
    c = Connection.__new__(Connection)
    c.pending = {'command_id':status['command_id'], 'document_id':'Pdesign',
        'stage':'command', 'export_only':export_only}
    c.message = NS(setText=lambda text:None)
    owner = NS(document_id='Pdesign',export_root=wb.desktop.root)
    c.owners = {'Test':(owner,None,None)}
    captured = {'submissions':[], 'links':[], 'runner':[], 'exports':[]}
    def native_submit(identifier):
        value = wb.desktop.submit_frozen(identifier)
        captured['submissions'].append(value)
        return value
    c.client = NS(native_submit=native_submit)
    c.request = lambda key,action,callback:callback(action())
    c.submit_native = lambda op,args,owner=None:captured['links'].append((op,args))
    c.open_runner = captured['runner'].append
    c.show_export = lambda manifest:captured['exports'].append(str(manifest))
    c.command_status(status)
    assert c.pending is None
    return captured


def same_submission(left, right):
    assert left['input'] == right['input'] and left['origin'] == right['origin']
    for key in ('id','request_id','request_hash','arguments'):
        assert left['job'][key] == right['job'][key]


def test_dynamic_freeze_and_read_use_same_queue_service_and_exact_lineage(monkeypatch,tmp_path):
    calls = install_process(monkeypatch,tmp_path)
    wb = Workbench(tmp_path/'workspace')
    try:
        auth, descriptor = host(wb)
        target = wb.desktop.root/'Pdesign'; target.mkdir()
        model = dynamic_model(mixed=True)
        manifest = snapshot(model,target/'Finitial')
        command = completed_export(wb,auth,descriptor,'Cinitial','pre.dynamic.freeze',manifest)
        # Input-only completion must not submit or silently calculate.
        exported = through_connection(wb,command,export_only=True)
        assert not exported['submissions'] and exported['exports'] == [str(manifest)] and not calls
        sent = through_connection(wb,command)
        first = sent['submissions'][0]
        assert sent['links'] == [('pre.links.record',{'job_id':first['job']['id']})]
        assert sent['runner'] == [first['job']['id']]
        duplicate = wb.desktop.submit_frozen('Cinitial')
        same_submission(duplicate,first)
        state = wait(wb,first['job']['id'])
        assert state['state'] == 'SUCCEEDED', state
        saved = wb.result(first['job']['id'])
        nav = wb.desktop.navigation(first['job']['id'])
        assert nav['frozen_origin'] == first['origin']
        assert nav['retained_design_input_id'] == first['input']['id']
        assert nav['origin_document']['id'] == 'Pdesign'
        assert {p['category'] for p in nav['post_inputs']} == {'dynamic','static-preload'}
        assert nav['post_input']['category'] == 'dynamic'
        for post in nav['post_inputs']:
            native = wb.native_input(post['id'])
            exact = load(native['path'],native['native_metadata'])
            assert exact['origin']['input_origin'] == first['origin']
            assert exact['origin']['job_id'] == first['job']['id']
            assert native['registration_origin'][KEY] == exact['origin']
            assert exact['origin']['snapshot_id'] == saved['snapshot_id']
        parent = wb.root/'native'/first['job']['id']
        parent_bytes = (parent/'solver/contact.rout').read_bytes()
        restart_manifest = prepare(parent,1,model['analysis_steps']['steps'][1:],target)
        command = completed_export(wb,auth,descriptor,'Crestart','pre.dynamic.restart',restart_manifest)
        resumed = through_connection(wb,command)['submissions'][0]
        same_submission(wb.desktop.submit_frozen('Crestart'),resumed)
        assert resumed['job']['id'] != first['job']['id']
        assert resumed['input']['id'] != first['input']['id']
        state = wait(wb,resumed['job']['id'])
        assert state['state'] == 'SUCCEEDED', state
        child = wb.root/'native'/resumed['job']['id']
        assert (child/'solver/contact.rin').read_bytes() == parent_bytes
        assert (parent/'solver/contact.rout').read_bytes() == parent_bytes
        data = read_attempt(child)
        assert data['state_source']['kind'] == 'native_restart_read'
        assert data['input_origin']['command_id'] == 'Crestart'
        child_nav = wb.desktop.navigation(resumed['job']['id'])
        assert [p['category'] for p in child_nav['post_inputs']] == ['dynamic']
        # Same physical timestamp in parent and child is not a global time key.
        parent_source = wb.native_input(nav['post_input']['id'])
        child_source = wb.native_input(child_nav['post_input']['id'])
        a = select(parent_source['path'],parent_source['native_metadata'],time=1.)
        b = select(child_source['path'],child_source['native_metadata'],time=1.)
        assert a['selected_location']['physical_time_s'] == b['selected_location']['physical_time_s']
        assert a['selected_location']['state_origin'] == 'PREVIOUS_NATIVE_STEP'
        assert b['selected_location']['state_origin'] == 'RESTART_READ'
        assert a['origin']['job_id'] != b['origin']['job_id']
        assert a['origin']['snapshot_id'] != b['origin']['snapshot_id']
        assert [c['restart'] for c in calls] == [False,True]
        # A cold service reuses the saved command/input/job; it does not solve.
        assert wb.shutdown()['joined']
        wb = Workbench(tmp_path/'workspace')
        retry = wb.desktop.submit_frozen('Crestart')
        same_submission(retry,resumed)
        assert len(calls)==2
        assert wb.desktop.navigation(resumed['job']['id'])['post_input']==child_nav['post_input']
    finally:
        assert wb.shutdown()['joined']


def test_dynamic_command_wrong_owner_and_unfinished_export_do_not_submit(tmp_path):
    wb = Workbench(tmp_path/'workspace')
    try:
        auth, descriptor = host(wb)
        wb.document_command('Pdesign','pre.dynamic.freeze',{},session_id='Snative',expected_generation=3,command_id='Cunfinished')
        with pytest.raises(ValueError,match='completed'):
            wb.desktop.submit_frozen('Cunfinished')
        # Finish the queued request to avoid an unrelated per-owner queue conflict.
        wb.native_commands.next('Hpre',session_id='Snative',host_token=auth['host_token'])
        other = wb.desktop.root/'Pother';other.mkdir()
        manifest = snapshot(dynamic_model(),other/'Fwrong')
        outcome={'state':'SUCCEEDED','result':{'status':'COMPLETED','generation':3,'view_generation':0,
            'result':{'snapshot_relative':manifest.relative_to(wb.desktop.root).as_posix()}}}
        wb.native_commands.event('Hpre',session_id='Snative',host_token=auth['host_token'],event='finished',
            command_id='Cunfinished',outcome=outcome,documents=[descriptor])
        with pytest.raises(ValueError,match='exact native document'):
            wb.desktop.submit_frozen('Cunfinished')
        assert not list((wb.root/'jobs').glob('J*.json'))
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('case',['initial-velocity','preload-release','preload-hold'])
def test_generator_draft_reaches_existing_service_not_just_input_creation(case,monkeypatch,tmp_path):
    from test_dynamic_correction_steps import example
    from caelab.dynamic_model import attach
    calls=install_process(monkeypatch,tmp_path)
    model,_,draft=example(case);model=attach(model,draft)
    wb=Workbench(tmp_path/'workspace')
    try:
        auth,descriptor=host(wb);target=wb.desktop.root/'Pdesign';target.mkdir()
        manifest=snapshot(model,target/'Fexample')
        command=completed_export(wb,auth,descriptor,'Cexample','pre.dynamic.freeze',manifest)
        first=through_connection(wb,command)['submissions'][0]
        state=wait(wb,first['job']['id'])
        assert state['state']=='SUCCEEDED',state
        nav=wb.desktop.navigation(first['job']['id'])
        assert nav['post_input']['category']=='dynamic' and len(calls)==1
        native=wb.native_input(nav['post_input']['id'])
        exact=load(native['path'],native['native_metadata'])
        # Stored native rounded values, not the nominal .002 endpoint.
        chosen=select(native['path'],native['native_metadata'],time=exact['frames'][-1]['timestep'])
        assert chosen['selected_location']['id']=='Dynamic2'
        assert chosen['selected_native']['step']==(2 if case=='initial-velocity' else 3)
        assert chosen['complete_analysis'] is True and chosen['qualification']=='UNKNOWN'
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('operation',['pre.dynamic.freeze','pre.dynamic.restart'])
def test_dynamic_command_cannot_be_a_different_snapshot_procedure(operation,tmp_path):
    from test_dynamic_support import base_model
    wb=Workbench(tmp_path/'workspace')
    try:
        auth,descriptor=host(wb);target=wb.desktop.root/'Pdesign';target.mkdir()
        # A contact kind alone is insufficient: freeze requires dynamic, READ
        # requires real restart members; neither may silently execute statics.
        model=base_model() if operation.endswith('freeze') else dynamic_model()
        manifest=snapshot(model,target/'Fwrongprocedure')
        completed_export(wb,auth,descriptor,'Cwrong',operation,manifest)
        with pytest.raises(ValueError,match='new-run/READ'):
            wb.desktop.submit_frozen('Cwrong')
        assert not list((wb.root/'jobs').glob('J*.json'))
    finally:
        assert wb.shutdown()['joined']


def test_post_publication_failure_keeps_native_files_and_does_not_resubmit(monkeypatch,tmp_path):
    calls=install_process(monkeypatch,tmp_path)
    wb=Workbench(tmp_path/'workspace')
    try:
        auth,descriptor=host(wb);target=wb.desktop.root/'Pdesign';target.mkdir()
        manifest=snapshot(dynamic_model(mixed=True),target/'Finitial')
        command=completed_export(wb,auth,descriptor,'Cinitial','pre.dynamic.freeze',manifest)
        import caelab.native_inputs as registrar
        original=registrar.register_native_input
        count=[]
        def fail_second(*args,**kwargs):
            count.append(1)
            if len(count)==2:raise OSError('EXPLICIT publication failure, no second solve')
            return original(*args,**kwargs)
        monkeypatch.setattr(registrar,'register_native_input',fail_second)
        first=through_connection(wb,command)['submissions'][0]
        state=wait(wb,first['job']['id'])
        assert state['state']=='FAILED'
        result=wb.result(first['job']['id'])
        assert result['native_execution_status']=='SUCCEEDED'
        assert result['post_registration']['status']=='FAILED'
        assert not result.get('post_input') and not result.get('post_inputs')
        same_submission(wb.desktop.submit_frozen('Cinitial'),first)
        assert len(calls)==1
        assert (wb.root/'native'/first['job']['id']/'solver/contact.rout').is_file()
        assert (wb.root/'native'/first['job']['id']/'dynamic_result.json').is_file()
    finally:
        assert wb.shutdown()['joined']


@pytest.mark.parametrize('damage',['rin_bytes','missing_member','unknown_member'])
def test_restart_registration_reuses_strict_read_member_gate(monkeypatch,tmp_path,damage):
    import hashlib
    from caelab.native_inputs import register_frozen_input
    from caelab.storage import save_json
    from test_dynamic_restart import split_double
    _,_,manifest=split_double(monkeypatch,tmp_path)
    data=json.loads(manifest.read_text(encoding='utf-8'))
    if damage=='rin_bytes':
        rin=manifest.parent/'contact.rin';rin.write_bytes(rin.read_bytes()+b'x')
        # Rehash the manifest: native READ identity must still reject it.
        for row in data['files']:
            if row['relative']=='contact.rin':
                row.update(bytes=rin.stat().st_size,sha256=hashlib.sha256(rin.read_bytes()).hexdigest())
    elif damage=='missing_member':data['files']=[r for r in data['files'] if r['relative']!='contact.rin']
    else:
        extra=manifest.parent/'unapproved.txt';extra.write_bytes(b'not an admitted restart member')
        data['files'].append({'relative':extra.name,'bytes':extra.stat().st_size,'sha256':hashlib.sha256(extra.read_bytes()).hexdigest()})
    save_json(manifest,data)
    registry=tmp_path/'registry'
    with pytest.raises(ValueError):
        register_frozen_input(registry,manifest.parent.parent,manifest,'Dinvalid',root_id='test',
            relative=manifest.parent.name+'/snapshot.json',limit=32*1024**2)
    assert not (registry/'inputs/Dinvalid/input.json').exists()
