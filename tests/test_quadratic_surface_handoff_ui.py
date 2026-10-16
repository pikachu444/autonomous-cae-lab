"""Manufactured saved-table metadata; no solver or native transport."""
from copy import deepcopy
import pytest
from test_post_history_handoff_ui import app,snapshot
from apps.research.post_measurement_dialog import MeasurementDialog
from caelab.post_observation import measurement_columns


@pytest.mark.parametrize('kind',['surface_average','surface_time'])
def test_quadratic_metadata_and_recovery_survive_read_only_handoff(app,kind):
    saved=snapshot(kind)
    saved['recipe']['surface_faces'][0]['point_indices']=list(range(6))
    saved['summary'].update(reduction='native_parametric_quadratic_area_weighted_mean',
        field_interpolation='native_quadratic_shape',area_unit='mm^2',
        field_recovery={'producer':'declared nodal recovery','method':'original producer'},
        quadrature={'version':1,'rules':['TRI6_7'],'error_bound':'NOT_ESTABLISHED','convergence':'UNKNOWN'})
    for row in saved['rows']:row['values'].update(SurfaceIntegral=4.,SurfaceAreaDifference=.01)
    original=deepcopy(saved);dialog=MeasurementDialog(saved)
    try:
        assert list(measurement_columns(saved))==['SurfaceAreaAverage']
        assert 'TRI6_7' in dialog.summary.text() and 'mm^2' in dialog.summary.text()
        assert '오차 한계는 미확정' in dialog.summary.text()
        assert '복구/평균 선언' in dialog.summary.text()
        assert 'original producer' in dialog.summary.toolTip()
        assert dialog.value_column.count()==2 and saved==original
    finally:dialog.close();app.processEvents()


def test_quadratic_handoff_does_not_accept_an_error_bound_claim():
    saved=snapshot('surface_average');saved['recipe']['surface_faces'][0]['point_indices']=list(range(8))
    saved['summary'].update(reduction='native_parametric_quadratic_area_weighted_mean',
        field_interpolation='native_quadratic_shape',
        quadrature={'version':1,'error_bound':'CERTIFIED','convergence':'PASS'})
    with pytest.raises(ValueError):measurement_columns(saved)
