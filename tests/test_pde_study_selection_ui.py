"""Same retained mesh rows in table and norm plots; no PDE evaluation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.pde_study_window import PDEStudyWindow


def test_norm_plot_selection_retains_group_and_original_row_identity():
    app = QApplication.instance() or QApplication([])
    rows = [dict(cells_per_axis=4, global_dofs=25, l2_error=.2, h1_seminorm_error=.3,
                 relative_residual=1e-10, l2_unit='K*m', h1_unit='K', reference='x',
                 norm_definition='domain L2 / H1 seminorm'),
            dict(cells_per_axis=8, global_dofs=81, l2_error=.05, h1_seminorm_error=None,
                 relative_residual=2e-10, l2_unit='K*m', h1_unit='K', reference='x',
                 norm_definition='domain L2 / H1 seminorm'),
            dict(cells_per_axis=4, global_dofs=25, l2_error=.4, h1_seminorm_error=.5,
                 relative_residual=3e-10, l2_unit='K*m', h1_unit='K', reference='y',
                 norm_definition='domain L2 / H1 seminorm')]
    original = deepcopy(rows)
    window = PDEStudyWindow({'diagnostics': {'mesh_studies': rows}})
    try:
        window.show(); app.processEvents()
        assert window.table.currentRow() == 0
        assert len(window.figure.axes[0].lines) == 2
        first = next(line for line in window.figure.axes[0].lines if line._study_rows == [0, 1])
        window._point_picked(SimpleNamespace(artist=first, ind=[1])); app.processEvents()
        assert window.table.currentRow() == 1
        assert '기준식: x' in window.detail.text()
        assert list(window.figure.axes[0].collections[0].get_offsets()[0]) == [81., .05]
        assert len(window.figure.axes[1].collections) == 0  # Missing norm remains unavailable.
        window.table.selectRow(2); app.processEvents()
        assert '기준식: y' in window.detail.text()
        assert list(window.figure.axes[0].collections[0].get_offsets()[0]) == [25., .4]
        assert rows == original
        for size in ((1100, 780), (880, 620)):
            window.resize(*size); app.processEvents()
            assert window.canvas.height() >= 300
            assert window.table.height() > 70
    finally:
        window.close()
        app.processEvents()


def test_scikit_dofs_and_retained_declaration_reference_without_invented_missing_data():
    app = QApplication.instance() or QApplication([])
    row = dict(cells_per_axis=2, dofs=9, l2_error=.1, h1_seminorm_error=.2,
               relative_residual=0., l2_unit='K*m', h1_unit='K',
               norm_definition='original norm', residual_definition='original residual',
               quadrature_degree=8)
    missing = dict(row); missing.pop('dofs')
    result = {'diagnostics': {'mesh_studies': [row, missing],
                             'declaration': {'model': {'reference': 'retained_reference'}}}}
    original = deepcopy(result)
    window = PDEStudyWindow(result)
    try:
        window.show(); app.processEvents()
        assert window.table.item(0, 1).text() == '9'
        assert window.table.item(1, 1).text() == '미제공'
        assert list(window.figure.axes[0].lines[0].get_xdata()) == [9]
        assert '기준식: retained_reference' in window.detail.text()
        assert 'original residual' in window.detail.text() and '적분 차수: 8' in window.detail.text()
        window.table.selectRow(1); app.processEvents()
        assert '자유도 미제공' in window.detail.text()
        assert not window.figure.axes[0].collections
        assert result == original
    finally:
        window.close(); app.processEvents()
