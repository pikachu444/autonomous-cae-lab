"""Local Qt reclosure policy editing; retained owner save/cold without execution."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from apps.research.appearance import apply_appearance
from apps.research.impact_bulk_editor import InterfaceDialog
from caelab.impact_reclosure_policy import POLICY
from examples.impact.cohesive_model import settings as coupon

CASE = ROOT / 'runs/interface-reclosure-20261018/p1-native-01'
DOC = 'V5e2a397dc6a442faad6ab8293a7f824c'


@pytest.fixture(scope='module')
def app():
    value = QApplication.instance() or QApplication([])
    apply_appearance(value)
    return value


def declared():
    value = coupon()
    value['contacts'] = [{'a': 'LOWER_TOP', 'b': 'UPPER_BOTTOM', 'law': 'TYPE24', 'friction': 0.}]
    value['interface_controls'] = [{'material': 'BOND', 'compression': 'INTACT_COMPRESSION_ISYM0',
        'reclosure': POLICY, 'contact_index': 0, 'contact_start_s': None}]
    return value


def click(dialog, standard):
    QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(standard), Qt.MouseButton.LeftButton)


def test_policy_exact_cancel_and_unknown_draft(app):
    original = declared(); before = deepcopy(original)
    for unknown in (False, True):
        value = deepcopy(original)
        if unknown:
            value['interface_controls'][0].update(reclosure='FUTURE_POLICY', compression='FUTURE_COMPRESSION',
                contact_index=19, contact_start_s='incomplete')
        dialog = InterfaceDialog(value, 'BOND')
        try:
            dialog.show(); app.processEvents()
            assert dialog.edited() == value
            assert dialog.mode.currentData() == value['interface_controls'][0]['reclosure']
            if not unknown:
                assert dialog.pair.isEnabled() and not dialog.start.isEnabled()
                assert dialog.view.selected
            click(dialog, QDialogButtonBox.StandardButton.Ok)
            assert dialog.applied == value
        finally:
            dialog.close(); dialog.deleteLater(); app.processEvents()
    dialog = InterfaceDialog(original, 'BOND')
    try:
        dialog.show(); dialog.mode.setCurrentIndex(dialog.mode.findData('DELAYED_TYPE24_REQUIRE_DELETION'))
        dialog.start.setText('0.0006'); click(dialog, QDialogButtonBox.StandardButton.Cancel)
        assert dialog.applied is None and original == before
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_explicit_policy_pair_clock_and_render(app, tmp_path):
    value = declared(); value['interface_controls'][0].update(reclosure='DELAYED_TYPE24_REQUIRE_DELETION',contact_start_s=.0005)
    dialog = InterfaceDialog(value, 'BOND')
    try:
        dialog.show(); dialog.mode.setFocus()
        dialog.mode.setCurrentIndex(dialog.mode.findData('DELETION_GATED_TYPE24')); app.processEvents()
        assert dialog.pair.isEnabled() and not dialog.start.isEnabled()
        assert dialog.edited()['interface_controls'][0]['contact_start_s'] is None
        dialog.pair.setFocus(); QTest.keyClick(dialog.pair, Qt.Key.Key_Home)
        assert dialog.pair.currentData() is None
        QTest.keyClick(dialog.pair, Qt.Key.Key_Down)
        assert dialog.pair.currentData() == 0 and dialog.view.selected
        dialog.check()
        assert '입력의 대응면' in dialog.status.text()
        for w,h,name in [(780,680,'reclosure-normal.png'),(650,610,'reclosure-narrow.png')]:
            dialog.resize(w,h); app.processEvents()
            assert dialog.grab().save(str(tmp_path/name))
            assert dialog.pair.geometry().right() <= dialog.width()
            button=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
            assert button.mapTo(dialog,button.rect().bottomRight()).y() < dialog.height()
        click(dialog, QDialogButtonBox.StandardButton.Ok)
        assert dialog.applied['interface_controls'][0]['reclosure'] == POLICY
        assert dialog.applied['interface_controls'][0]['contact_start_s'] is None
        assert dialog.applied['source'] == value['source']
        assert dialog.applied['cohesive'] == value['cohesive']
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_retained_p1_owner_editor_save_and_separate_cold(app, tmp_path, monkeypatch):
    from apps.research.impact_editor import ImpactEditor
    from examples.s1_windows_transfer import local_service, command
    import caelab.adapters.impact as adapter
    from caelab.storage import canonical_hash
    if not (CASE/'store').exists():
        pytest.skip('Retained private P1 store is required for actual owner integration')
    def forbidden(*a,**k):
        raise AssertionError('GUI save/cold must not probe or execute a solver')
    monkeypatch.setattr(adapter,'selected_runtime',forbidden)
    monkeypatch.setattr(adapter,'run_owned_command',forbidden)
    store=tmp_path/'store';shutil.copytree(CASE/'store',store)
    original_file=CASE/'declared-settings.json';original_sha=hashlib.sha256(original_file.read_bytes()).hexdigest()
    with local_service(store) as (wb,client):
        jobs=client.request('/api/workbench')['jobs']
        document=client.document_open(kind='simulation',document_id=DOC)
        original=deepcopy(document['draft']['settings'])
        assert original['interface_controls'][0]['reclosure']==POLICY
        editor=ImpactEditor(original)
        try:
            editor.show();editor.tabs.setCurrentWidget(editor.bulk_page);editor.bulk_page.tabs.setCurrentIndex(1)
            app.processEvents();table=editor.bulk_page.tables['interface'];table.selectRow(0)
            baseline=editor.edited();assert baseline==original
            assert '원 삭제 감지 후 TYPE24' in table.item(0,1).text()
            errors=[]
            def modal(accept):
                def act():
                    dialog=app.activeModalWidget()
                    try:
                        assert isinstance(dialog,InterfaceDialog)
                        assert dialog.mode.currentData()==POLICY and dialog.pair.currentData()==0
                        assert not dialog.start.isEnabled()
                        if accept:
                            dialog.check();assert '입력의 대응면' in dialog.status.text()
                            for w,h,name in [(780,680,'p1-policy-normal.png'),(650,610,'p1-policy-narrow.png')]:
                                dialog.resize(w,h);dialog.pair.setFocus();app.processEvents()
                                assert dialog.grab().save(str(tmp_path/name))
                        else:
                            dialog.mode.setCurrentIndex(dialog.mode.findData('COHESIVE_ONLY'))
                        click(dialog,QDialogButtonBox.StandardButton.Ok if accept else QDialogButtonBox.StandardButton.Cancel)
                    except BaseException as error:
                        errors.append(error);dialog.reject()
                QTimer.singleShot(40,act)
                QTest.mouseClick(editor.bulk_page.actions['interface','edit'],Qt.MouseButton.LeftButton)
                if errors:raise errors[0]
            modal(False);assert editor.edited()==baseline
            table.selectRow(0);modal(True);assert editor.edited()==baseline
            assert editor.tabs.currentWidget() is editor.bulk_page
            assert editor.bulk_page.tabs.currentIndex()==1
            edited=editor.edited();draft=deepcopy(document['draft']);draft['settings']=edited
            document=command(client,document,'simulation.update',{'draft':draft})['document']
            document=command(client,document,'document.save')['document']
            assert document['draft']['settings']==original
            assert client.request('/api/workbench')['jobs']==jobs
            expected={'document_id':DOC,'settings_sha256':canonical_hash(original),
                'jobs':jobs,'source_sha256':hashlib.sha256(original['source']['text'].encode()).hexdigest()}
            (tmp_path/'expected.json').write_text(json.dumps(expected),encoding='utf-8')
        finally:
            editor.close();editor.deleteLater();app.processEvents()
    run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--cold',str(tmp_path)],
        cwd=ROOT,capture_output=True,text=True,timeout=60)
    (tmp_path/'cold.stdout.log').write_text(run.stdout,encoding='utf-8')
    (tmp_path/'cold.stderr.log').write_text(run.stderr,encoding='utf-8')
    assert run.returncode==0,run.stderr
    assert hashlib.sha256(original_file.read_bytes()).hexdigest()==original_sha
    (tmp_path/'receipt.json').write_text(json.dumps({'status':'PASS','qt_platform':app.platformName(),
        'cancel_preserved':True,'accepted_policy_exact':True,'cold_process':True,'new_jobs':0,
        'new_solver':0,'original_settings_file_unchanged':True,'source_sha256':original_sha,
        'product_sha256':hashlib.sha256((ROOT/'apps/research/impact_bulk_editor.py').read_bytes()).hexdigest()},indent=2),encoding='utf-8')


def cold(folder):
    from examples.s1_windows_transfer import local_service
    from caelab.storage import canonical_hash
    import caelab.adapters.impact as adapter
    def forbidden(*a,**k):raise AssertionError('Cold reclosure open must not run or probe a solver')
    adapter.selected_runtime=forbidden;adapter.run_owned_command=forbidden
    folder=Path(folder);expected=json.loads((folder/'expected.json').read_text())
    app=QApplication([]);apply_appearance(app)
    with local_service(folder/'store') as (wb,client):
        jobs=client.request('/api/workbench')['jobs']
        doc=client.document_open(kind='simulation',document_id=expected['document_id'])
        settings=doc['draft']['settings'];assert canonical_hash(settings)==expected['settings_sha256']
        dialog=InterfaceDialog(settings,'BOND')
        try:
            dialog.show();app.processEvents()
            assert dialog.edited()==settings and dialog.mode.currentData()==POLICY
            assert dialog.pair.currentData()==0 and not dialog.start.isEnabled()
            assert dialog.grab().save(str(folder/'p1-policy-cold.png'))
            click(dialog,QDialogButtonBox.StandardButton.Cancel)
            assert client.document_read(doc['id'])==doc
            assert client.request('/api/workbench')['jobs']==jobs
            (folder/'cold.json').write_text(json.dumps({'status':'PASS','settings_exact':True,
                'new_jobs':0,'new_solver':0,'pid':__import__('os').getpid()}),encoding='utf-8')
        finally:
            dialog.close();dialog.deleteLater();app.processEvents()


if __name__=='__main__':
    assert sys.argv[1]=='--cold'
    cold(sys.argv[2])
