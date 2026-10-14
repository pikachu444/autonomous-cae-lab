"""Native Qt/HTTP editor and page export. No device/solver/inference requests."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import threading
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication
from apps.lab.server import LabHTTPServer
from apps.lab.service import LabService
from apps.research.appearance import apply_appearance
from apps.research.report_window import ReportWindow,section
from apps.research.report_pages import atomic_export,pdf_document,markdown
from apps.research.experiment_dialogs import CalibrationDialog,AcquisitionDialog
from caelab.workbench_client import Client
from test_experiment_calibration import calibration,mapping


@pytest.fixture
def app():
    value=QApplication.instance() or QApplication([])
    apply_appearance(value)
    return value


def wait(app,condition,window):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        app.processEvents()
        if condition():return
        time.sleep(.005)
    raise AssertionError(window.message.text())


@pytest.mark.parametrize('size',[(1100,780),(1440,900)])
def test_calibration_unapplied_number_keeps_plot_and_ranges(app,size):
    recipe=calibration()
    preview={'table_preview':{'headers':['time','voltage'],'rows':[['0','.001'],['1','.005'],['2','.006']],
        'row_numbers':[1,2,3]}}
    window=CalibrationDialog(None,mapping(recipe)['columns']['force'],preview)
    try:
        window.resize(*size);window.show();app.processEvents()
        assert window.width()==size[0] and window.height()==size[1]
        assert window.canvas.width()>550 and window.canvas.height()>260
        assert len(window.figure.axes)==2
        assert '[V]' in window.figure.axes[0].get_ylabel()
        assert '[N]' in window.figure.axes[1].get_ylabel()
        assert window.values.item(1,2).text()=='8.5'
        before=deepcopy(window.figure.axes[0].lines[0].get_ydata().tolist())
        window.fields['a'].setText('1e');window.refresh_preview()
        assert window.edited()['a']=='1e'
        assert window.figure.axes[0].lines[0].get_ydata().tolist()==before
        window.reject()
        assert recipe['a']==2.
    finally:window.close()


def test_report_native_pages_local_section_buffer_save_reopen_and_atomic_pdf(app,tmp_path):
    server=LabHTTPServer(LabService(tmp_path/'workspace'),0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client('http://127.0.0.1:'+str(server.server_port))
    windows=[]
    window=ReportWindow(client);windows.append(window)
    try:
        window.show();wait(app,lambda:window.document and not window._busy,window)
        window.append_section(section('시험 목적',text='공개 자료의 비교'))
        window.append_section(section('다음 시험',text='반복 문단\n'*160))
        window.sections.setCurrentRow(0);window.edit_section()
        window.section_text.setPlainText('미적용 메모 1e')
        window.close_editor();window.edit_section()
        assert window.section_text.toPlainText()=='미적용 메모 1e'
        window.cancel_section()
        assert window.section_text.toPlainText()=='공개 자료의 비교'
        window.section_text.setPlainText('교정된 힘과 원값을 비교한다.');window.apply_section();window.close_editor()
        assert window.draft['sections'][0]['text']=='교정된 힘과 원값을 비교한다.'
        window.undo();assert window.draft['sections'][0]['text']=='공개 자료의 비교'
        window.redo();assert window.draft['sections'][0]['text']=='교정된 힘과 원값을 비교한다.'
        for size in [(1100,780),(1440,900)]:
            window.resize(*size);app.processEvents()
            assert window.size().width()==size[0] and window.size().height()==size[1]
            assert window.preview.width()>600 and window.preview.height()>500
        assert window._page.pageCount()>1
        path=tmp_path/'보고서.pdf'
        atomic_export(path,lambda p:pdf_document(window._page,p))
        assert path.read_bytes().startswith(b'%PDF')
        old=path.read_bytes()
        def failed(p):
            p.write_bytes(b'partial');raise OSError('explicit output failure')
        with pytest.raises(OSError):atomic_export(path,failed)
        assert path.read_bytes()==old
        md=markdown(window.draft,window.assets)
        assert '교정된 힘' in md
        window.save_document()
        wait(app,lambda:not window._busy and not window._pending and bool(window.document.get('saved_revision')),window)
        identifier=window.document['id'];draft=deepcopy(window.draft)
        reopened=ReportWindow(client,document_id=identifier);windows.append(reopened)
        reopened.show();wait(app,lambda:reopened.document and not reopened._busy,reopened)
        assert reopened.draft==draft and not reopened.document['runs']
    finally:
        for w in windows:
            w._pending=None
            if w.document:w.document['dirty']=False;w.draft=deepcopy(w.document['draft'])
            w._edit_buffers.clear();w._editing_section=None;w.close()
        assert QThreadPool.globalInstance().waitForDone(5000)
        server.shutdown();server.server_close();thread.join(timeout=3)


def test_acquisition_partial_draft_and_explicit_canonical_role(app):
    dialog=AcquisitionDialog(None,{'force':{'calibration':calibration()}})
    try:
        dialog.fields['name'].setText('인장 시험')
        dialog.fields['sample_rate_hz'].setText('1e')
        dialog.add_channel({'name':'force','unit':'N','role':'measurement','calibration':calibration()})
        value=dialog.edited()
        assert value['sample_rate_hz']=='1e'
        assert value['channels'][0]['role']=='measurement'
        assert value['channels'][0]['calibration']['uncertainty']['k'] is None
        dialog.reject()
    finally:dialog.close()
