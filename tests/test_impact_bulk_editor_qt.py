"""B input GUI contracts, public synthetic inputs only; no solver/native runs."""
from copy import deepcopy
from pathlib import Path
import json,subprocess,sys,uuid
import pytest
from PySide6 import QtWidgets
from apps.research.impact_editor import ImpactEditor
from apps.research.impact_bulk_editor import BulkLawDialog,InterfaceDialog,ResponseDialog
from apps.research.impact_source_editor import ReferenceReviewDialog
from caelab import impact_bulk,impact_reference_bindings as bindings
from caelab.impact_model import validate_settings
from caelab.storage import canonical_hash
from examples.impact.bulk_interface.example import settings as public_settings

@pytest.fixture(scope='module')
def app():
    application=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(application);return application

def release(app,*widgets):
    for widget in widgets:widget.close();widget.deleteLater()
    app.processEvents()

def command(owner,document,operation,args=None):
    return owner.document_command(document['id'],operation,args or {},session_id=document['session_id'],
        expected_generation=document['generation'],command_id='C'+uuid.uuid4().hex)

def test_unknown_law_has_no_example_defaults_cancel_and_saved_execution_block(app,tmp_path):
    from caelab.workbench import Workbench
    settings=public_settings();settings['bulk_damage']=[];settings['b_responses']=[];original=deepcopy(settings)
    dialog=BulkLawDialog(settings,'BULK')
    try:
        assert dialog.fields['gf'].text()==dialog.fields['sr'].text()==dialog.fields['source'].text()==''
        dialog.check();assert '미입력' in dialog.status.text() or '교정점' in dialog.status.text()
        dialog.reject();assert settings==original
        dialog.apply();draft=dialog.applied;assert draft['bulk_damage'][0]['evolution']['gf_n_mm']==''
        assert all(value=='' for value in draft['bulk_damage'][0]['initiation']['eta'])
        owner=Workbench(tmp_path/'unknown',configuration={'workers':1})
        try:
            document=owner.document_open(kind='simulation',title='미확인 교정',draft={'backend':'explicit.opencourant.model','settings':draft})
            document=command(owner,document,'document.save')['document']
            assert document['draft']['settings']==draft
            with pytest.raises(ValueError):command(owner,document,'simulation.evaluate')
        finally:owner.shutdown(10)
    finally:release(app,dialog)

def test_existing_table_rate_gf_partial_input_and_parent_cancel_are_local(app,monkeypatch):
    settings=public_settings();original=deepcopy(settings);editor=ImpactEditor(settings);dialog=BulkLawDialog(editor.edited(),'BULK',editor)
    try:
        assert dialog.grid.rowCount()==3 and dialog.grid.columnCount()==4
        assert dialog.grid.item(2,3).text()==str(settings['bulk_damage'][0]['initiation']['plastic_strain'][1][2])
        monkeypatch.setattr(QtWidgets.QMessageBox,'question',lambda *a,**kw:QtWidgets.QMessageBox.StandardButton.Cancel)
        dialog.rate.setChecked(False);assert dialog.rate.isChecked() and dialog.grid.rowCount()==3
        dialog.fields['gf'].setText('1e');dialog.fields['source'].setText('사용자 교정 미완성');dialog.apply()
        assert dialog.applied['bulk_damage'][0]['evolution']['gf_n_mm']=='1e'
        editor.replace_settings(dialog.applied);editor.bulk_page.check();assert '미입력' in editor.bulk_page.status.text() or '유한' in editor.bulk_page.status.text()
        editor.reject();assert settings==original
    finally:release(app,dialog,editor)

def test_delayed_interface_requires_exact_existing_pair_and_clock_not_event(app):
    settings=public_settings();settings['contacts']=[{'a':'LOWERFACE','b':'UPPERFACE','law':'TYPE24','friction':0.}]
    dialog=InterfaceDialog(settings,'BOND')
    try:
        dialog.mode.setCurrentIndex(dialog.mode.findData('DELAYED_TYPE24_REQUIRE_DELETION'))
        dialog.pair.setCurrentIndex(dialog.pair.findData(0));dialog.check();assert '활성 시각' in dialog.status.text()
        dialog.start.setText('.001');dialog.check();assert '확인됨' in dialog.status.text()
        dialog.apply();row=dialog.applied['interface_controls'][0]
        assert row['contact_index']==0 and row['contact_start_s']==.001
        assert row['compression']=='INTACT_COMPRESSION_ISYM0'
        dialog.settings['contacts'].append(deepcopy(settings['contacts'][0]));dialog.check();assert '중복' in dialog.status.text() or '대응면' in dialog.status.text()
    finally:release(app,dialog)

def test_raw_channels_keep_units_and_pair_unknown_and_exact_id(app):
    settings=public_settings();settings['contacts']=[{'a':'LOWERFACE','b':'UPPERFACE','law':'TYPE24','friction':0.}]
    dialog=ResponseDialog(settings)
    try:
        dialog.quantity.setCurrentIndex(dialog.quantity.findData('internal_energy_density'))
        assert 'N/mm^2' in dialog.quantity.currentText()
        dialog.identity.setCurrentIndex(dialog.identity.findData(3));dialog.apply()
        row=dialog.applied['b_responses'][-1];assert row['identity']==3 and row['component']=='scalar'
        dialog.scope.setCurrentIndex(dialog.scope.findData('pair'))
        assert '미확인' in dialog.note.text()
        dialog.component.setCurrentIndex(dialog.component.findData('FTZ'));dialog.apply()
        row=dialog.applied['b_responses'][-1];assert row['identity']==0 and row['component']=='FTZ' and row['scope']=='pair'
    finally:release(app,dialog)

def test_native_rad_keeps_b_unavailable_without_erasing_draft(app):
    from caelab.impact_input_workflow import open_definition
    folder=Path(__file__).resolve().parents[1]/'examples/impact/input_a/native'
    settings=open_definition(folder/'impact_0000.rad',folder,engine=folder/'impact_0001.rad',units='Mg/mm/s')['settings']
    settings['bulk_damage']=[impact_bulk.default_law('UNSUPPORTED_NATIVE')];original=deepcopy(settings);editor=ImpactEditor(settings)
    try:
        assert editor.bulk_page.native and all(not button.isEnabled() for button in editor.bulk_page.actions.values())
        assert '지원하지 않습니다' in editor.bulk_page.note.text()
        assert editor.edited()['bulk_damage']==original['bulk_damage']
    finally:release(app,editor)

def test_b_review_includes_material_members_and_pair_without_reusing_identity(app):
    settings=public_settings();settings['contacts']=[{'a':'LOWERFACE','b':'UPPERFACE','law':'TYPE24','friction':0.}]
    settings['interface_controls'][0].update(reclosure='DELAYED_TYPE24_REQUIRE_DELETION',contact_index=0,contact_start_s=.001)
    settings['b_responses'].append({'name':'PAIR_UNKNOWN','scope':'pair','identity':0,'quantity':'force','component':'FNZ'})
    settings[bindings.KEY]=bindings.snapshot(settings)
    material=next(row for row in settings[bindings.KEY]['rows'] if row['selection']==['bulk_damage',0,'material'])
    material['source']['members'][0]['native_id']=999999
    pair=next(row for row in settings[bindings.KEY]['rows'] if row['selection']==['interface_controls',0,'contact_index'])
    pair['source']['a']['members'][0]['element']['native_id']=888888
    dialog=ReferenceReviewDialog(settings)
    try:
        rows={tuple(path):combo for path,combo in dialog.choices}
        assert rows[('bulk_damage',0,'material')].currentIndex()==-1
        assert rows[('interface_controls',0,'contact_index')].currentIndex()==-1
        for path,combo in dialog.choices:
            if combo.currentIndex()<0:combo.setCurrentIndex(combo.findData(settings[path[0]][path[1]][path[2]]))
        dialog.show_review();assert dialog.confirm.isEnabled()
        assert '999999' in dialog.details.toPlainText() and '888888' in dialog.details.toPlainText()
        before=deepcopy(settings);dialog.reject();assert settings==before
        dialog.apply();assert not bindings.review(dialog.applied)['changed']
    finally:release(app,dialog)

def test_same_simulation_b_save_separate_process_reopen_and_continue(app,tmp_path):
    from caelab.workbench import Workbench
    root=tmp_path/'saved';owner=Workbench(root,configuration={'workers':1});settings=public_settings();editor=ImpactEditor(settings);dialog=None
    try:
        document=owner.document_open(kind='simulation',title='벌크 계면 교정',draft={'backend':'explicit.opencourant.model','settings':settings})
        dialog=BulkLawDialog(editor.edited(),'BULK');dialog.fields['gf'].setText('.75');dialog.fields['source'].setText('공개 합성 입력의 GUI 저장 확인');dialog.apply();editor.replace_settings(dialog.applied)
        validate_settings(editor.edited())
        document=command(owner,document,'simulation.update',{'draft':{'backend':'explicit.opencourant.model','settings':editor.edited()}})['document']
        document=command(owner,document,'document.save')['document'];identifier=document['id'];expected=canonical_hash(document['draft'])
    finally:owner.shutdown(10);release(app,*([dialog] if dialog else []),editor)
    code='from caelab.workbench import Workbench;import sys,json;w=Workbench(sys.argv[1]);\ntry:\n print(json.dumps(w.document_open(kind="simulation",document_id=sys.argv[2])))\nfinally:w.shutdown(10)'
    cold=subprocess.run([sys.executable,'-c',code,str(root),identifier],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,check=True)
    document=json.loads(cold.stdout);assert canonical_hash(document['draft'])==expected
    reopened=ImpactEditor(document['draft']['settings']);continued=BulkLawDialog(reopened.edited(),'BULK')
    try:assert float(continued.fields['gf'].text())==.75 and continued.fields['source'].text()=='공개 합성 입력의 GUI 저장 확인'
    finally:release(app,continued,reopened)


@pytest.mark.parametrize('token',['nan','inf','1e'])
def test_invalid_numeric_tokens_remain_saveable_text_not_nonfinite_json(app,token):
    dialog=BulkLawDialog(public_settings(),'BULK')
    try:
        dialog.fields['gf'].setText(token);dialog.apply()
        assert dialog.applied['bulk_damage'][0]['evolution']['gf_n_mm']==token
        json.dumps(dialog.applied,allow_nan=False)
        with pytest.raises(ValueError):validate_settings(dialog.applied)
    finally:release(app,dialog)


def test_b_review_explicitly_accepts_removed_optional_pair_and_new_material_binding(app):
    settings=public_settings();settings['contacts']=[{'a':'LOWERFACE','b':'UPPERFACE','law':'TYPE24','friction':0.}]
    settings['interface_controls'][0].update(reclosure='DELAYED_TYPE24_REQUIRE_DELETION',contact_index=0,contact_start_s=.001)
    settings[bindings.KEY]=bindings.snapshot(settings)
    settings['interface_controls'][0].update(reclosure='COHESIVE_ONLY',contact_index=None,contact_start_s=None)
    settings['contacts']=[]
    settings[bindings.KEY]['rows']=[row for row in settings[bindings.KEY]['rows'] if row['selection']!=['bulk_damage',0,'material']]
    original=deepcopy(settings);dialog=ReferenceReviewDialog(settings)
    try:
        rows={tuple(path):combo for path,combo in dialog.choices}
        assert ('interface_controls',0,'contact_index') not in rows
        assert rows[('bulk_damage',0,'material')].currentIndex()==-1
        dialog.show_review();assert not dialog.confirm.isEnabled() and settings==original
        rows[('bulk_damage',0,'material')].setCurrentIndex(rows[('bulk_damage',0,'material')].findData('BULK'))
        dialog.show_review();assert dialog.confirm.isEnabled()
        assert 'LOWERFACE' in dialog.details.toPlainText() and 'BULK' in dialog.details.toPlainText()
        dialog.apply();assert dialog.applied['interface_controls'][0]['contact_index'] is None
        assert not bindings.review(dialog.applied)['changed']
        validate_settings(dialog.applied)
    finally:release(app,dialog)


def test_task_labels_and_optional_support_keep_physical_contract_visible(app,monkeypatch):
    settings=public_settings();settings['contacts']=[{'a':'LOWERFACE','b':'UPPERFACE','law':'TYPE24','friction':0.}]
    original=deepcopy(settings)
    bulk=BulkLawDialog(settings,'BULK');interface=InterfaceDialog(settings,'BOND');editor=ImpactEditor(settings)
    opened=[];monkeypatch.setattr(QtWidgets.QMessageBox,'information',lambda parent,title,text:opened.append((title,text)))
    try:
        assert 'SR_REF' in bulk.fields['sr'].toolTip()
        labels=[label.text() for label in bulk.findChildren(QtWidgets.QLabel)]
        assert '기준 변형률 속도 [1/s]' in labels and any('삼축응력비 η' in label for label in labels)
        assert 'η' in bulk.grid.item(0,0).text()
        bulk.support.click();interface.support.click();editor.bulk_page.support.click()
        assert len(opened)==3 and 'EPSD/SR_REF' in opened[0][1] and 'DPLA/dt' in opened[0][1]
        assert '솔버 실행·교정 유효성·공학 승인' in opened[0][1]
        assert '자동 요소 삭제 이벤트가 아닙니다' in opened[1][1] and '압축 이중계상' in opened[1][1]
        assert '공학 승인' not in editor.bulk_page.note.text()
        bulk.check();assert '시험 중인' in bulk.status.text() and '공학 승인' not in bulk.status.text()
        bulk.fields['gf'].setText('1e');bulk.check();assert 'Gf' in bulk.status.text() and 'UNKNOWN' not in bulk.status.text()
        assert 'UNKNOWN' in bulk.status.toolTip()
        assert settings==original
    finally:release(app,bulk,interface,editor)
