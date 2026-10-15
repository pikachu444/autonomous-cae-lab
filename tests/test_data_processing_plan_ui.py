import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QLabel
from apps.research.data_window import DataWindow
from apps.research.data_material_document_dialog import DataMaterialDocumentDialog
from apps.research.data_processing_dialog import DataProcessingPreviewDialog
from apps.research.data_processing_plan import open_processing_plan


def retained():
    return {'diagnostics': {'processing_record': {'id': 'Presult', 'source': dict(document_id='Tdata', job_id='Jraw', input_revision='Iraw', input_sha256='a' * 64)}},
            'responses': {'P11': dict(kind='series', measure='first_Piola', unit='MPa', value=[1., 2.], axes=[dict(name='time', unit='s', values=[0., 1.])])}}


def test_retained_stress_can_request_plan_but_preview_cannot():
    app = QApplication.instance() or QApplication([])
    result = retained()
    preview = DataProcessingPreviewDialog(result, allow_plan=True)
    assert preview.plan_button is None
    dialog = DataProcessingPreviewDialog(result, retained=True, allow_plan=True)
    assert dialog.plan_button.isEnabled()
    dialog._plan(); assert dialog.plan_requested and dialog.result() == QDialog.DialogCode.Accepted
    preview.close(); dialog.close(); app.processEvents()


def test_trial_review_does_not_connect_across_preserved_invalid_gap():
    app = QApplication.instance() or QApplication([])
    from apps.research.material_test_dialog import ExperimentDialog
    from caelab.material_document import default_draft
    result = retained()
    result['responses']['P11'].update(value=[1., 2., 4., 5.],
        axes=[dict(name='time', unit='s', values=[0., 1., 3., 4.])],
        segments=[{'rows': [0, 2]}, {'rows': [2, 4]}])
    dialog = ExperimentDialog(default_draft()['settings'], result)
    assert [list(line.get_xdata()) for line in dialog.figure.axes[0].lines] == [[0., 1.], [3., 4.]]
    assert len({line.get_color() for line in dialog.figure.axes[0].lines})==1
    preview=DataProcessingPreviewDialog(result,retained=True)
    assert len(preview.figure.axes[0].lines)==2
    assert len({line.get_color() for line in preview.figure.axes[0].lines})==1
    preview.close()
    dialog.close(); app.processEvents()


def test_host_only_stages_exact_retained_source_in_existing_plan_view(monkeypatch):
    app = QApplication.instance() or QApplication([])
    plan = dict(id='Nexisting', title='인장 피팅', kind='numerical', draft={'mode': 'fit', 'material': {'draft': {'backend': 'material.felupe'}}, 'variables': [], 'experiments': []})
    staged, reads = [], []
    class Client:
        def documents(self): reads.append('documents'); return {'documents': [deepcopy(plan)]}
    class PublicPlanView(QMainWindow):
        def __init__(self, client, *, document_id):
            super().__init__(); assert document_id == 'Nexisting'
            self.document = deepcopy(plan); self._busy = self._closed = False; self.message = QLabel()
        def stage_processed_trial(self, source, result): staged.append((source, result))
        def can_stage_processed_trial(self): return True
        def processed_trial_stage_pending(self): return False
    monkeypatch.setattr('apps.research.numerical_window.NumericalWindow', PublicPlanView)
    def choose(dialog): dialog.table.selectRow(0); dialog._choose(); return QDialog.DialogCode.Accepted
    monkeypatch.setattr(DataMaterialDocumentDialog, 'exec', choose)
    window = DataWindow(Client(), auto_open=False, poll_interval=0)
    result = retained(); before = deepcopy(result)
    try:
        assert open_processing_plan(window, result, 'P11')
        deadline = time.monotonic() + 5
        while not staged and time.monotonic() < deadline: app.processEvents(); QTest.qWait(10)
        assert len(staged) == 1 and reads == ['documents']
        assert staged[0][0] == {**result['diagnostics']['processing_record']['source'], 'processing_revision': 'Presult', 'response': 'P11'}
        assert staged[0][1] == result and result == before
    finally:
        window._allow_close = True; window.close()
        for target in window._processed_plan_windows: target.close()
        app.processEvents()


def test_new_plan_requires_explicit_material_choice_and_creates_once(monkeypatch):
    app = QApplication.instance() or QApplication([])
    from caelab.material_document import default_draft
    from caelab.numerical_document import from_material_document
    material = dict(id='Mchosen', kind='material', title='고무 인장', input_revision='Imaterial',
        generation=0, draft=default_draft())
    creates, staged, choices = [], [], []
    class Client:
        def documents(self): return {'documents': [deepcopy(material)]}
        def document_open(self, **arguments):
            creates.append(deepcopy(arguments))
            return dict(id='Nnew', **arguments)
    class PublicPlanView(QMainWindow):
        def __init__(self, client, *, document_id):
            super().__init__(); assert document_id == 'Nnew'
            self.document = dict(id=document_id); self._closed = False; self.message = QLabel()
        def stage_processed_trial(self, source, result): staged.append((source, result))
        def can_stage_processed_trial(self): return True
        def processed_trial_stage_pending(self): return False
    monkeypatch.setattr('apps.research.numerical_window.NumericalWindow', PublicPlanView)
    def choose(dialog):
        choices.append(dialog.windowTitle())
        if len(choices) == 1:
            assert not dialog.documents; dialog._create()
        else: dialog.table.selectRow(0); dialog._choose()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(DataMaterialDocumentDialog, 'exec', choose)
    window = DataWindow(Client(), auto_open=False, poll_interval=0)
    try:
        assert open_processing_plan(window, retained(), 'P11')
        deadline = time.monotonic() + 5
        while not staged and time.monotonic() < deadline: app.processEvents(); QTest.qWait(10)
        assert choices == ['피팅 계획 선택', '피팅할 재료 선택']
        assert creates == [dict(kind='numerical', title='고무 인장 피팅', draft=from_material_document(material))]
        assert len(staged) == 1
    finally:
        window._allow_close = True; window.close()
        for target in window._processed_plan_windows: target.close()
        app.processEvents()


@pytest.mark.parametrize('finish_ready',[True,False])
def test_host_waits_for_owner_read_and_preserves_terminal_message(monkeypatch,finish_ready):
    app=QApplication.instance() or QApplication([])
    plan=dict(id='Npending',kind='numerical',draft={'mode':'fit','material':{'draft':{'backend':'material.felupe'}}})
    stages=[]
    class Client:
        def documents(self): return {'documents':[deepcopy(plan)]}
    class PublicPlanView(QMainWindow):
        def __init__(self,client,*,document_id):
            super().__init__(); self.document=deepcopy(plan); self._closed=False
            self.pending=True; self.ready=False; self.message=QLabel('기존 읽기 결과')
        def stage_processed_trial(self,source,result): stages.append((source,result))
        def can_stage_processed_trial(self): return self.ready
        def processed_trial_stage_pending(self): return self.pending
    monkeypatch.setattr('apps.research.numerical_window.NumericalWindow',PublicPlanView)
    def choose(dialog): dialog.table.selectRow(0); dialog._choose(); return QDialog.DialogCode.Accepted
    monkeypatch.setattr(DataMaterialDocumentDialog,'exec',choose)
    window=DataWindow(Client(),auto_open=False,poll_interval=0)
    try:
        assert open_processing_plan(window,retained(),'P11')
        deadline=time.monotonic()+3
        while not window._processed_plan_windows and time.monotonic()<deadline:
            app.processEvents(); QTest.qWait(5)
        target=window._processed_plan_windows[0]
        QTest.qWait(100); app.processEvents(); assert not stages
        target.pending=False; target.ready=finish_ready
        QTest.qWait(100); app.processEvents()
        assert len(stages)==int(finish_ready) and target.message.text()=='기존 읽기 결과'
        if not finish_ready: assert '시험을 추가하지 못했습니다' in window.message.text()
        QTest.qWait(100); app.processEvents(); assert len(stages)==int(finish_ready)
    finally:
        window._allow_close=True; window.close()
        for target in window._processed_plan_windows: target.close()
        app.processEvents()
