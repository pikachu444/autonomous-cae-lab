"""Pure retained curve semantics; no native runtime or evaluation."""
from copy import deepcopy
import base64
import json
import struct
import xml.etree.ElementTree as ET
import pytest
from caelab.post_curves import from_response, compare, write_table
from caelab.post_comparison import observable_value


def curve(x, y, *, unit='N', axis_unit='s', component='x'):
    response = {'kind': 'series', 'value': y, 'unit': unit, 'quantity': 'force',
        'component': component, 'location': 'load cell', 'measure': 'force', 'frame': 'global',
        'axes': [{'name': 'elapsed', 'unit': axis_unit, 'values': x}],
        'source_rows': list(range(10, 10+len(x))), 'source_row_kind': 'physical_line'}
    return from_response(response, origin={'test': 'explicit fixture'}, title='시험')


def recipe():
    return {'version': 3, 'a': {}, 'b': {}, 'axis_kind': 'physical_time',
        'axis_origins': {'a': 'trigger', 'b': 'DAQ start'}, 'b_axis_offset': 0.,
        'alignment': 'exact', 'axis_tolerance': 0., 'max_gap': 1.,
        'target_unit': 'N', 'locations_confirmed': True}


def test_units_clock_origin_bracket_originals_and_zero_denominator():
    a = curve([0., .5, 1.], [0., 2., 4.])
    b = curve([100., 1100.], [0., .004], unit='kN', axis_unit='ms')
    r = recipe(); r.update(alignment='bracket', b_axis_offset=-.1)
    result = compare(a, b, r)
    assert result['blocked'] is None
    assert [v['delta'] for v in result['rows']] == pytest.approx([0., 0., 0.])
    assert result['rows'][0]['percent'] is None
    assert result['rows'][0]['percent_reason'] == 'zero_a'
    assert result['rows'][1]['weight'] == pytest.approx(.5)
    assert result['rows'][1]['b_rows'] == [{'kind':'physical_line','row':10}, {'kind':'physical_line','row':11}]
    assert result['a']['rows'] == a['rows'] and result['b']['rows'] == b['rows']


def test_missing_excluded_hidden_and_gap_preserve_both_originals():
    a = curve([0., .5, 1., 1.5, 2., 3.], [2.]*6)
    b = curve([0., 1., 2.], [2., None, 2.])
    r = recipe(); r.update(alignment='bracket', max_gap=2.)
    result = compare(a, b, r)
    assert result['rows'][0]['valid'] and result['rows'][4]['valid']
    assert [row['a'] for row in result['rows']] == [2.]*6
    assert all(not result['rows'][i]['valid'] for i in (1,2,3,5))
    assert result['rows'][5]['reason'] == 'outside_b_range'
    assert result['rows'][0]['b_segment'] != result['rows'][4]['b_segment']
    b['rows'][1].update(y=2., calculation=False, quality=True)
    assert compare(a,b,r)['rows'][2]['b'] is None
    b['rows'][1].update(calculation=True, visible=False)
    assert compare(a,b,r)['rows'][2]['delta'] == 0.
    r['max_gap'] = .1
    assert compare(a,b,r)['rows'][1]['reason'] == 'gap_exceeds_limit'


@pytest.mark.parametrize('change', ['component','magnitude','measure','static_time','duplicate','reverse','unknown'])
def test_refuse_only_alignment_keep_originals(change):
    a, b, r = curve([0.,1.,2.],[1.,2.,3.]), curve([0.,1.,2.],[1.,2.,3.]), recipe()
    if change == 'component': b['declaration']['observable'] = observable_value('vector','y')
    elif change == 'magnitude': b['declaration']['observable'] = observable_value('vector','magnitude')
    elif change == 'measure': b['declaration']['measure'] = 'other'
    elif change == 'static_time': b['axis'].update(unit='1', semantics='STATIC_LOAD_PARAMETER')
    elif change == 'duplicate': b['rows'][1]['x'] = 0.
    elif change == 'reverse': b['rows'].reverse()
    else: b['declaration']['observable'] = {'version':1, 'operation':'unknown'}
    result = compare(a,b,r)
    assert result['blocked'] and not result['rows']
    assert result['a']['rows'] == a['rows'] and result['b']['rows'] == b['rows']


def test_explicit_monotone_interval_and_exact_tolerance_ambiguity():
    a, b, r = curve([0.,1.],[1.,2.]), curve([0.,1.,1.],[1.,2.,4.]), recipe()
    r['b']['rows'] = [0,2]
    assert not compare(a,b,r)['blocked']
    r['axis_tolerance'] = 2.
    result = compare(a,b,r)
    assert result['blocked'] and not result['rows']


def test_raw_calibrated_mapping_and_masks_are_not_double_applied():
    response = {'kind':'series', 'unit':'N', 'component':'x', 'location':'sensor', 'measure':'force','frame':'global',
        'value':[12.,32.], 'axes':[{'name':'time','unit':'s','values':[0.,2.]}],
        'source_rows':[4,6], 'source_row_kind':'physical_line',
        'raw_samples': {'source_rows':[4,5,6], 'value':[1.,2.,3.], 'axis':[0.,1.,2.],
            'transformed_value':[12.,22.,32.], 'transformed_axis':[0.,1.,2.],
            'calculation_valid':[True,False,True], 'quality_valid':[True,True,True],
            'display_visible':[True,True,False], 'quality_reasons':['','',''], 'exclusion_reasons':['','saturated','']}}
    result = from_response(response,origin={},title='calibrated')
    assert [r['y'] for r in result['rows']] == [12.,22.,32.]
    assert result['provenance']['raw_samples']['value'] == [1.,2.,3.]
    assert not result['rows'][1]['calculation'] and not result['rows'][2]['visible']


def test_absolute_temperature_difference_percent_and_binary_missing(tmp_path):
    a, b, r = curve([0.,1.],[0.,1.]), curve([0.,1.],[273.15,274.15]), recipe()
    for c,u in ((a,'degC'),(b,'K')):
        c['declaration'].update(quantity='temperature', units=u, measure='temperature',
            temperature_kind='absolute', observable=observable_value('scalar','scalar'))
    r['target_unit']='K'
    result=compare(a,b,r)
    assert all(row['delta']==0 for row in result['rows'])
    assert all(row['percent'] is None for row in result['rows'])
    a['rows'][1]['y']=None
    path=tmp_path/'curve.vtt';write_table(path,a)
    node=ET.parse(path).find("./Table/Piece/RowData/DataArray[@Name='value']")
    binary=base64.b64decode(node.text)
    assert struct.unpack('<I',binary[:4])[0]==16
    values=struct.unpack('<2d',binary[4:])
    assert values[0]==0 and values[1]!=values[1]


def test_source_definitions_cannot_be_overwritten_and_partial_input_survives():
    a,b,r=curve([0.],[1.]),curve([0.],[1.]),recipe()
    r['b']['declaration']={'units':'Pa'}
    with pytest.raises(ValueError,match='저장된'):
        compare(a,b,r)
    r=recipe();r['b_axis_offset']='1e'
    before=deepcopy(r)
    result=compare(a,b,r)
    assert result['blocked'] and r==before


@pytest.mark.parametrize('side', ['a', 'b'])
def test_response_conversion_overflow_keeps_originals_and_other_rows(side):
    a, b, r = curve([0.,1.],[1.,2.]), curve([0.,1.],[1.,2.]), recipe()
    source = a if side == 'a' else b
    source['declaration']['units'] = 'kN'
    source['rows'][1]['y'] = source['rows'][1]['raw_y'] = 1e308
    result = compare(a, b, r)
    json.dumps(result, allow_nan=False)
    assert result[side]['rows'][1]['y'] == 1e308
    assert result['rows'][0]['valid']
    assert not result['rows'][1][side+'_valid']
    assert result['rows'][1][side] is None
    assert result['rows'][1]['reason'] == side+'_value_conversion_overflow'


def test_axis_conversion_overflow_does_not_hide_raw_curve_or_invent_bracket():
    a, b, r = curve([0.,1.],[1.,2.],axis_unit='us'), curve([0.,1e308],[1.,2.]), recipe()
    r.update(alignment='bracket', max_gap=2.)
    result = compare(a,b,r)
    json.dumps(result,allow_nan=False)
    assert result['b']['rows'][1]['x'] == 1e308
    assert result['b_axis'][1] is None
    assert result['rows'][0]['valid']
    assert not result['rows'][1]['valid']
    assert result['rows'][1]['reason'] == 'b_axis_conversion_overflow'
