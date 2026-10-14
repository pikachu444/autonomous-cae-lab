"""Exact retained partial scope through the existing measurement projection.

The ParaView proxy is an explicit test double. No native process or solver runs.
"""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from test_post_r3_repairs import post_modules
from test_post_workspace_ownership import owner_workspace
from test_contact_inspection_native_guards import contact_native, native_numpy_conversion_double
from test_contact_execution import model
from test_contact_steps import staged, two_step_outputs
from test_post_numerical import fixture_snapshot
from caelab.contact_deck import validate_model
from caelab.contact_steps import profile, validate_frames, axis
from caelab.adapters.frozen_fem import read_frd
from caelab.adapters.contact_results import read_dat, write_post
from caelab.contact_inspection import load, force_history
from caelab.post_observation import project_samples, completed_snapshot, file_pin
from caelab.storage import canonical_hash


@pytest.mark.parametrize('dynamic,status',[(False,'FAILED'),(True,'CANCELLED')])
def test_partial_execution_survives_saved_measurement_and_observation(
        model,tmp_path,contact_native,monkeypatch,dynamic,status):
    import caelab.contact_inspection as api
    m=staged(model,dynamic=dynamic)
    frd,dat,materials=two_step_outputs(m)
    fp,dp=tmp_path/'native.frd',tmp_path/'native.dat'
    fp.write_text(frd,encoding='ascii',newline='\n')
    dp.write_text(dat,encoding='ascii',newline='\n')
    nodes,elements,_=validate_model(m)
    observed=read_frd(fp,nodes,elements,contact_materials=materials,contact_profile=profile(m))
    validate_frames(m,observed)
    frames=observed['frames'][:1]
    rows=read_dat(dp,m['contacts'],frames,prefix=True)
    execution={'status':status,'complete_analysis':False,'scope':'CONVERGED_PREFIX'}
    folder=tmp_path/'partial'
    metadata=write_post(folder,m,frames,rows,provenance={
        'snapshot_id':'Fsteps','snapshot_sha256':'1'*64,'raw_frd_sha256':'2'*64,'raw_dat_sha256':'3'*64},
        execution=execution)
    bundle=load(folder/'contact.pvd',metadata['contact_inspection'])
    history=force_history(bundle,'Contact','CFN',2)
    assert history['execution']==execution and history['rows'][0]['valid']

    env=contact_native
    monkeypatch.setattr(env.module,'read',lambda *args:bundle)
    monkeypatch.setattr(env.module.external,'contact_api',lambda:api)
    proxy=NS(UpdatePipeline=lambda:None)
    monkeypatch.setattr(env.native,'ProgrammableSource',lambda **kw:proxy,raising=False)
    monkeypatch.setattr(env.module.analysis,'_fetch',lambda proxy:NS(GetNumberOfRows=lambda:len(history['rows'])))
    recipe=env.module.recipe(env.workspace,'Saved','Contact','CFN',2)
    assert recipe['execution']==execution
    measured=env.module.build_measurement(env.workspace,recipe,'Saved force')
    summary=measured['summary']
    assert summary['execution']==execution

    # Persist a native-command double with the actual product recipe/summary.
    snapshot,command=fixture_snapshot(tmp_path)
    sample_rows=[{'block':[],'row':i,'values':{
        history['axis']['name']:r['static']['load_parameter'],history['array']:r['value'],
        'vtkValidMask':int(r['valid']),'step':r['static']['step'],'increment':r['static']['increment']}}
        for i,r in enumerate(history['rows'])]
    snapshot.update(recipe=recipe,summary=summary,rows=sample_rows)
    origin=snapshot['origin']; path=Path(origin['project']['path'])
    project=json.loads(path.read_text(encoding='utf-8'))
    obj=project['analysis']['objects'][origin['object_ref']]
    obj['draft']=recipe
    record=obj['history'][0]; record.update(recipe=recipe,summary=summary)
    sample_path=Path(record['result_file'])
    sample_path.write_text(json.dumps(sample_rows),encoding='utf-8')
    record.update(result_files=[file_pin(sample_path)],result_sha256=file_pin(sample_path)['sha256'])
    path.write_text(json.dumps(project),encoding='utf-8')
    origin.update(project=file_pin(path),recipe_sha256=canonical_hash(recipe),
        result_files_sha256=canonical_hash(record['result_files']),result_sha256=record['result_sha256'])
    payload=command['outcome']['result']['result']
    saved=Path(payload['snapshot']['path'])
    saved.write_text(json.dumps(snapshot),encoding='utf-8')
    payload.update(origin=deepcopy(origin),snapshot=file_pin(saved),rows=len(sample_rows))
    reopened=completed_snapshot(command)
    selection={'block':[],'value_array':history['array'],'value_component':None,
        'axis':{'kind':'array','name':history['axis']['name'],'component':None},
        'unit':'N','axis_name':history['axis']['name'],'axis_unit':history['axis']['unit'],
        'component_label':summary['component_label'],'location':summary['location'],
        'frame':summary['frame'],'measure':summary['measure'],'role':'fit','exclude_invalid':False}
    projected=project_samples(reopened,selection)
    assert projected['origin']['summary']['execution']==execution
    assert projected['rows'][0]['value']==1. and projected['rows'][0]['valid']
    from caelab.adapters.file_table import read_table
    csv=tmp_path/'projected.csv'; csv.write_bytes(projected['csv'])
    response=read_table(csv,projected['mapping'])['responses']['measured']
    assert response['axes'][0]['unit']==axis(m)['unit']
    assert response['value']==[1.]
    assert response['raw_samples']['quality_valid']==[True]


@pytest.mark.parametrize('axis_name',['load_parameter','time'])
def test_native_saved_contact_chart_uses_its_declared_axis(owner_workspace,monkeypatch,axis_name):
    env=owner_workspace
    module=env.module
    view=NS(name='ForceChart',GetXMLName=lambda:'XYChartView',Representations=[])
    display=NS()
    monkeypatch.setattr(module.p,'GetActiveSource',lambda:None,raising=False)
    monkeypatch.setattr(module.p,'GetActiveView',lambda:None,raising=False)
    monkeypatch.setattr(module.p,'Show',lambda *args:display,raising=False)
    monkeypatch.setattr(module.p,'SetActiveSource',lambda *args:None,raising=False)
    monkeypatch.setattr(module.p,'SetActiveView',lambda *args:None,raising=False)
    monkeypatch.setattr(module.p,'Render',lambda *args:None,raising=False)
    env.work._views=lambda:[('ForceChart',view)]
    obj={'id':'Aforce','kind':'measurement'}
    record={'recipe':{'measurement':'contact_force','array':'CFN_Z_N','axis_name':axis_name},
            'view_name':'ForceChart'}
    env.work.show(obj,record,{'source':NS()})
    assert display.XArrayName==axis_name and display.UseIndexForXAxis==0
    assert display.AttributeType=='Row Data' and display.SeriesVisibility==['CFN_Z_N']
