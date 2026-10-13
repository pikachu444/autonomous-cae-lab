"""Native proxy doubles: graph guards and reopen must not discard native edits.

No installed ParaView, broker, solver or OS acceptance is claimed by this file.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import pytest

from test_post_r3_repairs import post_modules, Property


@pytest.fixture(autouse=True)
def native_numpy_conversion_double(monkeypatch):
    # Graph/CSV option checks never convert VTK arrays. Keep these unit tests
    # runnable without installing VTK into the separate research interpreter.
    support = ModuleType('paraview.numpy_support')
    support.vtk_to_numpy = lambda value: value
    monkeypatch.setitem(sys.modules, 'paraview.numpy_support', support)


class Proxy:
    def __init__(self, name, kind, **properties):
        self.name, self.kind, self.properties = name, kind, properties
        self.SMProxy = object()
        self.pending = []
    def GetXMLName(self):
        return self.kind
    def ListProperties(self):
        return list(self.properties)
    def GetProperty(self, name):
        return Property(self.properties[name])
    def __getattr__(self, name):
        try:
            return self.properties[name]
        except KeyError:
            raise AttributeError(name) from None


@pytest.fixture
def contact_native(post_modules, monkeypatch, tmp_path):
    import apps.desktop_post as package
    path = Path(__file__).resolve().parents[1]/'apps/desktop_post/contact_views.py'
    spec = importlib.util.spec_from_file_location('apps.desktop_post.contact_views_guard_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    native = post_modules.native
    reader = Proxy('Contact faces 1', 'XMLUnstructuredGridReader',
                   FileName=[str(tmp_path/'contact-surfaces.vtu')], PointArrayStatus=['NativeNodeId'])
    a = Proxy('Contact faces 1 A', 'Threshold', Input=[reader], Scalars=['CELLS', 'ContactSurfaceIndex'],
              ThresholdMethod='Between', LowerThreshold=0, UpperThreshold=0)
    b = Proxy('Contact faces 1 B', 'Threshold', Input=[reader], Scalars=['CELLS', 'ContactSurfaceIndex'],
              ThresholdMethod='Between', LowerThreshold=1, UpperThreshold=1)
    original = Proxy('result', 'PVDReader', FileName=str(tmp_path/'contact.pvd'))
    proxies = [reader, a, b]
    native.sources = {(proxy.name, 0): proxy for proxy in [original, *proxies]}
    view = Proxy('RenderView1', 'RenderView', Representations=[])
    native.views = {('RenderView1', 0): view}
    native.active = original
    bundle = {'descriptor': {'sha256': 'a'*64}, 'surfaces_path': reader.FileName[0], 'pairs': {'Pair': {}}}
    selection = {'source_ref': 'result', 'pair_id': 'Pair', 'side': 'both',
        'frame_index': 0, 'field': 'CPRESS', 'quantity': 'CFN', 'component': 2,
        'inspection_sha256': 'a'*64, 'overlay_names': [proxy.name for proxy in proxies],
        'view_name': 'RenderView1', 'overlay_graph': module._overlay_graph(proxies, bundle)}
    calls = []
    def unexpected(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError('Read/guard must not create, delete or replay the native display')
    for name in ('XMLUnstructuredGridReader', 'Threshold', 'Delete', 'Show', 'Render',
                 'SetActiveSource', 'SetActiveView', 'GetScalarBar'):
        monkeypatch.setattr(native, name, unexpected, raising=False)
    monkeypatch.setattr(post_modules.external, 'select_array', unexpected)
    api = SimpleNamespace(inspect=lambda *args: {'scope': 'shared_nodal_projection'})
    monkeypatch.setattr(post_modules.external, 'contact_api', lambda: api)
    workspace = SimpleNamespace(state={'contact_selection': selection}, document={'sources': {}},
        resolve=lambda ref: original, _views=lambda: [('RenderView1', view)],
        owner=SimpleNamespace(proxy_id=lambda proxy: proxy.name,
            native_properties=lambda proxy: ({}, list(proxy.pending))), restore_issues=[])
    monkeypatch.setattr(module, 'read', lambda work, ref: bundle)
    return SimpleNamespace(module=module, workspace=workspace, bundle=bundle, selection=selection,
        proxies=proxies, native=native, original=original, view=view, calls=calls)


@pytest.mark.parametrize('change', ['native_edit', 'pending', 'dependent'])
def test_show_preserves_edited_overlay_and_native_dependents(contact_native, change):
    env = contact_native
    if change == 'native_edit':
        env.proxies[1].properties['LowerThreshold'] = 9
        message = 'properties changed'
    elif change == 'pending':
        env.proxies[1].pending = ['LowerThreshold']
        message = 'BUSY_EDIT'
    else:
        clip = Proxy('User Clip', 'Clip', Input=[env.proxies[1]])
        env.native.sources[(clip.name, 0)] = clip
        message = 'dependent filter'
    before = dict(env.native.sources)
    with pytest.raises(ValueError, match=message):
        env.module._show(env.workspace, env.bundle, env.selection)
    assert env.native.sources == before
    assert env.calls == []


def test_overlay_identity_supports_identical_relocation_and_explicit_removal(contact_native, tmp_path):
    env = contact_native
    assert env.module._owned_overlay(env.workspace, env.selection, env.bundle, replacing=True) == env.proxies
    moved = str(tmp_path/'moved'/'contact-surfaces.vtu')
    env.proxies[0].properties['FileName'] = [moved]
    env.bundle['surfaces_path'] = moved
    assert env.module._owned_overlay(env.workspace, env.selection, env.bundle, replacing=True) == env.proxies
    del env.native.sources[(env.proxies[1].name, 0)]
    with pytest.raises(ValueError, match='branch changed'):
        env.module._owned_overlay(env.workspace, env.selection, env.bundle, replacing=True)
    for proxy in env.proxies:
        env.native.sources.pop((proxy.name, 0), None)
    assert env.module._owned_overlay(env.workspace, env.selection, env.bundle, replacing=True) == []
    assert env.calls == []


def test_cold_reopen_reuses_overlay_without_replaying_earlier_field_time_visibility(contact_native):
    env = contact_native
    # This models later native choices already restored by PVSM, independent of
    # the last explicit contact Show. Downstream user work is also retained.
    env.native.AnimationTime = 1.
    env.native.visible = False
    env.native.color_array = 'U_mm'
    clip = Proxy('User Clip', 'Clip', Input=[env.proxies[1]])
    env.native.sources[(clip.name, 0)] = clip
    saved = deepcopy(env.selection)
    assert env.module.restore(env.workspace)
    assert env.workspace.state['contact_selection'] == saved
    assert env.native.AnimationTime == 1. and env.native.visible is False
    assert env.native.color_array == 'U_mm'
    assert env.native.sources[(clip.name, 0)] is clip
    assert not env.workspace.restore_issues and not env.calls


def test_cold_reopen_keeps_modified_native_overlay_and_reports_it(contact_native):
    env = contact_native
    env.proxies[1].properties['LowerThreshold'] = 12
    assert env.module.restore(env.workspace) is False
    assert 'properties changed' in env.workspace.restore_issues[0]['message']
    assert env.proxies[1].LowerThreshold == 12 and env.calls == []


def test_retained_vtk_table_csv_uses_row_data_and_float64_precision(post_modules, monkeypatch, tmp_path):
    # Only the native writer is doubled; run the real file/receipt function.
    numpy_support = ModuleType('vtk.util.numpy_support')
    numpy_support.vtk_to_numpy = lambda value: value
    vtk, util = ModuleType('vtk'), ModuleType('vtk.util')
    vtk.util, util.numpy_support = util, numpy_support
    monkeypatch.setitem(sys.modules, 'vtk', vtk)
    monkeypatch.setitem(sys.modules, 'vtk.util', util)
    monkeypatch.setitem(sys.modules, 'vtk.util.numpy_support', numpy_support)
    path = Path(__file__).resolve().parents[1]/'apps/desktop_post/measurements.py'
    spec = importlib.util.spec_from_file_location('apps.desktop_post.measurements_csv_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = SimpleNamespace(GetClassName=lambda: 'vtkTable')
    source = SimpleNamespace(data=data, UpdatePipeline=lambda: None)
    writes = []
    def save(path, **kwargs):
        writes.append(kwargs)
        Path(path).write_text('load_parameter,CFN_Z_N\n0.5,1.2345678901234567\n', encoding='utf-8')
    monkeypatch.setattr(post_modules.native, 'SaveData', save, raising=False)
    result = module.save_native_data(source, tmp_path/'table', 'force')
    assert writes == [{'proxy': source, 'FieldAssociation': 'Row Data', 'Precision': 17,
                       'AddTime': 0, 'AddTimeStep': 0}]
    assert len(result['files']) == 1 and Path(result['entry']).is_file()
