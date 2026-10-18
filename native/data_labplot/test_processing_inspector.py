"""Focused Qt regressions for canonical sample inspection, without HTTP/runs."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy

import pytest
from PySide6.QtWidgets import QApplication, QLabel
from apps.research.data_processing_inspector import DataProcessingInspectorDialog, ProcessingSampleTraceDialog
from caelab.data_processing import preview_recipe
from caelab.evaluation import evaluate
from caelab.storage import canonical_hash


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope='module')
def processed(tmp_path_factory):
    path = tmp_path_factory.mktemp('inspector') / 'force.csv'
    path.write_text('time,force\n0,0\n1,10\n2,20\n', encoding='utf-8')
    mapping = dict(delimiter=',', columns={'force': dict(column='force', unit='N', measure='force', component='xx',
        location='material_point', frame='material_cartesian', axis=dict(column='time', name='time', unit='s'))})
    imported = evaluate('files.table', {**mapping, 'path': str(path)})
    identity = dict(document_id='Tfixture', job_id='Jfixture', input_revision='Ifixture', input_sha256=canonical_hash(mapping))
    return preview_recipe(imported, identity, dict(version=1, operations=[
        dict(id='Ostress', operation='nominal_stress', input='force', output='P11', settings=dict(A0=10., area_unit='mm2')),
        dict(id='Ogrid', operation='resample', input='P11', output='P_grid', settings=dict(method='linear', max_gap=1.1, range=[0., 2.], step=.001))]))


def test_page_and_channel_restore_same_sample_without_transient_trace(app, processed, monkeypatch):
    from caelab import data_processing_lineage
    original = data_processing_lineage.trace_sample; calls = []
    def traced(channel, sid, **kwargs):
        calls.append((channel['name'], sid)); return original(channel, sid, **kwargs)
    monkeypatch.setattr(data_processing_lineage, 'trace_sample', traced)
    before = deepcopy(processed); dialog = DataProcessingInspectorDialog(processed, retained=True)
    try:
        dialog.channel.setCurrentText('P_grid'); assert dialog.table.rowCount() == 1000
        dialog.page_start.setValue(1001); dialog.table.setCurrentCell(1, 0)
        sid = processed['channels']['P_grid']['samples'][1001]['sample_id']
        assert dialog._trace['sample_id'] == sid and dialog.selected_sample_index() == 1001
        calls.clear(); dialog.channel.setCurrentText('P11')
        assert len(calls) == 1 and calls[0][0] == 'P11'
        dialog.table.setCurrentCell(2, 0); calls.clear(); dialog.channel.setCurrentText('P_grid')
        assert calls == [('P_grid', sid)]
        assert dialog.page_start.value() == 1001 and dialog.selected_sample_index() == 1001
        assert '2001개' in dialog.audit_count.text() and '처음 1000' not in dialog.status.text()
        dialog.page_start.setValue(2001)
        assert dialog.table.rowCount() == 1 and dialog.table.item(0, 0).text() == '2001'
        assert processed == before
    finally: dialog.close(); app.processEvents()


def test_derived_trace_uses_signed_coefficients_and_legacy_unknown_value(app, processed):
    dialog = DataProcessingInspectorDialog(processed, retained=True, allow_plan=True)
    try:
        dialog.channel.setCurrentText('P_grid'); dialog.table.setCurrentCell(500, 0)
        assert dialog.table.item(500, 3).text() == '파생'
        trace = dialog._trace
        assert [term['coefficient'] for term in trace['terms']] == [.05, .05]
        assert [term['raw_value'] for term in trace['terms']] == [None, None]
        detail = ProcessingSampleTraceDialog(processed['channels']['P_grid'], 500, trace, 1, dialog)
        try:
            assert [detail.terms.item(i, 1).text() for i in range(2)] == ['1', '2']
            assert detail.terms.item(0, 3).text() == '—'
            assert '보존되지' in detail.terms.item(0, 3).toolTip()
        finally: detail.close()
        assert dialog.plan_button.isEnabled()
        dialog.plan_button.click(); assert dialog.plan_requested
    finally: dialog.close(); app.processEvents()


def test_legacy_result_has_no_invented_trace_or_row(app):
    result = dict(execution_status='FAILED', diagnostics={'processing_status': 'PARTIAL'},
        stages=[dict(output='bad', state='BLOCKED', error={'message': 'sample gap'})],
        responses={'derived': dict(kind='series', value=[2., 3.], unit='MPa', segments=[{'rows': [0, 1]}, {'rows': [1, 2]}],
            axes=[dict(name='time', unit='s', values=[0., .5])])})
    dialog = DataProcessingInspectorDialog(result)
    try:
        assert dialog.table.item(0, 3).text() == '—' and not dialog.trace_button.isEnabled()
        assert '제공되지' in dialog.audit_count.text() and '실패' in dialog.status.text()
        assert [len(line.get_xdata()) for line in dialog.figure.axes[0].lines] == [1, 1]
        assert dialog.stages.item(0, 2).text() == 'sample gap'
    finally: dialog.close(); app.processEvents()


def test_failed_trace_retains_result_and_recovers_on_another_channel(app, processed, monkeypatch):
    from caelab import data_processing_lineage
    original = data_processing_lineage.trace_sample
    def fail_grid(channel, sid, **kwargs):
        if channel['name'] == 'P_grid': raise ValueError('retained trace unavailable')
        return original(channel, sid, **kwargs)
    monkeypatch.setattr(data_processing_lineage, 'trace_sample', fail_grid)
    before = deepcopy(processed); dialog = DataProcessingInspectorDialog(processed, retained=True)
    try:
        dialog.channel.setCurrentText('P_grid')
        assert dialog._trace is None and not dialog.trace_button.isEnabled()
        assert '보존' in dialog.sample_status.text()
        dialog.channel.setCurrentText('P11')
        assert dialog._trace is not None and dialog.trace_button.isEnabled()
        assert dialog.sample_status.toolTip() == '' and processed == before
    finally: dialog.close(); app.processEvents()


@pytest.mark.parametrize('validity, expected', [([2, 3], '2, 3'), ([], '없음'), (None, '1, 2')])
def test_value_rows_and_validity_rows_are_separate_with_legacy_fallback(app, processed, monkeypatch, validity, expected):
    # UI-only payload variants: absent validity field is legacy; an explicit
    # empty field must remain empty even when value contributions are present.
    result = deepcopy(processed); sample = result['channels']['P_grid']['samples'][1]
    sample['source_rows'] = [1, 2]
    if validity is None: sample.pop('validity_source_rows', None)
    else: sample['validity_source_rows'] = validity
    monkeypatch.setattr('caelab.data_processing_lineage.trace_sample', lambda *args, **kwargs: {'terms': [], 'bias': None})
    dialog = DataProcessingInspectorDialog(result, retained=True)
    try:
        dialog.channel.setCurrentText('P_grid'); dialog.table.setCurrentCell(1, 0)
        assert '값 기여 원행 1, 2' in dialog.sample_status.text()
        assert '판정 원행 ' + expected in dialog.sample_status.text()
        detail = ProcessingSampleTraceDialog(result['channels']['P_grid'], 1, dialog._trace, 1, dialog)
        try:
            status = next(label.text() for label in detail.findChildren(QLabel) if '판정 원행' in label.text())
            assert '값 기여 원행: 1, 2' in status and '판정 원행: ' + expected in status
            assert detail.terms.rowCount() == 0
        finally: detail.close()
    finally: dialog.close(); app.processEvents()


def test_only_known_uniform_sampling_message_has_short_korean_caption(app):
    known = 'Savitzky-Golay requires uniform sampling; explicitly resample first'
    unknown = 'unrecognized failure must remain exact'
    dialog = DataProcessingInspectorDialog(dict(stages=[dict(output=name, state='BLOCKED', error={'message': message})
        for name, message in [('known', known), ('unknown', unknown)]]))
    try:
        assert dialog.stages.item(0, 2).text() == '간격이 일정하지 않아 평활화하지 못했습니다. 먼저 재표본화하세요.'
        assert dialog.stages.item(0, 2).toolTip() == known
        assert dialog.stage_recovery.text() == dialog.stages.item(0, 2).text()
        assert dialog.stage_recovery.wordWrap() and dialog.stage_recovery.toolTip() == known
        assert dialog.stages.item(1, 2).text() == unknown and dialog.stages.item(1, 2).toolTip() == unknown
    finally: dialog.close(); app.processEvents()
