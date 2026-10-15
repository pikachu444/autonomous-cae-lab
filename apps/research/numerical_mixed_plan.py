"""Small GUI hooks for the shared RequestPlanWindow and actual Pro B5/C1 API."""
from copy import deepcopy
from PySide6.QtWidgets import QDialog,QPushButton


def select_declared_variables(window,descriptors):
    from PySide6.QtWidgets import QAbstractItemView,QVBoxLayout,QDialogButtonBox
    from .runner_window import readonly_table
    from .numerical_methods import display_number
    dialog=QDialog(window);dialog.setWindowTitle('모델 변수 선택');dialog.resize(820,440)
    layout=QVBoxLayout(dialog)
    table=readonly_table(['변수','단위','현재값','하한','상한','종류']);table.setObjectName('declaredModelVariables')
    table.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection);table.setRowCount(len(descriptors))
    for row,item in enumerate(descriptors):
        value=item['value']
        if item.get('kind')=='categorical':value=next((choice['label'] for choice in item['choices'] if choice['value']==value),value)
        values=[item['label'],item['unit'],value,item.get('lower'),item.get('upper'),
                '범주' if item.get('kind')=='categorical' else '수치']
        for column,value in enumerate(values):
            window._set_cell(table,row,column,display_number(value) if value is None or type(value) in (int,float) else str(value),False)
        table.item(row,0).setToolTip(item['id'])
    table.resizeColumnsToContents();layout.addWidget(table,1)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    accept=buttons.button(QDialogButtonBox.StandardButton.Ok);accept.setText('선택 변수 추가');accept.setEnabled(False)
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
    table.itemSelectionChanged.connect(lambda:accept.setEnabled(bool(table.selectionModel().selectedRows())))
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return None
    return [deepcopy(descriptors[index.row()]) for index in sorted(table.selectionModel().selectedRows(),key=lambda index:index.row())]


def descriptor_complete(row):
    if not isinstance(row,dict) or not {'id','label','unit','value'}<=set(row):return False
    return isinstance(row.get('choices'),list) if row.get('kind')=='categorical' else {'lower','upper'}<=set(row)


def domain_button(window):
    button=QPushButton('변수 범위…',window)
    button.setObjectName('editVariableDomains');button.clicked.connect(lambda:open_domain_editor(window))
    return button


def open_domain_editor(window):
    if (not window.document or window._view_error or window._callbacks or window._pending_adoption
            or window.conflict or window._busy and not window._busy_background):return False
    window._commit_editor();before=deepcopy(window.edited_draft())
    inputs=deepcopy(before['request']['inputs']);variables=inputs.get('variables')
    if not isinstance(variables,list) or not variables:
        window.message.setText('모델에서 편집할 변수를 먼저 선택하세요.');return False
    settings=window._model_settings(inputs)
    if not isinstance(inputs.get('backend'),str) or settings is None:
        window.message.setText('계산 모델과 입력을 먼저 선택하세요.');return False
    identity=tuple(window.document[key] for key in ('id','session_id','generation'))
    def relevant():
        return (not window._closed and not window.conflict and window.document is not None
            and tuple(window.document[key] for key in ('id','session_id','generation'))==identity
            and window.edited_draft()==before)
    def failed(error):
        window.message.setText('모델의 변수 정보를 읽지 못했습니다. 모델 입력을 확인한 뒤 다시 여세요.')
        window.message.setToolTip(str(error))
    def loaded(payload):
        from .numerical_mixed_variables import MixedVariablesDialog
        descriptors=payload.get('inputs')
        if (not isinstance(descriptors,list) or not descriptors or not all(descriptor_complete(row) for row in descriptors)):
            failed(ValueError('The selected model did not advertise complete variable descriptors'));return
        window._worksheet_labels.update({row['id']:row['label'] for row in descriptors})
        dialog=MixedVariablesDialog(variables,descriptors,window,operation=before['request']['operation'])
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if not relevant():
            window.message.setText('검토 중 계획이 변경되었습니다. 변수 범위를 다시 여세요.');return
        reviewed=deepcopy(dialog.value)
        if window._edit_structure(lambda value:value.__setitem__('variables',deepcopy(reviewed))):
            window.message.setText('변수 범위를 초안에 반영했습니다. 계획에 적용한 뒤 계산하세요.')
    def begin():
        if relevant():return window._call(lambda:window.client.describe_inputs({'backend':inputs['backend'],'settings':settings}),
            loaded,relevant=relevant,rejected=failed)
        return False
    if window._busy_background:
        window._pending_adoption=begin;window._update_actions()
        window.message.setText('현재 읽기가 끝나면 모델의 변수 범위를 엽니다.');return True
    return begin()


def refresh_variable_sheet(window,inputs):
    """Keep the existing table; annotate only explicitly typed declarations."""
    from caelab.variable_domains import typed
    variables=inputs.get('variables',[])
    if not isinstance(variables,list) or any(not isinstance(row,dict) for row in variables) or not typed(variables):return
    for index,row in enumerate(variables):
        if not isinstance(row,dict):continue
        kind=row.get('kind','continuous');mode=row.get('mode','free')
        if mode=='dependent':window._sheet_cell(window.variable_sheet,index,2,None,label='종속식')
        elif kind=='categorical':
            choices=[(choice['label'],deepcopy(choice['value'])) for choice in row.get('choices',[])
                if isinstance(choice,dict) and {'label','value'}<=set(choice)]
            window._sheet_cell(window.variable_sheet,index,2,row.get('value'),('variables',index,'value'),choices=choices)
        if kind=='categorical':
            for column in (3,4):window._sheet_cell(window.variable_sheet,index,column,None)
        if kind!='continuous' or mode!='free':
            window._sheet_cell(window.variable_sheet,index,6,row.get('transform','linear'),choices=(('선형','linear'),('로그','log')))


def limit_unsupported_execution(window):
    """Run after the existing action policy; never enables an action it blocked."""
    from caelab.variable_domains import capability
    previous=getattr(window,'_mixed_run_tooltip',None)
    if previous and window.run_button.toolTip()==previous[1]:window.run_button.setToolTip(previous[0])
    window._mixed_run_tooltip=None
    def explain(text):
        window._mixed_run_tooltip=(window.run_button.toolTip(),text)
        window.run_button.setEnabled(False);window.run_button.setToolTip(text)
    if not window.document:return
    draft=window.edited_draft(commit=False)
    if draft.get('mode')!='request':return
    request=draft.get('request',{});variables=request.get('inputs',{}).get('variables')
    if not variables:return
    try:available=capability(request['operation'],variables)['available']
    except (ValueError,KeyError,TypeError) as error:
        explain('변수 입력을 확인하세요.\n'+str(error));return
    if not available:
        explain('선택한 방법은 독립 연속 변수만 지원합니다. DOE 또는 차분 진화를 선택하세요.')
