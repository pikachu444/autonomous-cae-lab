"""Changed-result preview and fresh-project isolation; no solver execution."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_research_post_ui import app, window, wait
from test_desktop_post_external import native
from apps.desktop_post.source_change import preview_change
from apps.research import post_source_dialogs as dialogs


def original_source():
    return {'source_ref': 'Sfirst', 'source_revision': 'old-revision', 'label': '기존 결과', 'entry_name': 'result.vtu',
        'files': [{'relative': 'result.vtu', 'bytes': 1, 'sha256': 'a'*64}],
        'metadata': {'points': 4, 'cells': 1, 'timesteps': [0., 1.],
            'arrays': [{'name': 'stress', 'association': 'POINTS', 'components': 1, 'units': 'MPa', 'range': [0., 3.]}]}}


def replacement(tmp_path):
    entry = tmp_path/'registered'/'result.vtu'
    receipt = {'id': 'Dnew', 'path': str(entry), 'format': 'vtu',
        'source_pins': [{'path': str(entry), 'bytes': 2, 'sha256': 'b'*64}]}
    metadata = {'points': 5, 'cells': 2, 'timesteps': [0., .5, 1.5],
        'arrays': [{'name': 'stress', 'association': 'POINTS', 'components': 1, 'units': 'MPa', 'range': [-4., 10.]},
                   {'name': 'U', 'association': 'POINTS', 'components': 3, 'units': 'mm', 'range': [0., 2.]}]}
    return {'input_id': 'Dnew', 'receipt': receipt, 'impact': preview_change(original_source(), receipt, metadata)}


def test_file_array_time_preview_has_no_old_object_or_physical_declaration_copy(tmp_path):
    preview = replacement(tmp_path)['impact']
    assert preview['content_changed'] and preview['files'] == [{'name': 'result.vtu', 'change': 'changed'}]
    assert preview['after']['timesteps'] == [0., .5, 1.5]
    added = next(row for row in preview['arrays'] if row['name'] == 'U')
    assert added['before'] is None and added['after']['units'] == 'mm'
    assert 'objects' not in preview and 'history' not in preview


def test_native_shaped_preview_restores_source_time_view_and_removes_probe(native, tmp_path, monkeypatch):
    fake, commands, external = native
    monkeypatch.setattr(fake, 'Delete', lambda source: setattr(fake, 'sources', {key: value for key, value in fake.sources.items() if value is not source}), raising=False)
    entry = tmp_path/'new.vtu'; entry.write_bytes(b'recorded reader boundary')
    source = fake.XMLUnstructuredGridReader(registrationName='Original', FileName=[str(entry)])
    view = fake.CreateView('RenderView'); view.ViewTime = 7.; fake.SetActiveView(view); fake.SetActiveSource(source); fake.scene.AnimationTime = 7.
    before = dict(fake.sources)
    monkeypatch.delitem(__import__('sys').modules, 'apps.desktop_post.source_repair', raising=False)
    repair = importlib.import_module('apps.desktop_post.source_repair')
    monkeypatch.setattr(repair, 'external', external)
    result = repair.preview_registered({'id': 'Dnew', 'path': str(entry), 'source_pins': external.pins([entry])})
    assert result['points'] == 4 and fake.sources == before
    assert fake.active is source and fake.view is view and view.ViewTime == 7. and fake.scene.AnimationTime == 7.


def test_fresh_project_prepares_only_new_input_and_reuses_saved_project_after_launch_failure(tmp_path, monkeypatch):
    from apps.research import desktop
    preview = replacement(tmp_path); client = NS(url='http://127.0.0.1:1', native_input=lambda _: deepcopy(preview['receipt']))
    calls = []; output = tmp_path/'new'; project = output/'workspace'/'project.json'
    def post(client, args):
        calls.append(args)
        assert args.job_id is None and args.research_source is None and args.measurement_result is None
        if args.prepare_only:
            assert args.input_id == 'Dnew' and args.project is None
            project.parent.mkdir(parents=True); project.write_text(json.dumps({'document_id': 'Dfresh', 'sources': {'result': {}}, 'analysis': {'objects': {}}}))
            return {'project': str(project), 'state': str(project.parent/'analysis.pvsm')}
        assert args.project == str(project) and args.input_id is None
        if len(calls) == 2: raise OSError('controlled launch failure')
        return {'status': 'LAUNCHED', 'pid': 42, 'project': str(project)}
    monkeypatch.setattr(desktop, '_post', post)
    result = dialogs.open_fresh_project(client, 'Dnew', str(output), expected=preview['receipt'])
    assert 'error' in result and project.is_file()
    saved = project.read_bytes()
    again = dialogs.open_fresh_project(client, 'Dnew', str(output), prepared=result['prepared'])
    assert again['launched']['pid'] == 42 and len(calls) == 3 and project.read_bytes() == saved
    changed = deepcopy(preview['receipt']); changed['source_pins'][0]['sha256'] = 'c'*64
    client.native_input = lambda _: changed
    with pytest.raises(ValueError, match='다시 미리보기'): dialogs.open_fresh_project(client, 'Dnew', str(tmp_path/'other'), expected=preview['receipt'])
    assert len(calls) == 3


@pytest.mark.parametrize('failure', [None, 'preview', 'prepare', 'launch'])
def test_qt_changed_source_preview_apply_cancel_and_failures_preserve_old_document(app, window, tmp_path, monkeypatch, failure):
    source = window._sources()[0]; source.update(original_source()); window._source_ref = 'Sfirst'
    window.document['state']['analysis']['objects'].append({'id': 'OldComparison', 'kind': 'comparison', 'history': [{'id': 'OldResult'}]})
    original = deepcopy(window.document)
    window.client.local_roots = lambda: {'roots': [{'id': 'approved', 'access': 'read_and_snapshot'}]}
    window.client.desktop_context = lambda: {'export_root': str(tmp_path/'exports')}
    window.client.register_local_input = lambda root, relative: {'id': 'Dnew'}
    preview = replacement(tmp_path); prepared = {'project': str(tmp_path/'new'/'workspace'/'project.json')}
    opened = []
    def inspect(*args):
        if failure == 'preview': raise ValueError('controlled read error')
        return deepcopy(preview)
    def apply(*args, **kwargs):
        opened.append((args, kwargs))
        if failure == 'prepare': raise ValueError('controlled save error')
        return {'prepared': prepared, **({'error': 'controlled launch error'} if failure == 'launch' and len(opened) == 1 else {'launched': {'pid': 42}})}
    monkeypatch.setattr(dialogs, 'inspect_replacement', inspect); monkeypatch.setattr(dialogs, 'open_fresh_project', apply)
    window._update_actions()
    window.changed_source_button.click(); dialog = window._source_update_dialog
    wait(app, lambda: not dialog._busy and dialog.roots.count() == 1)
    dialog.file.setText('result.vtu'); dialog.folder.setText(str(tmp_path/'new')); dialog.preview_button.click()
    wait(app, lambda: not dialog._busy)
    if failure == 'preview':
        assert dialog.preview is None and not dialog.apply_button.isEnabled() and dialog.details.toPlainText() == 'controlled read error'
    else:
        assert dialog.files.item(0, 1).text() == '내용 변경' and dialog.arrays.rowCount() == 2
        assert '3개' in dialog.time.text() and '비교 1개' in dialog.retained.text()
        dialog.apply_button.click(); wait(app, lambda: not dialog._busy)
        if failure == 'prepare': assert dialog.prepared is None and dialog.file.text() == 'result.vtu'
        elif failure == 'launch':
            assert dialog.prepared == prepared and dialog.apply_button.isEnabled()
            dialog.apply_button.click(); wait(app, lambda: not dialog._busy)
            assert opened[-1][1]['prepared'] == prepared and not dialog.apply_button.isEnabled()
        else: assert dialog._launched and not dialog.apply_button.isEnabled()
    assert window.document == original and not window.client.calls
    dialog.reject(); app.processEvents(); assert window.document == original


def test_approved_folder_picker_uses_service_listing_without_os_root_path(app, window, tmp_path, monkeypatch):
    source = original_source(); window._sources()[0].update(source); window._source_ref = source['source_ref']
    window.client.local_roots = lambda: {'roots': [{'id': 'approved'}]}
    window.client.desktop_context = lambda: {'export_root': str(tmp_path)}
    listed = []
    def files(root, relative='', cursor=0):
        listed.append((root, relative, cursor))
        return {'entries': [{'name': 'new.pvd', 'relative': 'new.pvd', 'directory': False}]}
    window.client.local_inputs = files
    monkeypatch.setattr(dialogs.QInputDialog, 'getItem', lambda *args, **kwargs: ('new.pvd', True))
    dialog = dialogs.SourceUpdateDialog(window, source); dialog.show()
    wait(app, lambda: not dialog._busy and dialog.roots.count() == 1)
    dialog.file_button.click(); wait(app, lambda: dialog.file.text() == 'new.pvd')
    assert listed == [('approved', '', 0)] and dialog.preview is None and not window.client.calls
    dialog.reject()


def test_cancel_during_preview_ignores_late_native_read_without_changing_old_document(app, window, tmp_path, monkeypatch):
    import threading
    source = original_source(); window._sources()[0].update(source); window._source_ref = source['source_ref']
    original = deepcopy(window.document)
    window.client.local_roots = lambda: {'roots': [{'id': 'approved'}]}
    window.client.desktop_context = lambda: {'export_root': str(tmp_path)}
    window.client.register_local_input = lambda *args: {'id': 'Dnew'}
    started, release = threading.Event(), threading.Event()
    def delayed(*args):
        started.set(); release.wait(3); return replacement(tmp_path)
    monkeypatch.setattr(dialogs, 'inspect_replacement', delayed)
    dialog = dialogs.SourceUpdateDialog(window, source); dialog.show()
    wait(app, lambda: not dialog._busy and dialog.roots.count() == 1)
    dialog.file.setText('new.pvd'); dialog.preview_button.click()
    wait(app, started.is_set); dialog.reject(); release.set()
    wait(app, lambda: not dialog._busy)
    assert dialog.preview is None and dialog._closed and window.document == original and not window.client.calls
