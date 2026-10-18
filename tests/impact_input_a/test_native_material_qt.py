"""Existing native source dialog, preview/apply/cancel; no native physics."""
from copy import deepcopy
import pytest
from PySide6.QtWidgets import QApplication
from apps.research.impact_editor import ImpactEditor
from apps.research.impact_source_editor import SourceChangeDialog
from caelab.impact_native import settings_from_source
from caelab.impact_input_edits import original_files
from caelab.impact_input_workflow import inspect
from native_material_fixtures import make_native


@pytest.fixture(scope='module')
def app():
    value=QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(value)
    return value


@pytest.mark.parametrize('kind,key,value',[('bulk','gf_n_mm',.025),('interface','normal_strength_mpa',2.1)])
def test_native_material_source_preview_cancel_and_explicit_apply(app,tmp_path,kind,key,value):
    _,_,_,source=make_native(tmp_path/'input',kind);settings=settings_from_source(source)
    editor=ImpactEditor(settings);dialog=None
    try:
        editor.show();editor.tabs.setCurrentWidget(editor.source_page);app.processEvents()
        field=next(row for row in inspect(editor.edited())['fields'] if row['field']==key)
        page=editor.source_page
        for i in range(page.files.topLevelItemCount()):
            item=page.files.topLevelItem(i)
            if item.text(0)==field['file']:page.files.setCurrentItem(item);break
        row=next(i for i in range(page.fields.rowCount()) if page.fields.item(i,0).data(256)['id']==field['id'])
        page.fields.selectRow(row);app.processEvents()
        assert field['value'] in page.original.textCursor().selectedText()
        before=deepcopy(editor.edited());dialog=SourceChangeDialog(page,field=field)
        dialog.replacement.setPlainText(str(value));dialog.show_preview();assert dialog.apply_button.isEnabled()
        dialog.reject();assert editor.edited()==before
        dialog.close();dialog.deleteLater();dialog=SourceChangeDialog(page,field=field)
        dialog.replacement.setPlainText(str(value));dialog.show_preview();dialog.apply()
        assert dialog.applied is not None
        editor.replace_settings(dialog.applied)
        current=editor.edited();assert not inspect(current)['blockers']
        assert original_files(current['source'])==original_files(settings['source'])
        assert len(current['source']['edits'])==1
        assert current['bulk_damage'][0]['evolution']['gf_n_mm']==value if kind=='bulk' else current['cohesive'][0]['normal_strength_mpa']==value
        # An incomplete/invalid field preview cannot mutate the live draft.
        changed=deepcopy(current);field=next(row for row in inspect(current)['fields'] if row['field']==key)
        dialog.close();dialog.deleteLater();dialog=SourceChangeDialog(page,field=field)
        dialog.replacement.setPlainText('-1');dialog.show_preview()
        assert not dialog.apply_button.isEnabled() and editor.edited()==changed
    finally:
        if dialog:dialog.close();dialog.deleteLater()
        editor.close();editor.deleteLater();app.processEvents()


@pytest.mark.parametrize('kind,scope,identity,quantity',[('bulk','bulk',1,'active'),('interface','interface',2,'cohesive_active')])
def test_native_material_actual_response_dialog_cancel_apply_and_same_bytes(app,tmp_path,monkeypatch,kind,scope,identity,quantity):
    from apps.research.impact_bulk_editor import ResponseDialog
    from caelab.impact_model import validate_settings
    def forbidden(*a,**k):raise AssertionError('Selecting retained native output must not probe or run a solver')
    monkeypatch.setattr('caelab.adapters.impact.selected_runtime',forbidden)
    monkeypatch.setattr('caelab.adapters.impact.run_owned_command',forbidden)
    _,_,_,source=make_native(tmp_path/'input',kind);settings=settings_from_source(source)
    before=deepcopy(settings);dialog=ResponseDialog(settings)
    try:
        dialog.show();app.processEvents()
        assert dialog.scope.findData(scope)>=0 and dialog.scope.findData('pair')<0
        dialog.scope.setCurrentIndex(dialog.scope.findData(scope))
        assert dialog.identity.count()==1 and dialog.identity.currentData()==identity
        dialog.quantity.setCurrentIndex(dialog.quantity.findData(quantity))
        dialog.reject();assert settings==before
        dialog.close();dialog.deleteLater();dialog=ResponseDialog(settings)
        dialog.scope.setCurrentIndex(dialog.scope.findData(scope));dialog.quantity.setCurrentIndex(dialog.quantity.findData(quantity))
        dialog.apply();assert dialog.applied is not None,dialog.status.text()
        assert settings==before and dialog.applied['source']==source
        assert dialog.applied['b_responses'][0]['scope']==scope and dialog.applied['b_responses'][0]['identity']==identity
        validate_settings(dialog.applied)
    finally:dialog.close();dialog.deleteLater();app.processEvents()
