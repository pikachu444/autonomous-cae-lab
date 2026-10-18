"""Native Qt editor for explicit experiment uncertainty / final-point diagnosis.

Uses existing Numerical Plan, command queue receipts, cancellation and saved
results. No JSON is required in the main editor; IDs are in explicit diagnostics.
"""
from copy import deepcopy
import json
import math
import uuid

from PySide6.QtCore import Qt, QTimer, QThreadPool, Slot, QObject, QEvent
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QTabWidget,QWidget,QTableWidget,QTableWidgetItem,QComboBox,QLineEdit,QSpinBox,
    QDoubleSpinBox,QHeaderView,QSplitter,QPlainTextEdit,QMessageBox)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.experiment_analysis_actions import ExplicitAnalysisAction,read_analysis_source,source_request_identity,save_analysis_study
from caelab.experiment_analysis_service import uncertainty_request,final_request
from caelab.experiment_analysis_reporting import coordinate,blocks,diagnosis_tables,STATES,UNKNOWN
from caelab.experiment_final_diagnosis import evaluation_plan,_admission
from caelab.experiment_uncertainty import covariance,plain
from caelab.storage import canonical_hash
from .data_window import _Read,number_or_raw,TERMINAL
from .appearance import configure_plot_fonts
from .report_pages import value_text
from .experiment_followup_dialog import choose_next_observation


class _AnalysisCloseGuard(QObject):
    """Let each owned analysis protect its edits before the source is deleted."""
    def __init__(self,source,children):
        super().__init__(source);self.children=children
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Close:
            from shiboken6 import isValid
            for child in list(self.children):
                if isValid(child) and not child.close():
                    event.ignore();return True
        return False


class ExperimentAnalysisWindow(QDialog):
    def __init__(self,client,*,source=None,evidence_reference=None,document_id=None,parent=None):
        super().__init__(parent)
        if sum(v is not None for v in (source,evidence_reference,document_id))!=1:
            raise ValueError('원 시험·후보 근거·저장 Plan 중 하나를 선택하세요.')
        self.client=client;self.source=deepcopy(source);self.evidence_reference=deepcopy(evidence_reference)
        self._document_id=document_id;self.document=None;self.result=None;self.job_id=None
        self._view=None;self._worker=None;self._worker_writes=False;self._retired_workers=[]
        self._closed=False;self._populating=True;self.dirty=False;self._shown_job_id=None
        self._pending=None;self._study_pending=None;self._children=[];self._loading_request=None;self._covariance_units=None
        self.setWindowTitle('시험 분석');self.resize(1160,790)
        configure_plot_fonts();layout=QVBoxLayout(self)
        self.summary=QLabel('보존한 원값을 읽고 있습니다. 새 평가를 실행하지 않습니다.');self.summary.setWordWrap(True);layout.addWidget(self.summary)
        split=QSplitter(Qt.Orientation.Vertical);layout.addWidget(split,1)
        self.tabs=QTabWidget();split.addWidget(self.tabs)
        inputs=QWidget();form=QVBoxLayout(inputs)
        self.inputs=QTableWidget(0,8);self.inputs.setHorizontalHeaderLabels(
            ['원값 / 계수','원값','원단위','종류','불확실성 값','불확실성 단위','포함인자 k','제공 근거'])
        self.inputs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.inputs.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Interactive)
        self.inputs.horizontalHeader().setStretchLastSection(True);self.inputs.itemChanged.connect(self._changed)
        form.addWidget(self.inputs);self.tabs.addTab(inputs,'입력·계수')
        dependency=QWidget();d=QVBoxLayout(dependency);row=QHBoxLayout()
        self.dependence=QComboBox()
        for label,key in [('상관 미확인','UNKNOWN'),('독립이라고 명시 제공','independent_declared'),('상관행렬 제공','correlation'),('공분산행렬 제공','covariance')]:self.dependence.addItem(label,key)
        row.addWidget(self.dependence);self.dependence_note=QLineEdit();self.dependence_note.setPlaceholderText('독립성 또는 행렬의 제공 근거');row.addWidget(self.dependence_note,1)
        d.addLayout(row);self.matrix=QTableWidget();d.addWidget(self.matrix)
        d.addWidget(QLabel('빈 성분은 미확인입니다. 공분산 행·열의 단위는 각 원변수의 원단위입니다.'))
        self.tabs.addTab(dependency,'상관·공분산')
        diagnosis=QWidget();diagnosis_layout=QVBoxLayout(diagnosis)
        self.diagnosis_summary=QLabel();self.diagnosis_summary.setWordWrap(True);diagnosis_layout.addWidget(self.diagnosis_summary)
        self.diagnosis_summary.setMinimumHeight(65)
        self.coefficients=QTableWidget();self.directions=QTableWidget()
        for table in (self.coefficients,self.directions):
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True);diagnosis_layout.addWidget(table,1)
        self.direction_label=QLabel('보존한 국소 미식별 방향입니다. 새 시험의 효과나 전역 유일성을 뜻하지 않습니다.')
        self.direction_label.setWordWrap(True);diagnosis_layout.addWidget(self.direction_label)
        self.tabs.addTab(diagnosis,'계수 진단');self.tabs.setTabVisible(2,False)
        self.dependence.currentIndexChanged.connect(self._dependence_changed)
        self.dependence_note.textEdited.connect(self._changed);self.matrix.itemChanged.connect(self._changed)
        bottom=QWidget();b=QVBoxLayout(bottom)
        self.figure=Figure(layout='tight');self.canvas=FigureCanvasQTAgg(self.figure);self.canvas.setMinimumHeight(200);b.addWidget(self.canvas,1)
        self.results=QTableWidget();self.results.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);b.addWidget(self.results)
        split.addWidget(bottom);split.setSizes([320,330])
        options=QHBoxLayout();self.axis=QComboBox();self.axis.addItem('축 불확실성 미확인','UNKNOWN');self.axis.addItem('축 좌표 고정 명시','fixed_coordinates_declared')
        self.axis.currentIndexChanged.connect(self._changed);options.addWidget(self.axis)
        self.step=QDoubleSpinBox();self.step.setDecimals(8);self.step.setRange(1e-8,1e-2);self.step.setValue(1e-4);self.step.valueChanged.connect(self._cost_changed)
        self.step_label=QLabel('계수 범위 대비 차분 간격');options.addWidget(self.step_label);options.addWidget(self.step)
        self.budget=QSpinBox();self.budget.setRange(1,1000000);self.budget.valueChanged.connect(self._changed)
        self.budget_label=QLabel('명시 평가 예산');options.addWidget(self.budget_label);options.addWidget(self.budget)
        self.cost=QLabel();self.cost.setWordWrap(True);options.addWidget(self.cost,1);layout.addLayout(options)
        for control in (self.axis,self.step,self.step_label,self.budget,self.budget_label):control.hide()
        actions=QHBoxLayout();layout.addLayout(actions)
        followup=QHBoxLayout();layout.addLayout(followup)
        self.save=QPushButton('계획 저장');self.run=QPushButton('명시 실행');self.cancel=QPushButton('계산 취소 요청')
        self.run.setProperty('appearanceRole','primary')
        self.read=QPushButton('결과 다시 읽기');self.study=QPushButton('다음 시험 기록…');self.report=QPushButton('보고서…');self.details=QPushButton('진단 정보…')
        for button,slot in [(self.save,lambda:self._start('save')),(self.run,lambda:self._start('run')),(self.cancel,self._cancel),
            (self.read,self._read_result),(self.study,self._study),(self.report,self._report),(self.details,self._details)]:
            button.setAutoDefault(False);button.clicked.connect(slot)
            (actions if button in (self.save,self.run,self.cancel,self.read) else followup).addWidget(button)
        self.message=QLabel('미제공값을 잔차·독립성·0으로 보충하지 않습니다.');self.message.setWordWrap(True);layout.addWidget(self.message)
        from .observation_uncertainty_dialog import install_action
        install_action(self,followup)
        self.output_k=QLineEdit();self.output_k.setMaximumWidth(90);self.output_k.setPlaceholderText('미지정');self.output_k.textEdited.connect(self._changed)
        self.output_k_label=QLabel('출력 포함인자 k');options.addWidget(self.output_k_label);options.addWidget(self.output_k)
        self.output_k.hide();self.output_k_label.hide()
        self.timer=QTimer(self);self.timer.setInterval(700);self.timer.timeout.connect(self._poll)
        self._update_actions();self._call(self._load,self._loaded)

    def _load(self):
        if self._document_id is not None:
            doc=self.client.document_read(self._document_id);request=doc['draft'].get('request',{})
            operation=request.get('operation')
            if operation not in ('experiment_uncertainty','identification_final'):raise ValueError('시험 분석 Plan이 아닙니다.')
            inputs=request['inputs'];source=inputs.get('source');ref=inputs.get('evidence_reference')
            if doc.get('runs'):
                job=doc['runs'][-1]['job_id']
                try:
                    result=self.client.document_result(doc['id'],job)
                    if source_request_identity(request)!=source_request_identity(result['experiment_analysis']['request']):
                        view=read_analysis_source(self.client,source=source,evidence_reference=ref,plan_mask=inputs.get('plan_mask'))
                        return view,doc,result,job,request,source,ref
                    problem=result['experiment_analysis']['source_problem']
                    source_ref=source.get('reference',{}) if source else ref['source']
                    keys=('document_id','job_id','input_revision','input_sha256','result_sha256')
                    view={'problem':problem,'source_reference':{k:source_ref[k] for k in keys if k in source_ref},'session_id':doc['session_id']}
                    return view,doc,result,job,request,source,ref
                except (KeyError,ValueError,FileNotFoundError):
                    # A damaged TERMINAL result is not an unfinished input.
                    # Never hide integrity failures by silently selecting a source.
                    run=doc['runs'][-1]
                    if run.get('retained_result') or run.get('retention_complete'):raise
                    if run.get('retained_state',run.get('state')) in TERMINAL-{'INTERRUPTED'}:raise
                    status=self.client.status(job)
                    if status['state']=='INTERRUPTED' and not status.get('result_refs'):
                        view=read_analysis_source(self.client,source=source,evidence_reference=ref,plan_mask=inputs.get('plan_mask'))
                        view['interrupted_without_result']=True
                        return view,doc,None,None,request,source,ref
                    if status['state'] in TERMINAL:raise
            view=read_analysis_source(self.client,source=source,evidence_reference=ref,plan_mask=inputs.get('plan_mask'))
            return view,doc,None,None,request,source,ref
        view=read_analysis_source(self.client,source=self.source,evidence_reference=self.evidence_reference)
        return view,None,None,None,None,self.source,self.evidence_reference

    def _call(self,fn,done,*,write=False):
        if self._closed or self._worker is not None:return False
        self._callback=done;worker=_Read(fn);self._worker=worker
        self._worker_writes=write
        worker.signals.finished.connect(self._finished,Qt.ConnectionType.QueuedConnection)
        self._update_actions();QThreadPool.globalInstance().start(worker);return True

    @Slot(object,object)
    def _finished(self,value,error):
        self._worker=None
        if self._closed:return
        if error:self.message.setText('작업 결과 미확인. 원 입력을 유지했습니다. 같은 버튼으로 같은 요청을 다시 시도하세요. '+str(error))
        else:
            try:self._callback(value)
            except Exception as exc:self.message.setText('표시/연결 실패. 보존 원결과는 변경하지 않았습니다. '+str(exc))
        self._update_actions()

    def _label(self,v):
        if v.get('label') and not v.get('operand'):return v['label']
        if v.get('operand'):
            return v['label']+' / '+('원행 '+str(v['source_row']) if 'source_row' in v else '표본 '+str(v['sample_index']+1))
        if v.get('source_row') is not None:return '원행 '+str(v['source_row'])
        if v.get('raw_ref'):return '원행 '+str(v['raw_ref'].get('source_row','미확인'))
        return {'a':'기울기 a','x0':'입력 영점','b':'출력 오프셋'}.get(v.get('coefficient',v['id']),v['id'])

    def _loaded(self,payload):
        self._view,self.document,self.result,self.job_id,request,self.source,self.evidence_reference=payload
        self._loading_request=deepcopy(request)
        self._populating=True;p=self._view['problem'];final=self.evidence_reference is not None
        difference=p.get('kind')=='comparison_difference' or p.get('comparison_difference',False)
        chain=p.get('kind')=='observation_chain'
        self.cost.setVisible(not difference and not chain)
        self.tabs.setTabText(0,'원 측정값' if difference else '입력·계수')
        self.inputs.setHorizontalHeaderItem(0,QTableWidgetItem('원 측정값' if difference else '원값 / 계수'))
        self.setWindowTitle('최종점 계수 진단' if final else '차이의 불확실성' if p.get('kind')=='comparison_difference' else '제공 불확실성 전파')
        self.run.setText('최종점 진단' if final else '전파 계산')
        spec=(request or {}).get('inputs',{}).get('specification',{})
        self.output_k.setVisible(chain);self.output_k_label.setVisible(chain)
        self.output_k.setText(str(spec['output_coverage_factor']) if spec.get('output_coverage_factor') is not None else '')
        self._observation_button.setVisible(not final)
        self.inputs.setRowCount(len(p['variables']))
        kind_width=0
        for i,v in enumerate(p['variables']):
            supplied=spec.get('uncertainties',{}).get(v['id']) or {}
            val=p.get('candidate',{}).get('values',{}).get(v['id'],v.get('value'))
            for col,text in [(0,self._label(v)),(1,value_text(val)),(2,v['unit']),(4,value_text(supplied['value']) if supplied.get('value') is not None else ''),
                (5,supplied.get('unit',v['unit'])),(6,str(supplied['k']) if supplied.get('k') is not None else ''),(7,supplied.get('note',''))]:
                item=QTableWidgetItem(text)
                if col<3 or final:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.inputs.setItem(i,col,item)
            kind=QComboBox()
            for text,key in [('미확인','UNKNOWN'),('표준','standard'),('확장','expanded')]:kind.addItem(text,key)
            kind.setCurrentIndex(max(0,kind.findData(supplied.get('kind','UNKNOWN'))));kind.setEnabled(not final);kind.currentIndexChanged.connect(self._changed)
            self.inputs.setCellWidget(i,3,kind)
            kind_width=max(kind_width,kind.sizeHint().width())
        if kind_width:self.inputs.setColumnWidth(3,kind_width+12)
        self.tabs.setTabEnabled(1,not final);self.axis.setVisible(not final);self.step.setVisible(final);self.step_label.setVisible(final)
        self.budget.setVisible(final);self.budget_label.setVisible(final)
        self._covariance_units=deepcopy((spec.get('dependence') or {}).get('units'))
        self.dependence.setCurrentIndex(max(0,self.dependence.findData((spec.get('dependence') or {}).get('kind','UNKNOWN'))))
        self.dependence_note.setText((spec.get('dependence') or {}).get('note',''))
        self._dependence_changed()
        matrix=(spec.get('dependence') or {}).get('matrix',[])
        for i,row in enumerate(matrix):
            for j,x in enumerate(row):
                if x is not None:self.matrix.setItem(i,j,QTableWidgetItem(str(x)))
        axis_value=spec.get('axis_uncertainty','UNKNOWN')
        if self.axis.findData(axis_value)<0:self.axis.addItem('보존한 축 입력 (전파 미지원)',axis_value)
        self.axis.setCurrentIndex(self.axis.findData(axis_value))
        self.step.setValue((request or {}).get('inputs',{}).get('relative_step',1e-4))
        self._cost_changed();cost=self._cost_number()
        self.budget.setValue((request or {}).get('budget',{}).get('evaluations',max(1,cost)))
        self.summary.setText('최종 선택 계수의 원 피팅 잔차와 가중치, 포함 구간을 그대로 사용합니다.' if final else
            '관측 A와 예측 B의 저장된 정렬·선택으로 차이 B−A를 계산합니다. 두 자료 사이의 상관도 제공하세요.' if difference else
            '보존한 시험의 원 교정값과 제공 출력 불확실성은 바꾸지 않습니다.')
        if chain:self.summary.setText('저장한 순서로 관측량을 변환합니다. 원 교정/처리 값과 비교는 보존하며, 제공한 불확실성과 공유 입력의 상관을 사용합니다.')
        self._populating=False;self.dirty=False
        self.tabs.setTabVisible(2,final)
        if final:self.tabs.setCurrentIndex(2)
        if self.result:self._show_result(self.result)
        elif not final:
            x,label=coordinate(p);self.figure.clear();ax=self.figure.subplots();ax.plot(x,p['values']);ax.set_xlabel(label);ax.set_ylabel(('차이 B−A' if difference else '관측 변환값' if chain else '원 교정값')+' ['+p['unit']+']');self.canvas.draw()
        if self._view.get('interrupted_without_result'):
            self.message.setText('이전 계산이 중단되어 결과가 없습니다. 입력을 확인한 뒤 새 계산을 명시적으로 실행하세요.')
        self._update_actions()

    def _changed(self,*_):
        if not self._populating:self.dirty=True;self.message.setText('미저장 입력입니다. 이전 결과는 수정하지 않았습니다.')

    def _dependence_changed(self,*_):
        if self._view is not None and self.dependence.currentData() in ('correlation','covariance'):
            variables=self._view['problem']['variables'];n=len(variables)
            if self.matrix.rowCount()!=n:
                self.matrix.setRowCount(n);self.matrix.setColumnCount(n)
            units=self._covariance_units or [v['unit'] for v in variables]
            labels=[self._label(v)+' ['+(units[i] if self.dependence.currentData()=='covariance' else '상관')+']' for i,v in enumerate(variables)]
            self.matrix.setHorizontalHeaderLabels(labels);self.matrix.setVerticalHeaderLabels(labels)
        self.matrix.setEnabled(self.dependence.currentData() in ('correlation','covariance'));self._changed()

    def _cost_number(self):
        if self._view is None or self.evidence_reference is None or (self._loading_request or {}).get('inputs',{}).get('reuse_result'):return 0
        p=self._view['problem']
        return 0 if _admission(p) else evaluation_plan(p,self.step.value())['model_evaluations']

    def _cost_changed(self,*_):
        try:self.cost.setText('추가 모델 평가 '+str(self._cost_number())+'회 · AI 호출 0회')
        except ValueError as error:self.cost.setText(str(error))
        self._changed()

    def request_value(self):
        if self.evidence_reference is not None:
            return final_request(self.evidence_reference,evaluations=self.budget.value(),relative_step=self.step.value(),
                purpose=(self._loading_request or {}).get('purpose','최종 선택 계수의 국소 식별 진단'),
                reuse_result=(self._loading_request or {}).get('inputs',{}).get('reuse_result'))
        p=self._view['problem'];uncertainties={}
        text=lambda i,c:self.inputs.item(i,c).text().strip() if self.inputs.item(i,c) else ''
        for i,v in enumerate(p['variables']):
            previous_record=deepcopy(((self._loading_request or {}).get('inputs',{}).get('specification',{}).get('uncertainties',{}).get(v['id'])) or {})
            uncertainties[v['id']]={**previous_record,'kind':self.inputs.cellWidget(i,3).currentData(),
                'value':number_or_raw(text(i,4)) if text(i,4) else None,'unit':text(i,5),
                'k':number_or_raw(text(i,6)) if text(i,6) else None,'note':text(i,7)}
        kind=self.dependence.currentData();dep={'kind':kind}
        if kind!='UNKNOWN':dep['note']=self.dependence_note.text()
        if kind in ('correlation','covariance'):
            n=len(p['variables']);dep['order']=[v['id'] for v in p['variables']]
            dep['matrix']=[[number_or_raw(self.matrix.item(i,j).text().strip()) if self.matrix.item(i,j) and self.matrix.item(i,j).text().strip() else None for j in range(n)] for i in range(n)]
            if kind=='covariance':dep['units']=deepcopy(self._covariance_units or [v['unit'] for v in p['variables']])
        previous=deepcopy((self._loading_request or {}).get('inputs',{}))
        specification=deepcopy(previous.get('specification',{}))
        specification.update(uncertainties=uncertainties,dependence=dep,axis_uncertainty=self.axis.currentData())
        if p.get('kind')=='observation_chain':specification['output_coverage_factor']=number_or_raw(self.output_k.text().strip()) if self.output_k.text().strip() else None
        return uncertainty_request(self.source,specification,plan_mask=previous.get('plan_mask'),
            purpose=(self._loading_request or {}).get('purpose','제공 불확실성 전파'))

    def _start(self,action):
        if self._view is None or self._worker is not None:return
        try:
            if self._pending is None:
                request=self.request_value()
                if action=='run':
                    if self.evidence_reference is not None and self.budget.value()<self._cost_number():raise ValueError('명시 예산이 필요한 실제 평가 횟수보다 작습니다.')
                    if self.evidence_reference is None:
                        s=request['inputs']['specification'];covariance(self._view['problem']['variables'],s['uncertainties'],s['dependence'])
                self._pending=ExplicitAnalysisAction(request,action,source_reference=self._view['source_reference'],session_id=self._view['session_id'],document=self.document)
            if self._pending.action!=action:raise ValueError('미확정된 이전 저장/실행을 같은 버튼으로 먼저 확인하세요.')
        except ValueError as error:self.message.setText(str(error));return
        submitted=self._pending
        def completed(receipt):
            self.document=receipt['document'];self._pending=None
            if self.request_value()==submitted.request:self.dirty=False
            if 'job' in receipt:
                self.job_id=receipt['job']['id'];self.message.setText('명시 평가를 제출했습니다. 취소 요청과 실제 중단 확인은 구별합니다.');self.timer.start()
            else:self.message.setText('계획과 현재 보존 결과를 저장했습니다. 새 평가는 실행하지 않았습니다.')
        self._call(lambda:submitted.perform(self.client),completed,write=True)

    def _poll(self):
        if self._worker is not None or self.job_id is None:return
        job=self.job_id
        def loaded(status):
            if self.job_id!=job:return
            if status['state'] in TERMINAL:self.timer.stop();self._read_result()
            else:self.message.setText('계산 진행 중' if not status.get('cancel_requested') else '취소 요청됨 — 중단 확인 전')
        self._call(lambda:self.client.status(job),loaded)

    def _read_result(self):
        if self._view is None:
            return self._call(self._load,self._loaded)
        if self.document is None or self.job_id is None:return
        doc,job=self.document['id'],self.job_id
        def read():return self.client.document_read(doc),self.client.document_result(doc,job)
        def show(value):
            # Do not replace local input edits or attach a later result to another job.
            if (self.document['id'],self.job_id)!=(doc,job):return
            self.document,self.result=value;self._show_result(self.result)
        self._call(read,show)

    def _show_result(self,result):
        same_job=self.job_id is not None and self.job_id==self._shown_job_id
        selected=[(index.row(),index.column()) for index in self.results.selectedIndexes()] if same_job else []
        current=(self.results.currentRow(),self.results.currentColumn()) if same_job else (-1,-1)
        scroll=(self.results.verticalScrollBar().value(),self.results.horizontalScrollBar().value())
        self.result=result;content=list(blocks(result))
        if result.get('kind')=='experiment_identification':
            diagnosis=result.get('identification',{})
            self.diagnosis_summary.setText(STATES.get(diagnosis.get('status'),UNKNOWN)+
                ' — 최종 선택점의 일반 잔차 Jacobian 진단입니다.'+
                '\n전역 유일성과 측정 불확실성은 미확인입니다. 공학 승인 아님.'+
                ('\n'+str(result.get('failure_reason') or diagnosis.get('reason')) if result.get('failure_reason') or diagnosis.get('reason') else ''))
            for widget,(head,data) in zip((self.coefficients,self.directions),diagnosis_tables(result)):
                old_current=(widget.currentRow(),widget.currentColumn()) if same_job else (-1,-1)
                old_selection=[(index.row(),index.column()) for index in widget.selectedIndexes()] if same_job else []
                old_scroll=(widget.verticalScrollBar().value(),widget.horizontalScrollBar().value())
                widget.setColumnCount(len(head));widget.setHorizontalHeaderLabels(head);widget.setRowCount(len(data))
                for row,values in enumerate(data):
                    for column,item in enumerate(values):widget.setItem(row,column,QTableWidgetItem(value_text(item)))
                widget.clearSelection();widget.setCurrentCell(*old_current)
                for row,column in old_selection:
                    item=widget.item(row,column)
                    if item is not None:item.setSelected(True)
                if same_job:
                    widget.verticalScrollBar().setValue(old_scroll[0]);widget.horizontalScrollBar().setValue(old_scroll[1])
            self.coefficients.setMinimumHeight(self.coefficients.horizontalHeader().height()+
                min(3,self.coefficients.rowCount())*self.coefficients.verticalHeader().defaultSectionSize()+4)
            has_directions=bool(self.directions.rowCount())
            self.directions.setVisible(has_directions)
            self.direction_label.setText('보존한 국소 미식별 방향입니다. 새 시험의 효과나 전역 유일성을 뜻하지 않습니다.' if has_directions else
                '보존한 미식별 방향이 없습니다. 실패 또는 미확인 진단은 계수 식별 성공을 뜻하지 않습니다.')
        if result.get('experiment_analysis',{}).get('source_problem',{}).get('kind') in ('comparison_difference','observation_chain'):
            self.results.setMinimumHeight(125)
        tables=[v for k,v in content if k=='table'];table=tables[-1] if tables else ([],[])
        headers,rows=table;self.results.setColumnCount(len(headers));self.results.setHorizontalHeaderLabels(headers);self.results.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,item in enumerate(row):self.results.setItem(i,j,QTableWidgetItem(value_text(item)))
        self.results.clearSelection()
        self.results.setCurrentCell(*current)
        for row,column in selected:
            item=self.results.item(row,column)
            if item is not None:item.setSelected(True)
        if same_job:
            self.results.verticalScrollBar().setValue(scroll[0]);self.results.horizontalScrollBar().setValue(scroll[1])
        self._shown_job_id=self.job_id
        curves=[v for k,v in content if k=='curve'];self.figure.clear()
        if curves:
            curve=curves[-1] if self.evidence_reference is None else curves[0]
            ax=self.figure.subplots();x,y=curve['x'],curve['y'];mask=curve.get('mask',[True]*len(y))
            yy=[float(v) if ok and isinstance(v,(int,float)) and math.isfinite(v) else math.nan for v,ok in zip(y,mask)]
            label=curve['y_label']
            if label=='선언 범위로 정규화한 잔차 민감도':label='선언 범위로 정규화한\n잔차 민감도'
            if any(math.isfinite(v) for v in yy):
                ax.plot(x,yy,marker='.');ax.set_xlabel(curve['x_label']);ax.set_ylabel(label)
            else:
                ax.set_axis_off()
                difference=result.get('experiment_analysis',{}).get('source_problem',{}).get('kind')=='comparison_difference'
                empty=('차이의 불확실성 미확인\n상관·공분산과 입력값을 확인하세요.' if difference else
                       '표시할 유효한 결과값이 없습니다.')
                ax.text(.5,.5,empty,ha='center',va='center',transform=ax.transAxes)
        self.canvas.draw();message=next((v for k,v in content if k=='paragraph'),'결과 보존됨')
        if self.dirty or self._loading_request and self._loading_request!=result.get('experiment_analysis',{}).get('request'):
            message+=' · 표·곡선은 보존한 실행 입력의 결과이며 현재 편집 입력과 다를 수 있습니다.'
        self.message.setText(message)
        self._update_actions()

    def _cancel(self):
        if self.job_id is None:return
        self._call(lambda:self.client.cancel(self.job_id),lambda _:(self.message.setText('취소를 요청했습니다. 실제 중단 확인까지 결과와 입력을 보존합니다.'),self.timer.start()),write=True)

    def _report(self):
        if not self.document or not self.result or self._shown_job_id is None:return
        doc,job=self.document['id'],self._shown_job_id
        def open_report(ref):
            if (self.document['id'],self._shown_job_id)!=(doc,job):
                self.message.setText('표시한 진단이 바뀌었습니다. 원하는 보존 결과에서 보고서를 다시 여세요.');return
            from .report_window import ReportWindow
            window=ReportWindow(self.client,reference={'kind':'result',**ref,'selection':{'metadata_only':True}})
            self._children.append(window);window.show()
        self._call(lambda:self.client.document_result_reference(doc,job),open_report)

    def _study(self):
        if not self.document or not self.result or self._shown_job_id is None or self._worker is not None:return
        if self._study_pending is None:
            document=deepcopy(self.document);job=self._shown_job_id;result=deepcopy(self.result)
            binding=(document['id'],document['session_id'],job,canonical_hash(result))
            selection=choose_next_observation(result,self)
            if not selection or not selection['question'].strip():return
            self._study_pending={**selection,'source_document':document['id'],'source_job':job,'source_session':document['session_id'],'create':'C'+uuid.uuid4().hex,'update':'C'+uuid.uuid4().hex,'save':'C'+uuid.uuid4().hex,'observation_id':'O'+uuid.uuid4().hex}
            current=(self.document['id'],self.document['session_id'],self._shown_job_id,canonical_hash(self.result))
            if current!=binding:
                self._study_pending['requires_confirmation']=True
                self.message.setText('질문 작성 중 표시한 진단이 바뀌었습니다. 원 질문을 보존했습니다. 원 진단 질문 기록으로 처음 선택한 결과에 기록할지 확인하세요.')
                self._update_actions();return
        pending=self._study_pending
        if pending.get('requires_confirmation'):
            answer=QMessageBox.question(self,'원 진단 질문 기록',
                '처음 선택한 진단의 질문을 보존하고 있습니다.\n'+pending['question']+'\n원 진단에 기록할까요?',
                QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if answer!=QMessageBox.StandardButton.Save:return
        pending.pop('requires_confirmation',None)
        displayed=(self.document['id'],self._shown_job_id)
        def opened(receipt):
            if (self.document['id'],self._shown_job_id)!=displayed:
                self.message.setText('표시한 진단이 바뀌었습니다. 다음 시험 저장 재시도로 원 요청의 연구를 확인하세요.');return
            self._study_pending=None
            from .study_window import StudyWindow
            window=StudyWindow(self.client,document_id=receipt['document']['id']);self._children.append(window);window.show()
        self._call(lambda:save_analysis_study(self.client,pending),opened,write=True)

    def _details(self):
        dialog=QDialog(self);dialog.setWindowTitle('원 입력과 실행 진단');dialog.resize(850,620);layout=QVBoxLayout(dialog)
        view=QPlainTextEdit();view.setReadOnly(True);view.setPlainText(json.dumps(plain({'source':self.source,'evidence':self.evidence_reference,
            'document':self.document,'result':self.result}),ensure_ascii=False,indent=2));layout.addWidget(view);dialog.exec()

    def _update_actions(self):
        idle=self._worker is None and not self._closed;loaded=self._view is not None
        for button in (self.save,self.run):button.setEnabled(idle and loaded)
        self.cancel.setEnabled(idle and self.job_id is not None and self.timer.isActive())
        self.read.setText('원자료 다시 읽기' if self._view is None else '결과 다시 읽기')
        self.read.setEnabled(idle and (self.job_id is not None or self._view is None))
        self.study.setText('원 진단 질문 기록…' if (self._study_pending or {}).get('requires_confirmation') else
            '다음 시험 저장 재시도' if self._study_pending else '다음 시험 기록…')
        self.study.setEnabled(idle and self.result is not None and self._shown_job_id is not None)
        self.report.setEnabled(idle and self.result is not None and self._shown_job_id is not None)
        self.details.setEnabled(idle and loaded)

    def reject(self):
        self.done(0)  # Esc follows the same input/command guard.

    def closeEvent(self,event):
        self.done(0)  # X / Alt-F4 share the same guard, not QDialog's C++ default.
        if self._closed:event.accept()
        else:event.ignore()

    def done(self,code):
        if self._worker is not None and self._worker_writes:
            self.message.setText('현재 요청 결과를 확인한 뒤 닫으세요. 입력은 유지됩니다.');return
        if self.dirty or self._pending or self._study_pending:
            answer=QMessageBox.question(self,'입력 보호','미저장 또는 결과 미확인 입력이 있습니다. 창의 입력을 버리고 닫을까요? 계산은 자동 취소하지 않습니다.',
                QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if answer!=QMessageBox.StandardButton.Discard:return
        if self._worker is not None:
            self._worker.abandon();self._retired_workers.append(self._worker);self._worker=None
        self._closed=True;self.timer.stop();super().done(code)


def show_analysis_window(window,*,source=None,evidence_reference=None):
    """Keep the source open when its owned analysis refuses to discard edits."""
    children=getattr(window,'_experiment_analysis_children',None)
    if children is None:
        children=[];guard=_AnalysisCloseGuard(window,children);window.installEventFilter(guard)
        window._experiment_analysis_children=children;window._experiment_analysis_guard=guard
    dialog=ExperimentAnalysisWindow(window.client,source=source,evidence_reference=evidence_reference,parent=window)
    children.append(dialog)
    dialog.finished.connect(dialog.deleteLater)
    dialog.destroyed.connect(lambda:children.remove(dialog) if dialog in children else None)
    dialog.show();return dialog


def attach_candidate_diagnosis(window):
    """Optional C1 GUI hook: the exact preserved ref, never the current best row.
    Sol/C2 retain ownership of the source window. No provider call on attachment.
    """
    from PySide6.QtGui import QAction
    action=QAction('최종점 일반 잔차 진단…',window)
    window.menuBar().addMenu('시험 진단').addAction(action)
    action.setEnabled(getattr(window,'_evidence_reference',None) is not None)
    window.evidence_preserved.connect(lambda ref:action.setEnabled(ref is not None))
    window.evidence_invalidated.connect(lambda:action.setEnabled(False))
    def opened():
        ref=getattr(window,'_evidence_reference',None)
        if ref is None or getattr(window,'_writing',False):return
        show_analysis_window(window,evidence_reference=deepcopy(ref))
    action.triggered.connect(opened)
    window._experiment_diagnosis_action=action
