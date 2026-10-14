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



def test_old_curve_revision_is_rejected_before_native_highlight(owner_workspace):
    env = owner_workspace
    obj = env.add_object('Aselected', revisions=2)
    with pytest.raises(ValueError, match='STALE_SAMPLE'):
        env.work.sample(object_ref=obj['id'], preview=False, point_index=3,
                        expected_revision=obj['history'][0]['id'])
    assert env.highlighted == []
    result = env.work.sample(object_ref=obj['id'], preview=False, point_index=3,
                             expected_revision=obj['history'][1]['id'])
    assert result['revision'] == obj['history'][1]['id']
    assert env.highlighted == [('Aselected-output-1',3)]


@pytest.mark.parametrize('kind', ['point','path'])
def test_observable_and_array_policy_follow_measurement_save_and_reopen(owner_workspace, monkeypatch, kind):
    from types import SimpleNamespace
    import sys
    from caelab import post_comparison as c
    from test_post_comparison_physics import recipe
    env = owner_workspace
    original = env.add_object('Aforce')
    r = recipe()
    for side in ('a','b'):
        r[side]['layout'] = {'kind':'vector','components':['x','y','z']}
    r['selection']='x'
    metadata = c.output_declarations(r)
    original['history'][0]['summary']['declarations'] = metadata
    native = env.module.p
    native.GetActiveSource = lambda: None
    native.GetActiveView = lambda: None
    native.SetActiveSource = lambda value: None
    native.SetActiveView = lambda value: None
    stages=[]
    def stage(source, operation, settings, namespace, proxies):
        stages.append((operation,deepcopy(settings)))
        return source
    monkeypatch.setitem(sys.modules,'apps.desktop_post.comparison_native',SimpleNamespace(_filter=stage))
    output=env.proxy('measured-force')
    env.measurements.build_measurement=lambda source,draft,name: {'source':output,'proxies':[output],'summary':{}}
    draft={'source_ref':original['id'],'array':'A_original','association':'POINTS',
           'measurement':kind,'time':None}
    obj=env.work.edit_measurement(draft=draft)
    preview=env.work.validate(object_ref=obj['id'])
    row=preview['summary']['declarations']['arrays'][0]
    assert row['observable']==metadata['arrays'][0]['observable']
    assert row['validity_policy']=='declared_array'
    assert next(settings for name,settings in stages if name=='quality_only')['validity_policy']=='declared_array'
    assert row['validity_masks']==(['vtkValidPointMask'] if kind=='path' else ['A_finite'])
    env.work.apply(object_ref=obj['id'],show=False)
    saved=env.work.prepare_save(deepcopy(env.document),env.folder/'saved-observable')
    reopened=env.module.Workspace(env.owner,saved)
    assert reopened._output_declaration(obj['id'])['arrays'][0]==row
    side=dict(row,source_ref=obj['id'],array=row['name'],coordinate_units='mm',
              coordinate_frame='global',frozen_clock=None,sampling={'mode':'exact','time':None})
    reopened._declared_side(side)
    changed=dict(side,observable=c.observable_value('vector','y'))
    with pytest.raises(ValueError,match='observable'):
        reopened._declared_side(changed)
    with pytest.raises(ValueError,match='observable'):
        reopened._declared_measurement(dict(draft,source_ref=obj['id'],observable=changed['observable']))


def test_legacy_meaning_requires_declaration_without_mutating_saved_output(owner_workspace):
    from caelab import post_comparison as c
    env=owner_workspace; obj,metadata=derived(env)
    metadata['derivation']='comparison_v2'
    obj['history'][0]['summary']['declarations']=deepcopy(metadata)
    before=deepcopy(obj)
    declaration=env.work._output_declaration(obj['id'])
    row=declaration['arrays'][0]
    assert row['observable']==c.UNKNOWN_OBSERVABLE
    side=dict(row,source_ref=obj['id'],array=row['name'],coordinate_units='mm',coordinate_frame='global',
        frozen_clock=metadata['frozen_clock'],sampling={'mode':'exact','time':None})
    with pytest.raises(ValueError,match='미확인'):
        env.work._declared_side(side)
    side['observable']=c.observable_value('scalar','scalar',scalar_semantics='invariant')
    env.work._declared_side(side)
    assert obj==before
    env.work._bundle(obj)  # Original saved output remains readable.


def test_unknown_source_cannot_bypass_native_mask_with_caller_policy(owner_workspace):
    env=owner_workspace
    with pytest.raises(ValueError,match='정책'):
        env.work._declared_side({'source_ref':'Sraw','validity_policy':'declared_array'})
    with pytest.raises(ValueError,match='정책'):
        env.work._declared_measurement({'source_ref':'Sraw','validity_policy':'declared_array'})


def test_measurement_read_and_restored_selection_use_exact_saved_array_policy(owner_workspace):
    from caelab import post_comparison as c
    env=owner_workspace;obj,metadata=derived(env)
    row=metadata['arrays'][0]
    row.update(observable=c.observable_value('scalar','scalar',scalar_semantics='invariant'),
               validity_policy='declared_array')
    obj['history'][0]['summary']['declarations']=deepcopy(metadata)
    calls=[]
    def sample(source, **kwargs):
        calls.append(deepcopy(kwargs.get('declarations')))
        return {'rows':[{'point_index':kwargs.get('point_index',0),'values':{'temperature':2.},
                         'validity':{'temperature':'valid'}}]}
    env.measurements.sample_data=sample
    env.work.sample(object_ref=obj['id'],preview=False,point_index=0)
    env.work.state['active_object']=obj['id']
    assert env.work.restore_selection()
    assert calls==[metadata,metadata]
