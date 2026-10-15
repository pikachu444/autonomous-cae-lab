"""Read-only mixed-domain projection into existing candidate/response widgets."""
from copy import deepcopy
from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTableWidgetItem
from .numerical_methods import ResultDisplay, display_number


def project_mixed_result(window,result,key):
    """Attach to the existing result draw after its method-specific projection."""
    controller=getattr(window,'_mixed_selection',None)
    if not isinstance(result.get('domain_input'),dict):
        if controller is not None and controller.result is not None:
            controller.result=controller.source=None
            window.candidates.setHorizontalHeaderLabels(['후보','실행 상태','변수 값','목적값','조건 충족','실패 이유'])
        window._mixed_result_key=None
        return False
    if controller is None:
        controller=RetainedMixedSelection(window.candidates,window.plot_response,window)
        window._mixed_selection=controller
        controller.selectionChanged.connect(lambda _:window._candidate_changed())
    run=next((row for row in window.document.get('runs',[]) if row['job_id']==window.selected_job()),{})
    source=dict(document_id=window.document['id'],job_id=window.selected_job(),
        input_revision=run.get('input_revision'),input_sha256=run.get('input_sha256'),result_sha256=key[-1])
    descriptors=[dict(id=identifier,label=label) for identifier,label in window._worksheet_labels.items()]
    inputs=run.get('draft',{}).get('request',{}).get('inputs',{})
    from caelab import dimensioned_models
    if inputs.get('backend')==dimensioned_models.ODE:
        try:descriptors=dimensioned_models.describe_inputs(dimensioned_models.ODE,inputs['settings'])
        except (ValueError,TypeError,KeyError):pass
    window._mixed_result_key=key
    try:controller.set_result(result,source,descriptors=descriptors)
    except (ValueError,TypeError,KeyError) as error:
        window.message.setText('선택한 결과의 변수와 표본이 일치하지 않습니다. 원본을 다시 읽으세요.')
        window.message.setToolTip(str(error))
    return True


def plot_mixed_selection(window,result):
    controller=getattr(window,'_mixed_selection',None)
    if controller is None or controller.result is None or window._mixed_result_key!=window._candidate_table_key:return False
    # Keep the existing method overview available alongside selected response curves.
    if window.plot_response.currentData() is None:return False
    window.result_summary.clear();plot_selected_mixed(window,controller.selection(),result)
    return True


def plot_selected_mixed(window,selection,result):
    """Reuse the existing retained-curve/scalar plot, keeping IDs out of titles."""
    window.figure.clear()
    if selection is None or selection['response'] is None:
        axes=window.figure.add_subplot(111)
        axes.text(.5,.5,'표본과 보존된 응답을 선택하세요.' if selection is None else '이 표본에는 보존된 응답이 없습니다.',
            ha='center',va='center',transform=axes.transAxes)
        axes.set_axis_off()
        window.canvas.setToolTip(str((selection or {}).get('candidate',{}).get('failure_reason') or ''))
    else:
        from .request_plan_window import RequestPlanWindow
        RequestPlanWindow._plot_candidate_response(window,result,selection['response_name'])
        number=next(i+1 for i,row in enumerate(result['candidates']) if row['candidate_id']==selection['candidate_id'])
        window.figure.axes[-1].set_title('표본 '+str(number)+' '+selection['response_name'])
        window.canvas.setToolTip('')
    window.figure.set_layout_engine('tight');window.canvas.draw_idle()


class RetainedMixedSelection(QObject):
    """No owner, evaluator, expression resolver or result writer is reachable."""
    selectionChanged=Signal(object)

    def __init__(self, table, response_combo, parent=None):
        super().__init__(parent)
        self.table,self.response_combo=table,response_combo
        self.result=None;self.source=None;self._showing=False;self._last_selection=None
        self.table.viewport().installEventFilter(self)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setItemDelegate(ResultDisplay(table))
        self.table.itemSelectionChanged.connect(self._row_selected)
        self.response_combo.currentIndexChanged.connect(self._response_selected)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Resize:QTimer.singleShot(0,self._ensure_selected_visible)
        return False

    def _ensure_selected_visible(self):
        from shiboken6 import isValid
        if not isValid(self.table) or self.result is None:return
        rows=self.table.selectionModel().selectedRows()
        if len(rows)==1:self.table.scrollToItem(self.table.item(rows[0].row(),0))

    def set_result(self,result,source,*,descriptors=None):
        from caelab.variable_domains import validate_retained_table
        try:variables=validate_retained_table(result)  # Parses/checks, never resolves a candidate.
        except (ValueError,TypeError,KeyError):
            self.result=self.source=None
            self.table.clearSelection();self.table.setRowCount(0);self.response_combo.clear();self.response_combo.setEnabled(False)
            self.selectionChanged.emit(None)
            raise
        old=self.selected_id() if self.source==source and self.result==result else None
        self.result,self.source=deepcopy(result),deepcopy(source)
        labels={d['id']:d.get('label',d['id']) for d in descriptors or []}
        self._showing=True
        blocked=self.table.blockSignals(True)
        try:
            table=self.table;table.clearSelection();table.setRowCount(0)
            table.setColumnCount(len(variables)+3)
            table.setHorizontalHeaderLabels(['표본','상태']+[labels.get(v['id'],v['id'])+' ['+v['unit']+']' for v in variables]+['계산 확인'])
            table.setRowCount(len(result['candidates']))
            selected=None
            statuses={'SUCCEEDED':'완료','FAILED':'실패','REJECTED':'입력 제외','CANCELLED':'취소',
                'PREDICTED':'예측','PARTIAL_FAILURE':'일부 실패'}
            for i,row in enumerate(result['candidates']):
                state=row.get('execution_status')
                texts=['표본 '+str(i+1),statuses.get(state,'상태 확인 필요')]
                for variable in variables:
                    value=row.get('values',{}).get(variable['id'])
                    label=next((choice['label'] for choice in variable.get('choices',[]) if type(choice['value']) is type(value) and choice['value']==value),None)
                    texts.append(label if label is not None else display_number(value))
                reason=row.get('domain_error',{}).get('code')
                texts.append('종속값 범위 확인' if reason in ('OUT_OF_BOUNDS','FRACTIONAL_INTEGER') else '입력 확인 필요' if state=='REJECTED' else
                    '계산 실패' if state in ('FAILED','PARTIAL_FAILURE') else '계산 취소' if state=='CANCELLED' else '')
                for column,text in enumerate(texts):
                    item=QTableWidgetItem(text);item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if column==0:item.setData(Qt.ItemDataRole.UserRole,row['candidate_id'])
                    elif 2<=column<2+len(variables):
                        value=row.get('values',{}).get(variables[column-2]['id']);item.setData(Qt.ItemDataRole.UserRole,deepcopy(value));item.setToolTip(str(value))
                    elif column==1:item.setToolTip(str(state))
                    else:item.setToolTip(str(row.get('failure_reason') or row.get('domain_error',{}).get('message') or ''))
                    table.setItem(i,column,item)
                if row['candidate_id']==old:selected=i
            table.resizeColumnsToContents()
            if selected is not None:table.selectRow(selected)
        finally:self._showing=False;self.table.blockSignals(blocked)
        self._row_selected()

    def selected_id(self):
        rows=self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(),0).data(Qt.ItemDataRole.UserRole) if len(rows)==1 else None

    def _selected(self):
        identifier=self.selected_id()
        return next((row for row in (self.result or {}).get('candidates',[]) if row['candidate_id']==identifier),None)

    def _row_selected(self):
        if self._showing or self.result is None:return
        row=self._selected();previous=self.response_combo.currentData()
        previous=previous.get('candidate_response') if isinstance(previous,dict) else previous
        self._showing=True
        blocked=self.response_combo.blockSignals(True)
        try:
            self.response_combo.clear()
            self.response_combo.addItem('계산 요약',None)
            for name,response in (row or {}).get('responses',{}).items():
                if isinstance(response,dict) and response.get('kind') in ('scalar','series'):
                    self.response_combo.addItem(name+' ['+str(response.get('unit','단위 미지정'))+']',{'candidate_response':name})
            if previous is not None:
                index=self.response_combo.findData({'candidate_response':previous})
                if index>=0:self.response_combo.setCurrentIndex(index)
            elif self.response_combo.count()>1:self.response_combo.setCurrentIndex(1)
            self.response_combo.setEnabled(self.response_combo.count()>1)
            self.response_combo.setToolTip('보존한 응답이 없습니다.' if row is not None and self.response_combo.count()==1 else '')
        finally:self._showing=False;self.response_combo.blockSignals(blocked)
        self._response_selected()

    def _response_selected(self,*_):
        if self._showing or self.result is None:return
        selected=self.selection()
        if selected!=self._last_selection:
            self._last_selection=deepcopy(selected);self.selectionChanged.emit(selected)

    def selection(self):
        row=self._selected()
        if row is None:return None
        choice=self.response_combo.currentData();name=choice.get('candidate_response') if isinstance(choice,dict) else None
        return {'source':deepcopy(self.source),'candidate_id':row['candidate_id'],
            'candidate':deepcopy(row),'response_name':name,'response':deepcopy(row.get('responses',{}).get(name))}
