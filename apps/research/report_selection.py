"""Preview exact retained samples before adding an immutable report section."""
from copy import deepcopy
from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QFormLayout,QVBoxLayout,
    QLineEdit,QSpinBox,QPushButton,QLabel)
from .data_window import _Read
from .reference_content import ReferenceContent
from caelab.report_document import check_selection


class ReportSelectionDialog(QDialog):
    def __init__(self,client,reference,response,parent=None,*,candidate_ids=None):
        super().__init__(parent)
        self.client=client; self.reference=deepcopy(reference); self.response=response
        self.candidate_ids=deepcopy(candidate_ids)
        self.selection=None; self._workers=[]; self._closed=False; self._serial=0
        self.setWindowTitle('보고서에 넣을 표본'); self.resize(950,700)
        layout=QVBoxLayout(self); form=QFormLayout()
        self.first=QSpinBox();self.last=QSpinBox()
        self.first.setRange(1,10_000_000);self.last.setRange(1,10_000_000);self.last.setValue(256)
        self.time=QLineEdit();self.time.setPlaceholderText('빈칸은 표본 구간, 입력하면 저장된 정확한 축 값')
        form.addRow('첫 표본',self.first);form.addRow('마지막 표본',self.last)
        form.addRow('정확한 시각 (원 축 단위)',self.time);layout.addLayout(form)
        self.read=QPushButton('선택한 값 읽기');self.read.clicked.connect(self.refresh);layout.addWidget(self.read)
        self.content=ReferenceContent();self.content.read.hide();layout.addWidget(self.content,1)
        self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('보고서에 추가')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        for widget in (self.first,self.last):widget.valueChanged.connect(self.invalidate)
        self.time.textChanged.connect(self.invalidate)
        if self.candidate_ids is not None:
            self.time.setEnabled(False)
            self.time.setPlaceholderText('선택 후보에 보존된 표본 구간')
        self.refresh()

    def invalidate(self,*_):
        self._serial+=1;self.selection=None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.message.setText('바뀐 구간을 읽은 뒤 추가하세요.')

    def requested(self):
        if self.first.value()>self.last.value():raise ValueError('첫 표본과 마지막 표본의 순서를 확인하세요.')
        result={'responses':[self.response],'rows':[self.first.value()-1,self.last.value()]}
        if self.time.text().strip():
            import math
            t=float(self.time.text())
            if not math.isfinite(t):raise ValueError('유효한 축 값을 입력하세요.')
            result.pop('rows');result['time_range']=[t,t]
        if self.candidate_ids is not None:result['candidate_ids']=self.candidate_ids
        return result

    def refresh(self):
        if self._workers:return
        self.invalidate()
        try:selection=self.requested()
        except ValueError as error:self.message.setText(str(error));return
        serial=self._serial
        reference={'kind':'result',**self.reference,'selection':selection}
        def read():
            payload=self.client.research_reference(reference)
            check_selection(reference,payload)
            return serial,selection,payload
        worker=_Read(read);self._workers.append(worker)
        worker.signals.finished.connect(self.finished_read,Qt.ConnectionType.QueuedConnection)
        self.read.setEnabled(False);QThreadPool.globalInstance().start(worker)

    @Slot(object,object)
    def finished_read(self,value,error):
        self._workers=[]
        if self._closed:return
        self.read.setEnabled(True)
        if error:self.message.setText(str(error));return
        serial,selection,payload=value
        if serial!=self._serial:return
        self.selection=deepcopy(selection);self.content.set_payload(payload,label='보고서에 고정할 값')
        self.content.read.hide()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.message.setText('표시한 원행·값·단위를 추가합니다. 원 창의 선택은 이후 변경해도 반영되지 않습니다.')

    def accept(self):
        if self.selection is not None:super().accept()

    def done(self,result):
        self._closed=True
        for worker in self._workers:worker.abandon()
        super().done(result)
