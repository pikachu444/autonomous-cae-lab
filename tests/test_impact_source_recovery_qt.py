"""Exact original-file recovery only; no native solver or provider is started."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
import shutil,time
import pytest
pytest.importorskip('PySide6')
from PySide6 import QtCore,QtGui,QtTest,QtWidgets
from apps.research.impact_project import ImportDialog,SourceDialog
from apps.research.impact_editor import ImpactEditor
from caelab.impact_source import capture,SourceError
from caelab.impact_model import default_settings,model_from_settings


def app():
    result=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    font=Path('C:/Windows/Fonts/malgun.ttf')
    if font.is_file():QtGui.QFontDatabase.addApplicationFont(str(font))
    result.setFont(QtGui.QFont('Malgun Gothic',10))
    return result


@pytest.fixture
def source_root(tmp_path):
    root=tmp_path/'입력 작업'
    shutil.copytree(Path(__file__).resolve().parents[1]/'examples/impact/include-project',root)
    bad=root/'Materials/Elastic.inp';good=bad.read_bytes()
    bad.write_bytes(good+b'\n*UNSUPPORTED_TEST_CARD\n1\n')
    return root,bad,good


def test_import_focuses_exact_bad_include_without_losing_editable_draft(source_root):
    application=app();root,bad,good=source_root;dialog=ImportDialog()
    try:
        dialog.entry.setText(str(root/'model.inp'));dialog.root.setText(str(root));dialog.units.setChecked(True)
        dialog.show();dialog.check_input();deadline=time.monotonic()+5
        while dialog.worker is not None and time.monotonic()<deadline:
            application.processEvents();QtTest.QTest.qWait(10)
        assert dialog.worker is None
        assert dialog.source is not None and dialog.ok.isEnabled()
        assert dialog.ok.text()=='초안으로 가져오기'
        assert dialog.files.currentText()=='Materials/Elastic.inp'
        assert dialog.original.textCursor().selectedText()=='*UNSUPPORTED_TEST_CARD'
        assert dialog.original.isReadOnly()
        assert bad.read_bytes()==good+b'\n*UNSUPPORTED_TEST_CARD\n1\n'
    finally:
        if dialog.worker is not None:dialog.worker.cancelled.set();dialog.worker.wait(5000)
        dialog.reject();dialog.deleteLater();application.processEvents()


@pytest.mark.parametrize('size',[(560,460),(860,600)])
def test_problem_source_to_explicit_corrected_import_keeps_original(source_root,size,tmp_path,monkeypatch):
    application=app();root,bad,good=source_root
    value=default_settings();value['source']=capture(root/'model.inp',root)
    original=deepcopy(value);editor=ImpactEditor(value);viewer=None
    try:
        editor.show();application.processEvents()
        page=editor.project
        assert page.model is None and page.actions['source'].text()=='문제 원파일 보기…'
        opened=[]
        def observe(dialog):
            opened.append((dialog.files.currentText(),dialog.view.textCursor().selectedText()))
            return QtWidgets.QDialog.DialogCode.Accepted
        monkeypatch.setattr(SourceDialog,'exec',observe)
        page.actions['source'].click()
        assert opened==[('Materials/Elastic.inp','*UNSUPPORTED_TEST_CARD')]
        before=SourceDialog(editor.value['source'],parent=editor)
        before.resize(*size);before.show();application.processEvents()
        before.grab().save(str(tmp_path/f'impact-source-before-{size[0]}.png'))
        before.close();before.deleteLater()
        viewer=SourceDialog(editor.value['source'],page.source_error,editor)
        viewer.resize(*size);viewer.show();viewer.activateWindow();application.processEvents()
        assert viewer.files.currentText()=='Materials/Elastic.inp'
        assert viewer.view.textCursor().selectedText()=='*UNSUPPORTED_TEST_CARD'
        assert viewer.view.hasFocus()
        viewer.view.setFocus();QtTest.QTest.keyClick(viewer.view,QtCore.Qt.Key_C,QtCore.Qt.ControlModifier)
        assert application.clipboard().text()=='*UNSUPPORTED_TEST_CARD'
        viewer.grab().save(str(tmp_path/f'impact-source-recovery-{size[0]}.png'))
        viewer.accept();application.processEvents()
        # External correction is explicit; the already retained original stays exact.
        bad.write_bytes(good);corrected=capture(root/'model.inp',root)
        class ImportCorrected:
            def __init__(self,parent):self.source=corrected
            def exec(self):return QtWidgets.QDialog.DialogCode.Accepted
        monkeypatch.setattr('apps.research.impact_project.ImportDialog',ImportCorrected)
        monkeypatch.setattr(QtWidgets.QMessageBox,'question',lambda *a,**k:QtWidgets.QMessageBox.StandardButton.Yes)
        editor.choose_file();application.processEvents()
        assert editor.project.model is not None
        assert editor.project.source_error is None
        assert editor.project.actions['source'].text()=='원파일 보기…'
        assert len(model_from_settings(editor.edited())['nodes'])>0
        assert editor.value['motions']==[] and editor.value.get('generated_sets',[])==[]
        assert value==original and '*UNSUPPORTED_TEST_CARD' in original['source']['text']
    finally:
        if viewer is not None:viewer.close();viewer.deleteLater()
        editor.reject();editor.deleteLater();application.processEvents()


def test_unrecorded_source_location_is_not_guessed(source_root):
    application=app();root,_,_=source_root;source=capture(root/'model.inp',root)
    viewer=SourceDialog(source,SourceError('원행 미확인','Materials/Elastic.inp',999))
    try:
        assert not viewer.view.textCursor().hasSelection()
        assert '999행' not in viewer.note.text()
    finally:viewer.close();viewer.deleteLater();application.processEvents()
