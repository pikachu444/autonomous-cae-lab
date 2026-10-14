"""Explicit repair on native-shaped doubles; these are not native CAD runs."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from test_pre_live_parameters import live, NativeObject, Quantity, command
from caelab.adapters import freecad_parameters as selectors


def entry(name='width', object='Sketch', **changes):
    return dict(name=name, label='설계 폭', min=8., max=16., unit='mm', object=object,
                kind='constraint', constraint=name, key=object + '|constraint|0', **changes)


def sketch(live, names):
    obj = NativeObject(live.doc, 'Sketch', 'Sketcher::SketchObject')
    obj.Constraints = [NS(Name=name, Type='Distance', Value=10.) for name in names]
    obj.getDriving = lambda index: True
    def rename(index, name):
        obj.Constraints[index].Name = name
        live.owner.slotChangedObject(obj, 'Constraints')
    def set_datum(index, value):
        obj.Constraints[index].Value = value.Value
        live.owner.slotChangedObject(obj, 'Constraints')
    obj.renameConstraint, obj.setDatum = rename, set_datum
    live.doc.Objects.append(obj)
    recompute = live.doc.recompute
    def update_shape():
        object.__setattr__(live.pad, 'Length', Quantity(str(obj.Constraints[-1].Value) + ' mm'))
        recompute()
    live.doc.recompute = update_shape
    open_transaction, abort = live.doc.openTransaction, live.doc.abortTransaction
    def open_with_sketch(title):
        open_transaction(title)
        live.doc.constraint_snapshot = deepcopy(obj.Constraints)
    def abort_with_sketch():
        obj.Constraints = deepcopy(live.doc.constraint_snapshot)
        abort()
    live.doc.openTransaction, live.doc.abortTransaction = open_with_sketch, abort_with_sketch
    return obj


def broken(live):
    obj = sketch(live, ['replacement'])
    saved = entry()
    live.worker._save_registry(live.doc, {'parameters': [saved], 'final': 'Pad'})
    live.owner.write_metadata({'parameters': {'width': {'mode': 'free', 'default_value': 10.,
                                                     'note': 'preserve user metadata', 'effect': {'old': True}}}})
    return obj, saved


def repair_args(live, trial=12.):
    info = live.parameters.discover()
    candidate = next(row for row in info['candidates'] if row['object'] == 'Sketch')
    proof = live.parameters.probe({'selector': candidate['key'], 'source_stamp': info['source_stamp'],
                                  'effect_object_id': 'Pad', 'trial_value': trial, 'unit': 'mm'})
    return {'parameter_id': 'width', 'selector': candidate['key'], 'source_stamp': info['source_stamp'],
            'proof_id': proof['proof_id']}


def test_stable_name_survives_reordering(live):
    obj = sketch(live, ['width', 'other'])
    live.worker._save_registry(live.doc, {'parameters': [entry()], 'final': 'Pad'})
    obj.Constraints.reverse()
    info = live.parameters.discover()
    assert info['parameters'][0]['resolved'] and info['parameters'][0]['current_value'] == 10.
    live.parameters.update({'parameter_id': 'width', 'value': 13., 'unit': 'mm'})
    assert obj.Constraints[1].Name == 'width' and obj.Constraints[1].Value == 13.


def test_missing_binding_does_not_hide_unaffected_registration_and_strict_gate_stays_closed(live):
    broken(live)
    registry = live.parameters.registry()
    good = dict(name='depth', label='깊이', min=8., max=16., unit='mm', object='Pad',
                kind='property', property='Length', key='Pad|property|Length')
    registry['parameters'].append(good)
    live.worker._save_registry(live.doc, registry)
    info = live.parameters.discover()
    assert [row['resolved'] for row in info['parameters']] == [False, True]
    assert info['parameters'][0]['current_value'] is None
    live.parameters.update({'parameter_id': 'depth', 'label': '수정한 깊이'})
    assert live.parameters.discover()['parameters'][1]['label'] == '수정한 깊이'
    preflight = live.parameters.dispatch('pre.parameters.preflight', {}, {})
    assert preflight['diagnostics'][0]['parameter_id'] == 'width'
    with pytest.raises(ValueError, match='MISSING'):
        selectors.registered_targets(live.doc, registry, live.worker._targets(live.doc), live.worker._datum)


@pytest.mark.parametrize('duplicate', ['constraint', 'name', 'key', 'identity'])
def test_ambiguous_bindings_are_all_unresolved(live, duplicate):
    obj = sketch(live, ['width', 'width' if duplicate == 'constraint' else 'other'])
    entries = [entry()]
    if duplicate != 'constraint':
        second = entry(name='other')
        second['key'] = 'Sketch|constraint|1'
        if duplicate == 'name': second['name'] = 'width'
        if duplicate == 'key': second['key'] = entries[0]['key']
        if duplicate == 'identity': second['constraint'] = 'width'
        entries.append(second)
    live.worker._save_registry(live.doc, {'parameters': entries, 'final': 'Pad'})
    info = live.parameters.discover()
    assert all(not row['resolved'] for row in info['parameters'])
    assert all(row['current_value'] is None for row in info['parameters'])
    assert obj.Constraints[0].Name == 'width'


def test_probe_then_cancel_keeps_record_and_geometry(live):
    obj, saved = broken(live)
    metadata = live.owner.read_metadata()
    repair_args(live)
    assert live.parameters.registry()['parameters'][0] == saved
    assert live.owner.read_metadata() == metadata
    assert obj.Constraints[0].Name == 'replacement' and obj.Constraints[0].Value == 10.
    assert live.pad.Shape.Volume == 40.


def test_explicit_repair_preserves_settings_and_allows_reedit(live):
    obj, saved = broken(live)
    result = live.owner.dispatch(command(live, 'pre.parameters.rebind', repair_args(live)))
    assert result['status'] == 'COMPLETED', result
    repaired = live.parameters.registry()['parameters'][0]
    for field in ('name', 'label', 'min', 'max', 'unit'): assert repaired[field] == saved[field]
    metadata = live.owner.read_metadata()['parameters']['width']
    assert metadata['mode'] == 'free' and metadata['default_value'] == 10. and metadata['note'] == 'preserve user metadata'
    assert metadata['effect']['changed'] and live.parameters.proofs == {}
    assert obj.Constraints[0].Name == 'width' and obj.Constraints[0].Value == 10.
    live.parameters.update({'parameter_id': 'width', 'value': 14., 'unit': 'mm'})
    assert obj.Constraints[0].Value == 14. and live.pad.Shape.Volume == 56.


def test_repair_one_binding_when_another_is_still_missing(live):
    broken(live)
    registry = live.parameters.registry()
    registry['parameters'].append(entry(name='missing', object='Deleted'))
    live.worker._save_registry(live.doc, registry)
    result = live.parameters.rebind(repair_args(live))
    assert [row['resolved'] for row in result['parameters']] == [True, False]


@pytest.mark.parametrize('conflict', ['stale', 'registered', 'bounds', 'unit', 'expression', 'reference'])
def test_repair_rejects_changed_or_incompatible_replacement(live, conflict):
    obj, saved = broken(live)
    args = repair_args(live, 17. if conflict == 'bounds' else 12.)
    if conflict == 'stale':
        obj.renameConstraint(0, 'changed')
    if conflict == 'registered':
        registry = live.parameters.registry()
        target = entry(name='another'); target['constraint'] = 'replacement'; target['key'] = 'occupied'
        registry['parameters'].append(target); live.worker._save_registry(live.doc, registry)
        args['source_stamp'] = live.parameters.discover()['source_stamp']
    if conflict == 'unit':
        registry = live.parameters.registry(); registry['parameters'][0]['unit'] = 'deg'
        live.worker._save_registry(live.doc, registry)
        args = repair_args(live)
    if conflict == 'expression': obj.ExpressionEngine = [('Constraints[0]', 'Spreadsheet.width')]
    if conflict == 'reference': obj.getDriving = lambda index: False
    with pytest.raises(ValueError): live.parameters.rebind(args)
    assert live.parameters.registry()['parameters'][0]['name'] == saved['name']
    assert obj.Constraints[0].Value == 10.


def test_rebind_write_failure_rolls_back_native_name_and_registry(live):
    obj, saved = broken(live)
    args = repair_args(live)
    metadata = live.owner.read_metadata()
    live.owner.write_metadata = lambda value: (_ for _ in ()).throw(RuntimeError('controlled metadata failure'))
    with pytest.raises(RuntimeError, match='controlled'): live.parameters.rebind(args)
    assert live.parameters.registry()['parameters'][0] == saved
    assert live.owner.read_metadata() == metadata
    assert obj.Constraints[0].Name == 'replacement' and obj.Constraints[0].Value == 10.
    assert live.pad.Shape.Volume == 40.


def test_repair_rejects_failed_proof_without_changing_binding(live):
    obj, saved = broken(live)
    args = repair_args(live)
    live.parameters.proofs[args['proof_id']]['changed'] = False
    with pytest.raises(ValueError, match='EFFECT_PROOF'):
        live.parameters.rebind(args)
    assert live.parameters.registry()['parameters'][0] == saved
    assert obj.Constraints[0].Name == 'replacement' and obj.Constraints[0].Value == 10.


def test_ambiguous_parameter_id_cannot_remove_multiple_user_records(live):
    broken(live)
    registry = live.parameters.registry()
    registry['parameters'].append(entry(object='AnotherDeleted'))
    live.worker._save_registry(live.doc, registry)
    with pytest.raises(ValueError, match='unique'):
        live.parameters.dispatch('pre.parameters.remove', {'parameter_id': 'width'}, {})
    assert live.parameters.registry() == registry


@pytest.mark.parametrize('action', ['set', 'generate'])
def test_saved_worker_actions_block_unresolved_required_binding_before_dispatch(live, tmp_path, action):
    from caelab.adapters import freecad_parameter_worker as adapter
    broken(live)
    source = tmp_path / 'public.FCStd'; source.write_bytes(b'native-shaped test input')
    calls = []
    live.worker.App = NS(openDocument=lambda path: live.doc, closeDocument=lambda name: calls.append('close'))
    live.worker._registry = lambda doc: live.parameters.registry()
    live.worker.dispatch = lambda request: calls.append('dispatch')
    with pytest.raises(ValueError, match='MISSING'):
        adapter.dispatch({'action': action, 'document': str(source)}, worker=live.worker)
    assert calls == ['close']


@pytest.mark.parametrize('apply_repair', [False, True])
def test_repair_dialog_explicit_choice_probe_then_cancel_or_apply(live, apply_repair):
    from PySide6 import QtWidgets as W, QtCore as C
    from apps.desktop_pre.parameter_panel import make_panel
    app = W.QApplication.instance() or W.QApplication([])
    obj, saved = broken(live)
    calls = []
    def submit(operation, args, target, accepted):
        calls.append(operation)
        accepted(live.parameters.dispatch(operation, args, target))
    panel = make_panel(W, C, live.parameters, submit)
    info = live.parameters.discover(); panel.populate(info)
    assert panel.table.item(len(info['candidates']), 1).text() == '—'
    panel.table.selectRow(len(info['candidates']))
    observed = []
    def interact():
        dialog = panel.repair_dialog
        buttons = dialog.findChild(W.QDialogButtonBox)
        apply = buttons.button(W.QDialogButtonBox.Apply)
        observed.append(not apply.isEnabled())
        combo = dialog.findChildren(W.QComboBox)[0]
        combo.setCurrentIndex(next(i for i in range(combo.count()) if str(combo.itemData(i)).startswith('Sketch|')))
        dialog.findChild(W.QLineEdit).setText('12')
        next(button for button in dialog.findChildren(W.QPushButton) if button.text() == '형상 영향 확인').click()
        observed.append(apply.isEnabled())
        if apply_repair: apply.click()
        else: buttons.button(W.QDialogButtonBox.Cancel).click()
    C.QTimer.singleShot(0, interact); panel.repair_selected()
    assert observed == [True, True]
    assert calls == ['pre.parameters.probe'] + (['pre.parameters.rebind'] if apply_repair else [])
    assert obj.Constraints[0].Name == ('width' if apply_repair else 'replacement')
    assert obj.Constraints[0].Value == 10.
    if not apply_repair: assert live.parameters.registry()['parameters'][0] == saved
    panel.close()
