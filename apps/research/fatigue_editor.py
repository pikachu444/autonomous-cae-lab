"""Explicit retained-history/S-N workflow; local draft until the user accepts."""
from copy import deepcopy
from PySide6.QtCore import Qt,QThreadPool,Slot
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLineEdit,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,
    QSplitter,QWidget,QCheckBox,QInputDialog)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .pde_window import _Read
from .impact_editor import numeric,text
from .response_selection import response_choices,choose_location
from caelab.fatigue import stress_history


class _LocalRead(_Read):
    def run(self):
        try:value,error=self.function(),None
        except Exception as exc:value,error=None,str(exc)
        try:self.signals.finished.emit(value,error)
        except RuntimeError:pass  # The cancelled/destroyed native dialog no longer owns callbacks.


class FatigueEditor(QDialog):
    def __init__(self,client,settings,parent=None):
        super().__init__(parent);self.client=client;self.value=deepcopy(settings)
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.setWindowTitle('반복하중 평가');self.resize(1060,740)
        self._worker=None;self._after=None;self._closed=False;self._serial=0
        self.finished.connect(self._closed_dialog)
        layout=QVBoxLayout(self);bar=QHBoxLayout()
        self.source=QLabel((settings.get('source') or {}).get('title') or '저장된 응력 이력을 선택하세요')
        self.source.setWordWrap(True);bar.addWidget(self.source,1)
        self.choose=QPushButton('응력 이력 선택…');self.choose.clicked.connect(self.choose_source);bar.addWidget(self.choose)
        layout.addLayout(bar)
        split=QSplitter();layout.addWidget(split,1)
        self.figure=Figure(figsize=(5,4),layout='constrained');self.canvas=FigureCanvasQTAgg(self.figure)
        split.addWidget(self.canvas)
        right=QWidget();right.setMaximumWidth(470);form=QVBoxLayout(right);split.addWidget(right);split.setSizes([610,420])
        form.addWidget(QLabel('S–N 시험 자료'))
        self.sn=QTableWidget(0,2);self.sn.setHorizontalHeaderLabels(['응력 진폭 [MPa]','수명 [사이클]'])
        self.sn.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);form.addWidget(self.sn,1)
        actions=QHBoxLayout()
        for label,call in (('시험점 추가',self.add_row),('선택 삭제',lambda:self.sn.removeRow(self.sn.currentRow()))):
            button=QPushButton(label);button.clicked.connect(call);actions.addWidget(button)
        form.addLayout(actions)
        self.fields={};conditions=QFormLayout()
        for key,label in (('reference','시험 자료 출처'),('conditions','재료·환경 조건'),
            ('mean_min_mpa','평균 응력 최소 [MPa]'),('mean_max_mpa','평균 응력 최대 [MPa]'),
            ('temperature_min_k','시험 온도 최소 [K]'),('temperature_max_k','시험 온도 최대 [K]')):
            field=QLineEdit(text(settings['calibration'][key]));self.fields[key]=field;conditions.addRow(label,field)
        self.temperature=QLineEdit(text(settings['temperature_k']));conditions.addRow('이력의 평가 온도 [K]',self.temperature)
        form.addLayout(conditions)
        self.repeat=QCheckBox('선택한 닫힌 이력을 반복 블록으로 가정');self.repeat.setChecked(settings['repeat_block'])
        form.addWidget(self.repeat);form.addWidget(QLabel('평균응력 보정 없음 / 시험 범위 밖은 미정'))
        self.message=QLabel();self.message.setWordWrap(True);layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('편집 반영')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        for row in settings['sn_curve']:self.add_row(row)
        self.draw(None)
        if settings.get('source'):self.load_source(settings['source'])

    def _closed_dialog(self,*_):
        self._closed=True;self._serial+=1;self._after=None

    def call(self,function,after):
        if self._worker or self._closed:return False
        self._after=after;self._request_serial=self._serial
        worker=_LocalRead(function);self._worker=worker
        worker.signals.finished.connect(self._done,Qt.ConnectionType.QueuedConnection)
        self.choose.setEnabled(False);self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        QThreadPool.globalInstance().start(worker);return True

    @Slot(object,object)
    def _done(self,value,error):
        worker=self._worker;after=self._after;self._worker=None;self._after=None
        if self._closed or self._request_serial!=self._serial:return
        self.choose.setEnabled(True);self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        if error:self.message.setText(str(error));return
        try:after(value)
        except (ValueError,KeyError,TypeError) as exc:self.message.setText(str(exc))

    def add_row(self,row=None):
        if not isinstance(row,dict):row={'amplitude_mpa':'','cycles':''}
        i=self.sn.rowCount();self.sn.insertRow(i)
        for col,key in enumerate(('amplitude_mpa','cycles')):self.sn.setItem(i,col,QTableWidgetItem(text(row[key])))

    def choose_source(self):
        def listed(payload):
            docs=[d for d in payload['documents'] if d.get('kind') in ('data','simulation','material','pde','evaluation')]
            labels=[str(i+1)+'. '+d['title'] for i,d in enumerate(docs)]
            label,ok=QInputDialog.getItem(self,'응력 이력','저장 문서',labels,0,False)
            if ok and not self._closed:self.call(lambda:self.client.document_read(docs[labels.index(label)]['id']),opened)
        def opened(doc):
            runs=[r for r in doc.get('runs',[]) if r.get('retention_complete') and r.get('retained_result')]
            labels=['계산 '+str(i+1) for i in range(len(runs))]
            label,ok=QInputDialog.getItem(self,'응력 이력','보존 계산',labels,0,False)
            if not ok or self._closed:return
            job=runs[labels.index(label)]['job_id']
            def described(payload):
                reference,metadata=payload;choices=response_choices(metadata)
                choices=[c for c in choices if c['definition'].get('unit') in ('Pa','MPa')]
                labels=[str(i+1)+'. '+c['label'] for i,c in enumerate(choices)]
                label,ok=QInputDialog.getItem(self,'응력 이력','성분과 위치',labels,0,False)
                if not ok or self._closed:return
                choice=choose_location(self,self.client,doc['id'],job,choices[labels.index(label)],relevant=lambda:not self._closed)
                if choice:self.load_source({'result':reference,'response':choice['selector'],'title':doc['title']})
            self.call(lambda:(self.client.document_result_reference(doc['id'],job),self.client.document_result_metadata(doc['id'],job)),described)
        self.call(self.client.documents,listed)

    def load_source(self,source):
        def read():
            ref=source['result']
            if self.client.document_result_reference(ref['document_id'],ref['job_id'])!=ref:raise ValueError('원 결과가 변경되었습니다')
            result=self.client.document_result(ref['document_id'],ref['job_id'],selection=[source['response']])
            if result.get('execution_status')!='SUCCEEDED' or result.get('prediction_status') or 'candidates' in result:
                raise ValueError('성공한 실제 응력 이력을 선택하세요')
            response=result['responses'][source['response']];stress_history(response)
            return response
        def done(response):
            self.value['source']=deepcopy(source)
            location=response['location']
            location_label=('절점 ' if location.get('kind')=='node' else '요소 ')+str(location.get('id','')) if isinstance(location,dict) else str(location)
            self.source.setText(source['title']+' / '+str(response['component'])+' ['+response['unit']+'] / '+location_label)
            self.draw(response)
            measure={'infinitesimal_Cauchy':'미소변형 Cauchy 응력','Cauchy_stress':'Cauchy 응력',
                     'cauchy_stress':'Cauchy 응력','engineering_stress':'공칭 응력','nominal_stress':'공칭 응력'}[response['measure']]
            self.message.setText(measure+' / 기준계 '+str(response['frame'])+' / 원 행 '+str(len(response['value']))+'개')
        self.call(read,done)

    def draw(self,response):
        self.figure.clear();ax=self.figure.add_subplot(111)
        if response:
            times,values,_=stress_history(response)
            ax.plot(times,values);ax.set_xlabel('시간 [s]');ax.set_ylabel('부호 있는 응력 [MPa]')
        else:
            ax.set_axis_off();ax.text(.5,.5,'응력 이력 선택',ha='center',va='center',transform=ax.transAxes)
        self.canvas.draw_idle()

    def edited(self):
        value=deepcopy(self.value)
        value['sn_curve']=[{key:numeric(self.sn.item(r,c).text().strip()) if self.sn.item(r,c) else ''
            for c,key in enumerate(('amplitude_mpa','cycles'))} for r in range(self.sn.rowCount())]
        value['calibration']={key:(field.text() if key in ('reference','conditions') else numeric(field.text().strip()))
                              for key,field in self.fields.items()}
        value['temperature_k']=numeric(self.temperature.text().strip());value['repeat_block']=self.repeat.isChecked()
        return value


def edit(window):
    draft=window.edited_draft()
    if draft.get('backend')!='damage.rainflow':return
    dialog=FatigueEditor(window.client,draft['settings'],window)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return
    draft['settings']=dialog.edited();window._show_document(window.document,preserve_draft=draft)
    window.local_dirty=True;window._update_actions()


def show_cycles(parent,result):
    from .appearance import configure_plot_fonts
    configure_plot_fonts()
    dialog=QDialog(parent);dialog.setWindowTitle('사이클과 누적값');dialog.resize(1060,740)
    layout=QVBoxLayout(dialog);detail=result.get('diagnostics',{})
    label=QLabel(detail.get('life_reason',''));label.setWordWrap(True);layout.addWidget(label)
    figure=Figure(layout='constrained');canvas=FigureCanvasQTAgg(figure);canvas.setMinimumHeight(220)
    layout.addWidget(canvas,1);ax=figure.add_subplot(111)
    response=result.get('responses',{}).get('stress_history')
    highlight=None
    if response:
        times,values,_=stress_history(response);ax.plot(times,values,color='#245f9e')
        highlight,=ax.plot([],[],'o',color='#c76624')
        ax.set_xlabel('시간 [s]');ax.set_ylabel('응력 [MPa]')
    canvas.draw_idle()
    table=QTableWidget(0,8);table.setObjectName('fatigueCycleRows')
    table.setHorizontalHeaderLabels(['진폭 [MPa]','평균 [MPa]','횟수','시작 [s]','끝 [s]','시험 수명','누적 증가','판정'])
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    rows=result.get('cycles',[]);page=[0];size=256
    def selected():
        index=page[0]*size+table.currentRow()
        if table.currentRow()<0 or index>=len(rows) or highlight is None:return
        row=rows[index];a,b=row['start_row'],row['end_row']
        highlight.set_data([times[a],times[b]],[values[a],values[b]]);canvas.draw_idle()
    table.itemSelectionChanged.connect(selected);layout.addWidget(table,1)
    nav=QHBoxLayout();previous=QPushButton('앞으로');following=QPushButton('다음');count=QLabel()
    nav.addWidget(previous);nav.addWidget(following);nav.addWidget(count);nav.addStretch();layout.addLayout(nav)
    def populate():
        start=page[0]*size;selected_rows=rows[start:start+size]
        table.blockSignals(True);table.setRowCount(len(selected_rows))
        for r,row in enumerate(selected_rows):
            for col,key in enumerate(('amplitude_mpa','mean_mpa','count','start_s','end_s','calibrated_cycles','damage','reason')):
                value=row.get(key)
                item=QTableWidgetItem('미정' if value is None else format(value,'.7g') if type(value) in (int,float) else str(value or '계산됨'))
                item.setToolTip(str(value));item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);table.setItem(r,col,item)
        table.blockSignals(False);previous.setEnabled(page[0]>0);following.setEnabled(start+size<len(rows))
        count.setText(f'{start+1 if rows else 0}–{start+len(selected_rows)} / {len(rows)}')
        if highlight is not None:highlight.set_data([],[]);canvas.draw_idle()
    def move(delta):page[0]+=delta;populate()
    previous.clicked.connect(lambda:move(-1));following.clicked.connect(lambda:move(1));populate()
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    dialog.exec()
