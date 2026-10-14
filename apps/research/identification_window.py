"""Read retained fit diagnosis and record an explicit next test, without evaluation."""
from copy import deepcopy
import uuid

from PySide6.QtCore import QThreadPool, Qt, Slot
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.study_document import default_draft
from .data_window import _Read
from .appearance import configure_plot_fonts
from .report_pages import value_text


class IdentificationWindow(QDialog):
    def __init__(self,client,document_id,job_id,parent=None):
        super().__init__(parent)
        self.client=client;self.document_id=document_id;self.job_id=job_id
        self._workers=[];self._closed=False;self._payload=None;self._study=None
        self._command_ids={};self._submitted=None
        self.setWindowTitle('계수 식별과 다음 시험');self.resize(1100,780)
        configure_plot_fonts()
        root=QVBoxLayout(self)
        self.summary=QLabel('선택한 피팅 결과를 읽고 있습니다…');self.summary.setWordWrap(True);root.addWidget(self.summary)
        split=QSplitter(Qt.Orientation.Vertical)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['계수','계산 값','단위','역할','국소 구분','경계'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        split.addWidget(self.table)
        self.figure=Figure();self.canvas=FigureCanvasQTAgg(self.figure);self.canvas.setMinimumHeight(220);split.addWidget(self.canvas)
        split.setSizes([230,350]);root.addWidget(split,1)
        self.question=QLineEdit();self.question.setPlaceholderText('다음 시험에서 무엇을 확인할까요?')
        root.addWidget(self.question)
        self.note=QPlainTextEdit();self.note.setPlaceholderText('미식별 조합을 구분할 조건과 판단 근거')
        self.note.setMaximumHeight(110);root.addWidget(self.note)
        row=QHBoxLayout();self.keep=QPushButton('연구 기록에 저장');self.keep.clicked.connect(self.save_study);row.addWidget(self.keep)
        report=QPushButton('보고서 만들기…');report.clicked.connect(self.open_report);row.addWidget(report)
        close=QPushButton('닫기');close.clicked.connect(self.reject);row.addWidget(close);root.addLayout(row)
        self.message=QLabel('고정 계수는 식별 성공으로 세지 않습니다.');self.message.setWordWrap(True);root.addWidget(self.message)
        self._read()

    def _run(self,fn,callback):
        if self._workers or self._closed:return False
        self._callback=callback
        worker=_Read(fn);self._workers.append(worker)
        worker.signals.finished.connect(self._finished,Qt.ConnectionType.QueuedConnection)
        self.keep.setEnabled(False);QThreadPool.globalInstance().start(worker);return True

    @Slot(object,object)
    def _finished(self,value,error):
        self._workers=[];self.keep.setEnabled(True)
        if self._closed:return
        if error:self.message.setText('읽기/저장 실패. 입력은 유지됩니다. '+str(error))
        else:self._callback(value)

    def _read(self):
        def read():
            document=self.client.document_read(self.document_id)
            result=self.client.document_result(self.document_id,self.job_id)
            reference=self.client.document_result_reference(self.document_id,self.job_id)
            run=next(r for r in document['runs'] if r['job_id']==self.job_id)
            return document,run,result,reference
        self._run(read,self.show_result)

    def show_result(self,payload):
        self._payload=payload
        _,run,result,_=payload
        if result.get('kind')!='fit':
            self.summary.setText('선택한 계산은 피팅 결과가 아닙니다.');self.keep.setEnabled(False);return
        diagnosis=result.get('identification') or {}
        method=diagnosis.get('method')
        available=method=='scaled_residual_jacobian_svd' and diagnosis.get('parameter_values')==result.get('parameters')
        states={'DISTINGUISHABLE_LOCAL':'국소 구분 가능','UNRESOLVED_LOCAL':'미식별 조합'}
        info={p['id']:p for p in diagnosis.get('parameters',[])} if available else {}
        variables=deepcopy(run['draft'].get('variables') or result.get('variables',[]))
        self.table.setRowCount(len(variables))
        for i,v in enumerate(variables):
            free=v.get('free',True);p=info.get(v['id'],{})
            status=states.get(p.get('status'),'진단 미확인') if free else '고정 (식별 안 함)'
            value=(result.get('parameters') or {}).get(v['id']) if free else v.get('value')
            cells=[v.get('label',v['id']),value,v.get('unit',''), '피팅' if free else '고정',status,
                   '하한' if p.get('active_bound')==-1 else '상한' if p.get('active_bound')==1 else '']
            for j,c in enumerate(cells):self.table.setItem(i,j,QTableWidgetItem(value_text(c)))
        self.figure.clear()
        if available and diagnosis.get('singular_values'):
            ax=self.figure.subplots()
            spectrum=diagnosis['singular_values']
            ax.bar(range(1,len(spectrum)+1),spectrum)
            ax.axhline(diagnosis['absolute_rank_tolerance'],linestyle='--',label='구분 기준')
            ax.set_xlabel('독립 계수 방향');ax.set_ylabel('정규화된 민감도');ax.legend()
            self.summary.setText('최종 피팅점: 독립 방향 '+str(diagnosis['jacobian_rank'])+' / '+str(diagnosis['coefficient_count'])+
                '\n명시한 탐색범위로 정규화한 잔차 Jacobian SVD. 전역 유일성과 측정 불확실성은 미확인입니다.')
        else:self.summary.setText('이 결과에는 완전한 식별 진단이 없습니다. '+str(diagnosis.get('reason','재계산하지 않았습니다.')))
        self.figure.tight_layout();self.canvas.draw_idle()

    def save_study(self):
        if not self._payload or self._workers:return
        if not self.question.text().strip():
            self.message.setText('다음 시험 질문을 작성하세요.');return
        submitted=(self.question.text(),self.note.toPlainText())
        # Retries use the originally submitted snapshot/IDs. Later typing is not lost.
        if self._submitted is None:self._submitted=submitted
        question,note=self._submitted
        def save():
            if self._study is None:
                self._study=self.client.result_followup(self._payload[3],'study',
                    session_id=self._payload[0]['session_id'],
                    command_id=self._command_ids.setdefault('create','C'+uuid.uuid4().hex))['document']
            # Keep the submitted draft/generation through a lost reply. Never replace
            # unrelated hypotheses or notes if this follow-up already exists.
            if not hasattr(self,'_study_update'):
                document=self.client.document_read(self._study['id'])
                draft=deepcopy(document['draft'])
                draft['next_observations'].append({'id':'O'+uuid.uuid4().hex,
                    'question':question,'hypothesis_ids':[],'evidence_ids':['Eresult'],
                    'status':'PLANNED','note':note})
                self._study_update=(document,draft,'C'+uuid.uuid4().hex)
            document,draft,command_id=self._study_update
            receipt=self.client.document_command(document['id'],'study.update',{'draft':draft},
                session_id=document['session_id'],expected_generation=document['generation'],command_id=command_id)
            document=receipt['document']
            return self.client.document_command(document['id'],'document.save',{},
                session_id=document['session_id'],expected_generation=document['generation'],
                command_id=self._command_ids.setdefault('save','C'+uuid.uuid4().hex))
        def saved(receipt):
            self._study=receipt['document']
            self._submitted=None;self._study_update=None
            del self._study_update
            self._command_ids.pop('save',None)
            from .study_window import StudyWindow
            window=StudyWindow(self.client,document_id=self._study['id'])
            self._children=getattr(self,'_children',[])+[window];window.show()
            # Same UI text is one completed action, not a second submission.
            if (self.question.text(),self.note.toPlainText())==(question,note):
                self.question.clear();self.note.clear()
            self.message.setText('다음 시험을 저장했습니다. 새 계산은 제출하지 않았습니다.')
        self._run(save,saved)

    def open_report(self):
        if not self._payload:return
        from .report_window import ReportWindow
        reference={'kind':'result',**self._payload[3],'selection':{'metadata_only':True}}
        window=ReportWindow(self.client,reference=reference)
        self._children=getattr(self,'_children',[])+[window];window.show()

    def done(self,result):
        self._closed=True
        for worker in self._workers:worker.abandon()
        super().done(result)
