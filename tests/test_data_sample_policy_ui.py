import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('caelab.data_processing_selection')
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication, QDialog
from apps.research.data_sample_policy_dialog import SamplePolicyDialog


@pytest.fixture
def policy(tmp_path):
    from caelab.evaluation import evaluate
    from caelab.storage import canonical_hash
    from caelab.data_processing import preview_recipe
    from caelab.data_processing_selection import propose_sample_policy
    source = tmp_path / 'force.csv'; source.write_text('time,force\n0,0\n1,10\n2,20\n', encoding='utf-8')
    mapping = dict(delimiter=',', columns={'force': dict(column='force', unit='N', measure='force', component='xx',
        location='material_point', frame='material_cartesian', axis=dict(column='time', name='time', unit='s'))})
    imported = evaluate('files.table', {**mapping, 'path': str(source)})
    identity = dict(document_id='Tfixture', job_id='Jfixture', input_revision='Ifixture', input_sha256=canonical_hash(mapping))
    result = preview_recipe(imported, identity, dict(version=1, operations=[
        dict(id='Ostress', operation='nominal_stress', input='force', output='P11', settings=dict(A0=10., area_unit='mm2')),
        dict(id='Ogrid', operation='resample', input='P11', output='P_grid', settings=dict(method='linear', max_gap=1.1, range=[0., 2.], step=.5))]))
    channel = result['channels']['P_grid']
    return QApplication.instance() or QApplication([]), propose_sample_policy(channel), channel


def test_sample_policy_review_preserves_identity_and_actual_contributors(policy):
    app, proposal, channel = policy
    before = deepcopy(proposal); dialog = SamplePolicyDialog(proposal, channel)
    try:
        dialog.table.setCurrentCell(1, 0)
        assert dialog.contributors.rowCount() == 2
        assert [float(dialog.contributors.item(row, 2).text()) for row in range(2)] == [.05, .05]
        assert dialog.entries == before['entries'] and proposal == before
        assert channel['samples'][1]['sample_id'] in dialog.entries
    finally: dialog.close(); app.processEvents()


def test_batch_role_weight_keeps_selection_and_never_changes_unselected_samples(policy):
    app, proposal, channel = policy; dialog = SamplePolicyDialog(proposal, channel)
    try:
        dialog.table.clearSelection()
        for row in (1, 2):
            dialog.table.selectionModel().select(dialog.table.model().index(row, 0),
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        dialog.role.setCurrentIndex(1); dialog.weight.setText('2.5'); dialog._batch()
        assert {index.row() for index in dialog.table.selectedIndexes()} == {1, 2}
        for row, sample in enumerate(channel['samples']):
            entry = dialog.entries[sample['sample_id']]
            assert entry['role'] == ('holdout' if row in (1, 2) else 'fit')
            assert entry['weight'] == (2.5 if row in (1, 2) else 1.)
        assert proposal['state'] == 'UNADOPTED'
    finally: dialog.close(); app.processEvents()


def test_partial_weight_remains_editable_and_blocks_adoption(policy):
    app, proposal, channel = policy; dialog = SamplePolicyDialog(proposal, channel)
    try:
        dialog.table.item(1, 5).setText('1e'); dialog._accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.entries[channel['samples'][1]['sample_id']]['weight'] == '1e'
        assert dialog.table.item(1, 5).text() == '1e' and '가중치' in dialog.message.text()
    finally: dialog.close(); app.processEvents()


def test_policy_compact_paint_keeps_exact_item_and_entry_values(policy,monkeypatch):
    app,proposal,channel=policy
    from PySide6.QtWidgets import QLineEdit
    exact=.30000000000000004
    sid=channel['samples'][1]['sample_id'];initial=deepcopy(proposal['entries']);initial[sid]['weight']=exact
    original=deepcopy(channel)
    monkeypatch.setattr('caelab.data_processing_lineage.trace_sample',lambda *args:{'terms':[{'raw_ref':{'column':'force','source_row':2},'coefficient':exact,'value':None}]})
    dialog=SamplePolicyDialog(proposal,channel,initial_entries=initial)
    try:
        dialog.show();app.processEvents()
        item=dialog.table.item(1,0)
        assert item.text()==str(channel['axis']['values'][1]) and item.toolTip()==repr(channel['axis']['values'][1])
        assert dialog.table.itemDelegateForColumn(0).displayText(repr(exact),dialog.locale())=='0.3'
        dialog.table.setCurrentCell(1,5);dialog.table.editItem(dialog.table.item(1,5));app.processEvents()
        line=dialog.table.findChild(QLineEdit)
        assert line.text()==repr(exact) and dialog.entries[sid]['weight']==exact
        assert dialog.contributors.item(0,3).text()=='—'
        assert dialog.contributors.item(0,2).text()==repr(exact)
        assert channel==original
    finally: dialog.close();app.processEvents()


def test_existing_review_entries_seed_without_changing_proposal(policy):
    app, proposal, channel = policy
    initial = deepcopy(proposal['entries']); original = deepcopy(proposal)
    sid = channel['samples'][1]['sample_id']
    initial[sid] = dict(included=False, role='holdout', weight=2.5)
    dialog = SamplePolicyDialog(proposal, channel, initial_entries=initial)
    try:
        assert dialog.entries == initial and proposal == original
        assert dialog.table.item(1, 4).text() == '검증 (holdout)'
        assert dialog.table.item(1, 5).text() == '2.5'
        dialog.table.item(1, 5).setText('3')
        assert initial[sid]['weight'] == 2.5 and proposal == original
    finally: dialog.close(); app.processEvents()


@pytest.mark.parametrize('change', ['missing', 'role', 'included', 'weight', 'extra'])
def test_bad_seed_rejected_before_display(policy, change):
    app, proposal, channel = policy
    initial = deepcopy(proposal['entries']); sid = channel['samples'][0]['sample_id']
    if change == 'missing': initial.pop(sid)
    elif change == 'role': initial[sid]['role'] = 'unknown'
    elif change == 'included': initial[sid]['included'] = 1
    elif change == 'weight': initial[sid]['weight'] = float('nan')
    else: initial[sid]['hidden'] = 'unexpected'
    with pytest.raises(ValueError, match='표본 용도'):
        SamplePolicyDialog(proposal, channel, initial_entries=initial)
