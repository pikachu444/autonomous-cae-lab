"""Execute existing desktop._post with Popen replaced; no process is started."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.research import desktop
from apps.research.report_image_origin import prepare_native_environment
from apps.desktop_post.report_image_origin_native import startup_request, select_restored_source
from report_image_fixture import fixture


@pytest.fixture
def launch(tmp_path, monkeypatch):
    f = fixture(tmp_path/'saved-project'); root = Path(__file__).parents[1]
    folder = tmp_path/'existing-launcher-folder'; folder.mkdir()
    context = {'repo_root': str(root), 'python': '/SCRIPTED/python', 'paraview_executable': '/SCRIPTED/paraview'}
    client = SimpleNamespace(url='http://127.0.0.1:18766', desktop_context=lambda: context)
    args = desktop._arguments(['post', '--project', str(f['manifest'])])
    calls = []
    monkeypatch.setattr(desktop, '_executable', lambda *args, **kwargs: Path('/SCRIPTED/paraview'))
    monkeypatch.setattr(desktop, '_folder', lambda *args: folder)
    def spawn(argv, **kwargs):
        calls.append((deepcopy(argv), deepcopy(kwargs))); return SimpleNamespace(pid=445566)
    monkeypatch.setattr(desktop.subprocess, 'Popen', spawn)
    monkeypatch.setattr(desktop.subprocess, 'run', lambda *args, **kwargs: pytest.fail('No reader preparation/solver process for a saved project'))
    return SimpleNamespace(f=f, client=client, args=args, folder=folder, calls=calls)


def test_existing_post_project_launcher_receives_verified_pin_environment(launch):
    x = launch; origin = x.f['snapshot']['origin']; progress = {'phase': 'PREPARING'}
    before = {key: x.f[key].read_bytes() for key in ('manifest', 'state', 'result', 'source')}
    result = desktop._post(x.client, x.args, _report_origin=origin, _report_launch=progress)
    assert result['status'] == 'LAUNCHED' and progress == {'phase': 'CREATED', 'pid': 445566}
    assert len(x.calls) == 1
    args, kwargs = x.calls[0]
    assert '--disable-registry' in args
    script = next(arg.removeprefix('--script=') for arg in args if arg.startswith('--script='))
    assert Path(script).resolve() == (Path(__file__).parents[1] / 'apps/desktop_post/startup.py').resolve()
    assert 'shell' not in kwargs
    env = kwargs['env']; path = Path(env['CAE_POST_REPORT_ORIGIN'])
    assert path.parent == x.folder and json.loads(path.read_text()) == origin
    assert env['CAE_POST_PROJECT'] == str(x.f['manifest']) and 'CAE_POST_MEASUREMENT' not in env
    assert startup_request(path, x.f['manifest']) == origin
    assert before == {key: x.f[key].read_bytes() for key in before}


def test_ordinary_launch_clears_inherited_report_and_measurement_requests(launch, monkeypatch):
    x = launch; monkeypatch.setenv('CAE_POST_REPORT_ORIGIN', 'do-not-inherit.json')
    monkeypatch.setenv('CAE_POST_MEASUREMENT', 'also-do-not-inherit.json')
    desktop._post(x.client, x.args)
    assert 'CAE_POST_REPORT_ORIGIN' not in x.calls[0][1]['env']
    assert 'CAE_POST_MEASUREMENT' not in x.calls[0][1]['env']
    assert not (x.folder/'report-origin.json').exists()


def test_late_source_change_before_popen_is_rejected(launch, monkeypatch):
    from apps.research import report_image_origin
    x = launch
    def prepare(*args):
        prepare_native_environment(*args)
        x.f['source'].write_text('changed after first check')
    monkeypatch.setattr(report_image_origin, 'prepare_native_environment', prepare)
    progress = {'phase': 'PREPARING'}
    with pytest.raises(ValueError): desktop._post(x.client, x.args, _report_origin=x.f['snapshot']['origin'], _report_launch=progress)
    assert not x.calls and progress['phase'] == 'PREPARING'


@pytest.mark.parametrize('interrupt,phase', [(False, 'NOT_CREATED'), (True, 'SPAWNING')])
def test_real_popen_boundary_marks_only_confirmed_failure_as_retryable(launch, monkeypatch, interrupt, phase):
    x = launch; progress = {'phase': 'PREPARING'}
    def failed(*args, **kwargs):
        if interrupt: raise KeyboardInterrupt('scripted ambiguous interruption')
        raise OSError('scripted process creation failure')
    monkeypatch.setattr(desktop.subprocess, 'Popen', failed)
    with pytest.raises((OSError, KeyboardInterrupt)):
        desktop._post(x.client, x.args, _report_origin=x.f['snapshot']['origin'], _report_launch=progress)
    assert progress['phase'] == phase


@pytest.mark.parametrize('fault', ['wrongProject', 'sourceMissing', 'workspaceHash'])
def test_startup_rechecks_before_restore_not_just_parent_validation(launch, fault):
    x = launch; origin = x.f['snapshot']['origin']; path = x.folder/'report-origin.json'
    path.write_text(json.dumps(origin))
    project = x.f['manifest']
    if fault == 'wrongProject': project = x.folder/'other-project.json'
    elif fault == 'sourceMissing': x.f['source'].unlink()
    else: x.f['state'].write_text('changed after parent launch')
    with pytest.raises((OSError, ValueError)): startup_request(path, project)


def test_cold_selection_reuses_restored_pipeline_and_view_without_rebuilding(launch, monkeypatch):
    import sys
    x = launch; source = object(); view = object(); calls = []
    p = SimpleNamespace(FindSource=lambda name: source if name == 'saved-filter' else None,
        SetActiveSource=lambda obj: calls.append(('source', obj)),
        SetActiveView=lambda obj: calls.append(('view', obj)), Render=lambda obj: calls.append(('Render', obj)))
    manager = SimpleNamespace(GetProxiesInGroup=lambda group: {('RenderView1', 'session'): view})
    monkeypatch.setitem(sys.modules, 'paraview', SimpleNamespace(simple=p,
        servermanager=SimpleNamespace(ProxyManager=lambda: manager)))
    select_restored_source(x.f['snapshot']['origin'])
    assert calls == [('source', source), ('view', view), ('Render', view)]
    # No OpenDataFile/Show/ColorBy/SetTime API is even present in this mock.


def test_cold_selection_missing_view_is_not_success(launch, monkeypatch):
    import sys
    x = launch; calls = []
    p = SimpleNamespace(FindSource=lambda _: object(), SetActiveSource=lambda _: calls.append('changed'))
    manager = SimpleNamespace(GetProxiesInGroup=lambda _: {})
    monkeypatch.setitem(sys.modules, 'paraview', SimpleNamespace(simple=p,
        servermanager=SimpleNamespace(ProxyManager=lambda: manager)))
    with pytest.raises(ValueError, match='view'): select_restored_source(x.f['snapshot']['origin'])
    assert not calls


def test_source_cli_argument_is_mutually_exclusive_with_other_entrypoints():
    with pytest.raises(SystemExit): desktop._arguments(['post', '--report-image', '{}', '--project', 'other.json'])
    with pytest.raises(SystemExit): desktop._arguments(['post', '--report-image', '{}', '--measurement-result', '{}'])


def test_native_executable_unavailable_does_not_launch_or_change_project(launch, monkeypatch):
    x = launch
    before = x.f['manifest'].read_bytes()
    def unavailable(*args, **kwargs):
        raise ValueError('Configured native ParaView unavailable; no fallback executable')
    monkeypatch.setattr(desktop, '_executable', unavailable)
    progress = {'phase': 'PREPARING'}
    with pytest.raises(ValueError, match='unavailable'):
        desktop._post(x.client, x.args, _report_origin=x.f['snapshot']['origin'], _report_launch=progress)
    assert not x.calls and progress == {'phase': 'PREPARING'}
    assert x.f['manifest'].read_bytes() == before
