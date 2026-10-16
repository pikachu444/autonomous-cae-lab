"""Real Qt controls; transport/native selection are not replaced by claims."""
from copy import deepcopy
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QComboBox, QCheckBox, QLineEdit
from PySide6.QtTest import QTest
from apps.research.post_comparison_editor import ComparisonEditor
from test_post_strain_measures import recipe
from caelab import post_comparison as p


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def sources():
    rows=[{'name':'strain','association':'POINTS','components':9},
          {'name':'F','association':'POINTS','components':9,'units':'1','frame':'current',
           'material_frame':'reference','orientation':'current_from_reference','basis':'fixed_cartesian',
           'layout':{'kind':'tensor','components':list(p.COMPONENTS),'shear':'tensor','indices':'spatial_material_basis'},
           'validity_masks':['F_quality']}, {'name':'wrong_location','association':'CELLS','components':9},
          {'name':'F_quality','association':'POINTS','components':1}]
    return [{'source_ref':key,'label':label,'metadata':{'arrays':deepcopy(rows)}}
            for key,label in [('A','합성 기준 변형률'),('B','합성 현재 변형률')]]


def type_value(field,text):
    field.selectAll();QTest.keyClicks(field,text)


def draft_recipe():
    value=recipe()
    # Existing settings dialog writes its canonical static clock fields when
    # accepted. Use that existing shape to isolate new strain edit boundaries.
    value['clock']={'value':None,'unit':None,'semantics':None,'exact_tolerance':0.}
    for name in ('a','b'):value[name].update(time=None,clock_offset=0.)
    return value


def test_cancel_and_passive_settings_preserve_original_invalid_draft(app,monkeypatch):
    draft=draft_recipe();draft['b']['deformation_gradient']['orientation']='unresolved orientation'
    editor=ComparisonEditor(draft,sources());before=editor.draft()
    try:
        monkeypatch.setattr(QDialog,'exec',lambda self:QDialog.DialogCode.Rejected)
        editor.settings();assert editor.draft()==before
        monkeypatch.setattr(QDialog,'exec',lambda self:QDialog.DialogCode.Accepted)
        editor.settings();assert editor.draft()==before
    finally:editor.close()


def test_explicit_native_f_and_definition_repair_preserve_raw_fields(app,monkeypatch):
    draft=draft_recipe();draft.pop('strain_conversion');draft['b'].pop('deformation_gradient');draft['b'].pop('strain_precision')
    draft['b'].pop('strain_role');draft['b'].pop('reference_configuration')
    editor=ComparisonEditor(draft,sources())
    def edit(dialog):
        dialog.findChild(QCheckBox,'strainConversionEnabled').setChecked(True)
        field=dialog.findChild(QComboBox,'bGradientArray')
        assert field.findData('wrong_location')<0
        field.setCurrentIndex(field.findData('F'))
        dialog.findChild(QCheckBox,'bStrainTotal').setChecked(True)
        type_value(dialog.findChild(QLineEdit,'bStrainReference'),'undeformed specimen')
        for key,text in [('absolute_tolerance','1e-13'),('relative_tolerance','1e-13'),
                         ('producer','analytic fixture'),('format','float64 E/e/F9'),('reference','predetermined C rounding bound')]:
            type_value(dialog.findChild(QLineEdit,'bStrain'+key),text)
        return QDialog.DialogCode.Accepted
    try:
        monkeypatch.setattr(QDialog,'exec',edit);editor.settings();actual=editor.draft()
        p.validate(actual,[],[])
        assert actual['a']==draft['a']
        assert actual['b']['deformation_gradient']['validity_masks']==['F_quality']
        assert actual['b']['strain_precision']['kind']=='declared_C_bound'
        assert actual['b']['array']==draft['b']['array'] and actual['b']['layout']==draft['b']['layout']
        reopened=ComparisonEditor(actual,sources());assert reopened.draft()==actual;reopened.close()
    finally:editor.close()


def test_known_elastic_role_cannot_be_redeclared_and_no_f_h_needs_no_bound(app,monkeypatch):
    rows=sources();rows[1]['metadata']['arrays'][0].update(strain_role='elastic',measure='material_hencky')
    draft=draft_recipe();draft['b'].update(measure='material_hencky',frame='reference',strain_role='elastic')
    draft['b'].pop('deformation_gradient');draft['b'].pop('strain_precision')
    editor=ComparisonEditor(draft,rows);before=editor.draft()
    def read(dialog):
        assert not dialog.findChild(QCheckBox,'bStrainTotal').isEnabled()
        assert not dialog.findChild(QComboBox,'bStrainMeasure').isEnabled()
        return QDialog.DialogCode.Accepted
    try:
        monkeypatch.setattr(QDialog,'exec',read);editor.settings();assert editor.draft()==before
        draft['b']['strain_role']='total'
        p.validate(draft,[],[])
    finally:editor.close()


def test_no_f_optional_definition_only_changes_on_explicit_selection(app,monkeypatch):
    draft=draft_recipe();draft['b'].update(measure='material_hencky',frame='reference')
    editor=ComparisonEditor(draft,sources())
    def choose(dialog):
        field=dialog.findChild(QCheckBox,'bUseGradient');assert field.isEnabled() and field.isChecked()
        field.setChecked(False);return QDialog.DialogCode.Accepted
    try:
        monkeypatch.setattr(QDialog,'exec',choose);editor.settings();actual=editor.draft()
        assert 'deformation_gradient' not in actual['b']
        assert actual['b']['strain_precision']==draft['b']['strain_precision']
        p.validate(actual,[],[])
    finally:editor.close()


def test_known_producer_bound_stays_read_only(app,monkeypatch):
    draft=draft_recipe();rows=sources()
    rows[1]['metadata']['arrays'][0]['strain_precision']=deepcopy(draft['b']['strain_precision'])
    editor=ComparisonEditor(draft,rows)
    def read(dialog):
        assert dialog.findChild(QLineEdit,'bStrainabsolute_tolerance').isReadOnly()
        assert dialog.findChild(QLineEdit,'bStrainproducer').isReadOnly()
        return QDialog.DialogCode.Accepted
    try:
        monkeypatch.setattr(QDialog,'exec',read);editor.settings();assert editor.draft()==draft
    finally:editor.close()


def test_old_invalid_dual_conversion_can_be_explicitly_repaired(app,monkeypatch):
    draft=draft_recipe();draft['stress_conversion']={'version':1,'target_measure':'cauchy'}
    editor=ComparisonEditor(draft,sources())
    def repair(dialog):
        field=dialog.findChild(QCheckBox,'stressConversionEnabled');assert field.isChecked()
        field.setChecked(False);return QDialog.DialogCode.Accepted
    try:
        monkeypatch.setattr(QDialog,'exec',repair);editor.settings();actual=editor.draft()
        assert 'stress_conversion' not in actual and actual['strain_conversion']==draft['strain_conversion']
        assert actual['a']==draft['a'] and actual['b']==draft['b'];p.validate(actual,[],[])
    finally:editor.close()
