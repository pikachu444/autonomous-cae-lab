"""GUI-only initial B5 contract checks; no owner integration or solver claims."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
domains=pytest.importorskip('caelab.variable_domains')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QComboBox,QLineEdit,QTableWidget
from apps.research.numerical_mixed_variables import MixedVariablesDialog,declared_variable
from apps.research.numerical_mixed_results import RetainedMixedSelection
from caelab.variable_binding import ode_solver_descriptor


def declarations():
    return [dict(id='count',unit='1',kind='integer',value=1,lower=1,upper=3),
        dict(id='base_rate',unit='1/s',kind='discrete',values=[.1,.2],value=.1),
        dict(id='sink_rate',unit='1/s',mode='dependent',expression='count * base_rate',lower=0.,upper=.5),
        dict(id='ambient',unit='K',mode='fixed',value=290.),
        declared_variable(ode_solver_descriptor({'solver':{'method':'RK45'}}))]


@pytest.fixture
def app():
    app=QApplication.instance() or QApplication([])
    yield app
    for window in app.topLevelWidgets():
        if isinstance(window,MixedVariablesDialog):window.reject()
    app.processEvents()


def forbidden(*args,**kwargs):raise AssertionError('Selection/edit must not resolve or evaluate a candidate')


def test_model_picker_accepts_numeric_and_exact_enum_without_source_edits(app):
    from PySide6.QtCore import QTimer
    from apps.research.numerical_window import NumericalWindow
    from apps.research.numerical_mixed_plan import select_declared_variables
    from PySide6.QtWidgets import QWidget
    from types import MethodType
    rows=[dict(id='count',label='개수',unit='1',value=1,lower=1,upper=3),ode_solver_descriptor({'solver':{'method':'RK45'}})]
    original=deepcopy(rows);host=QWidget();host._set_cell=MethodType(NumericalWindow._set_cell,host)
    def choose():
        modal=app.activeModalWidget();table=modal.findChild(QTableWidget,'declaredModelVariables')
        table.selectRow(1);modal.accept()
    QTimer.singleShot(0,choose)
    try:selected=select_declared_variables(host,rows)
    finally:host.close()
    assert selected==[rows[1]] and rows==original and type(selected[0]['value']) is str


def test_edit_validation_uses_public_parser_without_evaluating_and_keeps_input(app,monkeypatch):
    from caelab import dimensioned_expression
    raw=declarations();before=deepcopy(raw)
    monkeypatch.setattr(domains.VariableDomains,'resolve',forbidden)
    monkeypatch.setattr(dimensioned_expression,'evaluate',forbidden)
    dialog=MixedVariablesDialog(raw)
    assert dialog.validate_inputs()
    assert raw==before and dialog.rows==before
    dialog.operation='fit';assert not dialog.validate_inputs()
    assert '지원하지 않습니다' in dialog.error.text()
    dialog.reject();assert raw==before and dialog.value is None


def test_integer_fraction_error_selects_original_row_without_rounding(app):
    dialog=MixedVariablesDialog(declarations())
    dialog.table.item(0,4).setText('1.5')
    assert not dialog.validate_inputs()
    assert dialog.rows[0]['value']==1.5 and dialog.table.currentRow()==0
    dialog.accept();assert dialog.value[0]['value']==1.5  # Editable invalid draft, never admitted for a run.


def test_real_delegate_preserves_unfinished_numeric_and_cancel_is_local(app):
    raw=declarations();before=deepcopy(raw);dialog=MixedVariablesDialog(raw)
    dialog.show();app.processEvents();dialog.table.setCurrentCell(0,4)
    dialog.table.editItem(dialog.table.item(0,4));app.processEvents()
    editor=dialog.table.findChild(QLineEdit);assert editor is not None
    editor.selectAll();QTest.keyClicks(editor,'1e');QTest.keyClick(editor,Qt.Key.Key_Return);app.processEvents()
    assert dialog.rows[0]['value']=='1e'
    dialog.reject();assert raw==before


def test_enum_combo_returns_exact_string_not_choice_index(app):
    dialog=MixedVariablesDialog(declarations());dialog.show();app.processEvents()
    dialog.table.setCurrentCell(4,4);dialog.table.editItem(dialog.table.item(4,4));app.processEvents()
    editor=dialog.table.findChild(QComboBox);assert editor is not None
    index=editor.findData('BDF');assert index>=0;editor.setCurrentIndex(index)
    QTest.keyClick(editor,Qt.Key.Key_Return);app.processEvents()
    assert dialog.rows[4]['value']=='BDF' and type(dialog.rows[4]['value']) is str
    assert dialog.validate_inputs()


@pytest.mark.parametrize('expression',['count * missing','sink_rate + base_rate','count + base_rate'])
def test_dependency_error_goes_to_bound_expression_and_keeps_text(app,expression):
    dialog=MixedVariablesDialog(declarations());dialog.table.setCurrentCell(2,0)
    dialog.expression.setPlainText(expression)
    assert not dialog.validate_inputs()
    assert dialog.table.currentRow()==2 and dialog.expression.toPlainText()==expression
    assert dialog.error.toolTip() and 'variables.2.expression' in dialog.error.toolTip()


def test_mode_change_and_undo_preserve_full_typed_declaration(app):
    raw=declarations();dialog=MixedVariablesDialog(raw)
    dialog.table.item(0,2).setText('종속식');app.processEvents()
    assert dialog.rows[0]['mode']=='dependent' and 'value' not in dialog.rows[0]
    assert not dialog.table.item(0,4).flags() & Qt.ItemFlag.ItemIsEditable
    dialog.undo();assert dialog.rows==raw
    dialog.redo();assert dialog.rows[0]['mode']=='dependent'


def test_static_omitted_default_is_visible_without_rewriting_raw_or_stale_error(app):
    raw=declarations();raw[4].pop('value');dialog=MixedVariablesDialog(raw)
    assert dialog.table.item(4,4).text()=='RK45' and 'value' not in dialog.rows[4]
    dialog.table.setCurrentCell(2,0);dialog.expression.setPlainText('count * missing')
    assert not dialog.validate_inputs() and dialog.error.toolTip()
    dialog.undo();assert dialog.rows==raw and not dialog.error.text() and not dialog.error.toolTip()
    dialog.accept();assert dialog.value==raw


def test_discrete_values_and_category_order_remain_separate_from_labels(app):
    dialog=MixedVariablesDialog(declarations())
    dialog.table.setCurrentCell(1,0);dialog.values.item(0,0).setText('0.15');app.processEvents()
    assert dialog.rows[1]['values']==[.15,.2]
    dialog.table.setCurrentCell(4,0);dialog.choices.setCurrentRow(1);dialog._move_choice(-1);app.processEvents()
    assert dialog.rows[4]['choices'][0]['value']=='DOP853'
    assert dialog.rows[4]['choices'][0]['id']=='dop853'
    dialog.accept();assert dialog.value[1]['values']==[.15,.2]


def retained_table():
    """Literal response fixture; Pro resolves inputs only during fixture creation."""
    domain=domains.VariableDomains(declarations());rows=[]
    for i,(count,base,method) in enumerate([(1,.1,'RK45'),(3,.2,'RK45'),(2,.1,'DOP853')]):
        resolved=domain.resolve({'count':count,'base_rate':base,'solver-method':method},tolerate=True)
        row=dict(candidate_id='C'+str(i),values=resolved['values'],execution_status='REJECTED' if resolved['error'] else 'SUCCEEDED',
            responses={} if resolved['error'] else {'temperature':dict(kind='scalar',unit='K',value=300.-i),
                'rate':dict(kind='scalar',unit='1/s',value=resolved['values']['sink_rate'])})
        if resolved['error']:row['domain_error']=resolved['error']
        rows.append(domain.attach(row,resolved))
    return dict(variables=domain.variables,domain_input=domain.snapshot,candidates=rows)


def test_retained_row_response_selection_has_exact_values_no_hidden_resolution(app,monkeypatch):
    result=retained_table();before=deepcopy(result)
    monkeypatch.setattr(domains.VariableDomains,'resolve',forbidden)
    table=QTableWidget();combo=QComboBox();selector=RetainedMixedSelection(table,combo)
    source={'document_id':'Nfixture','job_id':'Jfixture','input_revision':'Ifixture','input_sha256':'a'*64}
    selector.set_result(result,source);assert selector.selection() is None
    table.selectRow(2)
    assert table.item(2,0).text()=='표본 3'
    selection=selector.selection();assert selection['candidate_id']=='C2'
    assert selection['candidate']['values']['count']==2 and type(selection['candidate']['values']['count']) is int
    assert selection['candidate']['values']['solver-method']=='DOP853'
    combo.setCurrentIndex(combo.findData({'candidate_response':'rate'}))
    assert selector.selection()['response']['value']==.2
    assert selector.selection()['source']==source and result==before
    selector.selection()['candidate']['values']['count']=99
    assert selector.selection()['candidate']['values']['count']==2


def test_rejected_candidate_keeps_missing_dependent_value_and_no_response(app,monkeypatch):
    result=retained_table();monkeypatch.setattr(domains.VariableDomains,'resolve',forbidden)
    table=QTableWidget();combo=QComboBox();selector=RetainedMixedSelection(table,combo)
    selector.set_result(result,{'job_id':'Jfixture'});table.selectRow(1)
    selection=selector.selection()
    assert selection['candidate']['execution_status']=='REJECTED' and selection['response'] is None
    assert 'sink_rate' not in selection['candidate']['values'] and not combo.isEnabled()
    assert table.item(1,4).text()=='—'


def test_new_origin_clears_selection_and_forged_assignment_is_rejected(app):
    result=retained_table();table=QTableWidget();combo=QComboBox();selector=RetainedMixedSelection(table,combo)
    selector.set_result(result,{'job_id':'Jone'});table.selectRow(0)
    selector.set_result(result,{'job_id':'Jone'});assert selector.selected_id()=='C0'
    selector.set_result(result,{'job_id':'Jtwo'});assert selector.selection() is None
    forged=deepcopy(result);forged['candidates'][0]['values']['count']=1.5
    with pytest.raises(ValueError):selector.set_result(forged,{'job_id':'Jtwo'})
    assert selector.selection() is None and table.rowCount()==0


def test_unchanged_retained_poll_keeps_selection_receipt_and_legacy_combo(app):
    from types import SimpleNamespace
    from PySide6.QtTest import QSignalSpy
    from apps.research.numerical_mixed_results import project_mixed_result
    table=QTableWidget();combo=QComboBox();selector=RetainedMixedSelection(table,combo)
    result=retained_table();source={'job_id':'Jfixture'};spy=QSignalSpy(selector.selectionChanged)
    selector.set_result(result,source);table.selectRow(0);count=spy.count()
    selector.set_result(result,source);assert spy.count()==count and selector.selected_id()=='C0'
    host=SimpleNamespace(_mixed_selection=selector,candidates=table)
    assert not project_mixed_result(host,{},None)
    combo.clear();combo.addItem('원래 응답','original');table.selectRow(1)
    assert combo.currentData()=='original' and combo.count()==1


def test_legacy_coefficient_checkbox_keeps_bool_owner_and_other_window_separate(app):
    from apps.research.numerical_window import NumericalWindow,cell_value
    from apps.research.numerical_variable_display import refresh_frozen_material_display
    from caelab.material_document import default_draft
    from caelab.numerical_document import from_material_document
    material={'id':'Mfixture','input_revision':'Ifixture','generation':0,'draft':default_draft()}
    document=dict(id='Nfixture',session_id='Sfixture',generation=0,title='인장 계획',
        draft=from_material_document(material),runs=[],diagnostics=[],dirty=False)
    left=NumericalWindow(None,auto_open=False,poll_interval=0)
    right=NumericalWindow(None,auto_open=False,poll_interval=0)
    try:
        for window in (left,right):window._show_document(deepcopy(document));refresh_frozen_material_display(window)
        assert left.material_label.text()=='선형 탄성 [MPa]'
        assert left.variables.item(0,0).text()=='E'
        assert left.variables.itemDelegateForColumn(0).displayText('E',None)=='탄성계수'
        left.show();left.variables.setCurrentCell(0,5);left.variables.setFocus();app.processEvents()
        QTest.keyClick(left.variables,Qt.Key.Key_Space);app.processEvents()
        assert cell_value(left.variables,0,5) is False
        assert left.variables.item(0,5).checkState()==Qt.CheckState.Unchecked
        assert left.variables.item(0,5).data(Qt.ItemDataRole.AccessibleTextRole)=='고정 변수'
        assert cell_value(right.variables,0,5) is True
        assert document['draft']['variables'][0]['free'] is True
        assert left.edited_draft()['variables'][0]['free'] is False
        assert left.variables.itemDelegateForColumn(6).displayText('linear',None)=='선형'
        assert left.variables.item(0,6).text()=='linear'
    finally:
        for window in (left,right):window._allow_close=True;window.close()


def test_coefficient_refresh_reuses_delegates_and_updates_physical_label_without_window(app):
    from types import SimpleNamespace
    from apps.research.numerical_variable_display import refresh_coefficient_display,FreeCoefficientDelegate,VariableNameDisplay
    table=QTableWidget();host=SimpleNamespace(variables=table)
    refresh_coefficient_display(host,descriptors=[dict(id='E',label='탄성계수')])
    delegates=(host._free_coefficient_display,host._variable_name_display,host._coordinate_display)
    for _ in range(20):refresh_coefficient_display(host,descriptors=[dict(id='E',label='종방향 탄성계수')])
    assert len(table.findChildren(FreeCoefficientDelegate))==1
    assert len(table.findChildren(VariableNameDisplay))==2
    assert delegates==(host._free_coefficient_display,host._variable_name_display,host._coordinate_display)
    assert host._variable_name_display.displayText('E',None)=='종방향 탄성계수'
    table.close()


@pytest.mark.parametrize('late',[False,True])
def test_opt_in_domain_editor_only_updates_same_local_draft_after_review(app,monkeypatch,late):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QLabel,QDialog
    from apps.research.numerical_mixed_plan import open_domain_editor
    import apps.research.numerical_mixed_variables as ui
    raw=declarations();before=deepcopy(raw)
    descriptors=[]
    for row in domains.normalize(raw):
        descriptors.append(ode_solver_descriptor({'solver':{'method':'RK45'}}) if row.get('kind')=='categorical'
            else {**deepcopy(row),'label':row['id'],'value':row.get('value',.1)})
    class Host:
        document=dict(id='Nfixture',session_id='Sfixture',generation=0)
        _view_error=None;_callbacks=0;_pending_adoption=None;_busy=False;_busy_background=False;_closed=False;conflict=False
        def __init__(self):
            self.message=QLabel();self.calls=[];self._worksheet_labels={}
            self.draft={'mode':'request','request':{'operation':'doe','inputs':{'backend':'fixture','settings':{'name':'literal UI fixture'},'variables':deepcopy(raw)}}}
            def read(arguments):self.calls.append(('describe',deepcopy(arguments)));return {'inputs':deepcopy(descriptors)}
            self.client=SimpleNamespace(describe_inputs=read)
        def edited_draft(self,**kwargs):return deepcopy(self.draft)
        def _model_settings(self,inputs):return deepcopy(inputs['settings'])
        def _commit_editor(self):pass
        def _call(self,function,accepted,**kwargs):
            result=function()
            if kwargs['relevant']():accepted(result)
            return True
        def _edit_structure(self,change):change(self.draft['request']['inputs']);self.calls.append(('local_edit',));return True
    host=Host()
    class Dialog:
        def __init__(self,variables,actual,parent,*,operation):
            assert variables==raw and actual==descriptors and operation=='doe'
            self.value=deepcopy(variables);self.value[0]['value']=3
        def exec(self):
            if late:host.document={**host.document,'generation':1}
            return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ui,'MixedVariablesDialog',Dialog)
    assert open_domain_editor(host)
    assert raw==before
    assert host.draft['request']['inputs']['variables'][0]['value']==(1 if late else 3)
    assert [call[0] for call in host.calls]==(['describe'] if late else ['describe','local_edit'])
    if late:assert '변경되었습니다' in host.message.text()


def test_unsupported_method_disables_only_run_without_enabling_other_guards(app):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QPushButton
    from apps.research.numerical_mixed_plan import limit_unsupported_execution
    run=QPushButton();save=QPushButton();run.setEnabled(True)
    inputs={'mode':'request','request':{'operation':'fit','inputs':{'variables':declarations()}}}
    host=SimpleNamespace(document={'id':'Nfixture'},run_button=run,save_button=save,edited_draft=lambda **kwargs:deepcopy(inputs))
    limit_unsupported_execution(host);assert not run.isEnabled() and save.isEnabled()
    inputs['request']['operation']='doe'
    limit_unsupported_execution(host);assert not run.isEnabled()  # Existing action policy owns enabling.
