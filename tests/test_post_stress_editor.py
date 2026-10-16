"""Qt command/draft boundaries; candidate imports never overwrite product files."""
from copy import deepcopy
from pathlib import Path
import importlib.util
import sys
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QCheckBox, QComboBox, QLineEdit
from test_post_stress_measures import c, recipe


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ui(monkeypatch, app):
    base = Path(__file__).resolve().parents[1] / 'apps/research'
    for name in ('post_stress_editor', 'post_comparison_editor'):
        spec = importlib.util.spec_from_file_location('apps.research.' + name, base / (name + '.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        monkeypatch.setitem(sys.modules, 'apps.research.' + name, module)
    return module


def sources():
    arrays = [{'name': 'stress', 'association': 'POINTS', 'components': 9},
              {'name': 'F', 'association': 'POINTS', 'components': 9, 'units': '1',
               'frame': 'global', 'material_frame': 'reference'},
              {'name': 'wrong_association', 'association': 'CELLS', 'components': 9},
              {'name': 'F_valid', 'association': 'POINTS', 'components': 1}]
    return [{'source_ref': ref, 'label': label, 'metadata': {'arrays': deepcopy(arrays)}}
            for ref, label in [('Sa', '현재 응력'), ('Sb', '제1 Piola 응력')]]


def prepared(ui):
    draft = recipe(); draft['a']['source_ref'] = 'Sa'; draft['b']['source_ref'] = 'Sb'
    return ui.ComparisonEditor(draft, sources())


def test_cancel_and_passive_ok_preserve_unknown_auxiliary_draft(ui, monkeypatch):
    editor = prepared(ui); editor.value['b']['deformation_gradient']['orientation'] = 'unknown_future'
    before = editor.draft()
    monkeypatch.setattr(QDialog, 'exec', lambda self: QDialog.DialogCode.Rejected)
    editor.settings(); assert editor.draft() == before
    monkeypatch.setattr(QDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    editor.settings(); assert editor.draft()['b']['deformation_gradient'] == before['b']['deformation_gradient']
    editor.close()


def test_explicit_f_selection_and_declared_frames_then_recipe_reopens(ui, monkeypatch):
    editor = prepared(ui); editor.value.pop('stress_conversion'); editor.value['b'].pop('deformation_gradient')
    def choose(dialog):
        dialog.findChild(QCheckBox, 'stressConversionEnabled').setChecked(True)
        field = dialog.findChild(QComboBox, 'bGradientArray')
        assert field.findData('wrong_association') < 0
        assert field.findData('stress') < 0
        field.setCurrentIndex(field.findData('F'))
        # Units and frames come from this actual F descriptor. Orientation and
        # fixed basis are independent user declarations, never inferred from F9.
        for widget in dialog.findChildren(QComboBox):
            for data in ('current_from_reference', 'fixed_cartesian'):
                i = widget.findData(data)
                if i >= 0 and widget.isEnabled(): widget.setCurrentIndex(i)
        for field in dialog.findChildren(QLineEdit):
            if field.placeholderText().startswith('실제 9성분'):
                field.setText(','.join(c.COMPONENTS))
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, 'exec', choose); editor.settings()
    actual = editor.draft(); c.validate(actual, [], [])
    assert actual['b']['deformation_gradient']['units'] == '1'
    assert actual['b']['deformation_gradient']['spatial_frame'] == 'global'
    reopened = ui.ComparisonEditor(actual, sources()); assert reopened.draft() == actual
    editor.close(); reopened.close()


def test_legacy_settings_do_not_enable_conversion(ui, monkeypatch):
    editor = prepared(ui); editor.value.pop('stress_conversion')
    monkeypatch.setattr(QDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    editor.settings(); assert 'stress_conversion' not in editor.draft()
    editor.close()


def test_enable_without_f_does_not_guess_identity_or_orientation(ui, monkeypatch):
    editor = prepared(ui); editor.value.pop('stress_conversion'); editor.value['b'].pop('deformation_gradient')
    def enable(dialog):
        dialog.findChild(QCheckBox, 'stressConversionEnabled').setChecked(True)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, 'exec', enable); editor.settings()
    assert 'deformation_gradient' not in editor.draft()['b']
    with pytest.raises(ValueError, match='F 배열'): c.validate(editor.draft(), [], [])
    editor.close()


def test_pk1_two_basis_layout_is_an_explicit_existing_meaning_choice(ui, monkeypatch):
    editor = prepared(ui)
    def inspect(dialog):
        choices = [w for w in dialog.findChildren(QComboBox) if w.findData('spatial_material_basis') >= 0]
        assert len(choices) == 1
        assert choices[0].currentData() == 'spatial_material_basis'
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(QDialog, 'exec', inspect); before = editor.draft(); editor.meaning('b')
    assert editor.draft() == before
    editor.close()


def test_selected_known_f_quality_and_spatial_masks_cannot_be_removed(ui, monkeypatch):
    editor=prepared(ui)
    editor.sources[1]['metadata']['arrays'][1].update(validity_masks=['F_valid'], spatial_mask='inside')
    def choose(dialog):
        field=dialog.findChild(QComboBox,'bGradientArray');field.setCurrentIndex(field.findData(None))
        field.setCurrentIndex(field.findData('F'))
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog,'exec',choose);editor.settings()
    actual=editor.draft()['b'];assert actual['deformation_gradient']['validity_masks']==['F_valid','inside']
    c.validate_gradient_declaration(actual,editor.sources[1]['metadata']);editor.close()
