"""Selection/basis recovery with explicit software owners; no native run."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel
from test_research_post_ui import app, window, edit
from apps.research.post_contact_dialog import ContactDialog


def retained(window):
    recipe = {'source_ref': 'Sfirst', 'measurement': 'point', 'array': 'stress', 'association': 'POINTS',
              'units': 'MPa', 'frame': 'lab', 'time': .25, 'time_units': 's', 'point_indices': [4]}
    obj = {'id': 'Aretained', 'kind': 'measurement', 'title': '점 응력', 'draft': deepcopy(recipe),
           'position': 0, 'history': [{'id': 'Vretained', 'recipe': deepcopy(recipe)}], 'preview': None}
    document = deepcopy(window.document)
    document['state']['analysis']['objects'] = [obj, {**deepcopy(obj), 'id': 'Aother', 'title': '다른 응력'}]
    window._object_ref = obj['id']; window._tree_selection = ('object', obj['id'])
    window._show_document(document)
    window._show_samples({'object_ref': obj['id'], 'revision': 'Vretained', 'preview': False,
        'rows': [{'row': 0, 'values': {'stress': 0.0}, 'validity': {'stress': 'valid'}}]})
    return recipe


def test_source_browse_keeps_draft_and_blocked_object_restores_highlight(app, window):
    original = retained(window)
    window.show(); app.processEvents()
    edit(window, ('time',), '.5')
    objects = window.tree.topLevelItem(1)
    window.tree.setCurrentItem(objects.child(1))
    assert window.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == ('object', 'Aretained')
    window.tree.setCurrentItem(window.tree.topLevelItem(0).child(1))
    assert window._source_ref == 'Ssecond' and window._object_ref == 'Aretained'
    assert window.edited_draft()['source_ref'] == 'Sfirst' and window.edited_draft()['time'] == .5
    assert window.array_table.isVisible() and window.return_editor.isVisible() and not window.samples.isVisible()
    window.return_to_editor()
    assert window._tree_selection == ('object', 'Aretained')
    assert window.samples.isVisible() and window.local_dirty
    assert window._sample_basis['draft'] == original
    assert '0.25' in window.sample_context.text() and '미적용' in window.sample_context.text()
    assert window._samples['rows'][0]['values']['stress'] == 0.0
    window.document['state']['analysis']['objects'][0]['draft']['time'] = .5
    window.local_dirty = False
    window._draft['time'] = .5
    window._update_actions()
    assert '이전 조회' in window.sample_context.text() and '0.25' in window.sample_context.text()
    window.document['state']['analysis']['objects'][0]['history'].append({'id': 'Vnew', 'recipe': deepcopy(original)})
    window.document['state']['analysis']['objects'][0]['position'] = 1
    window._draft = deepcopy(original); window._populate_editor()
    window._update_actions()
    assert '이전 조회' in window.sample_context.text()


def test_new_object_clears_old_samples_without_changing_retained_values(app, window):
    original = retained(window)
    window.new_object('measurement')
    assert window._samples is None and window._sample_basis is None and window.samples.rowCount() == 0
    assert window.samples.columnCount() == 0 and '새 측정' in window.message.text()
    assert window.document['state']['analysis']['objects'][0]['history'][0]['recipe'] == original
    assert window.editor_toggle.isChecked()
    assert window._recipe_meaning({'measurement': 'contact_force', 'component': 'invalid'}).find('invalid') >= 0


def test_contact_changed_selection_and_first_read_failure_are_recoverable(app, window):
    calls = []
    window.queue_command = lambda operation, arguments, **options: calls.append((operation, deepcopy(arguments))) or True
    dialog = ContactDialog(window, 'Sfirst')
    window._contact_dialog = dialog
    try:
        window._last_command = {'operation': 'post.contact_inspect', 'state': 'FAILED'}
        dialog.sync()
        assert dialog.read_button.isEnabled() and not dialog.save_measurement.isEnabled()
        assert '마지막 성공' not in dialog.status.text()
        dialog.read()
        assert calls[-1][1] == {'source_ref': 'Sfirst', 'show': False, 'offset': 0, 'limit': 500}
        for combo, value in ((dialog.pair, 'Pair'), (dialog.frame, 0), (dialog.field, 'CPRESS')):
            combo.addItem(str(value), value)
        dialog.quantity.setCurrentIndex(dialog.quantity.findData('CFN'))
        dialog.component.setCurrentIndex(2)
        dialog.payload = {'selection': dialog.selection(), 'offset': 0, 'next_offset': None}
        window._last_command = None
        dialog.sync()
        assert dialog.save_measurement.isEnabled()
        dialog.quantity.setCurrentIndex(dialog.quantity.findData('CF'))
        assert not dialog.save_measurement.isEnabled() and not dialog.numerical.isEnabled()
        count = len(calls)
        dialog.create_measurement()
        assert len(calls) == count and '먼저 조회' in dialog.status.text()
    finally:
        dialog.close()
        window._contact_dialog = None
