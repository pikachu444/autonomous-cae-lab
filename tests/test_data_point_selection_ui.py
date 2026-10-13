"""Curve gestures and original-row paging, no importer/solver/provider run."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time
import pytest
pytest.importorskip('PySide6')
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from matplotlib.backend_bases import MouseEvent
from apps.research.data_window import DataWindow
from test_research_data_numerical_ui import data_document


def response(rows=80):
    source = [10 * (i + 1) for i in range(rows)]
    x, y = list(range(rows)), [i * 2. for i in range(rows)]
    x[1:3], y[1:3] = [1., 1.], [5., 15.]
    x[5:7], y[5:7] = [5., 5.], [25., 25.]
    used, quality, visible = [True]*rows, [True]*rows, [True]*rows
    used[2] = False
    quality[1] = False
    visible[4] = False
    raw = {'source_rows':source, 'axis':x, 'value':y, 'transformed_axis':x, 'transformed_value':y,
           'calculation_valid':used, 'quality_valid':quality, 'display_visible':visible,
           'exclusion_reasons':['']*rows, 'quality_reasons':['']*rows, 'total_count':rows}
    indexes = [i for i in range(rows) if used[i]]
    return {'kind':'series', 'source_row_kind':'physical_line', 'source_rows':[source[i] for i in indexes],
            'axes':[{'name':'시간', 'unit':'s', 'values':[x[i] for i in indexes]}],
            'value':[y[i] for i in indexes], 'unit':'MPa', 'component':'xx', 'measure':'Cauchy',
            'location':'point', 'frame':'lab', 'raw_samples':raw}


class Reader:
    def __init__(self, full): self.full, self.calls = full, []
    def document_result(self, identifier, job, *, selection):
        self.calls.append(deepcopy(selection))
        first, last = selection['rows']
        raw = deepcopy(self.full['raw_samples'])
        total = len(raw['source_rows'])
        for name, value in list(raw.items()):
            if isinstance(value, list): raw[name] = value[first:last]
        raw.update(page_start=first, total_count=total)
        return {'responses':{'response':{'raw_samples':raw}}}


@pytest.fixture
def scene():
    app = QApplication.instance() or QApplication([])
    for font in ('segoeui.ttf', 'malgun.ttf'): QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
    full = response()
    reader = Reader(full)
    window = DataWindow(reader, auto_open=False, poll_interval=0)
    window._show_document(data_document())
    window._selected_job, window._result_channel = 'Jimport', 'response'
    window.row_count.setValue(80)
    receipt = {'status':{'state':'SUCCEEDED'}, 'result':{'responses':{'response':full}}}
    key = window._result_key()
    window._results[key] = receipt
    window._draw_result(receipt, key)
    window.resize(1100,780); window.show(); app.processEvents(); window.canvas.draw()
    yield window, app, reader, receipt
    window._allow_close = True; window.close(); app.processEvents()


def wait(app, window):
    deadline = time.monotonic()+5
    while window._busy and time.monotonic()<deadline: app.processEvents(); time.sleep(.005)
    assert not window._busy
    app.processEvents()


def gesture(window, point, *, key=None, offset=(0,0)):
    x, y = window.axes.transData.transform(point)
    for name, px, py in [('button_press_event', x, y),
                         ('motion_notify_event', x+offset[0], y+offset[1]),
                         ('button_release_event', x+offset[0], y+offset[1])]:
        event = MouseEvent(name, window.canvas, px, py, button=1, key=key)
        window.canvas.callbacks.process(name, event)


def test_exact_duplicate_x_excluded_quality_and_ctrl_selection(scene):
    window, app, reader, _ = scene
    before, original = deepcopy(window.edited_draft()), deepcopy(window.document)
    gesture(window, (1.,15.))  # excluded but explicitly displayed marker, not x-neighbour.
    assert window._selected_original_rows() == {30}
    assert window.values.currentRow() == 2
    gesture(window, (1.,5.), key='control')  # poor quality remains selectable.
    assert window._selected_original_rows() == {20,30}
    assert not reader.calls
    assert window.edited_draft() == before and window.document == original and not window.local_dirty
    # Completely coincident samples preserve an already selected exact row.
    window._select_original_rows({70})
    gesture(window, (5.,25.))
    assert window._selected_original_rows() == {70}
    window.values.clearSelection()
    gesture(window, (5.,25.))
    assert window._selected_original_rows() == {60}


def test_hidden_nonfinite_missing_mapping_blank_space_and_pan_do_not_pick(scene):
    window, app, reader, _ = scene
    window._select_original_rows({20})
    assert 50 not in window._selection_points
    # Restrict the test to no other nearby legitimate sample.
    points = window._selection_points
    window._selection_points = {40:(float('nan'),float('inf'))}
    gesture(window, (4.,8.))
    assert window._selected_original_rows() == {20}
    window._selection_points = points
    window.axes.set_navigate_mode('PAN')
    gesture(window, (1.,15.))
    assert window._selected_original_rows() == {20}
    window.axes.set_navigate_mode(None)
    gesture(window, (75.,10.))  # blank area, not nearest-X guessing.
    assert window._selected_original_rows() == {20}
    assert not reader.calls


def test_only_rendered_segment_points_can_be_clicked(scene):
    window, app, reader, receipt = scene
    page = deepcopy(receipt)
    page['result']['responses']['response']['segments'] = [{'source_rows':[10,20]}]
    window._draw_result(page, window._result_key())
    window.axes.set_xlim(0.,4.); window.axes.set_ylim(0.,20.); window.canvas.draw()
    window._select_original_rows({20})
    x, y = window.axes.transData.transform((3.,6.))
    assert MouseEvent('button_press_event',window.canvas,x,y,button=1).inaxes is window.axes
    gesture(window,(3.,6.))  # mapped original row 40, but absent from every drawn segment.
    assert window._selected_original_rows() == {20} and not reader.calls


def test_drag_selects_interval_click_jitter_does_not_erase_and_scrolls(scene):
    window, app, reader, _ = scene
    gesture(window, (1.,15.), offset=(2.,1.))
    assert window._selected_original_rows() == {30}
    # Real SpanSelector callbacks select all represented rows in the interval.
    start = window.axes.transData.transform((1.,5.))
    stop = window.axes.transData.transform((8.,16.))
    gesture(window, (1.,5.), offset=(stop[0]-start[0],stop[1]-start[1]))
    selected = window._selected_original_rows()
    assert {20,30,60,70,80}.issubset(selected) and 50 not in selected
    gesture(window, (79.,158.))
    assert window._selected_original_rows() == {800}
    assert window.values.currentRow() == 79
    assert window.values.verticalScrollBar().value() > 0
    window._draw_cached_result()
    assert window.values.currentRow() == 79 and window._selected_original_rows() == {800}


def test_outside_audit_page_read_only_moves_table_keeps_curve_and_poll_selection(scene):
    window, app, reader, receipt = scene
    # Calculation page contains source 40, but the raw audit page only 10/20.
    page = deepcopy(receipt)
    for name, value in list(page['result']['responses']['response']['raw_samples'].items()):
        if isinstance(value,list): page['result']['responses']['response']['raw_samples'][name] = value[:2]
    page['result']['responses']['response']['raw_samples']['page_start'] = 0
    window.row_count.setValue(2)
    key = window._result_key(); window._results[key] = page
    window._draw_result(page,key); window.canvas.draw()
    original_lines = [line.get_ydata().copy() for line in window.axes.lines]
    original_draft = deepcopy(window.edited_draft())
    window._select_original_rows({20})
    gesture(window,(3.,6.),key='control'); wait(app,window)
    assert window._selected_original_rows() == {40}
    assert [window.values.item(i,0).text() for i in range(2)] == ['30','40']
    assert '이전 선택' in window.message.text()
    assert window.row_start.value() == 0
    assert all((before == after.get_ydata()).all() for before,after in zip(original_lines,window.axes.lines))
    assert window._selection_artist is not None
    window._draw_cached_result(); window.canvas.draw()
    assert window._selected_original_rows() == {40}
    assert window.values.item(1,0).text() == '40'
    assert window._selection_artist is not None
    assert window.edited_draft() == original_draft and not window.local_dirty
    assert all(set(call) == {'responses','rows'} for call in reader.calls)


@pytest.mark.parametrize('change', ['channel','draft','page','table','drag'])
def test_late_read_does_not_change_newer_view_or_edits(scene, change):
    window, app, reader, receipt = scene
    window._point_raw_total, window._point_row_kind = 80, 'physical_line'
    entered, release = threading.Event(), threading.Event()
    old = reader.document_result
    def blocked(*args, **kwargs):
        entered.set(); release.wait(2)
        return old(*args, **kwargs)
    reader.document_result = blocked
    window._point_lookup_serial = 1
    window._select_original_rows({20})
    window._read_point_row(40,False)
    assert entered.wait(2)
    if change == 'channel': window._result_channel = 'another'
    elif change == 'page': window.row_start.setValue(2)
    elif change == 'draft': window.test_fields['temperature'].setText('새 편집')
    elif change == 'table': window.values.selectRow(4)
    else: window._select_curve_interval(5.,5.)
    selected = window._selected_original_rows()
    release.set(); wait(app,window)
    assert window._selected_original_rows() == selected
    assert window.values.rowCount() == 80


def test_read_failure_preserves_old_table_selection(scene):
    window, app, reader, _ = scene
    window._point_lookup_serial = 1
    window._select_original_rows({20})
    def fail(*args, **kwargs): raise ValueError('controlled read failure')
    reader.document_result = fail
    window._read_point_row(40,False); wait(app,window)
    assert window._selected_original_rows() == {20}
    assert window.values.rowCount() == 80 and 'failure' in window.message.text()


def test_missing_original_row_never_invents_table_record(scene):
    window, app, reader, _ = scene
    window._point_lookup_serial = 1
    window._select_original_rows({20})
    before = [window.values.item(row,0).text() for row in range(window.values.rowCount())]
    window._read_point_row(35,False); wait(app,window)
    assert window._selected_original_rows() == {20}
    assert before == [window.values.item(row,0).text() for row in range(window.values.rowCount())]


def test_closed_window_abandons_pending_row_read(scene):
    window, app, reader, _ = scene
    entered, release = threading.Event(), threading.Event()
    old = reader.document_result
    def blocked(*args, **kwargs):
        entered.set(); release.wait(2)
        return old(*args, **kwargs)
    reader.document_result = blocked
    window._point_lookup_serial = 1
    window._select_original_rows({20})
    window._read_point_row(40,False)
    assert entered.wait(2)
    worker = window._worker
    window._allow_close = True; window.close(); release.set()
    assert worker.completed.wait(3)
    app.processEvents()
    assert window._closed and window._selected_original_rows() == {20}


def test_logical_click_jitter_scales_with_canvas_pixel_ratio(scene):
    window, app, reader, _ = scene
    window.canvas._set_device_pixel_ratio(2)
    window.canvas.draw()
    gesture(window,(1.,15.),offset=(6.,2.))  # sqrt(40)/2 logical pixels < 4.
    assert window._selected_original_rows() == {30}
