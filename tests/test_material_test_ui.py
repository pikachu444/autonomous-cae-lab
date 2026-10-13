"""Focused Qt interactions. Transport doubles are explicit; no native/AI execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import time
import threading
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from apps.research.data_window import DataWindow
from apps.research.numerical_window import NumericalWindow
from apps.research.material_test_dialog import ExperimentDialog, TestColumnsDialog
from apps.research.request_plan_window import RequestPlanWindow
from caelab.material_document import default_draft
from caelab.numerical_document import from_material_document, request_draft
from caelab.storage import canonical_hash


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


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
        assert window.canvas.width()>400 and window.canvas.height()>200
        assert window.edited_draft()['variables'][0]['lower']=='1e'
        assert window.study_splitter.orientation()==Qt.Orientation.Horizontal
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
