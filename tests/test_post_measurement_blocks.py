"""Real VTK leaf identity/aggregation checks; no ParaView/native run claim."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
vtk=pytest.importorskip('vtk')
from test_post_measurement_histories import histories,surface,recipe
from test_post_analysis import analysis
from apps.desktop_post import measurement_blocks as blocks


def composite():
    root=vtk.vtkMultiBlockDataSet();nested=vtk.vtkMultiBlockDataSet()
    root.SetNumberOfBlocks(3);root.SetBlock(0,surface());root.SetBlock(1,nested)
    nested.SetNumberOfBlocks(2);nested.SetBlock(1,surface(quad=True))
    return root


def test_native_leaf_paths_flat_indices_and_empty_nodes_remain_distinct():
    data=composite();rows=blocks.leaves(data)
    assert [(r['leaf_path'],r['flat_index'],r['empty']) for r in rows]==[
        ([0],1,False),([1,0],3,True),([1,1],4,False),([2],5,True)]
    iterator=data.NewTreeIterator();iterator.SkipEmptyNodesOff();iterator.VisitOnlyLeavesOn();iterator.InitTraversal()
    native=[]
    while not iterator.IsDoneWithTraversal():
        native.append(iterator.GetCurrentFlatIndex());iterator.GoToNextItem()
    assert native==[r['flat_index'] for r in rows]
    for path in ([1],[2],[1,0],[8],[-1],[True]):
        with pytest.raises(ValueError):blocks.resolve(data,path)


def test_same_native_ids_in_different_leaves_do_not_merge(histories):
    data=composite();selections=[{'leaf_path':path,'surface_faces':histories.surface_catalog(blocks.resolve(data,path)['data'])}
        for path in ([0],[1,1])]
    before=deepcopy(selections)
    rows=blocks.selected(data,selections,track=histories._tracking,faces=histories._faces)
    assert [r['leaf_path'] for r in rows]==[[0],[1,1]] and selections==before
    reports=[]
    for row in rows:
        leaf=row['data'];reports.append({**histories.surface_average(leaf,recipe(histories,leaf)),
            'leaf_path':row['leaf_path']})
    result=blocks.aggregate(reports,'area_weighted_mean')
    assert result['area']==3.5 and result['value']==pytest.approx((17+1/3)/3.5)
    assert blocks.aggregate(reports,'integral_sum')['value']==pytest.approx(17+1/3)
    assert len(blocks.aggregate(reports,'per_leaf')['leaves'])==2
    with pytest.raises(ValueError,match='twice'):
        blocks.selected(data,[selections[0],selections[0]],track=histories._tracking,faces=histories._faces)


def test_invalid_selected_leaf_does_not_silently_shrink_union():
    reports=[{'leaf_path':[0],'area':2.,'value':8.,'valid':True},
             {'leaf_path':[1],'area':None,'value':None,'valid':False,'reason':'vtkGhostType'}]
    combined=blocks.aggregate(reports,'area_weighted_mean')
    assert not combined['valid'] and combined['value'] is None and combined['area'] is None
    assert combined['leaves']==reports


@pytest.mark.parametrize('mode',['area_weighted_mean','integral_sum','per_leaf'])
def test_user_leaf_recipe_builds_retained_output_with_lineage(histories,monkeypatch,mode):
    data=composite();source=SimpleNamespace(TimestepValues=[],data=data)
    paths=[[0],[1,1]];first=blocks.resolve(data,paths[0])['data']
    draft={**recipe(histories,first),'measurement':'surface_average','time':None,
        'time_units':None,'time_origin':None,'aggregation':mode,
        'leaf_selections':[{'leaf_path':path,'surface_faces':histories.surface_catalog(blocks.resolve(data,path)['data'])} for path in paths]}
    monkeypatch.setattr(histories.analysis,'_freeze',lambda source,time,namespace,proxies:source)
    monkeypatch.setattr(histories.analysis,'_fetch',lambda source:source.data)
    monkeypatch.setattr(histories,'_table',lambda values,namespace:SimpleNamespace(values=values))
    monkeypatch.setattr(blocks,'_tables',lambda history,values,namespace:SimpleNamespace(values=values))
    result=histories.build(source,draft,'user selected leaves')
    assert result['summary']['recipe']==draft
    assert [row['leaf_path'] for row in result['summary']['leaf_results']]==paths
    assert result['summary']['samples'][0]['leaves'][1]['leaf_path']==[1,1]
    if mode=='per_leaf':
        assert len(result['source'].values)==2
        assert result['source'].values[0]['SurfaceAreaAverage']==[6.8]
        assert result['summary']['leaf_results'][1]['table_block']==[1]
    else:
        assert result['source'].values['SurfaceArea']==[3.5]
        assert result['source'].values[result['summary']['array']][0]==pytest.approx(
            17+1/3 if mode=='integral_sum' else (17+1/3)/3.5)
        assert result['summary']['units']==('MPa*mm^2' if mode=='integral_sum' else 'MPa')


def test_retained_native_leaf_tables_cold_read_exact_rows(histories,monkeypatch,tmp_path):
    class Source:
        def UpdatePipeline(self):
            self.data=vtk.vtkMultiBlockDataSet()
            exec(self.Script,{'self':SimpleNamespace(GetOutputDataObject=lambda index:self.data)})
    monkeypatch.setattr(histories.p,'ProgrammableSource',lambda **kwargs:Source(),raising=False)
    values=[{'SampleIndex':[0],'SurfaceAreaAverage':[6.8],'vtkValidMask':[1]},
            {'SampleIndex':[0],'SurfaceAreaAverage':[1/3],'vtkValidMask':[1]}]
    result=blocks._tables(histories,values,'retained leaf tables')
    path=tmp_path/'leaf-results.vtm';writer=vtk.vtkXMLMultiBlockDataWriter()
    writer.SetFileName(str(path));writer.SetInputData(result.data)
    assert writer.Write()==1
    reader=vtk.vtkXMLMultiBlockDataReader();reader.SetFileName(str(path));reader.Update()
    cold=SimpleNamespace(data=reader.GetOutput(),UpdatePipeline=lambda:None)
    monkeypatch.setattr(histories.analysis,'_fetch',lambda source:source.data)
    rows=histories._measurement_module().sample_data(cold)['rows']
    assert [(row['block'],row['row']) for row in rows]==[([0],0),([1],0)]
    assert [row['values']['SurfaceAreaAverage'] for row in rows]==[6.8,1/3]


def test_duplicate_high_order_ghost_cannot_hide_original_outer_faces(histories):
    from test_quadratic_surface_native import grid
    from vtk.util.numpy_support import numpy_to_vtk
    import numpy as np
    data=grid();ids=vtk.vtkIdList();ids.DeepCopy(data.GetCell(0).GetPointIds())
    data.InsertNextCell(22,ids)
    ghost=numpy_to_vtk(np.array([0,1],dtype=np.uint8),deep=True);ghost.SetName('vtkGhostType')
    data.GetCellData().AddArray(ghost)
    with pytest.raises(ValueError,match='ghost.*coverage'):histories.surface_catalog(data)


def native_measurement_bundle(histories,monkeypatch,*,mode='per_leaf',current=False,invalid_displacement_paths=()):
    """Run the saved product scripts against real VTK table data objects."""
    import numpy as np
    from vtk.util.numpy_support import numpy_to_vtk
    data=composite();paths=[[0],[1,1]];first=blocks.resolve(data,paths[0])['data']
    if current:
        for path in paths:
            leaf=blocks.resolve(data,path)['data']
            xyz=np.asarray([leaf.GetPoint(i) for i in range(leaf.GetNumberOfPoints())])
            array=numpy_to_vtk(xyz*np.array([1.,2.,0.]),deep=True);array.SetName('U');leaf.GetPointData().AddArray(array)
            if path in invalid_displacement_paths:array.SetComponent(0,0,float('nan'))
    draft={**recipe(histories,first),'measurement':'surface_average','time':None,'time_units':None,
        'time_origin':None,'aggregation':mode,'geometry':'current' if current else 'fixed_reference',
        'leaf_selections':[{'leaf_path':path,'surface_faces':histories.surface_catalog(blocks.resolve(data,path)['data'])} for path in paths]}
    if current:draft['geometry_state']={'mode':'reference_plus_displacement','array':'U',
        'association':'POINTS','units':'mm','frame':'lab','basis':'fixed_cartesian'}
    class NativeScript:
        def __init__(self,kind):self.kind=kind;self.data=None
        def UpdatePipeline(self):
            self.data=vtk.vtkTable() if self.kind=='vtkTable' else vtk.vtkMultiBlockDataSet()
            exec(self.Script,{'self':SimpleNamespace(GetOutputDataObject=lambda index:self.data,
                                                    GetTableOutput=lambda:self.data)})
    monkeypatch.setattr(histories.p,'ProgrammableSource',lambda **kwargs:NativeScript(kwargs['OutputDataSetType']),raising=False)
    monkeypatch.setattr(histories.analysis,'_freeze',lambda source,time,namespace,proxies:source)
    monkeypatch.setattr(histories.analysis,'_fetch',lambda source:source.data)
    measurement=histories._measurement_module()
    monkeypatch.setattr(measurement.analysis,'_fetch',lambda source:source.data)
    source=SimpleNamespace(data=data,TimestepValues=[],UpdatePipeline=lambda:None)
    bundle=histories.build(source,draft,'user measurement integration')
    return draft,bundle,measurement


@pytest.mark.parametrize('mode',['per_leaf','area_weighted_mean','integral_sum'])
@pytest.mark.parametrize('current',[False,True])
def test_actual_build_table_rows_project_with_current_and_aggregation_contract(histories,monkeypatch,mode,current):
    from caelab.post_observation import measurement_columns,project_samples
    from test_post_measurement_history_observation import selection
    draft,bundle,measurement=native_measurement_bundle(histories,monkeypatch,mode=mode,current=current)
    snapshot={'complete':True,'origin':{},'recipe':draft,'summary':bundle['summary'],
              'rows':measurement.sample_data(bundle['source'])['rows']}
    assert set(measurement_columns(snapshot))=={bundle['summary']['array']}
    chosen=selection(snapshot);chosen['block']=[1] if mode=='per_leaf' else []
    projected=project_samples(snapshot,chosen)
    assert projected['rows'][0]['native']=={'block':chosen['block'],'row':0}
    assert projected['rows'][0]['axis']==0 and projected['importable']
    expected=(1/3 if mode=='per_leaf' else (17+1/3)*(6 if current else 1)
              if mode=='integral_sum' else (17+1/3)/3.5)
    assert projected['rows'][0]['value']==pytest.approx(expected)
    assert projected['mapping']['columns']['measured']['unit']==('MPa*mm^2' if mode=='integral_sum' else 'MPa')
    if current:
        assert bundle['summary']['samples'][0]['leaves'][1]['reference_geometry_area']==pytest.approx(1.)
        assert bundle['summary']['samples'][0]['leaves'][1]['current_geometry_area']==pytest.approx(6.)


def test_workspace_block_local_pick_and_saved_selection_recovery(histories,monkeypatch,tmp_path):
    import importlib.util
    import json
    from pathlib import Path
    draft,bundle,measurement=native_measurement_bundle(histories,monkeypatch)
    source_path=Path(__file__).resolve().parents[1]/'apps/desktop_post/workspace.py'
    spec=importlib.util.spec_from_file_location('apps.desktop_post.workspace_measurement_block_test',source_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.measurements=measurement
    record={'id':'VleafMeasurement','recipe':draft,'summary':bundle['summary'],'key':'current'}
    obj={'id':'AuserMeasurement','kind':'measurement','selection_context':{'old':'preserved until explicit pick'}}
    host=SimpleNamespace(object=lambda ref:obj,_bundle=lambda obj,**kwargs:(record,bundle),
        _touch=lambda:None,state={'active_object':obj['id'],'objects':{obj['id']:obj}},
        applied=lambda obj:record,restore_issues=[])
    selected=module.Workspace.sample(host,object_ref=obj['id'],preview=False,row_index=0,table_block=[1],
                                     expected_revision=record['id'])
    assert selected['rows'][0]['block']==[1] and selected['rows'][0]['row']==0
    assert selected['rows'][0]['values']['SurfaceAreaAverage']==pytest.approx(1/3)
    assert obj['selection_revision']==record['id'] and 'selection_context' not in obj
    assert bundle['summary']['leaf_results'][1]['leaf_path']==[1,1]
    with pytest.raises(ValueError,match='STALE_SAMPLE'):
        module.Workspace.sample(host,object_ref=obj['id'],preview=False,row_index=0,table_block=[1],expected_revision='Vold')
    with pytest.raises(ValueError):
        module.Workspace.sample(host,object_ref=obj['id'],preview=False,row_index=0,table_block=[999])
    before=deepcopy(obj)
    with pytest.raises(ValueError):
        module.Workspace.sample(host,object_ref=obj['id'],preview=False,row_index=0)
    assert obj==before
    path=tmp_path/'selected-leaf-results.vtm';writer=vtk.vtkXMLMultiBlockDataWriter()
    writer.SetFileName(str(path));writer.SetInputData(bundle['source'].data);assert writer.Write()==1
    reader=vtk.vtkXMLMultiBlockDataReader();reader.SetFileName(str(path));reader.Update()
    cold_bundle={**bundle,'source':SimpleNamespace(data=reader.GetOutput(),UpdatePipeline=lambda:None)}
    cold_obj=json.loads(json.dumps(obj));cold_record=json.loads(json.dumps(record))
    cold=SimpleNamespace(state={'active_object':cold_obj['id'],'objects':{cold_obj['id']:cold_obj}},
        applied=lambda obj:cold_record,_bundle=lambda obj:(cold_record,cold_bundle),restore_issues=[])
    assert module.Workspace.restore_selection(cold)
    assert cold_obj['selection']==obj['selection'] and cold.restore_issues==[]
    cold_obj['selection'][0]['block']=[0]
    assert not module.Workspace.restore_selection(cold)
    assert cold.restore_issues
    cold_obj['selection']=deepcopy(obj['selection']);cold_obj['selection_revision']='Vold'
    assert not module.Workspace.restore_selection(cold)


def test_workspace_capture_passes_explicit_leaf_selection_into_actual_catalog(histories,monkeypatch):
    import importlib.util
    from pathlib import Path
    data=composite();source=SimpleNamespace(data=data,TimestepValues=[],UpdatePipeline=lambda:None)
    monkeypatch.setattr(histories.analysis,'_freeze',lambda source,time,namespace,proxies:source)
    monkeypatch.setattr(histories.analysis,'_fetch',lambda source:source.data)
    source_path=Path(__file__).resolve().parents[1]/'apps/desktop_post/workspace.py'
    spec=importlib.util.spec_from_file_location('apps.desktop_post.workspace_measurement_capture_test',source_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module.external,'set_time',lambda source:None,raising=False)
    verified=[]
    host=SimpleNamespace(document={'sources':{'SuserResult':{}}},resolve=lambda ref:source,
        pending=lambda refs:verified.append(('pending',refs)),_verify_inputs=lambda refs:verified.append(('verify',refs)))
    result=module.Workspace.capture_selection(host,source_ref='SuserResult',array='q',
        measurement='surface_average',leaf_paths=[[1,1]])
    assert result['leaf_selections'][0]['leaf_path']==[1,1]
    assert result['leaf_selections'][0]['surface_faces']==histories.surface_catalog(data.GetBlock(1).GetBlock(1))
    assert verified==[('pending',['SuserResult']),('verify',['SuserResult'])]


@pytest.mark.parametrize('mode',['per_leaf','area_weighted_mean','integral_sum'])
def test_no_valid_actual_geometry_does_not_gain_a_verified_display_scale_claim(histories,monkeypatch,mode):
    from caelab.post_observation import project_samples
    from test_post_measurement_history_observation import selection
    draft,bundle,measurement=native_measurement_bundle(histories,monkeypatch,mode=mode,current=True,
        invalid_displacement_paths=([0],[1,1]))
    assert bundle['summary']['display_scale_used'] is None
    assert all(report['valid'] is False for sample in bundle['summary']['samples'] for report in sample['leaves'])
    rows=measurement.sample_data(bundle['source'])['rows']
    assert all(row['values']['vtkValidMask']==0 and row['values'][bundle['summary']['array']] is None for row in rows)
    snapshot={'complete':True,'origin':{},'recipe':draft,'summary':bundle['summary'],'rows':rows}
    with pytest.raises(ValueError):project_samples(snapshot,selection(snapshot))


def test_valid_leaf_geometry_is_importable_without_admitting_an_invalid_leaf(histories,monkeypatch):
    from caelab.post_observation import project_samples
    from test_post_measurement_history_observation import selection
    draft,bundle,measurement=native_measurement_bundle(histories,monkeypatch,current=True,
        invalid_displacement_paths=([0],))
    assert bundle['summary']['display_scale_used'] is False
    reports=bundle['summary']['samples'][0]['leaves']
    assert reports[0]['valid'] is False and reports[0]['reason']=='nonfinite_actual_displacement'
    assert reports[1]['valid'] is True and reports[1]['display_scale_used'] is False
    snapshot={'complete':True,'origin':{},'recipe':draft,'summary':bundle['summary'],
        'rows':measurement.sample_data(bundle['source'])['rows']}
    chosen={**selection(snapshot),'block':[1]}
    assert project_samples(snapshot,chosen)['rows'][0]['value']==pytest.approx(1/3)
    with pytest.raises(ValueError,match='no valid measured samples'):
        project_samples(snapshot,{**chosen,'block':[0]})
