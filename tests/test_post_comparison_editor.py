"""Qt selection/draft checks; no ParaView or provider execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.post_comparison_editor import ComparisonEditor, default_recipe


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def sources():
    return [{'source_ref':'Sa','label':'기준 압력',
        'metadata':{'arrays':[{'name':'pressure','association':'POINTS','components':1}], 'timesteps':[0.,1.]},
        'native_metadata': {'coordinate_units':'mm','coordinate_frame':'global',
            'arrays':[{'name':'pressure','association':'POINTS','components':1,'quantity':'stress',
                       'measure':'pressure','units':'MPa','frame':'global'}],
            'time': {'unit':'s','semantics':'physical_time'}}}]


def test_select_actual_array_and_keep_exact_partial_draft(app):
    editor=ComparisonEditor(default_recipe(),sources()); editor.resize(760,230); editor.show(); app.processEvents()
    source, field=editor.selectors['a']; source.setCurrentIndex(source.findData('Sa'))
    source, field=editor.selectors['a']; field.setCurrentIndex(field.findData(['pressure','POINTS']))
    draft=editor.draft()
    assert draft['a']['units']=='MPa' and draft['a']['quantity']=='stress'
    assert draft['a']['sampling']['time'] is None
    draft['tolerance']='1e'; draft['alignment']['translation'][0]='-'
    reopened=ComparisonEditor(draft,sources())
    assert reopened.draft()==draft
    assert editor.width()==760
    editor.close(); reopened.close()


def test_transform_cancel_preserves_recipe_and_no_implicit_sample(app,monkeypatch):
    draft=default_recipe(); draft['a']['source_ref']='Sa'
    editor=ComparisonEditor(draft,sources())
    monkeypatch.setattr(QDialog,'exec',lambda self: QDialog.DialogCode.Rejected)
    editor.settings(); editor.meaning('a')
    assert editor.draft()==draft
    editor.close()


def test_same_label_source_identity_and_unknown_layout_remain_distinct(app):
    rows=sources(); rows.append(dict(rows[0],source_ref='Sb'))
    editor=ComparisonEditor(default_recipe(),rows)
    widget=editor.selectors['b'][0]; widget.setCurrentIndex(widget.findData('Sb'))
    assert editor.draft()['b']['source_ref']=='Sb'
    assert editor.draft()['b']['layout'] is None
    editor.close()


def test_curve_reads_same_rows_units_and_invalid_gaps_without_jobs(app):
    pytest.importorskip('matplotlib')
    from apps.research.post_comparison_plot import ComparisonPlot
    draft=default_recipe(); draft['target']['units']='MPa'; draft['a']['coordinate_units']='mm'
    rows=[{'point_index':5,'coordinates':[1,2,3],'a':2.,'b':3.,'delta':1.},
          {'point_index':6,'coordinates':[2,2,3],'a':0.,'b':None,'delta':None}]
    plot=ComparisonPlot({'rows':rows},{'draft':draft,'preview':False,'object_ref':'A','revision':'V'})
    assert plot.rows==rows and len(plot.figure.axes)==2
    assert 'MPa' in plot.figure.axes[0].get_ylabel()
    assert list(plot.figure.axes[0].lines[0].get_xdata())==[5,6]
    assert len(plot.figure.axes[1].lines[0].get_ydata())==2
    plot.close()


def test_clearing_field_clears_executable_selection(app):
    editor=ComparisonEditor(default_recipe(),sources())
    editor.change_source('a','Sa'); editor.change_field('a',['pressure','POINTS'])
    notifications=[]; editor.changed.connect(lambda: notifications.append(True))
    editor.change_field('a',None)
    assert editor.draft()['a']['array']=='' and editor.draft()['a']['layout'] is None
    assert notifications
    editor.close()


def test_known_derived_layout_and_independent_alignment_survive_dialog_ok(app,monkeypatch):
    draft=default_recipe(); draft['a'].update(source_ref='Sa',array='pressure',units='MPa',
        layout={'kind':'scalar','components':['scalar']})
    draft['alignment'].update(geometry_declared=True,response_declared=False)
    draft['a']['sampling']={'mode':'future_mode','retained_value':'1e'}
    rows=sources(); rows[0]['native_metadata']['arrays'][0]['layout']=draft['a']['layout']
    editor=ComparisonEditor(draft,rows)
    monkeypatch.setattr(QDialog,'exec',lambda self: QDialog.DialogCode.Accepted)
    editor.meaning('a')
    assert editor.draft()['a']['layout']==draft['a']['layout']
    editor.settings()
    assert editor.draft()['a']['sampling']==draft['a']['sampling']
    assert editor.draft()['alignment']['geometry_declared'] is True
    assert editor.draft()['alignment']['response_declared'] is False
    editor.close()



def test_old_plot_cannot_select_new_native_revision_or_a_late_table_row():
    from types import SimpleNamespace
    from apps.research.post_window import PostWindow
    revision = ['V2']; commands = []; selected = []; messages = []
    window = SimpleNamespace(_object_ref='A', _sample_basis={'revision':'V1'},
        _current_sample_revision=lambda preview: revision[0],
        _samples={'rows':[{'point_index':3}]},
        samples=SimpleNamespace(selectRow=lambda row:selected.append(row)),
        message=SimpleNamespace(setText=lambda text:messages.append(text)))
    def queue(operation, arguments, accepted):
        commands.append((operation, arguments, accepted)); return True
    window.queue_command=queue
    basis={'object_ref':'A','revision':'V1','preview':False}
    assert PostWindow.select_comparison_point(window,3,basis) is False
    assert not commands and not selected
    revision[0]='V1'
    assert PostWindow.select_comparison_point(window,3,basis) is True
    assert commands[-1][1]['expected_revision']=='V1'
    commands[-1][2]({'object_ref':'A','revision':'V2'})
    assert selected==[]
    commands[-1][2]({'object_ref':'A','revision':'V1'})
    assert selected==[0]



def test_saved_measurement_array_choices_and_declarations_preserve_partial_geometry():
    from copy import deepcopy
    from types import SimpleNamespace
    from apps.research.post_window import PostWindow
    metadata = {'coordinate_units':'mm','coordinate_frame':'global','time':None,
        'frozen_clock':{'value':.5,'unit':'s','semantics':'physical_time'},
        'arrays':[{'name':'A_original','association':'POINTS','units':'degC',
            'quantity':'temperature','measure':'temperature','frame':'global',
            'temperature_kind':'absolute','layout':{'kind':'scalar','components':['scalar']},
            'validity_masks':['A_finite']}]}
    draft={'source_ref':'A','array':'A_original','association':'POINTS','measurement':'path',
           'point1':['1e',0,0],'point2':[1,0,0],'resolution':'-'}
    editor=SimpleNamespace(_sources=lambda:[], _objects=lambda:[{'id':'A','position':0,'output_metadata':metadata}],
        edited_draft=lambda:deepcopy(draft), _populate_editor=lambda:None, _edited=lambda:None,
        message=SimpleNamespace(setText=lambda text:None))
    editor._source_choice_metadata=lambda ref:PostWindow._source_choice_metadata(editor,ref)
    assert editor._source_choice_metadata('A')[0]['arrays'][0]['name']=='A_original'
    PostWindow.use_declarations(editor)
    assert editor._draft['point1']==['1e',0,0] and editor._draft['resolution']=='-'
    assert editor._draft['temperature_kind']=='absolute'
    assert editor._draft['validity_masks']==['A_finite']
    assert editor._draft['time'] is None and editor._draft['time_units']=='s'
