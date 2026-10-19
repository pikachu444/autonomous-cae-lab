"""Controlled native-table shapes; these checks never simulate CZM physics."""
from copy import deepcopy
import json
import pytest

from caelab.adapters.implicit_interface_results import history, point_fields, TRACTIONS, VARIABLES
from caelab.implicit_interface import SOURCE


def tables(order, kappa=.02):
    rows = [3,1,4,2]
    base = dict(MAILLE=['37']*4,POINT=rows,SOUS_POINT=[1]*4,NUME_ORDRE=[order]*4,
                COOR_X=[11.+p for p in rows],COOR_Y=[-7.]*4,COOR_Z=[3.]*4)
    stress = {**deepcopy(base),**{k:[value]*4 for k,value in zip(TRACTIONS,[12.,-3.,4.])}}
    values = [kappa,1.,1.,.2,.04,.01,.008,.001,-.002]
    state = {**deepcopy(base),**{k:[value]*4 for k,value in zip(VARIABLES,values)}}
    return dict(SIEF_ELGA=stress,VARI_ELGA=state)


CELLS = {37:dict(element_id=9103,interface_id='BondSurface73')}


def test_original_joint_points_local_tractions_and_nine_variables_are_preserved():
    source = tables(4)
    original = deepcopy(source)
    parsed = point_fields(source,CELLS,4,.7)
    assert point_fields(source,json.loads(json.dumps(CELLS)),4,.7) == parsed
    assert [r['point'] for r in parsed] == [1,2,3,4]
    assert [r['coordinates_mm'][0] for r in parsed] == [12.,13.,14.,15.]
    assert all(r['element_id'] == 9103 and r['interface_id'] == 'BondSurface73' for r in parsed)
    assert parsed[0]['values'] == dict(SIGN=12.,SITX=-3.,SITY=4.,
        V1=.02,V2=1.,V3=1.,V4=.2,V5=.04,V6=.01,V7=.008,V8=.001,V9=-.002)
    assert parsed[0]['basis'] == 'NATIVE_JOINT_LOCAL'
    assert source == original
    source['VARI_ELGA']['V3'][0] = .37
    with pytest.raises(ValueError,match='0, 1, 2'):
        point_fields(source,CELLS,4,.7)


def test_missing_partial_native_values_stay_unknown_and_wrong_locations_block():
    source = tables(4)
    source['SIEF_ELGA']['SIGN'][0] = None
    rows = point_fields(source,CELLS,4,.7)
    assert rows[2]['values']['SIGN'] is None and not rows[2]['valid_mask']['SIGN']
    del source['VARI_ELGA']
    partial = point_fields(source,CELLS,4,.7,complete=False)
    assert all(r['values']['V1'] is None and r['values']['V9'] is None for r in partial)
    assert partial[0]['values']['SITX'] == -3.
    with pytest.raises(ValueError):
        point_fields(source,CELLS,4,.7)
    wrong = tables(4)
    wrong['VARI_ELGA']['COOR_X'][0] += .001
    with pytest.raises(ValueError,match='위치'):
        point_fields(wrong,CELLS,4,.7)
    wrong = tables(4)
    wrong['SIEF_ELGA']['MAILLE'][0] = '99'
    with pytest.raises(ValueError,match='선택 영역'):
        point_fields(wrong,CELLS,4,.7)


def test_history_keeps_actual_orders_and_reports_irreversible_state_loss():
    raw = dict(versions=dict(code_aster='17.4.0'),source_commit=SOURCE,
        solver_status='COMPLETED',converged=True,available_orders=[4,9],
        access_parameters=dict(NUME_ORDRE=[4,9],INST=[.7,2.6]),
        states=[dict(order=4,tables=tables(4,.02)),dict(order=9,tables=tables(9,.03))])
    result = history(raw,CELLS)
    assert [r['order'] for r in result['steps']] == [4,9]
    assert [r['load_parameter'] for r in result['steps']] == [.7,2.6]
    assert result['axis']['unit'] == '1' and result['diagnostics'] == []
    raw['states'][1]['tables'] = tables(9,.01)
    failed = history(raw,CELLS)
    assert len(failed['diagnostics']) == 4
    assert failed['steps'][1]['points'][0]['values']['V1'] == .01
    assert failed['qualification'] == 'UNKNOWN' and failed['decision'] == 'NOT_RELEASED'
    raw['solver_status'] = 'FAILED'
    raw['converged'] = False
    del raw['states'][1]['tables']['VARI_ELGA']
    partial = history(raw,CELLS)
    assert not partial['complete'] and partial['original_solver_status'] == 'FAILED'
    assert partial['steps'][1]['points'][0]['values']['V1'] is None
    raw['available_orders'][0] = 0
    raw['access_parameters']['NUME_ORDRE'][0] = 0
    raw['access_parameters']['INST'][0] = 0.
    raw['states'][0] = dict(order=0,tables=tables(0,.0001))
    assert history(raw,CELLS)['steps'][0]['order'] == 0
