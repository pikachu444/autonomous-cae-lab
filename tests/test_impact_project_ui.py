"""Offscreen Qt workflow; no native solver or fabricated solver values."""
from copy import deepcopy
from pathlib import Path
import os
import tempfile
import time
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox
from PySide6.QtCore import Qt
from apps.research.appearance import apply_appearance
from apps.research.impact_editor import ImpactEditor
from apps.research.impact_project import TargetDialog,ImportDialog,MeshPreview
from examples.impact.include_project import settings
from caelab.impact_model import model_from_settings

APP=QApplication.instance() or QApplication([])
apply_appearance(APP)
ROOT=Path(__file__).resolve().parents[1]


def wait(predicate,seconds=3):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        APP.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Qt operation did not finish')


class ProjectUITests(unittest.TestCase):
    def tearDown(self):
        for window in APP.topLevelWidgets():window.close()
        APP.processEvents()
    def test_model_face_selection_and_cancel_preserve_incomplete_conditions(self):
        original=settings();window=ImpactEditor(original);window.resize(1100,780);window.show();APP.processEvents()
        window.motion.item(0,5).setText('1e');window.times['end_s'].setText('0.00400000000000001')
        before=window.edited();dialog=TargetDialog(before,'MOVING','surface',parent=window)
        dialog.show();APP.processEvents();dialog.select_face((2,'S1'))
        self.assertEqual([(f['element'],f['side']) for f in dialog.chosen()],[(2,'S1')])
        self.assertIn((2,'S1'),dialog.view.selected)
        dialog.reject();self.assertEqual(window.edited(),before);self.assertEqual(original['motions'][0]['velocity_mm_s'][2],-10.)
        dialog=TargetDialog(before,'MOVING','surface',parent=window);dialog.name.setText('OTHER_FACE');dialog.select_face((2,'S2'));dialog.apply()
        self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)
        window.value['generated_sets'].append(dialog.result_definition);window.project.refresh()
        self.assertEqual(window.motion.item(0,5).text(),'1e');self.assertEqual(window.times['end_s'].text(),'0.00400000000000001')
        self.assertIn('OTHER_FACE',model_from_settings(window.edited())['surfaces'])
        self.assertEqual(window.size().width(),1100);self.assertGreater(window.project.view.width(),550);self.assertGreater(window.project.view.height(),400)
    def test_edit_reference_and_delete_are_explicit(self):
        original=settings();window=ImpactEditor(original)
        definition=original['generated_sets'][1]
        dialog=TargetDialog(window.edited(),'BASE','surface',definition,window)
        self.assertTrue(dialog.name.isReadOnly());dialog.table.clearSelection();dialog.select_face((1,'S3'));dialog.apply()
        self.assertEqual(dialog.result_definition['faces'],[[1,'S3']]);self.assertEqual(window.edited(),original)
        group=window.project.tree.topLevelItem(2)
        item=next(group.child(i) for i in range(group.childCount()) if group.child(i).text(0)=='LOWER_CONTACT')
        window.project.tree.setCurrentItem(item)
        with patch.object(QMessageBox,'question',side_effect=AssertionError('referenced deletion must not reach confirmation')):window.project.remove()
        self.assertIn('사용 중',window.project.message.text());self.assertEqual(window.edited(),original)
    def test_existing_motion_target_can_change_elset_without_changing_live_conditions(self):
        original=settings();dialog=TargetDialog(original,'MOVING','nset',original['generated_sets'][0])
        dialog.element_set.setCurrentText('BASE')
        self.assertTrue(dialog.internal.isEnabled());self.assertEqual(dialog.view.nodes,set(range(1,9)))
        dialog.apply()
        self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.result_definition['nodes'],list(range(1,9)))
        self.assertEqual(dialog.result_definition['name'],'MOVEMENT')
        self.assertEqual(original['generated_sets'][0]['nodes'],list(range(11,19)))
        self.assertEqual(original['motions'][0]['velocity_mm_s'],[0.,0.,-10.])
    def test_target_change_does_not_transfer_row_selection_to_different_face(self):
        dialog=TargetDialog(settings(),'MOVING','surface');dialog.name.setText('NEW_FACE')
        dialog.select_face((2,'S1'));dialog.element_set.setCurrentText('BASE')
        self.assertEqual(dialog.chosen(),[]);dialog.apply();self.assertIsNone(dialog.result_definition)
        dialog.select_face((1,'S2'));dialog.mode.setCurrentIndex(1)
        self.assertEqual(dialog.chosen(),[])
    def test_large_mesh_context_sampling_keeps_selected_face_visible(self):
        from caelab import impact_sets as sets
        source=model_from_settings(settings());model={'nodes':{},'elements':{}}
        for i in range(1001):
            conn=[]
            for n in range(1,9):
                key=i*8+n;conn.append(key);model['nodes'][key]=[source['nodes'][n][0]+i*12,*source['nodes'][n][1:]]
            model['elements'][i+1]={'type':'C3D8','nodes':conn}
        view=MeshPreview();view.resize(800,500);view.set_model(model,selected=[(1,'S2')]);view.show();APP.processEvents()
        self.assertIn((1,'S2'),[key for _,key in view.polygons]);self.assertLess(len(view.polygons),len(view.faces))
    def test_import_failed_cancelled_and_successful_snapshots(self):
        dialog=ImportDialog();dialog.entry.setText(str(ROOT/'examples/impact/include-project/model.inp'));dialog.root.setText(str(ROOT/'examples/impact/include-project'));dialog.units.setChecked(True)
        dialog.check_input();wait(lambda:dialog.worker is None)
        self.assertIsNotNone(dialog.source);self.assertTrue(dialog.ok.isEnabled());self.assertGreater(dialog.files.count(),3)
        original=deepcopy(dialog.source)
        dialog.entry.setText(str(ROOT/'examples/impact/include-project/missing.inp'));dialog.invalidate();dialog.check_input();wait(lambda:dialog.worker is None)
        self.assertIsNone(dialog.source);self.assertFalse(dialog.ok.isEnabled());self.assertIn('missing.inp',dialog.status.text())
        self.assertIn('*NODE',original['text'])
        # Stop a real pending capture; no running thread survives dialog close.
        dialog.entry.setText(str(ROOT/'examples/impact/include-project/model.inp'));dialog.check_input();dialog.reject();wait(lambda:dialog.worker is None)
        self.assertEqual(dialog.result(),QDialog.DialogCode.Rejected)


if __name__=='__main__':unittest.main()
