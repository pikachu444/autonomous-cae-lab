"""Original-row masks and channel meaning through the existing table adapter."""
from copy import deepcopy

import pytest

from caelab.adapters.file_table import read_table
from caelab.data_comparison import compare_data_curves
from caelab.data_document import default_draft, diagnostics


def draft():
    value = default_draft()
    value['data_id'] = 'Dsource'
    value['mapping']['skip_header'] = 1
    response = value['mapping']['columns']['response']
    response.update(unit='MPa', component='xx', location='material_point', measure='Cauchy', frame='lab')
    response['axis'].update(name='time', unit='s')
    second = deepcopy(response)
    second.update(column=2, component='yy')
    value['mapping']['columns']['transverse'] = second
    value['test_metadata'] = {'test_id': 'test α', 'specimen': '시편 2', 'protocol': 'operator declared', 'temperature': '25 °C'}
    return value


def test_multichannel_mask_retains_raw_values_quality_and_gaps(tmp_path):
    source = tmp_path / '시험.csv'
    content = 'time,stress,transverse\n0,10,20\n1,nan,21\n2,12,22\n3,13,23\n'
    source.write_text(content)
    value = draft()
    value['mapping']['columns']['response']['row_selection'] = {
        'include_ranges': [[1, 4]], 'exclude_rows': [2], 'quality_rows': [3],
        'display_hidden_rows': [4], 'reasons': {'2': 'sensor disconnected'},
        'quality_reasons': {'3': 'operator flagged noisy sample'}}
    assert diagnostics(value) == []
    result = read_table(source, value['mapping'])['responses']
    response = result['response']
    assert response['value'].tolist() == [10, 12, 13]
    assert response['source_rows'].tolist() == [1, 3, 4]
    assert response['has_calculation_gaps']
    assert [segment['source_rows'] for segment in response['segments']] == [[1], [3, 4]]
    raw = response['raw_samples']
    assert raw['value'] == [10, 'nan', 12, 13]
    assert raw['calculation_valid'] == [True, False, True, True]
    assert raw['quality_valid'] == [True, False, False, True]
    assert raw['display_visible'] == [True, True, True, False]
    assert raw['exclusion_reasons'][1] == 'sensor disconnected'
    assert raw['quality_reasons'][2] == 'operator flagged noisy sample'
    assert result['transverse']['value'].tolist() == [20, 21, 22, 23]
    assert source.read_text() == content


def test_quality_display_do_not_silently_exclude_nonfinite_or_change_valid_rows(tmp_path):
    source = tmp_path / 'measure.csv'
    source.write_text('t,a,b\n0,1,2\n1,nan,3\n2,4,5\n')
    value = draft()
    spec = value['mapping']['columns']['response']
    spec['row_selection'] = {'quality_rows': [2], 'display_hidden_rows': [2]}
    with pytest.raises(ValueError, match='explicitly exclude'):
        read_table(source, value['mapping'])
    spec['row_selection']['exclude_rows'] = [2]
    response = read_table(source, value['mapping'])['responses']['response']
    prediction = deepcopy(response)
    prediction['value'] = [2, 5]
    comparison = compare_data_curves(prediction, response)
    assert comparison['rmse'] == pytest.approx(1)
    assert comparison['count'] == 2
    assert comparison['observation_source_rows'].tolist() == [1, 3]
    prediction['axes'][0]['values'] = [0, 3]
    with pytest.raises(ValueError, match='exact matching'):
        compare_data_curves(prediction, response)


def test_invalid_multichannel_draft_reports_explicit_metadata(tmp_path):
    value = draft()
    value['mapping']['columns']['transverse']['frame'] = ''
    assert 'transverse' in diagnostics(value)[0]['message']
    value = draft()
    value['mapping']['columns']['response']['row_selection'] = {'include_ranges': 'unfinished range'}
    assert diagnostics(value)
    value = draft()
    value['test_metadata']['temperature'] = 25
    assert 'explicitly supplied' in diagnostics(value)[0]['message']
