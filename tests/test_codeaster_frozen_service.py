"""Real owner/job/input/Post integration with explicitly doubled native execution."""
import json
import time

import pytest

from test_pre_frozen_analysis import native
from test_codeaster_frozen import raw_result
from apps.desktop_pre.freeze_analysis import _freeze_legacy_analysis as freeze_analysis
from caelab.adapters import codeaster_frozen as adapter
from caelab.backends import get_backend
from caelab.workbench import Workbench


def wait(wb,identifier):
    deadline = time.monotonic()+10
    while time.monotonic()<deadline:
        status = wb.manager.status(identifier)
        if status['state'] in {'SUCCEEDED','FAILED','CANCELLED'}:return status
        time.sleep(.01)
    raise AssertionError('Job did not finish')


def completed_native(output,budgets):
    path = output/'solver'
    mesh = json.loads((path/'mesh.json').read_text())
    config = json.loads((path/'input.json').read_text())
    raw = raw_result(mesh)
    raw.update(input_sha256=adapter._sha(path/'input.json'),mail_sha256=config['mail_sha256'])
    adapter.save_json(path/'worker_result.json',raw)
    adapter.save_json(path/'native_mesh_checks.json',raw['native_mesh_checks'])
    (path/'results.med').write_bytes(b'Explicit native execution double')
    return {'test_double':True}


def exported(wb,native):
    descriptor = {'id':'Pdesign','kind':'pre','generation':3,'view_generation':0,
        'title':'Curved clamp input double','capabilities':['pre.freeze','document.activate']}
    auth = wb.native_commands.register(host_id='Hpre',session_id='Snative',application='freecad',
        version='TEST_ONLY',execution_mode='headless',documents=[descriptor],registration_nonce='n'*32)
    wb.document_command('Pdesign','pre.freeze',{},session_id='Snative',expected_generation=3,command_id='Cfreeze')
    wb.native_commands.next('Hpre',session_id='Snative',host_token=auth['host_token'])
    manifest = freeze_analysis(native.analysis,native.solver,wb.desktop.root/'Pdesign')
    result = {'status':'COMPLETED','result':{'snapshot_relative':manifest.relative_to(wb.desktop.root).as_posix(),
        'label':'Input double; no native CAD run'},'generation':3,'view_generation':0}
    wb.native_commands.event('Hpre',session_id='Snative',host_token=auth['host_token'],event='finished',
        command_id='Cfreeze',outcome={'state':'SUCCEEDED','result':result},documents=[descriptor])


@pytest.mark.parametrize('publication_failure',[None,'first','second'])
def test_same_frozen_model_solver_choice_retention_and_post_reopen(native,tmp_path,monkeypatch,publication_failure):
    assert isinstance(get_backend('structure.codeaster.frozen'),adapter.FrozenFemCodeAsterAdapter)
    monkeypatch.setattr(adapter,'execute_native',completed_native)
    wb = Workbench(tmp_path/'workspace')
    if publication_failure:
        from caelab.workbench import register_native_input
        calls = []
        def refuse(*args,**kwargs):
            calls.append(1)
            if len(calls)==(2 if publication_failure=='second' else 1):
                raise OSError('Explicit Post publication failure')
            return register_native_input(*args,**kwargs)
        monkeypatch.setattr('caelab.workbench.register_native_input',refuse)
    try:
        exported(wb,native)
        submitted = wb.desktop.submit_frozen('Cfreeze',solver='codeaster')
        retry = wb.desktop.submit_frozen('Cfreeze',solver='codeaster')
        assert retry['job']['id']==submitted['job']['id']
        assert retry['input']['id']==submitted['input']['id']
        status = wait(wb,submitted['job']['id'])
        assert status['state']==('FAILED' if publication_failure else 'SUCCEEDED'),status
        result = wb.result(submitted['job']['id'])
        assert result['origin_input']['kind']=='frozen_fem'
        assert result['decision']=='NOT_RELEASED'
        navigation = wb.desktop.navigation(submitted['job']['id'])
        assert navigation['retained_design_input_id']==submitted['input']['id']
        assert navigation['origin_document']['id']=='Pdesign'
        if publication_failure:
            assert result['native_execution_status']=='SUCCEEDED'
            assert navigation['post_input'] is None
            assert result['post_registration']['status']=='FAILED'
            assert len(navigation['post_inputs'])==(1 if publication_failure=='second' else 0)
            assert (wb.root/'native'/submitted['job']['id']/'solver/results.med').is_file()
            assert (wb.root/'native'/submitted['job']['id']/'post/stress_points.vtu').is_file()
        else:
            assert len(navigation['post_inputs'])==2
            for entry in navigation['post_inputs']:
                metadata = wb.native_input(entry['id'])['native_metadata']
                assert metadata['coordinate_units']=='mm'
                assert metadata['static']['load_parameter']==0.
            assert any(r.get('quantity')=='native_integration_point_stress'
                for r in wb.native_input(navigation['post_inputs'][1]['id'])['native_metadata']['arrays'])
            # Reading the retained result a second time cannot launch a native job.
            count = len(wb.manager.list())
            assert wb.result(submitted['job']['id'])==result
            assert len(wb.manager.list())==count
        with pytest.raises(ValueError,match='Choose'):wb.desktop.submit_frozen('Cfreeze',solver='unknown')
    finally:
        assert wb.shutdown()['joined']
