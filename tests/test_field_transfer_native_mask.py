"""Actual VTK stage data with frozen-time/proxy doubles, not a native campaign."""
import numpy as np
import pytest

pytest.importorskip('vtk')
from test_post_analysis import analysis
from test_post_comparison_native import native, tetra, add, run
from test_post_comparison_physics import recipe


@pytest.mark.parametrize('second', [[1, 0, 1, 0], [0, 1, 1, 0], [1, .5, 1, 0], [1, np.nan, 1, 0]])
def test_a_temporal_required_mask_must_be_same_binary_region(native, analysis, monkeypatch, second):
    left, right = tetra(), tetra()
    add(left.GetPointData(), 'required', [1, 0, 1, 0])
    add(right.GetPointData(), 'required', second)
    add(right.GetPointData(), 'response', [4., 4., 4., 4.])
    r = recipe(); r['a']['array'] = 'response'
    r['coverage'] = {'policy': 'a_mask', 'array': 'required'}
    module, _ = analysis
    monkeypatch.setattr(module, '_freeze', lambda source, time, *args: {0.: left, 2.: right}[time])
    monkeypatch.setattr(module, '_fetch', lambda source: source)
    stages = []
    def stage(inputs, name, settings, *args):
        stages.append(name)
        return run(native, name, inputs if isinstance(inputs, list) else [inputs], settings)
    monkeypatch.setattr(native, '_filter', stage)
    def prepare():
        return native._side(None, r['a'], {'times': [0., 2.], 'weights': [.5, .5]}, r, 'a', 'test', [])
    if second == [1, 0, 1, 0]:
        result, original = prepare()
        np.testing.assert_equal(native._values(result, native.VALUE), [[3.]] * 4)
        assert original is left and 'temporal' in stages
    else:
        with pytest.raises(ValueError, match='0/1|정확한 저장 시각'):
            prepare()
        assert 'temporal' not in stages
    assert native._required(left, r).tolist() == [1, 0, 1, 0]
