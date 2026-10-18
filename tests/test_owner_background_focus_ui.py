"""Read-only owner polling preserves enabled input and its selection.

Native focus is verified separately by the Windows owner-opening matrix.
"""
from copy import deepcopy
import os
import threading
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.numerical_window import NumericalWindow
from caelab.material_document import default_draft
from caelab.numerical_document import from_material_document


def wait(app,predicate):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Read-only owner callback did not settle')


@pytest.mark.parametrize('metadata_changed',[False,True])
def test_poll_preserves_clean_and_unapplied_input_through_background_callback(metadata_changed):
    app=QApplication.instance() or QApplication([])
    draft=from_material_document({'id':'Mfixture','generation':0,'input_revision':'Ifixture','draft':default_draft()})
    document={'id':'Nfixture','kind':'numerical','session_id':'Sfixture','generation':0,
        'title':'Controlled polling','draft':draft,'runs':[],'diagnostics':[],'dirty':False}
    release=threading.Event();reading=threading.Event()
    def read(identifier):
        assert identifier==document['id'];reading.set()
        assert release.wait(5)
        return deepcopy(document)
    window=NumericalWindow(SimpleNamespace(document_read=read),auto_open=False,poll_interval=0)
    try:
        window._show_document(document);window.settings_toggle.setChecked(True)
        window.resize(1200,850);window.show();app.processEvents()
        if metadata_changed:document['saved_revision']='Rretained'
        field=window.budget
        for edited in (False,True):
            release.clear();reading.clear()
            if edited:
                field.setText('1e');field.textEdited.emit('1e')
            field.setFocus();field.selectAll();app.processEvents()
            before=(field.text(),field.selectedText(),deepcopy(window.edited_draft(commit=False)))
            assert field.isEnabled()
            window.refresh_document();wait(app,reading.is_set)
            assert field.isEnabled() and field.selectedText()==before[1]
            release.set();wait(app,lambda:not window._busy and not window._callbacks)
            assert window.budget is field and field.isEnabled()
            assert (field.text(),field.selectedText(),window.edited_draft(commit=False))==before
            assert window.document==document
    finally:
        release.set();wait(app,lambda:not window._busy)
        window._allow_close=True;window.close();app.processEvents()
