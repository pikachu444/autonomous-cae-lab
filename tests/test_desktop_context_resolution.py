"""Keep server CAD runtime resolution separate from desktop client choices."""
from types import SimpleNamespace

from apps.lab.workbench_routes import handle
from caelab.desktop_links import DesktopLinks


def test_server_environment_and_path_do_not_become_explicit_client_choices(tmp_path, monkeypatch):
    monkeypatch.setenv('CAELAB_FREECAD_EXE', '/server/FreeCAD')
    monkeypatch.delenv('CAELAB_PARAVIEW_EXE', raising=False)
    monkeypatch.setattr('caelab.desktop_links.shutil.which',
                        lambda name: '/server/paraview' if name == 'paraview' else None)
    links = DesktopLinks(SimpleNamespace(root=tmp_path, config={}, session_id='Sdesktop'))
    server = links.context()
    assert server['freecad_executable'] == '/server/FreeCAD'
    assert server['paraview_executable'] == '/server/paraview'
    client = links.context(resolve_executables=False)
    assert client['freecad_executable'] is None
    assert client['paraview_executable'] is None
    assert {key: value for key, value in server.items() if not key.endswith('_executable')} == {
        key: value for key, value in client.items() if not key.endswith('_executable')}


def test_explicit_config_reaches_both_server_and_client_without_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('CAELAB_FREECAD_EXE', '/other/FreeCAD')
    monkeypatch.setenv('CAELAB_PARAVIEW_EXE', '/other/paraview')
    desktop = {'freecad_executable': '/configured/FreeCAD',
               'paraview_executable': '/configured/paraview'}
    links = DesktopLinks(SimpleNamespace(root=tmp_path, config={'desktop': desktop}, session_id='Sdesktop'))
    for resolve in (False, True):
        context = links.context(resolve_executables=resolve)
        assert {key: context[key] for key in desktop} == desktop


def test_desktop_http_route_returns_only_explicit_runtime_config(tmp_path, monkeypatch):
    monkeypatch.setenv('CAELAB_PARAVIEW_EXE', '/server/paraview')
    workbench = SimpleNamespace(root=tmp_path, config={}, session_id='Sdesktop')
    workbench.desktop = DesktopLinks(workbench)
    handler = SimpleNamespace(server=SimpleNamespace(workbench=workbench),
                              _json=lambda code, body: (code, body))
    code, context = handle(handler, 'GET', '/api/workbench/desktop', {})
    assert code == 200
    assert context['paraview_executable'] is None
    assert context['export_root'] == str(workbench.desktop.root)
    assert workbench.desktop.context()['paraview_executable'] == '/server/paraview'
