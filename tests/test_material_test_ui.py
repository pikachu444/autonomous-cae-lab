"""Focused Qt interactions. Transport doubles are explicit; no native/AI execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import time
import threading
import warnings
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QFileDialog, QInputDialog
from apps.research.data_window import DataWindow
from apps.research.numerical_window import NumericalWindow
from apps.research.material_test_dialog import ExperimentDialog, TestColumnsDialog
from apps.research.request_plan_window import RequestPlanWindow
from caelab.material_document import default_draft
from caelab.numerical_document import from_material_document, request_draft
from caelab.storage import canonical_hash


@pytest.fixture
def app():
    application=QApplication.instance() or QApplication([])
    previous=set(application.topLevelWidgets())
    yield application
    # Includes assertion-failure cleanup: never leave a read scheduled against
    # a later test's dead service or a disappearing QApplication.
    for window in set(application.topLevelWidgets())-previous:
        if isinstance(window,(DataWindow,NumericalWindow)):
            window._allow_close=True
            window.close()
    application.processEvents()
    assert QThreadPool.globalInstance().waitForDone(5000), 'D5 read workers did not drain'
    application.processEvents()


def wait(app,condition):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        app.processEvents()
        if condition():return
        time.sleep(.005)
    raise AssertionError('changed Qt callback did not settle')


def document():
    material={'id':'Mtest','input_revision':'Itest','generation':0,'draft':default_draft()}
    return dict(id='Ntest',session_id='Sowner',generation=0,input_revision='In',title='시편 피팅',
        draft=from_material_document(material),runs=[],diagnostics=[],dirty=False)


def test_fit_layout_physical_residual_selection_and_precise_draft(app):
    window=NumericalWindow(None,auto_open=False,poll_interval=0)
    doc=document()
    run={'job_id':'Jfit','input_generation':0,'input_revision':'In','draft':deepcopy(doc['draft'])}
    doc['runs']=[run]
    window._show_document(doc)
    observations={'unit':'MPa','component':'xx','axes':[{'name':'time','unit':'s','values':[0,1,2]}],'value':[0,1,2]}
    window._result_cache['Jfit']={'kind':'fit','parameters':{'E':1200,'nu':.25},'candidates':[],
        'curves':[dict(experiment_id='Test1',role='fit',execution_status='SUCCEEDED',
                      observations=observations,prediction=[0,1.2,1.8],residual=[90,90,90],rmse=.2),
                  dict(experiment_id='Test2',role='holdout',execution_status='FAILED',
                      observations=observations,failure_reason='budget exhausted')]}
    window._draw_result()
    assert list(window.figure.axes[1].lines[0].get_ydata())==pytest.approx([0,.2,-.2])
    window.curve_selector.setCurrentIndex(1)
    assert 'FAILED' in window.figure.axes[0].get_title()
    assert not any(line.get_label()=='최종 예측' for line in window.figure.axes[0].lines)
    window.variables.item(0,3).setText('1e')
    for width,height in ((1100,780),(1440,900)):
        window.resize(width,height);window.show();app.processEvents()
        assert window.width()==width and window.height()==height
        assert window.editor.width()<=480 and window.canvas.width()>400 and window.canvas.height()>200
        assert window.canvas.width()>window.editor.width()
        with warnings.catch_warnings(record=True) as observed_warnings:
            warnings.simplefilter('always')
            window.canvas.draw()
        from apps.research.appearance import configure_plot_fonts
        family=configure_plot_fonts()
        if os.name=='nt':
            assert family, 'Windows chart requires an existing installed Korean font'
        if family:
            assert not [warning for warning in observed_warnings if 'Glyph' in str(warning.message)]
        assert window.edited_draft()['variables'][0]['lower']=='1e'
        assert window.study_splitter.orientation()==Qt.Orientation.Horizontal
    window.variables.item(0,3).setText('NaN')
    import json
    json.dumps(window.edited_draft(),allow_nan=False)
    assert window.edited_draft()['variables'][0]['lower']=='NaN'
    window._allow_close=True;window.close()


def test_coefficient_display_keeps_exact_editor_and_partial_input(app):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit
    window=NumericalWindow(None,auto_open=False,poll_interval=0)
    doc=document()
    value=1199.9999999999853
    doc['draft']['variables'][0].update(value=value,lower=value/10,upper=value*10)
    window._show_document(doc);window.show();app.processEvents()
    item=window.variables.item(0,2)
    assert window.edited_draft()['variables'][0]['value']==value
    assert item.toolTip()==repr(value)
    assert window.variables.itemDelegateForColumn(2).displayText(item.text(),window.locale())=='1200'
    window.variables.editItem(item);app.processEvents()
    editor=window.variables.findChild(QLineEdit)
    assert editor is not None and editor.text()==repr(value)
    editor.setText('1e');QTest.keyClick(editor,Qt.Key.Key_Tab);app.processEvents()
    assert window.edited_draft()['variables'][0]['value']=='1e'
    assert window.variables.item(0,2).toolTip()=='1e'
    window._allow_close=True;window.close()


def test_curve_interval_uses_original_rows_and_separate_masks(app):
    from caelab.data_document import default_draft as data_draft
    draft=data_draft();draft['data_id']='Dtest'
    spec=draft['mapping']['columns']['response']
    spec['row_selection']={'quality_rows':[8],'display_hidden_rows':[9]}
    run={'job_id':'Jdata','input_generation':0,'input_revision':'Idata','input_sha256':canonical_hash(draft)}
    doc=dict(id='Ttest',session_id='Sowner',generation=0,input_revision='Idata',title='시험',
        draft=draft,runs=[run],diagnostics=[],dirty=False)
    window=DataWindow(None,auto_open=False,poll_interval=0)
    window._show_document(doc)
    response={'kind':'series','unit':'MPa','component':'xx','measure':'infinitesimal_Cauchy','frame':'material_cartesian',
        'axes':[{'name':'time','unit':'s','values':[0,1,2,3]}],'value':[0,1,2,3],'source_rows':[4,7,8,9]}
    receipt={'status':{'state':'SUCCEEDED'},'metadata':{'responses':{'response':response}},
        'result':{'responses':{'response':response}}}
    window._results[window._result_key()]=receipt;window._draw_result(receipt,window._result_key())
    window._select_curve_interval(.5,2.5)
    assert {window.values.item(i.row(),0).text() for i in window.values.selectedIndexes()}=={'7','8'}
    window.select_calculation_rows('exclude')
    selection=window.edited_draft()['mapping']['columns']['response']['row_selection']
    assert selection['exclude_rows']==[7,8]
    assert selection['quality_rows']==[8] and selection['display_hidden_rows']==[9]
    assert doc['draft']==draft
    window.row_fields['exclude_rows'].setText('1e')
    window._select_curve_interval(.5,2.5)
    before=deepcopy(window.edited_draft())
    window.select_calculation_rows('exclude')
    assert window.edited_draft()==before and '미완성' in window.message.text()
    window._allow_close=True;window.close()


def test_protocol_cancel_and_explicit_driver_use(app):
    response=dict(kind='series',unit='1',component='xx',measure='engineering_strain',frame='material_cartesian',
        location='material_point',reduction='none',value=[0,.01],
        axes=[dict(name='time',unit='s',values=[0,1])])
    stress={**deepcopy(response),'unit':'MPa','measure':'infinitesimal_Cauchy','value':[0,12]}
    result={'execution_status':'SUCCEEDED','responses':{'strain':response,'stress':stress}}
    settings=default_draft()['settings'];before=deepcopy(settings)
    dialog=ExperimentDialog(settings,result)
    dialog.reject();assert dialog.value is None and settings==before
    dialog=ExperimentDialog(settings,result)
    dialog.protocol.setCurrentIndex(1);dialog.driver.setCurrentIndex(dialog.driver.findData('strain'))
    dialog.lateral_22.setText('1');dialog.lateral_33.setText('1')
    dialog.role.setCurrentIndex(1);dialog._accept()
    assert dialog.result()==QDialog.DialogCode.Accepted
    assert dialog.value['role']=='holdout'
    assert dialog.value['settings']['deformation_gradient'][1][0][0]==1.01
    assert settings==before
    dialog.weight.setText('nan');dialog.scale.setText('inf');dialog._accept()
    import json
    json.dumps(dialog.value,allow_nan=False)
    assert dialog.value['weight']=='nan' and dialog.value['scale']=='inf'


def test_update_receipt_preserves_late_edits(app):
    release=threading.Event()
    original=document()
    class Client:
        def document_command(self,*args,**kw):
            release.wait(2)
            return {'document':{**original,'generation':1,'draft':deepcopy(args[2]['draft'])}}
    window=NumericalWindow(Client(),auto_open=False,poll_interval=0);window._show_document(original)
    window.variables.item(0,2).setText('900');window.apply_inputs()
    window.variables.item(0,2).setText('850')
    release.set();wait(app,lambda:not window._busy)
    assert window.edited_draft()['variables'][0]['value']==850 and window.local_dirty
    assert window.document['draft']['variables'][0]['value']==900
    window._allow_close=True;window.close()


def test_saved_cad_declarations_are_display_fallbacks_not_draft_mutations(app):
    window=RequestPlanWindow(None,auto_open=False,poll_interval=0)
    inputs={'backend':'structure.cad.calculix','settings':{'recipe':{
        'variables':[{'id':'length','label':'Stock 길이'}],
        'responses':[{'id':'force','kind':'contact_resultant','quantity':'CFN','component':'Z',
            'unit':'N','increment':'final','reduction':'value'}]}},
        'variables':[{'id':'length','value':20,'lower':19,'upper':22,'unit':'mm'}],
        'responses':['force'],'count':2,'seed':0}
    doc=document();doc['draft']=request_draft({'purpose':'CAD 후보','operation':'doe','inputs':inputs,'budget':{'evaluations':2}})
    window._show_document(doc)
    before=deepcopy(window.edited_draft())
    assert window.variable_sheet.item(0,0).text()=='Stock 길이'
    assert window.response_sheet.item(0,5).text()=='N'
    assert 'CFN' in window.response_sheet.item(0,1).toolTip()
    window._worksheet_responses['force']={'unit':'kN','reduction':'final'}
    window._worksheet_labels['length']='선택한 길이'
    window._refresh_worksheet()
    assert window.response_sheet.item(0,5).text()=='kN'
    assert window.variable_sheet.item(0,0).text()=='선택한 길이'
    assert window.edited_draft()==before
    window._allow_close=True;window.close()


def test_new_upload_clears_old_columns_when_preview_fails(app,tmp_path,monkeypatch):
    from caelab.data_document import default_draft as data_draft
    class Client:
        preview_calls=0
        def upload(self,name,payload):
            assert name=='new.csv'
            return {'id':'Dnew','name':name}
        def input_preview(self,identifier):
            assert identifier=='Dnew'
            self.preview_calls+=1
            raise ValueError('new source preview unavailable')
    source=tmp_path/'new.csv';source.write_text('t,x\n0,1\n',encoding='utf-8')
    client=Client();window=DataWindow(client,auto_open=False,poll_interval=0)
    draft=data_draft();draft['data_id']='Dold'
    doc=dict(id='Ttest',session_id='Sowner',generation=0,input_revision='Id',title='시험',
        draft=draft,runs=[],diagnostics=[],dirty=False)
    window._show_document(doc)
    window._preview={'table_preview':{'headers':['OLD'],'rows':[['7']]}}
    window._preview_key=('Ttest','Dold',None);window.preview_table.setRowCount(1)
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args: (str(source),''))
    window.choose_local_csv()
    wait(app,lambda:client.preview_calls==1 and not window._busy)
    assert window._source_id=='Dnew' and window._preview is None and window.preview_table.rowCount()==0
    before=deepcopy(window.edited_draft())
    window.configure_test_columns()
    assert window.edited_draft()==before and '현재 CSV' in window.message.text()
    window._allow_close=True;window.close()


def test_fit_names_measured_axis_and_old_summary_never_cross_runs(app):
    settings=default_draft()['settings']
    trial=lambda i,component,kind: dict(id='Test'+str(i),role='fit',source={
        'document_id':'T'+str(i),'job_id':'J'+str(i),'input_revision':'I'+str(i),'input_sha256':str(i)*64,'response':'stress'},
        response='stress_'+component,settings=deepcopy(settings),weight=1.,scale=1.,
        kinematics=dict(channel='deformation',kind=kind,lateral_22=1,lateral_33=1))
    doc=document()
    frozen=[trial(1,'xx','engineering_strain'),trial(2,'xy','simple_shear')]
    doc['draft']['experiments']=deepcopy(frozen)
    run=dict(job_id='Jfit',input_generation=0,input_revision='In',draft=deepcopy(doc['draft']))
    doc['runs']=[run,dict(job_id='Jfailed',input_generation=0,input_revision='In',draft=deepcopy(doc['draft']))]
    window=NumericalWindow(None,auto_open=False,poll_interval=0);window._show_document(doc)
    curves=[]
    for item,filename,drive in zip(frozen,['axial.csv','shear.csv'],[[0,.002,.001],[0,.01,-.005]]):
        component=item['response'].removeprefix('stress_')
        obs=dict(kind='series',unit='MPa',component=component,value=[0,1,2],source_rows=[4,7,8],
            axes=[dict(name='time',unit='s',values=[0,1,2])],source_selector={'file':'source.csv'})
        driver=dict(kind='series',unit='1',measure=item['kinematics']['kind'],component=component,
            frame='material_cartesian',location='material_point',reduction='none',source_rows=[4,7,8],
            axes=[dict(name='time',unit='s',values=[0,1,2])],value=drive)
        window._trial_sources[window._trial_source_key(item)]={'filename':filename,'title':filename,
            'result':dict(execution_status='SUCCEEDED',responses={'stress':obs,'deformation':driver})}
        curves.append(dict(experiment_id=item['id'],role='fit',execution_status='SUCCEEDED',
            observations=obs,prediction=[0,1.2,1.8],rmse=.2))
    window._refresh_experiment_labels()
    assert window.experiments.item(0,2).text()=='axial.csv / xx'
    assert window.experiments.item(1,2).text()=='shear.csv / xy'
    window._result_cache['Jfit']=dict(kind='fit',parameters={'E':1200,'nu':.25},curves=curves)
    window._result_cache['Jfailed']=dict(kind='fit',execution_status='FAILED',error='retained failure')
    window._populate_runs('Jfit');window._draw_result()
    assert 'axial.csv / xx' in window.curve_selector.itemText(0)
    assert 'shear.csv / xy' in window.curve_selector.itemText(1)
    # Current unsent protocol is deliberately different; old result uses frozen run.
    window._experiments[1]['kinematics']['channel']='not-the-retained-driver'
    window.curve_selector.setCurrentIndex(1);window.plot_axis.setCurrentIndex(1)
    top,bottom=window.figure.axes
    assert list(top.lines[0].get_xdata())==[0,.01,-.005]
    assert list(top.lines[1].get_xdata())==[0,.01,-.005]
    assert list(bottom.lines[0].get_xdata())==[0,.01,-.005]
    assert list(bottom.lines[0].get_ydata())==pytest.approx([0,.2,-.2])
    assert '전단량' in bottom.get_xlabel() and '1200' in window.curve_summary.text()
    # Selecting an unread result / failure clears both curve and coefficient summary.
    window._populate_runs('Jfailed');window._draw_result()
    assert window.curve_summary.text()=='' and window.curve_selector.count()==0
    window._result_cache.pop('Jfailed');window._draw_result()
    assert window.curve_summary.text()==''
    window._allow_close=True;window.close()


def test_deformation_display_does_not_bind_deformation_as_stress(app,monkeypatch):
    from caelab.data_document import default_draft as data_draft
    import apps.research.desktop
    stress=dict(kind='series',measure='infinitesimal_Cauchy',component='xx',unit='MPa',
        axes=[dict(name='time',unit='s')])
    class Client:
        calls=[]
        def document_result(self,identifier,job,*,selection=None):
            return {'execution_status':'SUCCEEDED','responses':{
                'deformation':{**stress,'measure':'engineering_strain','unit':'1'},'stress':stress}}
        def documents(self):
            return {'documents':[dict(id='Mtest',kind='material',title='저장된 재료',draft=default_draft())]}
        def data_followup(self,source,kind,**kw):
            self.calls.append(deepcopy(source))
            assert source['response']=='stress' and kw['material_document_id']=='Mtest'
            return {'executed':False,'document':{'id':'Ncreated','title':'피팅'}}
    client=Client();window=DataWindow(client,auto_open=False,poll_interval=0)
    monkeypatch.setattr(window,'refresh_result',lambda:None)
    draft=data_draft();draft['data_id']='Dtest'
    doc=dict(id='Ttest',session_id='Sowner',generation=0,input_revision='Id',title='시험',
        draft=draft,runs=[dict(job_id='Jtest',input_generation=0,input_revision='Id',input_sha256='a'*64)],diagnostics=[],dirty=False)
    window._show_document(doc);window.result_channel.blockSignals(True)
    window.result_channel.addItem('deformation');window.result_channel.blockSignals(False)
    window._selected_job='Jtest';window._result_channel='deformation'
    # Cancel at observation selection must not create a Material or Plan.
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**kw: ('',False))
    window.request_followup('numerical');wait(app,lambda:not window._busy)
    assert client.calls==[] and window.document['draft']==draft
    def choose(parent,title,label,choices,*args,**kwargs):
        return (choices[-1],True)
    monkeypatch.setattr(QInputDialog,'getItem',choose)
    monkeypatch.setattr(apps.research.desktop,'launch_tool',lambda *a,**kw: None)
    # Command-path double models the explicit chooser/owner calls, not polling.
    receipts=[];window.numerical_requested.connect(receipts.append)
    window.request_followup('numerical')
    wait(app,lambda:bool(receipts) and not window._busy)
    assert receipts[0]['source']['response']=='stress' and window.document['draft']==draft
    assert window.result_channel.currentText()=='deformation'
    window._allow_close=True;window.close()


def test_delayed_run_read_keeps_new_selection_and_summary(app):
    release=threading.Event()
    doc=document()
    doc['runs']=[dict(job_id=job,input_generation=0,input_revision='In',draft=deepcopy(doc['draft']))
                 for job in ('Jold','Jnew')]
    class Client:
        def status(self,job):
            release.wait(2);return {'state':'SUCCEEDED','result_refs':[1]}
        def document_result(self,identifier,job):
            return {'kind':'fit','parameters':{'E':999},'curves':[]}
    window=NumericalWindow(Client(),auto_open=False,poll_interval=0);window._show_document(doc)
    window._populate_runs('Jold');window.refresh_result()
    window._populate_runs('Jnew');window._draw_result();release.set()
    wait(app,lambda:not window._busy)
    assert window.selected_job()=='Jnew' and window.curve_summary.text()==''
    assert 'Jold' in window._result_cache
    window._allow_close=True;window.close()
