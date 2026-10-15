"""Acknowledged Post selections link immutable plot snapshots without replay."""
from copy import deepcopy

import pytest

pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import QCoreApplication, QEvent, Qt

from apps.research.post_comparison_plot import ComparisonPlot
from apps.research.post_curve_plot import CurvePlot
from test_post_table_selection import selection_window
from test_research_post_ui import wait


def open_plot(window, curve):
    window.show_comparison_curve()
    return window.findChildren(CurvePlot if curve else ComparisonPlot)[-1]


def assert_selected(plot, curve, index):
    if curve:
        table = plot.tables['aligned']
        assert table.item(table.currentRow(), 0).data(Qt.ItemDataRole.UserRole) == index
        assert plot.tabs.currentWidget() is table
        assert 'aligned' in plot.markers
    else:
        assert plot._selected_index == index
        assert plot._markers


@pytest.mark.parametrize('curve', [False, True])
def test_table_selection_highlights_plot_after_reply_without_native_replay(selection_window, curve):
    app, client, window = selection_window(curve=curve)
    plot = open_plot(window, curve)
    before = deepcopy(window._samples)
    client.release = False
    window.samples.selectRow(1)
    wait(app, lambda: len(client.calls) == 1 and not window._busy)
    assert not (plot.markers if curve else plot._markers)
    client.release = True
    wait(app, lambda: not window._busy and window._pending is None)
    assert_selected(plot, curve, 19)
    assert len(client.calls) == 1
    assert window._samples == before


@pytest.mark.parametrize('curve', [False, True])
def test_reopened_plot_starts_from_confirmed_selection_only(selection_window, curve):
    app, client, window = selection_window(curve=curve)
    window.samples.selectRow(1)
    wait(app, lambda: not window._busy and window._pending is None)
    plot = open_plot(window, curve)
    assert_selected(plot, curve, 19)
    assert len(client.calls) == 1


@pytest.mark.parametrize('curve', [False, True])
def test_old_plot_rejects_other_owner_revision_and_preview(selection_window, curve):
    app, client, window = selection_window(curve=curve)
    plot = open_plot(window, curve)
    window.samples.selectRow(0)
    wait(app, lambda: not window._busy and window._pending is None)
    basis = deepcopy(window._sample_basis)
    assert_selected(plot, curve, 7)
    for key, value in [('document_id', 'Dother'), ('session_id', 'Sother'),
                       ('object_ref', 'Aother'), ('revision', 'Vother'), ('preview', True)]:
        window.sampleSelectionChanged.emit(19, {**basis, key: value})
        assert_selected(plot, curve, 7)
    assert len(client.calls) == 1


def test_spatial_highlight_keeps_missing_b_and_delta_missing(selection_window):
    app, client, window = selection_window()
    client.rows[1].update(b=None, delta=None, valid=False)
    window._show_samples(client.payload())
    plot = open_plot(window, False)
    window.samples.selectRow(1)
    wait(app, lambda: not window._busy and window._pending is None)
    assert len(plot._markers) == 1
    assert plot._markers[0].get_offsets().tolist() == [[19., 2.]]
    assert not plot.figure.axes[1].collections
    assert plot.rows[1]['b'] is None and plot.rows[1]['delta'] is None
    plot.axis.setCurrentIndex(1)
    assert plot._selected_index == 19 and len(plot._markers) == 1


def test_closed_plot_disconnects_before_next_selection(selection_window, capfd):
    app, client, window = selection_window()
    plot = open_plot(window, False)
    plot.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    window.samples.selectRow(1)
    wait(app, lambda: not window._busy and window._pending is None)
    assert len(client.calls) == 1
    assert window._confirmed_sample_selection[0] == 19
    assert 'RuntimeError' not in capfd.readouterr().err


def test_curve_missing_row_clears_previous_ring_without_filling_values(selection_window):
    app, client, window = selection_window(curve=True)
    client.rows[1].update(a=None, b=None, delta=None, percent=None,
                          a_valid=False, b_valid=False, valid=False)
    window._show_samples(client.payload())
    plot = open_plot(window, True)
    window.samples.selectRow(0)
    wait(app, lambda: not window._busy and window._pending is None)
    assert 'aligned' in plot.markers
    window.samples.selectRow(1)
    wait(app, lambda: not window._busy and window._pending is None)
    assert plot.tables['aligned'].currentRow() == 1
    assert 'aligned' not in plot.markers
    assert plot.payload['rows'][1]['a'] is None
    assert len(client.calls) == 2
