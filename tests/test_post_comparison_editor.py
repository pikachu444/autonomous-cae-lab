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
