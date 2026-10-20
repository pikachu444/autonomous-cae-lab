"""Post macro navigation without starting ParaView/FreeCAD or another process."""
from types import SimpleNamespace
import pytest
from apps.desktop_post.navigation import return_to_design


def test_saved_post_origin_uses_primary_python_and_keeps_native_environment_out(tmp_path, monkeypatch):
    python = tmp_path / 'python.exe'
    python.write_text('TEST_ONLY executable reference')
    document = {'origin_job_id':'Jrecorded','desktop_python':str(python),
                'repo_root':str(tmp_path),'service_url':'http://127.0.0.1:8766'}
    called=[]
    monkeypatch.setattr('apps.desktop_post.navigation.subprocess.Popen',
                        lambda command,**kwargs:called.append((command,kwargs)) or SimpleNamespace(pid=13))
    result=return_to_design(document,environment={'QT_PLUGIN_PATH':'native-only','PYTHONHOME':'native-python','PATH':'retained-path'})
    assert result['status']=='NAVIGATION_REQUESTED' and result['job_id']=='Jrecorded'
    command,options=called[0]
    assert command==[str(python),'-m','apps.research.desktop','--service','http://127.0.0.1:8766','origin','--job-id','Jrecorded']
    assert options['env']=={'PATH':'retained-path'}
    assert document['origin_job_id']=='Jrecorded'


def test_independent_result_does_not_invent_a_design_origin(monkeypatch):
    monkeypatch.setattr('apps.desktop_post.navigation.subprocess.Popen',lambda *a,**k:pytest.fail('No process should start'))
    with pytest.raises(ValueError,match='no recorded design'):
        return_to_design({},environment={})


def test_independent_result_returns_to_its_connected_native_model(tmp_path, monkeypatch):
    import json
    python = tmp_path / 'python.exe'
    python.touch()
    model = tmp_path / 'saved.FCStd'
    model.touch()
    state = {'model': {'original_path': str(model), 'saved_path': str(model)}}
    document = {'discussion_id': 'Xoriginal', 'workbench': state, 'desktop_python': str(python),
                'repo_root': str(tmp_path), 'service_url': 'http://127.0.0.1:8766'}
    called = []
    monkeypatch.setattr('apps.desktop_post.navigation.subprocess.Popen',
        lambda command, **kwargs: called.append(command) or SimpleNamespace(pid=13))
    result = return_to_design(document, environment={})
    command = called[0]
    assert result['job_id'] is None
    assert command[command.index('--source') + 1] == str(model)
    assert command[command.index('--discussion-id') + 1] == 'Xoriginal'
    assert json.loads(command[command.index('--workbench-context') + 1]) == state
