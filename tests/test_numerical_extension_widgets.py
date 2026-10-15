"""Changed Qt behavior with retained inputs; no JobManager or solver."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication

from apps.research.numerical_extension_widgets import JointDistributionEditor, SobolConvergenceWindow
from apps.research.numerical_methods import MethodDialog, method_settings
from caelab.numerical_extensions import covariance_units, compare_sobol


def variables():
    return [dict(id='x',unit='MPa',value=0.,lower=-20.,upper=20.),dict(id='y',unit='mm',value=0.,lower=-40.,upper=40.)]


def joint():
    return {'family':'multivariate_normal','covariance':{'variables':['x','y'],
        'units':covariance_units(variables()),'matrix':[[4.,4.],[4.,16.]]}}


def analysis(count):
    from caelab.storage import canonical_hash
    context={'backend':'public.algebra','settings':{},'model_source':None,'variables':None}
    return {'method':'SALib.sobol','evaluation_context':context,'evaluation_context_sha256':canonical_hash(context),
        'sampling':{'method':'SALib.sobol','problem':{
        'num_vars':2,'names':['x','y'],'bounds':[[-20,20],[-40,40]]},'base_count':count,'seed':4,'second_order':False},
        'variables':variables(),'response':{'response':'cost','unit':'N'},'matched_design_sha256':str(count%10)*64,
        'candidate_ids':['S'+str(i) for i in range(count*4)],
        'indices':{'S1':[.2,None],'ST':[.3,.7],'S1_conf':[.1,None],'ST_conf':[.12,.2]}}


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def fill(editor, matrix):
    for i,row in enumerate(matrix):
        for j,value in enumerate(row):editor.matrix.item(i,j+1).setText(str(value))


def test_joint_editor_keeps_invalid_original_until_explicit_edit_and_unit_order(app):
    value={'independence':'JOINT_USER_DECLARED','joint':joint()}
    value['joint']['covariance']['variables']=['y','x']
    widget=JointDistributionEditor(value,variables())
    try:
        assert widget.matrix.item(0,1).text()==''
        assert widget.apply(value)==value
        fill(widget,[[4,4],[4,16]])
        got=widget.apply(value)
        assert got['joint']['covariance']['variables']==['x','y']
        assert got['joint']['covariance']['units']==covariance_units(variables())
        assert value['joint']['covariance']['variables']==['y','x']
    finally:widget.close()


def test_joint_editor_no_implicit_matrix_or_assumption_and_switch_preserves_edit(app):
    value={'independence':'INDEPENDENT_USER_DECLARED'}
    widget=JointDistributionEditor(value,variables())
    try:
        widget.family.setCurrentIndex(widget.family.findData('gaussian_copula'))
        assert widget.matrix.item(0,1).text()==''
        fill(widget,[[1,.4],[.4,1]])
        widget.family.setCurrentIndex(widget.family.findData('multivariate_normal'))
        assert widget.matrix.item(0,1).text()==''
        widget.family.setCurrentIndex(widget.family.findData('gaussian_copula'))
        got=widget.apply(value)
        assert got['joint']['correlation']['matrix']==[[1,.4],[.4,1]]
        assert got['independence']=='JOINT_USER_DECLARED'
        assert '잠재 정규' in widget.note.text() and 'Pearson' in widget.note.text()
        widget._clear()
        assert widget.apply(got)=={'independence':'INDEPENDENT_USER_DECLARED'}
    finally:widget.close()


def test_method_dialog_cancel_keeps_distribution_and_neighbors_global_choice(app):
    value={'variables':variables(),'distributions':{},'joint':joint(),'independence':'JOINT_USER_DECLARED'}
    original=deepcopy(value)
    dialog=MethodDialog(None,value,'uq')
    try:
        fill(dialog.joint_editor,[[4,3],[3,16]])
        assert dialog.value()['joint']['covariance']['matrix'][0][1]==3
        dialog.reject()
        assert value==original
        setting=next(row for row in method_settings('surrogate',{}) if row[1]==('options','neighbors'))
        assert setting[2] is None and setting[4]==(('전역',None),)
    finally:dialog.close()


def test_convergence_view_is_exact_read_only_and_handles_small_window(app):
    result=compare_sobol(analysis(8),analysis(16))
    original=deepcopy(result)
    widget=SobolConvergenceWindow(result)
    try:
        widget.resize(680,480);widget.show();app.processEvents()
        assert widget.table.rowCount()==4
        assert widget.table.item(1,4).text()=='—'
        assert widget.table.item(1,4).data(256) is None
        assert result==original
    finally:widget.close()


def test_prediction_search_constraints_partial_draft_and_cancel(app):
    from apps.research.numerical_extension_widgets import SurrogateSearchDialog
    value={'result_refs':{'model':{'original':'reference'}},'search':{
        'variables':variables(),'objective':{'response':'force','unit':'N','direction':'minimize'},
        'constraints':[],'seed':0,'options':{'max_generations':1,'population_size':5}}}
    original=deepcopy(value);dialog=SurrogateSearchDialog(value)
    try:
        dialog.add_constraint.click()
        dialog.constraints.item(0,2).setText('1e')
        dialog.table.item(0,3).setText('-10')
        changed=dialog.value()
        assert changed['search']['constraints'][0]['limit']=='1e'
        assert changed['search']['constraints'][0]['unit']=='N'
        assert changed['search']['variables'][0]['lower']==-10
        dialog.reject();assert value==original
        dialog.constraints.selectRow(0);dialog.remove_constraint.click()
        assert dialog.value()['search']['constraints']==[]
    finally:dialog.close()
