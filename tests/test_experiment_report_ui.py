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
        window.fields['a'].setText('1e');window.fields['a'].textEdited.emit('1e')
        assert '미적용' in window.message.text()
        window.refresh_preview()
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
        for index in (0,1):
            window.sections.setCurrentRow(index);window.edit_section()
            window.section_text.setPlainText('미적용 '+str(index));window.close_editor()
        assert len(window._edit_buffers)==2
        before=deepcopy(window.draft)
        assert window.use_study({}) is False
        assert window.draft==before and len(window._edit_buffers)==2
        for index in (0,1):
            window.sections.setCurrentRow(index);window.edit_section();window.cancel_section();window.close_editor()
        assert not window._edit_buffers
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
        assert window.close()  # Reopening follows the accepted owner-close boundary.
        app.processEvents()
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


def test_retained_calibration_is_read_without_recalculation_and_unknown_kind_survives(app,monkeypatch):
    from caelab.experiment_calibration import calibrate
    import apps.research.experiment_dialogs as dialogs
    recipe=calibration();recipe['uncertainty']['kind']=None
    values,audit=calibrate([.001,.005],recipe)
    response={'unit':'N','calibration':recipe,'raw_samples':{**audit,
        'value':[.001,.005],'transformed_value':values.tolist(),'source_rows':[1,4]}}
    monkeypatch.setattr(dialogs,'calibrate',lambda *args:(_ for _ in ()).throw(AssertionError('retained read recalculated')))
    dialog=CalibrationDialog(None,mapping(recipe)['columns']['force'],None,retained_response=response)
    try:
        assert dialog.ukind.currentData() is None
        assert dialog.edited()['uncertainty']['kind'] is None
        assert dialog.values.item(1,2).text()=='8.5'
        assert dialog.values.item(1,0).text()=='4'
        assert '보존' in dialog.message.text()
    finally:dialog.close()


def test_report_invalid_unknown_values_checks_and_nonconvergence_are_visible(app):
    from apps.research.report_pages import blocks
    result={'execution_status':'SUCCEEDED','converged':False,'termination_reason':'MAX_ITERATIONS',
        'checks':[{'name':'energy_balance','passed':False,'value':.23,'limit':.05,'unit':'1'}],
        'responses':{
            'invalid':{'kind':'series','value':[7.,8.],'unit':'N','valid':False,'reason':'sensor failed',
                'axes':[{'name':'time','unit':'s','values':[0.,1.]}]},
            'unknown':{'kind':'series','value':[3.],'unit':'N',
                'axes':[{'name':'time','unit':'s','values':[0.]}]},
            'scalar':{'kind':'scalar','value':5.,'unit':'N','valid':False,'reason':'inadmissible'}}}
    content={'kind':'result','result':result}
    output=list(blocks(content))
    curves=[v for kind,v in output if kind=='curve']
    assert curves[0]['mask']==[False,False] and curves[1]['mask']==[None]
    assert curves[0]['y']==[7.,8.]
    text=markdown({'title':'판정 보존','sections':[section('계산',asset={'id':'Acheck'})]},
        {'Acheck':{'source_status':'AVAILABLE','content':content,'reference':{}}})
    for evidence in ('미수렴','MAX_ITERATIONS','energy_balance','0.23','0.05','실패','sensor failed','행 판정 없음','inadmissible'):
        assert evidence in text


def test_identification_lost_save_reply_retry_keeps_new_question(app,monkeypatch):
    from apps.research.identification_window import IdentificationWindow
    import apps.research.study_window as study_module
    monkeypatch.setattr(IdentificationWindow,'_read',lambda self:None)
    class Child:
        def __init__(self,*args,**kwargs):pass
        def show(self):pass
    monkeypatch.setattr(study_module,'StudyWindow',Child)
    class SaveDouble:
        def __init__(self):
            from caelab.study_document import default_draft
            self.doc={'id':'Sstudy','session_id':'Ssession','generation':0,'draft':default_draft()}
            self.receipts={};self.fail=True
        def document_read(self,identifier):return deepcopy(self.doc)
        def document_command(self,identifier,operation,arguments,**kwargs):
            key=kwargs['command_id']
            if key not in self.receipts:
                if operation=='study.update':self.doc['draft']=deepcopy(arguments['draft'])
                self.doc['generation']+=1
                self.receipts[key]={'document':deepcopy(self.doc)}
            if operation=='document.save' and self.fail:
                self.fail=False
                raise OSError('reply lost after save')
            return deepcopy(self.receipts[key])
    client=SaveDouble();window=IdentificationWindow(client,'Nplan','Jfit')
    try:
        window._study=deepcopy(client.doc)
        window._payload=({'session_id':'Ssession'},{},{'kind':'fit'},{'document_id':'Nplan','job_id':'Jfit'})
        window._run=lambda fn,accepted:accepted(fn())
        window.question.setText('시험 A');window.note.setPlainText('근거 A')
        with pytest.raises(OSError):window.save_study()
        window.question.setText('아직 전송하지 않은 B');window.note.setPlainText('근거 B')
        window.save_study()
        assert len(client.receipts)==2
        assert [r['question'] for r in client.doc['draft']['next_observations']]==['시험 A']
        assert window.question.text()=='아직 전송하지 않은 B' and window.note.toPlainText()=='근거 B'
    finally:window.close()


def test_summary_reduction_dialog_reads_exact_final_value_without_curve(app):
    from apps.research.report_selection import ReportSelectionDialog
    from caelab.research_workflows import _candidate_reference_view
    result={'execution_status':'SUCCEEDED','candidates':[{'candidate_id':'Cselected','values':{'E':1000.},
        'execution_status':'SUCCEEDED','responses':{},'response_reductions':[
            {'response':'stress','kind':'scalar','original_kind':'series','reduction':'max','value':8.,'unit':'MPa'},
            {'response':'stress','kind':'scalar','original_kind':'series','reduction':'final','value':3.,'unit':'MPa'}]}]}
    class ReadDouble:
        def research_reference(self,reference):
            return {'kind':'result','status':'AVAILABLE','reference':reference,
                'result':_candidate_reference_view(result,reference['selection'])}
    dialog=ReportSelectionDialog(ReadDouble(),{'document_id':'Nsaved'},'stress',
        candidate_ids=['Cselected'],reduction_index=1)
    try:
        dialog.show();wait(app,lambda:dialog.selection is not None,dialog)
        assert dialog.selection=={'responses':['stress'],'candidate_ids':['Cselected'],'reduction_index':1}
        assert not dialog.time.isEnabled() and not dialog.first.isEnabled()
        assert '최종값' in dialog.content.values.item(0,0).text()
        assert float(dialog.content.values.item(0,1).text())==3.
        assert dialog.content.values.item(0,2).text()=='MPa'
        dialog.accept()
    finally:
        dialog.close();assert QThreadPool.globalInstance().waitForDone(5000)
