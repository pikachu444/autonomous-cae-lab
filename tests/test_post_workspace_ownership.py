"""Post owner bookkeeping with controlled proxies, without native execution."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def owner_workspace(monkeypatch, tmp_path):
    import apps.desktop_post as package

    registered, checked, cleaned, highlighted = {}, [], [], []
    simple = SimpleNamespace(GetSources=lambda: {(name, 0): item for name, item in registered.items()},
        FindSource=lambda name: registered.get(name), GetAnimationScene=lambda: SimpleNamespace(AnimationTime=0))
    para = ModuleType('paraview')
    para.simple = simple
    para.servermanager = SimpleNamespace(vtkSMCoreUtilities=SimpleNamespace(GetFileNameProperty=lambda proxy: 'FileName'))
    monkeypatch.setitem(sys.modules, 'paraview', para)

    def verify(_path, document):
        refs = set(document['sources'])
        checked.append(refs)
        if 'Sunavailable' in refs:
            raise ValueError('CONTROLLED unavailable unrelated source')

    external = SimpleNamespace(_same_proxy=lambda a, b: a is b, verify_sources=verify,
        verify_readers=lambda document: verify(None, document), sha=lambda path: 'retained-bytes')
    analysis = SimpleNamespace(graph_signature=lambda bundle: deepcopy(bundle['source'].graph),
        cleanup=lambda bundle: cleaned.append(bundle['source'].name))
    measurements = SimpleNamespace(save_native_data=lambda source, folder, stem: {
        'entry': str(folder / 'result.vtu'), 'files': [{'path': str(folder / 'result.vtu'), 'sha256': 'retained-bytes', 'bytes': 1}]},
        highlight_point=lambda source, index: highlighted.append((source.name, index)),
        sample_data=lambda source, **kwargs: {'rows': [{'point_index': kwargs.get('point_index', 0), 'values': {'stress': 2.0}}]})
    for name, module in (('external', external), ('analysis', analysis), ('measurements', measurements)):
        monkeypatch.setitem(sys.modules, 'apps.desktop_post.' + name, module)
        monkeypatch.setattr(package, name, module, raising=False)
    path = Path(__file__).resolve().parents[1] / 'apps/desktop_post/workspace.py'
    spec = importlib.util.spec_from_file_location('apps.desktop_post.workspace_ownership_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def proxy(name, props=None):
        item = SimpleNamespace(name=name, SMProxy=object(), props=props or {}, graph={'sha256': name}, ListProperties=lambda: [])
        registered[name] = item
        return item

    original = proxy('raw-reader', {'FileName': [str(tmp_path / 'raw.vtu')], 'PointArrayStatus': ['stress']})
    record = {'reader_name': original.name, 'entry_path': str(tmp_path / 'raw.vtu'),
        'source_pins': [{'path': str(tmp_path / 'raw.vtu'), 'sha256': 'source-bytes', 'bytes': 1}]}
    owner = SimpleNamespace(project_path=tmp_path / 'project.json', generation=0,
        native_properties=lambda item: (deepcopy(item.props), []), proxy_id=lambda item: item.name)
    document = {'sources': {'Sraw': record, 'Sunavailable': deepcopy(record)}}
    work = module.Workspace(owner, document)

    def add_object(ref, inputs=('Sraw',), revisions=1):
        obj = {'id': ref, 'kind': 'filter', 'title': ref, 'draft': {'source_ref': inputs[0]},
               'history': [], 'position': -1, 'preview': None, 'selection': [], 'diagnostics': []}
        work.state['objects'][ref] = obj
        for index in range(revisions):
            output = proxy(ref + '-output-' + str(index), {'Input': {'proxy_id': inputs[0]}})
            revision = {'id': ref + '-V' + str(index), 'recipe': {'source_ref': inputs[0], 'filter': 'Clip'},
                'source_name': output.name, 'proxy_names': [output.name], 'summary': {}, 'graph': deepcopy(output.graph),
                'bindings': work.source_stamps(inputs), 'previous': obj['history'][-1]['id'] if obj['history'] else None}
            obj['history'].append(revision)
            work.bundles[revision['id']] = {'source': output, 'proxies': [output], 'summary': {}}
            obj['position'] = index
        return obj

    work._visibility = lambda revision, visible: visible_events.append((None if revision is None else revision['id'], visible))
    visible_events = []
    return SimpleNamespace(work=work, module=module, owner=owner, document=document, add_object=add_object,
        checked=checked, cleaned=cleaned, highlighted=highlighted, measurements=measurements,
        visible_events=visible_events, proxy=proxy, folder=tmp_path)


def test_chained_input_stamp_survives_saved_artifacts_and_reopen(owner_workspace):
    env = owner_workspace
    upstream = env.add_object('Aupstream')
    downstream = env.add_object('Adownstream', inputs=('Aupstream',))
    before = env.work.source_stamps(['Aupstream'])
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    reopened = env.module.Workspace(env.owner, saved)
    assert reopened.source_stamps(['Aupstream']) == before
    reopened._bundle(reopened.object(downstream['id']))
    assert saved['analysis']['objects'][upstream['id']]['history'][0]['result_file']


@pytest.mark.parametrize('operation', ['undo', 'redo'])
def test_history_target_is_verified_before_visibility_or_state_mutation(owner_workspace, operation):
    env = owner_workspace
    obj = env.add_object('Aobject', revisions=2)
    if operation == 'undo':
        target = obj['history'][0]
    else:
        obj.update(position=0, redo_stack=[obj['history'][1]['id']])
        target = obj['history'][1]
    env.work.bundles[target['id']]['source'].graph['sha256'] = 'CONTROLLED native edit'
    before = deepcopy(obj)
    with pytest.raises(ValueError, match='PIPELINE_CHANGED'):
        getattr(env.work, operation)(object_ref=obj['id'])
    assert obj == before
    assert env.visible_events == []


def test_selected_dependency_checks_do_not_read_unrelated_unavailable_original(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Aselected')
    env.work._bundle(obj)
    assert env.checked
    assert all('Sunavailable' not in refs for refs in env.checked)


def test_deeper_upstream_native_edit_blocks_downstream_samples(owner_workspace):
    env = owner_workspace
    upstream = env.add_object('Aupstream')
    downstream = env.add_object('Adownstream', inputs=('Aupstream',))
    # The direct output's properties are unchanged. Its owned upstream graph is not.
    env.work.bundles[upstream['history'][0]['id']]['source'].graph['sha256'] = 'CONTROLLED deeper edit'
    with pytest.raises(ValueError, match='PIPELINE_CHANGED'):
        env.work._bundle(downstream)


def test_save_discards_only_unapplied_preview_nodes_and_preserves_draft(owner_workspace):
    env = owner_workspace
    transient = env.add_object('Atransient', revisions=0)
    output = env.proxy('unapplied-preview')
    transient['draft'] = {'source_ref': 'Sraw', 'filter': 'Clip', 'settings': {'origin': [9, 0, 0]}}
    transient['preview'] = {'id': 'Vpreview'}
    env.work.bundles['Vpreview'] = {'source': output, 'proxies': [output]}
    applied = env.add_object('Aapplied')
    applied['preview'] = deepcopy(applied['history'][0])
    before_draft = deepcopy(transient['draft'])
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'save')
    assert env.cleaned == ['unapplied-preview']
    assert 'Vpreview' not in env.work.bundles
    assert applied['history'][0]['id'] in env.work.bundles
    assert transient['draft'] == before_draft
    assert transient['preview'] is None and applied['preview'] is None
    assert saved['analysis']['objects']['Atransient']['draft'] == before_draft


def test_explicit_point_query_highlights_exact_applied_output_and_retains_row_identity(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Aselected')
    result = env.work.sample(object_ref=obj['id'], preview=False, point_index=3)
    assert env.highlighted == [('Aselected-output-0', 3)]
    assert obj['selection'] == result['rows']
    assert obj['selection_hash'] == env.module.digest(result['rows'])
    assert obj['selection_revision'] == obj['history'][0]['id']
    assert env.visible_events == []


@pytest.mark.parametrize('changed', [False, True])
def test_restore_pick_requires_active_applied_revision_and_matching_native_sample(owner_workspace, changed):
    env = owner_workspace
    obj = env.add_object('Aselected')
    env.work.state['active_object'] = obj['id']
    env.work.sample(object_ref=obj['id'], preview=False, point_index=3)
    env.highlighted.clear()
    if changed:
        env.measurements.sample_data = lambda source, **kwargs: {'rows': [{'point_index': 3, 'values': {'stress': 9.0}}]}
    assert env.work.restore_selection() is (not changed)
    assert env.highlighted == ([] if changed else [('Aselected-output-0', 3)])
    assert bool(env.work.restore_issues) is changed


def test_history_navigation_clears_preview_without_deleting_retained_pipeline(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Aobject', revisions=2)
    obj['preview'] = deepcopy(obj['history'][1])
    env.work.undo(object_ref=obj['id'])
    assert obj['preview'] is None
    assert obj['history'][1]['id'] in env.work.bundles
    env.work.redo(object_ref=obj['id'])
    assert obj['preview'] is None
    assert env.cleaned == []


def test_history_visibility_only_changes_explicitly_owned_views(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Acurve')
    record = obj['history'][0]
    source = env.work.bundles[record['id']]['source']
    displays = [SimpleNamespace(Input=source, Visibility=1) for _ in range(3)]
    unrelated = SimpleNamespace(Input=env.proxy('another-curve'), Visibility=1)
    views = [('curve-own', SimpleNamespace(Representations=[displays[0]])),
             ('overlay', SimpleNamespace(Representations=[displays[1], unrelated])),
             ('manual-other', SimpleNamespace(Representations=[displays[2]]))]
    record.update(view_name='overlay', view_names=['curve-own', 'overlay'])
    env.work._views = lambda: views
    env.module.p.RenderAllViews = lambda: None
    env.module.Workspace._visibility(env.work, record, False)
    assert [item.Visibility for item in displays] == [0, 0, 1]
    assert unrelated.Visibility == 1
    env.module.Workspace._visibility(env.work, record, True)
    assert [item.Visibility for item in displays] == [1, 1, 1]


def test_apply_cannot_append_an_already_retained_noncurrent_revision(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Aobject', revisions=2)
    obj['preview'] = deepcopy(obj['history'][1])
    obj['preview']['key'] = 'same-key'
    obj['position'] = 0
    env.work._key = lambda obj: 'same-key'
    before = deepcopy(obj)
    with pytest.raises(ValueError, match='already retained'):
        env.work.apply(object_ref=obj['id'], show=False)
    assert obj == before
    assert env.visible_events == []


@pytest.mark.parametrize('existing,cleanup_fails', [(False, False), (True, False), (False, True)])
def test_failed_native_show_rolls_back_only_created_resources_and_active_selection(owner_workspace, existing, cleanup_fails):
    env = owner_workspace
    obj = env.add_object('Aobject')
    record = deepcopy(obj['history'][0])
    bundle = env.work.bundles[record['id']]
    native = env.module.p
    original_source, original_view = object(), object()
    active = [original_source, original_view]
    created = SimpleNamespace(GetXMLName=lambda: 'RenderView', Representations=[])
    layout = object()
    cleanup = []
    native.GetActiveSource = lambda: active[0]
    native.GetActiveView = lambda: active[1]
    native.SetActiveSource = lambda item: active.__setitem__(0, item)
    native.SetActiveView = lambda item: active.__setitem__(1, item)
    native.CreateLayout = lambda **kwargs: layout
    native.CreateView = lambda kind: created
    native.AssignViewToLayout = lambda **kwargs: None
    native.Show = lambda *args: SimpleNamespace()
    native.ResetCamera = lambda view: None
    native.Hide = lambda source, view: cleanup.append(('hide', source, view))
    native.RemoveLayout = lambda item: cleanup.append(('layout', item))
    def delete(item):
        cleanup.append(('view', item))
        if cleanup_fails:
            raise RuntimeError('CONTROLLED cleanup failure')
    native.Delete = delete
    def render(view):
        raise RuntimeError('CONTROLLED primary render failure')
    native.Render = render
    env.work._views = lambda: [('created-view', created)]
    if existing:
        record['view_name'] = 'created-view'
    with pytest.raises(RuntimeError, match='primary render failure'):
        env.work.show(obj, record, bundle)
    assert active == [original_source, original_view]
    if existing:
        assert cleanup == [('hide', bundle['source'], created)]
    else:
        assert cleanup == [('view', created), ('layout', layout)]
        assert 'view_name' not in record
    assert bool(obj['diagnostics']) is cleanup_fails
