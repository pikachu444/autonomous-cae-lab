import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.impact_editor import ImpactEditor
from examples.impact.user_model import settings


def test_cancel_precise_and_partial_motion_edit_are_local():
    app=QApplication.instance() or QApplication([])
    original=settings();window=ImpactEditor(original)
    window.resize(1060,700);window.show();app.processEvents()
    window.motion.item(0,5).setText('1e')
    edited=window.edited()
    assert edited['motions'][0]['velocity_mm_s'][2]=='1e'
    assert original['motions'][0]['velocity_mm_s'][2]==-100.
    window.reject();app.processEvents()
    reopened=ImpactEditor(edited)
    reopened.motion.item(0,5).setText('-125.123456789012')
    assert reopened.edited()['motions'][0]['velocity_mm_s'][2]==-125.123456789012
    assert reopened.motion.cellWidget(0,1).currentData()=='velocity'
    reopened.reject()


def test_small_motion_editor_has_full_mode_and_visible_shift_z(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    app=QApplication.instance() or QApplication([])
    window=ImpactEditor(settings());window.tabs.setCurrentWidget(window.motion.parentWidget());window.resize(1060,700);window.show();app.processEvents()
    assert not window.components[14].isHidden() and window.components[14].width()>=100
    combo=window.motion.cellWidget(0,1)
    assert combo.width()>200
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Cancel)
    combo.setCurrentIndex(combo.findData('release_height'))
    assert combo.currentData()=='velocity' and window.edited()['motions'][0]['velocity_mm_s'][2]==-100.
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    combo.setCurrentIndex(combo.findData('release_height'))
    assert window.edited()['motions'][0]['velocity_mm_s']==[0.,0.,0.]
    assert not window.components[5].isEnabled() and window.components[14].isEnabled()
    window.reject()


def test_cohesive_and_exact_response_editor_preserves_partial_cancel():
    from examples.impact.cohesive_model import settings as cohesive_settings
    from copy import deepcopy
    app=QApplication.instance() or QApplication([])
    original=cohesive_settings();saved=deepcopy(original);window=ImpactEditor(original)
    window.damage.selectRow(0);app.processEvents()
    window.damage_fields['mode_I_n_mm'].setText('1e')
    # textEdited is the actual user path; setText alone is programmatic.
    window.damage_fields['mode_I_n_mm'].textEdited.emit('1e')
    window.responses.cellWidget(2,3).setCurrentIndex(window.responses.cellWidget(2,3).findData('xy'))
    edited=window.edited()
    assert edited['cohesive'][0]['mode_I_n_mm']=='1e'
    assert edited['responses'][2]['component']=='xy' and edited['responses'][2]['identity']==3
    window.reject()
    assert original==saved
    reopened=ImpactEditor(edited);reopened.damage.selectRow(0)
    reopened.damage_fields['mode_I_n_mm'].textEdited.emit('0.02345678901234')
    assert reopened.edited()['cohesive'][0]['mode_I_n_mm']==.02345678901234
    reopened.reject()


@pytest.mark.parametrize('accepted',[True,False])
@pytest.mark.parametrize('width',[760,1060])
def test_modal_edit_pauses_owner_refresh_and_restores_polling(accepted,width,monkeypatch):
    from copy import deepcopy
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog,QLabel,QWidget
    from PySide6.QtTest import QTest
    from apps.research.impact_editor import edit
    app=QApplication.instance() or QApplication([])
    class Owner(QWidget):
        def __init__(self):
            super().__init__();self._busy=False;self.local_dirty=False
            self.document={'id':'Doriginal','session_id':'Soriginal','generation':1,
                'draft':{'backend':'explicit.opencourant.model','settings':settings()}}
            self.draft=deepcopy(self.document['draft']);self.message=QLabel(self);self.polls=0
            self.timer=QTimer(self);self.timer.setInterval(5);self.timer.timeout.connect(self.refresh)
        def refresh(self):
            self.polls+=1;self.document['generation']+=1
        def edited_draft(self):return deepcopy(self.draft)
        def _show_document(self,document,*,preserve_draft):
            self.document=deepcopy(document);self.draft=deepcopy(preserve_draft)
        def _update_actions(self):pass
    def modal(dialog):
        dialog.resize(width,500 if width==760 else 700)
        dialog.tabs.setCurrentIndex(dialog.tabs.count()-1)
        field=dialog.times['end_s'];field.clear();field.setFocus();QTest.keyClicks(field,'1e')
        capture=os.environ.get('IMPACT_MODAL_RENDER_DIR')
        if capture:
            from pathlib import Path
            folder=Path(capture);folder.mkdir(parents=True,exist_ok=True)
            QTimer.singleShot(20,lambda:dialog.grab().save(str(folder/f'impact-modal-{width}-{accepted}.png')))
        QTimer.singleShot(40,dialog.accept if accepted else dialog.reject)
        return QDialog.exec(dialog)
    monkeypatch.setattr(ImpactEditor,'exec',modal)
    owner=Owner();original=deepcopy(owner.document);owner.timer.start()
    try:
        edit(owner)
        assert owner.polls==0 and owner.document==original
        assert owner.timer.isActive()
        assert owner.local_dirty is accepted
        assert owner.draft['settings']['time']['end_s']==('1e' if accepted else original['draft']['settings']['time']['end_s'])
    finally:
        owner.timer.stop();owner.close();app.processEvents()


def test_busy_owner_cannot_open_a_second_impact_edit(monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QLabel
    from apps.research.impact_editor import edit
    app=QApplication.instance() or QApplication([])
    def unexpected(*_):raise AssertionError('Busy owner must retain its pending request')
    owner=SimpleNamespace(_busy=True,message=QLabel(),edited_draft=unexpected)
    edit(owner)
    assert '요청' in owner.message.text()
