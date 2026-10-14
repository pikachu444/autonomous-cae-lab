"""Injected real Qt controls and existing quality reader; synthetic mesh only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from copy import deepcopy
import pytest

from apps.desktop_pre.mesh_compare_panel import make_dialog
from apps.desktop_pre.mesh_quality_compare import compare_mesh_quality
from apps.desktop_pre.fem_edit import _mesh_hash
from test_pre_fem_edit import native, Mesh, Object

QtWidgets = pytest.importorskip('PySide6.QtWidgets')
QtCore = pytest.importorskip('PySide6.QtCore')


@pytest.fixture(scope='module')
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def prepare(native):
    native.doc.getObject = lambda name: next((o for o in native.doc.Objects if o.Name == name), None)
    native.document_id, native.session_id = 'Pexample', 'Sexample'
    native.generation, native.closed = 0, False
    native.refresh = lambda: None
    native.mesh.Label = '브래킷 메시'
    native.mesh.FemMesh = Mesh(2)
    native.metadata['mesh_history'] = []
    native.calls = []
    for index, size in [(1, 1), (2, 1.5)]:
        archive = Object(native.doc, 'Archive' + str(index), 'Fem::FemMeshObject', FemMesh=Mesh(size))
        archive.Label = '브래킷 메시 — previous mesh Hhidden' if index == 1 else '국부 크기 수정 전'
        native.metadata['mesh_history'].append({'id': 'Hhidden' + str(index), 'mesh_id': native.mesh.Name,
            'state': 'SUCCEEDED', 'previous_mesh_object_id': archive.Name,
            'previous_mesh_sha256': _mesh_hash(archive.FemMesh)})
    def dispatch(request):
        native.calls.append(deepcopy(request))
        assert request['document_id'] == native.document_id and request['session_id'] == native.session_id
        assert request['expected_generation'] == native.generation
        assert request['target'] == {'object_id': native.mesh.Name}
        try:
            if request['operation'] == 'pre.fem.mesh_compare':
                value = compare_mesh_quality(native.editor, native.mesh,
                    request['arguments']['history_id'], request['arguments']['mesh_sha256'])
            else:
                assert request['operation'] == 'pre.fem.mesh_quality'
                value = native.editor.dispatch(request['operation'], request['arguments'], request['target'])
            return {'status': 'COMPLETED', 'result': value}
        except ValueError as error:
            return {'status': 'FAILED', 'error': {'message': str(error)}}
    native.dispatch = dispatch


@pytest.fixture
def panel(native, app):
    prepare(native)
    widget = make_dialog(QtWidgets, QtCore, native, native.mesh)
    widget.timer.stop()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_select_preserved_mesh_read_actual_statistics_and_keep_model_unmodified(panel, native):
    before = deepcopy(native.metadata), _mesh_hash(native.mesh.FemMesh)
    assert panel.history.currentData() == 'Hhidden2'
    assert panel.history.currentText() == '2번째 재메시 전: 국부 크기 수정 전'
    panel.history.setCurrentIndex(1)
    assert panel.history.currentText() == '1번째 재메시 전: 브래킷 메시'
    expected = compare_mesh_quality(native.editor, native.mesh, 'Hhidden1', _mesh_hash(native.mesh.FemMesh))
    assert panel._result == expected
    assert panel.summary.rowCount() == 6
    assert panel.summary.item(2, 3).text() == format(expected['changes']['absolute_jacobian_mm3']['minimum'], '.6g')
    old, new, note = panel.distributions['absolute_jacobian_mm3']
    assert old.item(0, 0).text() != new.item(0, 0).text()
    assert '서로 다릅니다' in note.text()
    labels = [panel.history.itemText(i) for i in range(panel.history.count())]
    assert all('Hhidden' not in s and 'Archive' not in s and 'sha256' not in s for s in labels)
    assert all(c['operation'] in {'pre.fem.mesh_quality', 'pre.fem.mesh_compare'} for c in native.calls)
    assert before == (native.metadata, _mesh_hash(native.mesh.FemMesh))
    assert native.transactions == [] and native.tools == []


def test_stale_mesh_error_clears_old_current_values_and_refresh_recovers(panel, native):
    native.mesh.FemMesh = Mesh(3)
    panel.compare()
    assert panel._result is None and panel.summary.rowCount() == 0
    assert '현재 메시가 바뀌었습니다' in panel.status.text()
    panel.refresh_button.click()
    assert panel._result['current']['mesh_sha256'] == _mesh_hash(native.mesh.FemMesh)
    assert panel._result['current']['absolute_jacobian_mm3']['minimum'] == pytest.approx(27)


def test_deleted_archive_and_document_changes_have_requery_recovery(panel, native):
    archive = native.doc.getObject('Archive2')
    native.doc.Objects.remove(archive)
    native.generation += 1
    panel._check_changes()
    assert panel._result is None and '모델이 변경됐습니다' in panel.status.text()
    panel.refresh()
    assert '보관 메시 없음' in panel.history.currentText()
    assert panel.summary.rowCount() == 0
    native.doc.Objects.append(archive)
    panel.refresh()
    assert panel._result is not None
    native.closed = True
    panel._check_changes()
    assert panel._result is None and '문서가 닫히거나 바뀌었습니다' in panel.status.text()
    assert native.transactions == [] and native.tools == []


def test_no_history_is_an_empty_actionable_window_without_quality_run(native, app):
    prepare(native)
    native.metadata['mesh_history'] = []
    widget = make_dialog(QtWidgets, QtCore, native, native.mesh)
    assert not widget.history.isEnabled() and widget.summary.rowCount() == 0
    assert '보관된 이전 메시가 없습니다' in widget.status.text()
    assert native.calls == []
    widget.close()
