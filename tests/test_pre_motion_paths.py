"""Recorded native samples through paging, Qt selection and ordinary Data save."""
import time
from types import SimpleNamespace as NS

import pytest
from test_pre_motion import setup, qt_panel, native_modules, calculate
from apps.desktop_pre.motion import Motion
from apps.desktop_pre.motion_path import merge_path, csv_payload, data_draft, save_data_document
from apps.desktop_pre.connection import Connection


def samples(count=2001, start=0, end=None, trace='Tip', calculation='Krecorded'):
    return {'calculation_id': calculation, 'trace_id': trace, 'total_frames': count,
        'coordinate_unit': 'mm', 'frame': 'document_global', 'clock': 'nominal output grid; native time unavailable',
        'rows': [{'frame': i, 'nominal_time': i*.25, 'point': [i*.1, i*.2, 0.]} for i in range(start, count if end is None else end)]}


def read_recorded(setup, start=0, count=3):
    owner, motion, target, result = calculate(setup)
    path = motion.dispatch('pre.motion.path', {'calculation_id': result['id'], 'trace_id': 'Tip', 'start': start, 'count': count}, target)
    return owner, motion, target, result, path


def test_path_pages_join_all_frames_without_crossing_traces_or_calculations():
    for trace in ('Tip', 'Other'):
        result = None
        for start in range(0, 2001, 200):
            result = merge_path(result, samples(start=start, end=min(start+200, 2001), trace=trace))
        assert result['complete'] and len(result['rows']) == 2001
        duplicate = merge_path(result, samples(start=0, end=200, trace=trace))
        assert duplicate == result
        newer = merge_path(result, samples(start=200, end=400, trace=trace, calculation='Knew'))
        assert len(newer['rows']) == 200 and not newer['complete']
    missing = merge_path(samples(start=0, end=1), samples(start=2, end=3))
    assert [row['frame'] for row in missing['rows']] == [0, 2] and not missing['complete']


def test_native_shaped_path_save_cold_read_stale_and_failed_page_keep_original(setup):
    owner, motion, target, result, first = read_recorded(setup, count=1)
    owner.doc.frame_error = 1
    with pytest.raises(RuntimeError, match='native frame failure'):
        motion.dispatch('pre.motion.path', {'calculation_id': result['id'], 'trace_id': 'Tip', 'start': 1, 'count': 2}, target)
    assert motion.descriptor()['path']['rows'] == first['rows']
    motion.before_design_action('save')
    reopened = Motion(owner); reopened._modules = native_modules(); calls = list(owner.doc.calls)
    saved = reopened.descriptor()['path_results'][0]
    assert saved['paths']['Tip']['rows'] == first['rows'] and saved['source_status'] == 'CURRENT'
    assert reopened.descriptor()['calculation'] is None and owner.doc.calls == calls
    owner.doc.moving.Placement.Base.x = 7; owner.generation += 1
    assert reopened.descriptor()['path_results'][0]['source_status'] == 'STALE'
    assert reopened.descriptor()['path_results'][0]['paths']['Tip']['rows'] == first['rows']
    # Existing saves that only contain last_completed.path remain readable.
    owner.metadata.pop('motion_paths'); owner.metadata['motion']['last_completed'].pop('paths')
    assert reopened.descriptor()['path_results'][0]['paths']['Tip']['rows'] == first['rows']


def test_path_persistence_failure_keeps_exportable_buffer(setup):
    owner, motion, target, result, path = read_recorded(setup)
    owner.write_metadata = lambda value: (_ for _ in ()).throw(ValueError('Native research metadata exceeds 8 MiB'))
    with pytest.raises(ValueError, match='8 MiB'): motion.before_design_action('save')
    assert motion._pending_summary['paths']['Tip']['rows'] == path['rows']
    assert b'world_x_mm' in csv_payload(motion.descriptor()['path_results'][0]['paths']['Tip'])


def test_adopting_pose_retains_original_path_as_past_source(setup):
    owner, motion, target, result, path = read_recorded(setup)
    motion.dispatch('pre.motion.frame', {'calculation_id': result['id'], 'frame': 2}, target)
    motion.dispatch('pre.motion.adopt_pose', {'calculation_id': result['id'], 'frame': 2}, target)
    saved = motion.descriptor()['path_results'][0]
    assert saved['paths']['Tip']['rows'] == path['rows'] and saved['source_status'] == 'STALE'
    assert motion.descriptor()['calculation'] is None


def test_qt_curve_table_pose_and_saved_selection(qt_panel, tmp_path, monkeypatch):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, result, path = read_recorded(setup)
    widget.refresh(descriptor()); browser = panel.path_browser
    widget.findChild(panel.Q.QTabWidget).setCurrentIndex(3); app.processEvents()
    panel._show_path(path); browser.plot.grab(); app.processEvents()
    assert browser.plot.points and browser.table.rowCount() == 3
    from PySide6.QtTest import QTest
    before = list(owner.doc.calls)
    point = next(point for index, point in browser.plot.points if index == 2)
    QTest.mouseClick(browser.plot, panel.QtCore.Qt.LeftButton, pos=point.toPoint())
    assert browser.table.currentRow() == 2 and browser.plot.index == 2 and owner.doc.calls == before
    browser.pose_button.click()
    op, args, selected, done = queued[-1]
    assert op == 'pre.motion.frame' and args['frame'] == 2 and args['calculation_id'] == result['id']
    done({'result': motion.dispatch(op, args, selected)})
    browser.mode.setCurrentIndex(1); browser.plot.grab()
    saved = panel.editor_snapshot(); motion.dispatch('pre.motion.save_editor', {'editor': saved['editor']}, target)
    panel.accept_saved_editor(saved); motion.before_design_action('save')
    data = descriptor(); data['session_id'] = 'ColdPath'; widget.refresh(data)
    assert browser.current_view() == saved['editor']['path_view']
    assert not browser.pose_button.isEnabled() and not panel._edited and not panel._joint_edited
    monkeypatch.setattr(panel.Q.QFileDialog, 'getSaveFileName', lambda *a: (str(tmp_path/'path.csv'), ''))
    browser._csv(); assert (tmp_path/'path.csv').read_bytes() == csv_payload(browser.path_value)
    widget.resize(720, 700); app.processEvents(); widget.grab()  # Actual injected Qt paint, no OS input claim.


def test_qt_full_read_advances_pages_without_recalculating(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, result, path = read_recorded(setup)
    motion._calculation['frame_count'] = 401
    motion._path_result = None; motion._pending_summary.pop('paths', None); motion._pending_summary.pop('path', None)
    widget.refresh(descriptor()); before = len(queued)
    panel._read_path(all_frames=True)
    pages = []; value = None
    for start in (0, 200, 400):
        op, args, selected, done = queued[-1]; pages.append(args)
        assert op == 'pre.motion.path' and args['start'] == start
        value = merge_path(value,
            samples(count=401, start=start, end=min(start+200, 401), calculation=result['id']))
        descriptor_value = descriptor()
        descriptor_value['motion']['path_results'] = [{'id': result['id'], 'assembly_id': target['assembly_id'], 'paths': {'Tip': value}, 'source_status': 'CURRENT'}]
        descriptor_value['motion']['path'] = value
        panel.read = lambda: descriptor_value
        done({'result': value})
    assert len(queued)-before == 3 and panel.path.rowCount() == 401
    assert panel._path_read_scope is None and '전체 경로' in panel.path_browser.notice.text()


@pytest.mark.parametrize('partial', [False, True])
def test_data_handoff_uploads_exact_csv_and_saved_source_reopens(tmp_path, partial):
    from caelab.workbench import Workbench
    from caelab.adapters.file_table import read_table
    wb = Workbench(tmp_path/'service')
    try:
        path = merge_path(None, samples(count=3))
        if partial: path['rows'] = [path['rows'][0], path['rows'][2]]; path['complete'] = False
        saved = save_data_document(wb, path)
        assert not saved['diagnostics'] and not saved['runs']
        original = wb.input_path(saved['draft']['data_id'])
        assert original.read_bytes() == csv_payload(path)
        assert len(wb.document_source_preview(saved['id'])['table_preview']['rows']) == 3
        values = read_table(original, saved['draft']['mapping'])['responses']
        assert list(values['X']['value']) == [row['point'][0] for row in path['rows']]
        assert list(values['프레임']['value']) == [row['frame'] for row in path['rows']]
        assert values['Y']['axes'][0]['name'] == 'nominal_time'
        if partial:
            import csv, io, json
            from urllib.parse import unquote
            lines = csv_payload(path).decode().splitlines()
            source = json.loads(unquote(lines[0].split('=', 1)[1]))
            assert source['sampled_frames'] == [0, 2]
            assert source['gap_markers'] == [{'csv_row': 3, 'after_frame': 0, 'before_frame': 2, 'unread_frames': [1, 1]}]
            assert list(csv.reader(io.StringIO('\n'.join(lines[2:]))))[1] == ['nan']*5
            raw = values['X']['raw_samples']
            assert values['X']['has_calculation_gaps'] and [segment['source_rows'] for segment in values['X']['segments']] == [[2], [4]]
            assert raw['axis'] == [0., 'nan', .5] and raw['value'] == [0., 'nan', .2]
            assert raw['calculation_valid'] == [True, False, True] and raw['quality_valid'] == [True, False, True]
            assert '미읽기 경로 구간' in raw['exclusion_reasons'][1]
            unmasked = data_draft(path, saved['draft']['data_id'])
            for channel in unmasked['mapping']['columns'].values(): channel.pop('row_selection')
            with pytest.raises(ValueError, match='missing or nonfinite'): read_table(original, unmasked['mapping'])
        imported = wb.document_command(saved['id'], 'data.import', {}, session_id=saved['session_id'], expected_generation=saved['generation'])
        deadline = time.monotonic()+10
        while wb.manager.status(imported['job']['id'])['state'] not in ('SUCCEEDED', 'FAILED') and time.monotonic() < deadline: time.sleep(.01)
        assert wb.manager.status(imported['job']['id'])['state'] == 'SUCCEEDED'
        saved = save_data_document(wb, path, document=saved)
        # A fresh owner reads its retained CSV and multichannel import without native CAD.
        from caelab.data_document import DataDocuments
        fresh = DataDocuments(wb.root, 'Snew', None, None,
            resolve_input=lambda _: (_ for _ in ()).throw(FileNotFoundError('registration unavailable')))
        reopened = fresh.read(saved['id'])
        assert reopened['draft'] == saved['draft']
        assert fresh.source_preview(saved['id'])['retained']
        retained = fresh.result(saved['id'], imported['job']['id'])['responses']
        assert retained['Z']['value'] == [0.]*len(path['rows'])
        if partial:
            assert retained['X']['has_calculation_gaps'] and retained['X']['segments'] == values['X']['segments']
            assert retained['프레임']['value'] == [0., 2.] and retained['X']['raw_samples']['value'][1] == 'nan'
            from caelab.data_comparison import compare_data_curves
            missing_observation = dict(retained['X'], value=[.1], has_calculation_gaps=False,
                axes=[{'name': 'nominal_time', 'unit': 's', 'values': [.25]}])
            with pytest.raises(ValueError, match='exact matching'): compare_data_curves(retained['X'], missing_observation)
            import os
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
            from PySide6.QtWidgets import QApplication
            from apps.research.data_window import DataWindow
            app = QApplication.instance() or QApplication([])
            window = DataWindow(wb, auto_open=False, poll_interval=0)
            try:
                window._opened(saved)
                deadline = time.monotonic()+3
                while (len(window.axes.lines) != 2 or window._busy) and time.monotonic() < deadline:
                    app.processEvents(); time.sleep(.01)
                assert [list(line.get_xdata()) for line in window.axes.lines] == [[0.], [.5]]
                assert window.values.rowCount() == 3
            finally:
                window._allow_close = True; window.close(); window.deleteLater(); app.processEvents()
    finally: wb.manager.shutdown()


def test_first_path_selection_flows_through_general_connection_save(qt_panel):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, result, path = read_recorded(setup)
    panel.joint.setCurrentIndex(-1); widget.refresh(descriptor())
    motion.dispatch('pre.motion.set_view', {'view': panel.current_view()}, target); widget.refresh(descriptor())
    assert not panel._edited and not panel._joint_edited and not owner.metadata.get('motion_editors')
    assert panel.current_view() == owner.metadata['motion']['view']
    browser = panel.path_browser; browser.table.selectRow(2); browser.mode.setCurrentIndex(1)
    expected = browser.current_view()
    owner.document_id = 'Dnative'; owner.session_id = 'Snative'; owner.refresh = lambda: None
    connection = Connection.__new__(Connection)
    connection.owners = {owner.doc.Name: (owner, None, NS(stop=NS(is_set=lambda: False), registered=NS(is_set=lambda: True)))}
    connection.panels = {owner.doc.Name: {'motion': NS(widget=lambda: widget)}}
    connection.native_requests = {}; connection.message = NS(setText=lambda text: None)
    sent = []; completed = []; connection._send_native = sent.append
    connection.submit_native('document.save', {}, owner=owner, on_done=completed.append)
    first = connection.native_requests[sent[0]]
    assert first['operation'] == 'pre.motion.save_editor' and first['arguments']['editor']['path_view'] == expected
    args = dict(first['arguments']); selected = args.pop('target')
    value = motion.dispatch(first['operation'], args, selected)
    connection._native_status({'command_id': sent[0], 'state': 'SUCCEEDED', 'outcome': {'result': {'result': value}}})
    assert connection.native_requests[sent[1]]['operation'] == 'document.save'
    motion.before_design_action('save')
    connection._native_status({'command_id': sent[1], 'state': 'SUCCEEDED', 'outcome': {'result': {'result': {'status': 'SAVED'}}}})
    assert completed[0]['status'] == 'SAVED' and owner.metadata['motion_editors'][target['assembly_id']]['path_view'] == expected
    fresh = Motion(owner); fresh._modules = native_modules()
    cold = descriptor(); cold['session_id'] = 'ColdPathSelection'; cold['motion'] = fresh.descriptor(); widget.refresh(cold)
    assert browser.current_view() == expected and fresh.descriptor()['calculation'] is None


def test_connection_data_launch_failure_retries_saved_document(qt_panel, monkeypatch):
    app, widget, panel, queued, descriptor, setup = qt_panel
    owner, motion, target, result, path = read_recorded(setup)
    connection = Connection.__new__(Connection)
    calls = []; document = {'id': 'Tpath', 'session_id': 'Sdata', 'generation': 0}
    connection.client = NS(upload=lambda name, content: calls.append(('upload', content)) or {'id': 'Dcsv'},
        document_open=lambda **kwargs: calls.append(('open', kwargs)) or document,
        document_read=lambda identifier: document,
        document_command=lambda *args, **kwargs: calls.append(('save', args)) or {'document': document})
    connection.config = {'python': 'python.exe', 'service_url': 'http://127.0.0.1:1'}
    connection.request = lambda key, call, done: done(call())
    monkeypatch.setattr('apps.desktop_pre.connection.subprocess.Popen', lambda *a, **k: (_ for _ in ()).throw(OSError('launch failed')))
    browser = panel.path_browser; browser.open_data = connection.open_motion_data
    widget.refresh(descriptor()); panel._show_path(path); browser._data()
    assert 'launch failed' in browser.message.text()
    browser._data()
    assert [call[0] for call in calls] == ['upload', 'open', 'save', 'save']
    assert browser.path_value['rows'] == path['rows']
