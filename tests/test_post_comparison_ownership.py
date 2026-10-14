"""Owner declaration regressions with controlled proxies, no native execution."""
from copy import deepcopy
import pytest
from test_post_workspace_ownership import owner_workspace


def derived(env, ref='Atemperature'):
    obj = env.add_object(ref)
    metadata = {'coordinate_units':'mm', 'coordinate_frame':'global', 'time':None,
        'frozen_clock':{'value':.5,'unit':'s','semantics':'physical_time'},
        'arrays':[{'name':'temperature','association':'POINTS','quantity':'temperature',
            'units':'degC','measure':'temperature','frame':'global',
            'layout':{'kind':'scalar','components':['scalar'],'scalar_semantics':'invariant'},
            'temperature_kind':'absolute','validity_masks':['comparison_valid']}]}
    obj['history'][0]['summary']['declarations'] = deepcopy(metadata)
    return obj, metadata


def test_unknown_verified_legacy_filter_still_allows_explicit_measurement(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Alegacy')
    assert env.work._output_declaration(obj['id']) is None
    env.work._declared_measurement({'source_ref':obj['id'], 'array':'stress',
        'association':'POINTS', 'measurement':'point', 'units':'MPa'})
    env.work.bundles[obj['history'][0]['id']]['source'].graph['sha256'] = 'changed'
    with pytest.raises(ValueError, match='PIPELINE_CHANGED'):
        env.work._output_declaration(obj['id'])


def test_fixed_sample_meaning_and_temperature_survive_derived_measurement(owner_workspace):
    env = owner_workspace; obj, metadata = derived(env)
    draft = {'source_ref':obj['id'], 'array':'temperature', 'association':'POINTS',
             'measurement':'point','time':None,'units':'degC'}
    env.work._declared_measurement(draft)
    assert env.work._output_declaration(obj['id']) == metadata
    for change in ({'time':.6}, {'measurement':'time'}, {'temperature_kind':'difference'},
                   {'layout':{'kind':'scalar','components':['scalar'],'scalar_semantics':'component'}},
                   {'time_units':'ms'}):
        with pytest.raises(ValueError):
            env.work._declared_measurement(dict(draft, **change))
    # Two checked derived samples at different actual times are not timeless.
    side = dict(metadata['arrays'][0], source_ref=obj['id'],
        coordinate_units='mm', coordinate_frame='global', frozen_clock=metadata['frozen_clock'],
        sampling={'mode':'exact','time':None})
    side['array'] = side.pop('name')
    env.work._declared_side(side)
    with pytest.raises(ValueError, match='고정 시각'):
        env.work._declared_side(dict(side, frozen_clock={'value':.6,'unit':'s','semantics':'physical_time'}))
    saved = env.work.prepare_save(deepcopy(env.document), env.folder / 'declared-save')
    reopened = env.module.Workspace(env.owner, saved)
    assert reopened._output_declaration(obj['id']) == metadata
