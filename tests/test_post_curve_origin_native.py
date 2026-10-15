"""Actual VTK table writer/reader + existing sampling; SCRIPTED ParaView owner.

This is not a ParaView GUI/Windows test. Native property, registry and render
boundaries are doubles. The original data, saved manifests and pins are real.
"""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import pytest
vtk=pytest.importorskip('vtk')
from caelab.post_observation import file_pin, check_pin
from caelab.storage import canonical_hash
from apps.desktop_post import curve_origin_native as origin
from test_post_r3_repairs import post_modules
from test_post_curves import recipe


@pytest.fixture
def native(tmp_path,monkeypatch,post_modules):
    import apps.desktop_post as package
    base=Path(__file__).parents[1]
    modules={}
    for name in ('measurements','contact_views','curve_native','workspace'):
        spec=importlib.util.spec_from_file_location('apps.desktop_post.'+name,base/'apps/desktop_post'/f'{name}.py')
        module=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,spec.name,module);monkeypatch.setattr(package,name,module,raising=False)
        spec.loader.exec_module(module);modules[name]=module
    p=post_modules.native;curves=modules['curve_native'];W=modules['workspace'].Workspace
    p.GetRepresentations=lambda:{};p.GetLayouts=lambda:{};p.Render=lambda *args:None
    selected=[]
    sm=SimpleNamespace(DATA_SERVER=2,GetNumberOfProcesses=lambda server:1)
    class Proxy:
        def __init__(self,data,path=None):
            self.data=data;self.FileName=[str(path)] if path else [];self.chosen=None
            self.SMProxy=SimpleNamespace(GetSession=lambda:sm,GetSelectionInput=lambda port:self.chosen,
                SetSelectionInput=lambda port,value,output:setattr(self,'chosen',value))
        def UpdatePipeline(self):pass
        def GetDataInformation(self):return SimpleNamespace(GetNumberOfPoints=lambda:0)
    def reader(**kwargs):
        r=vtk.vtkXMLTableReader();r.SetFileName(kwargs['FileName'][0]);r.Update()
        return Proxy(r.GetOutput(),kwargs['FileName'][0])
    p.XMLTableReader=reader;p.Delete=lambda source:None
    selection_module=ModuleType('paraview.selection')
    def choose(kind, **args):
        selected.append((kind, deepcopy({k:v for k,v in args.items() if k!='Source'})))
        args['Source'].chosen = object()
    selection_module.SelectIDs=lambda **args:choose('ids',**args)
    selection_module.SelectCompositeDataIDs=lambda **args:choose('composite',**args)
    monkeypatch.setitem(sys.modules,'paraview.selection',selection_module)
    owner=SimpleNamespace(project_path=tmp_path/'project.json',document_id='Dpost',session_id='Scurrent',
        generation=5,view_generation=6,closed=False,snapshot={'sources':[],'views':[],'representations':{}},
        assert_thread=lambda:None,refresh=lambda:None)
    statefile=tmp_path/'state.pvsm';statefile.write_text('<ServerManagerState/>')
    rawfiles=[]
    for name,text in [('raw.pvd','<VTKFile><Collection><DataSet file="frame.vtu"/></Collection></VTKFile>'),
                      ('frame.vtu','<VTKFile type="UnstructuredGrid"/>'),('source.json','{"frame":"global"}')]:
        path=tmp_path/name;path.write_text(text);rawfiles.append(file_pin(path))
    objects={};bundles={};dependency_reads=[]
    document={'document_id':'Dpost','project_root':str(tmp_path),'workspace_file':'state.pvsm',
        'workspace_sha256':file_pin(statefile)['sha256'],'sources':{'Sraw':{'source_pins':rawfiles}},
        'analysis':{'version':1,'objects':objects,'active_object':'Acompare'}}
    ws=SimpleNamespace(owner=owner,document=document,state=document['analysis'],restore_issues=[])
    ws.object=lambda ref:objects[ref]
    ws.applied=lambda obj:obj['history'][obj['position']]
    ws._bundle=lambda obj:(ws.applied(obj),bundles[ws.applied(obj)['id']])
    ws._verify_result_pins=W._verify_result_pins
    ws._refs=W._refs
    ws._retained_dependencies=lambda record,refs:W._retained_dependencies(ws,record,refs)
    def verify_inputs(refs,revisions=None):
        dependency_reads.append((deepcopy(refs),deepcopy(revisions)))
        for ref in refs:
            if ref=='Sraw':
                for pin in rawfiles:check_pin(pin)
    ws._verify_inputs=verify_inputs
    def verify_record(obj,record,bundle):
        for pin in record['result_files']:check_pin(pin)
        if record['recipe'].get('version')==3:
            assert curves.fingerprint(bundle['source'].data)['output_hash']==record['summary']['output_hash']
    ws._verify_record=verify_record
    ws._touch=lambda:setattr(owner,'generation',owner.generation+1)
    views=[]
    ws.show=lambda obj,record,bundle:views.append(obj['id'])
    def save():owner.project_path.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
    def measurement(ref,x,y,block=False):
        table=vtk.vtkTable()
        for name,values in [('Time',x),('F',y)]:
            a=vtk.vtkDoubleArray();a.SetName(name)
            if name=='F':
                a.SetNumberOfComponents(3)
                for index, label in enumerate(('X', 'Y', 'Z')):a.SetComponentName(index, label)
                for value in values:a.InsertNextTuple3(value,2*value,3*value)
            else:
                for value in values:a.InsertNextValue(value)
            table.AddColumn(a)
        path=tmp_path/(ref+'.vtt');writer=vtk.vtkXMLTableWriter();writer.SetFileName(str(path));writer.SetInputData(table);assert writer.Write()==1
        if block:
            data=vtk.vtkMultiBlockDataSet();data.SetBlock(0,table)
        else:data=table
        r={'measurement':'time','source_ref':'Sraw','array':'F','association':'POINTS','units':'N',
            'measure':'force','quantity':'force','frame':'global','time_units':'s','time_origin':'analysis_start',
            'layout':{'kind':'vector','components':['x','y','z']}}
        record={'id':'V'+ref,'recipe':r,'summary':deepcopy(r),'graph':{},'bindings':{'Sraw':{'revision':'raw'}},
            'result_file':str(path),'result_files':[file_pin(path)],'result_sha256':file_pin(path)['sha256']}
        obj={'id':ref,'kind':'measurement','title':ref,'draft':deepcopy(r),'history':[record],'position':0}
        objects[ref]=obj;bundles[record['id']]={'source':Proxy(data),'summary':record['summary'],'retained_only':True}
        save();return obj
    measurement('Aleft',[0.,.5,1.],[0.,2.,4.]);measurement('Aright',[0.,1.],[0.,4.],True)
    def comparison():
        save();r=recipe();r.update(alignment='bracket',a=curves.options(ws,'Aleft')[0],b=curves.options(ws,'Aright')[0])
        bundle=curves.build(ws,r,'SCRIPTED-VTK');path=Path(bundle['source'].FileName[0])
        record={'id':'Vcompare','recipe':r,'summary':bundle['summary'],'graph':{},
            'bindings':{ref:{'revision':canonical_hash({k:ws.applied(objects[ref])[k] for k in ('id','recipe','graph','bindings')})}
                for ref in ('Aleft','Aright')},'result_file':str(path),'result_files':[file_pin(path)],
            'result_sha256':file_pin(path)['sha256']}
        obj={'id':'Acompare','kind':'comparison','draft':deepcopy(r),'history':[record],'position':0}
        objects['Acompare']=obj;bundles[record['id']]=bundle;save()
        return origin.read(ws,object_ref='Acompare',revision='Vcompare',table='aligned',row_index=1,expected_view_generation=6)
    receipt=comparison()
    return SimpleNamespace(ws=ws,curves=curves,modules=modules,receipt=receipt,objects=objects,bundles=bundles,
        owner=owner,rawfiles=rawfiles,save=save,measurement=measurement,comparison=comparison,selected=selected,
        views=views,dependency_reads=dependency_reads,p=p,sm=sm,Proxy=Proxy)


def test_actual_existing_vtk_comparison_samples_to_saved_owner_fullpins(native):
    n=native;receipt=n.receipt
    assert receipt['status']=='ORIGINALS_READ' and len(receipt['targets'])==3
    assert [t['raw']['identity'] for t in receipt['targets']]==[
        {'block':[],'row':1},{'block':[0],'row':0},{'block':[0],'row':1}]
    for t in receipt['targets']:
        assert t['saved_origin']['kind']=='post_measurement'
        assert t['saved_origin']['pid']==os.getpid() and t['saved_origin']['session_id']=='Scurrent'
        assert set(t['origin'])=={'document_id','object_ref','revision','recipe','result_sha256'}
        verified=origin.verify(n.ws,target=t,expected_view_generation=6)
        assert verified['status']=='SOURCE_VERIFIED' and verified['raw']['raw_x']==t['raw']['raw_x']
    assert not n.selected and not n.views


@pytest.mark.parametrize('fault',['project','workspace','result','pvd','frame','sidecar','unsaved','draft','historical','clone','pending','view','raw_value','wrong_row'])
def test_changed_missing_or_wrong_owner_refuses_without_native_selection(native,fault,tmp_path):
    n=native;t=deepcopy(n.receipt['targets'][2]);record=n.objects['Aright']['history'][0]
    if fault in ('project','workspace','result'):
        path=Path(t['saved_origin']['project']['path'] if fault=='project' else t['saved_origin']['workspace']['path'] if fault=='workspace' else record['result_file'])
        path.write_bytes(path.read_bytes()+b' ')
    elif fault in ('pvd','frame','sidecar'):Path(n.rawfiles[('pvd','frame','sidecar').index(fault)]['path']).unlink()
    elif fault=='unsaved':n.owner.project_path=tmp_path/'not-saved.json'
    elif fault=='draft':n.objects['Aright']['draft']['units']='kN'
    elif fault=='historical':n.objects['Aright']['history'].append(deepcopy(record));n.objects['Aright']['history'][-1]['id']='Vnew';n.objects['Aright']['position']=1
    elif fault=='clone':
        other=tmp_path/'clone.json';other.write_bytes(n.owner.project_path.read_bytes());n.owner.project_path=other
    elif fault=='pending':n.owner.snapshot['sources']=[{'pending_properties':['F']}]
    elif fault=='view':n.owner.view_generation+=1
    elif fault=='raw_value':n.bundles[record['id']]['source'].data.GetBlock(0).GetColumnByName('F').SetTuple3(1,9,8,7)
    else:t['raw']['identity']['row']=999
    with pytest.raises((ValueError,OSError,KeyError)):origin.verify(n.ws,target=t,expected_view_generation=6)
    assert not n.selected and not n.views


def test_actual_vtk_flat_block_selection_not_solver_global_id(native):
    n=native;t=n.receipt['targets'][2];source=n.bundles['VAright']['source']
    origin._highlight(source,{'block':[0],'row':1,'values':{}})
    assert n.selected==[('composite',{'IDs':[1,0,1],'FieldType':'ROW'})]
    n.sm.GetNumberOfProcesses=lambda server:2
    with pytest.raises(ValueError):origin._highlight(source,{'block':[0],'row':1})
    assert len(n.selected)==1


@pytest.mark.parametrize('fault', [None, 'selector_noop', 'selector_domain_missing'])
def test_select_save_cold_restore_has_no_persisted_session_authority(native, chart_scene, fault):
    n=native;t=n.receipt['targets'][2]
    scene=chart_scene(n.bundles['VAright']['source'])
    verified=origin.verify(n.ws,target=t,expected_view_generation=6)
    selected=origin.select(n.ws,target=t,verified=verified,expected_view_generation=6)
    assert selected['status']=='SOURCE_SELECTED' and selected['row']['row']==1
    obj=n.objects['Aright'];persisted=deepcopy(obj)
    text=json.dumps(persisted['selection_context'])
    assert all(key not in text for key in ('saved_origin','Scurrent','host_token','session_id','pid'))
    n.save()
    # A new owner object/session, JSON reload and fresh display, not old authority.
    n.ws.owner=SimpleNamespace(**{**vars(n.owner), 'session_id':'Sreopened'})
    loaded=json.loads(n.owner.project_path.read_text())['analysis']['objects']['Aright']
    n.objects['Aright']=loaded
    fresh=chart_scene(n.bundles['VAright']['source'], fault=fault)
    before=fresh.snapshot()
    if fault:
        with pytest.raises(ValueError):origin.restore(n.ws,loaded)
        fresh.assert_restored(before)
    else:
        assert origin.restore(n.ws,loaded)
        assert fresh.values()==scene.values() and loaded['selection']==persisted['selection']
        assert n.selected[-1]==('composite',{'IDs':[1,0,1],'FieldType':'ROW'})
    assert origin.saved_origin(n.ws,loaded,loaded['history'][0])['session_id']=='Sreopened'


def test_native_selection_failure_restores_record_and_does_not_become_success(native,monkeypatch):
    n=native;t=n.receipt['targets'][2];obj=n.objects['Aright'];before=deepcopy(obj)
    active=n.ws.state['active_object'];source=n.bundles['VAright']['source'];old=object();source.chosen=old
    def fail(*args):
        obj['history'][0]['view_name']='new transient view'
        source.chosen=object()
        raise RuntimeError('SCRIPTED render error')
    monkeypatch.setattr(origin,'_show_selected',fail)
    verified=origin.verify(n.ws,target=t,expected_view_generation=6)
    with pytest.raises(RuntimeError,match='SCRIPTED'):
        origin.select(n.ws,target=t,verified=verified,expected_view_generation=6)
    assert obj==before and n.ws.state['active_object']==active and source.chosen is old


def test_cross_page_b_brackets_use_real_original_indices(native):
    n=native
    n.measurement('Aright',[i/1000 for i in range(1002)],[float(i) for i in range(1002)],True)
    n.measurement('Aleft',[0.,.9995,1.001],[0.,999.5,1001.])
    result=n.comparison()
    assert [r['raw']['identity']['row'] for r in result['targets']]==[1,999,1000]
    assert [r['raw']['raw_x'] for r in result['targets']]==[.9995,.999,1.]


def test_original_frame_change_during_fetch_cannot_hide_behind_retained_result(native,monkeypatch):
    n=native;original=n.curves.sample
    def changed(*args,**kwargs):
        page=original(*args,**kwargs)
        Path(n.rawfiles[1]['path']).write_bytes(b'changed during fetch')
        return page
    monkeypatch.setattr(n.curves,'sample',changed)
    with pytest.raises(ValueError):
        origin.read(n.ws,object_ref='Acompare',revision='Vcompare',table='aligned',row_index=1,expected_view_generation=6)
    assert not n.selected and not n.views


def test_noop_selection_does_not_pass_with_previous_selection(native,monkeypatch):
    n=native;source=n.bundles['VAright']['source'];source.chosen=object()
    monkeypatch.setattr(sys.modules['paraview.selection'],'SelectCompositeDataIDs',lambda **kwargs:None)
    with pytest.raises(ValueError,match='적용되지'):
        origin._highlight(source,{'block':[0],'row':1})


class ChartProperty:
    def __init__(self, value, available=(), domains=None):
        self.value=deepcopy(value);self.available=available;self.domains=domains or {}
    def GetData(self):return deepcopy(self.value)
    @property
    def Available(self):return list(self.available() if callable(self.available) else self.available)
    def FindDomain(self, kind):return self.domains.get(kind)


class ChartProxy:
    """Strict existing-proxy boundary. Unknown properties are never synthesized."""
    def __init__(self, properties, kind='XYChartView'):
        object.__setattr__(self,'props',{name:ChartProperty(value) for name,value in properties.items()})
        object.__setattr__(self,'kind',kind)
        object.__setattr__(self,'SMProxy',SimpleNamespace(UpdatePropertyInformation=self.UpdateVTKObjects))
    def GetXMLName(self):return self.kind
    def GetProperty(self,name):return self.props.get(name)
    def __getattr__(self,name):
        if name not in self.props:raise AttributeError(name)
        return self.props[name]
    def __setattr__(self,name,value):
        if name not in self.props:raise AttributeError(name)
        self.props[name].value=deepcopy(value)
    def UpdateVTKObjects(self):pass
    def values(self):return {name:prop.GetData() for name,prop in self.props.items()}


def nested_source(native, point=False):
    """Two same-named arrays with DISTINCT values; empty ancestors consume flat IDs."""
    source=native.bundles['VAright']['source'];table=source.data.GetBlock(0)
    leaves=[]
    for offset in (0.,100.):
        leaf=vtk.vtkTable();leaf.DeepCopy(table)
        for row in range(leaf.GetNumberOfRows()):
            value=leaf.GetColumnByName('F').GetTuple(row)
            leaf.GetColumnByName('F').SetTuple(row,[x+offset for x in value])
        if point:
            data=vtk.vtkPolyData();points=vtk.vtkPoints()
            for row in range(leaf.GetNumberOfRows()):points.InsertNextPoint(row,0,0)
            for index,label in enumerate(('X','Y','Z')):points.GetData().SetComponentName(index,label)
            data.SetPoints(points)
            for index in range(leaf.GetNumberOfColumns()):data.GetPointData().AddArray(leaf.GetColumn(index))
            leaf=data
        leaves.append(leaf)
    child=vtk.vtkMultiBlockDataSet();child.SetBlock(1,leaves[0]);child.SetBlock(2,leaves[1])
    source.data=vtk.vtkMultiBlockDataSet();source.data.SetBlock(1,child)
    return source, leaves


@pytest.fixture
def chart_scene(native,monkeypatch):
    """6.2 SM/property/domain/render/metadata doubles + REAL VTK hierarchy/arrays.

    No ParaView process, chart renderer or OS input is executed. Component names
    are explicit in the VTK fixture; the mangling double mirrors the cited 6.2
    native helper API (not the A2 'F (1)' convention).
    """
    n=native;manager=sys.modules['paraview'].servermanager
    class ArrayInformation:
        def CopyFromArray(self,array):self.array=array
    def mangle(info,index):
        array=info.array
        label='Magnitude' if index==array.GetNumberOfComponents() else array.GetComponentName(index)
        assert label is not None, 'fixture must provide native component metadata'
        return array.GetName()+'_'+label
    monkeypatch.setattr(manager,'vtkPVArrayInformation',ArrayInformation,raising=False)
    monkeypatch.setattr(manager,'vtkSMArrayListDomain',SimpleNamespace(CreateMangledName=mangle),raising=False)

    def setup(source, *, fault=None, create=False, legacy=False):
        hierarchy=vtk.vtkDataAssembly()
        if source.data.IsA('vtkCompositeDataSet'):
            assert vtk.vtkDataAssemblyUtilities.GenerateHierarchy(source.data,hierarchy)
        flat=4 if source.data.IsA('vtkMultiBlockDataSet') and source.data.GetNumberOfBlocks()>1 else 1
        nodes=list(hierarchy.SelectNodes(["//*[@cid='%d']" % flat]))
        if nodes:
            node=nodes[0]
            if fault=='selector_not_found':hierarchy.SetAttribute(node,'cid','999')
            if fault=='selector_multiple':
                other=hierarchy.AddNode('Duplicate');hierarchy.SetAttribute(other,'cid',str(flat))
            if fault=='selector_branch':hierarchy.AddNode('Child',node)
            if fault=='selector_dataset_mismatch':hierarchy.AddDataSetIndex(node,999)
        consumed=set();writes=[];rendered=[];deleted=[];removed=[]
        field='POINT' if source.data.IsA('vtkMultiBlockDataSet') and source.data.GetNumberOfBlocks()>1 and source.data.GetBlock(1).GetBlock(1).IsA('vtkPolyData') else 'ROW'
        wanted='Point Data' if field=='POINT' else 'Row Data'
        class Display(ChartProxy):
            def __setattr__(self,name,value):
                noop={'selector_noop':'BlockSelectors','assembly_noop':'Assembly','mode_noop':'ArraySelectionMode',
                      'association_noop':'AttributeType','axis_noop':'XArrayName','series_noop':'SeriesVisibility',
                      'legacy_noop':'CompositeDataSetIndex'}
                if noop.get(fault)==name:return
                if fault=='series_apply_noop' and name=='SeriesVisibility' and value!=['old']:return
                if fault=='rollback_noop' and name=='SeriesColor' and value==['old',.1,.2,.3]:return
                changed=self.props[name].value!=value
                super().__setattr__(name,value);writes.append((name,deepcopy(value)))
                if changed and name in ('AttributeType','Assembly','ArraySelectionMode','BlockSelectors'):
                    # Like native domain observers, control changes reset dependent
                    # defaults. A rollback in reverse/random order loses old styles.
                    self.props['SeriesVisibility'].value=['domain default']
                    self.props['SeriesColor'].value=['domain default',1.,0.,0.]
                    self.props['SeriesLabel'].value=['domain default','auto label']
                    if name in ('Assembly','ArraySelectionMode') and 'BlockSelectors' in self.props:
                        self.props['BlockSelectors'].value=['/']
        display=Display({'AttributeType':'Cell Data','Visibility':0,'UseIndexForXAxis':1,
            'XArrayName':'old axis','SeriesVisibility':['old'],'SeriesColor':['old',.1,.2,.3],
            'SeriesLabel':['old','retained label'],'SeriesOpacity':['old',.7],
            'SeriesLineStyle':['old','2'],'SeriesMarkerStyle':['old','4'],
            'ShowBlockName':1,'SelectionOnly':0},kind='XYChartRepresentation')
        if legacy:
            display.props['CompositeDataSetIndex']=ChartProperty([99],domains={
                'vtkSMCompositeTreeDomain':object()} if fault!='legacy_domain_missing' else {})
        else:
            # The named Assembly alternative is a scripted domain; flat IDs must
            # be qualified by Hierarchy, never interpreted in that alternative.
            display.props.update(Assembly=ChartProperty('Assembly',['Hierarchy','Assembly']),
                ArraySelectionMode=ChartProperty('Individual Blocks',['Merged Blocks','Individual Blocks']),
                BlockSelectors=ChartProperty(['/']))
            domain=SimpleNamespace(
                GetDataAssemblyName=lambda:'Assembly' if fault=='wrong_domain_assembly' else display.props['Assembly'].value,
                GetMode=lambda:1 if fault=='wrong_domain_mode' else (0 if display.props['ArraySelectionMode'].value=='Merged Blocks' else 1),
                GetDataAssembly=lambda:None if fault=='hierarchy_missing' else hierarchy)
            if fault!='selector_domain_missing':display.props['BlockSelectors'].domains['vtkSMDataAssemblyDomain']=domain
            for name,key in (('Assembly','assembly_missing'),('BlockSelectors','selectors_missing'),('ArraySelectionMode','mode_missing')):
                if fault==key:display.props.pop(name)
            if fault=='assembly_domain_missing':display.props['Assembly'].available=[]
            if fault=='mode_domain_missing':display.props['ArraySelectionMode'].available=[]
        display.props['AttributeType'].available=[] if fault=='association_domain_missing' else ['Point Data','Cell Data','Row Data']
        # These are live domains. Series become available only after association,
        # hierarchy, mode and selectors refer to one actual leaf.
        def available(axis=False):
            if display.props['AttributeType'].value!=wanted:return []
            leaf=source.data
            if leaf.IsA('vtkCompositeDataSet'):
                if legacy:
                    ids=display.props['CompositeDataSetIndex'].value
                else:
                    if display.props.get('Assembly') is None or display.props['Assembly'].value!='Hierarchy':return []
                    if display.props.get('ArraySelectionMode') is None or display.props['ArraySelectionMode'].value!='Merged Blocks':return ['F_X (Other block)']
                    if display.props.get('BlockSelectors') is None:return []
                    selected_nodes=list(hierarchy.SelectNodes(display.props['BlockSelectors'].value))
                    if len(selected_nodes)!=1 or hierarchy.GetNumberOfChildren(selected_nodes[0]):return []
                    ids=list(hierarchy.GetDataSetIndices(selected_nodes[0],False))
                iterator=leaf.NewIterator();iterator.InitTraversal();matches=[]
                while not iterator.IsDoneWithTraversal():
                    if iterator.GetCurrentFlatIndex() in ids:matches.append(iterator.GetCurrentDataObject())
                    iterator.GoToNextItem()
                if len(matches)!=1:return []
                leaf=matches[0]
            attrs=leaf.GetRowData() if field=='ROW' else leaf.GetPointData()
            labels=[]
            for i in range(attrs.GetNumberOfArrays()):
                arr=attrs.GetArray(i)
                if arr.GetNumberOfComponents()==1:labels.append(arr.GetName())
                else:
                    labels.extend(arr.GetName()+'_'+arr.GetComponentName(j) for j in range(arr.GetNumberOfComponents()))
                    labels.append(arr.GetName()+'_Magnitude')
            if fault=='series_missing' and not axis:return ['F_Magnitude']
            if fault=='axis_missing' and axis:return []
            return labels
        display.props['SeriesVisibility'].available=lambda:available()
        display.props['XArrayName'].available=lambda:available(True)
        oldview=ChartProxy({'ChartTitle':'old scene'},'RenderView')
        chart=ChartProxy({'ChartTitle':'original chart','LeftAxisTitle':'force','BottomAxisTitle':'time'})
        oldrep=ChartProxy({'Visibility':1},'GeometryRepresentation')
        oldlayout=object();newlayout=object();other=n.Proxy(vtk.vtkTable())
        views={'old':oldview};reps={'other':oldrep};layouts={'old':oldlayout}
        if not create:views['chart']=chart;reps['chart']=display
        active=[other,oldview];source.chosen=object()
        def show(obj,record,bundle):
            n.views.append(obj['id'])
            if create:views['chart']=chart;reps['chart']=display;layouts['new']=newlayout
            display.Visibility=1;display.UseIndexForXAxis=0
            display.XArrayName=record['recipe'].get('axis_name','Time')
            display.SeriesVisibility=[record['recipe'].get('array','F')]
            chart.ChartTitle='shown target'
            record['view_name']='chart';record['view_names']=['chart']
            active[:]=[bundle['source'],chart]
        def delete(proxy):
            assert proxy is not source and proxy is not other
            deleted.append(proxy)
            for collection in (views,reps):
                for key,value in list(collection.items()):
                    if value is proxy:del collection[key]
        def remove(layout):
            removed.append(layout)
            for key,value in list(layouts.items()):
                if value is layout:del layouts[key]
        def render(view):
            rendered.append(view)
            if view is chart and not consumed:
                if fault in ('render_error','rollback_noop'):
                    consumed.add(fault);raise RuntimeError('SCRIPTED render error')
                if fault=='render_interrupt':consumed.add(fault);raise KeyboardInterrupt('SCRIPTED interrupt')
                if fault=='late_selector_reset':
                    consumed.add(fault);display.props['BlockSelectors'].value=['/']
        monkeypatch.setattr(n.ws,'show',show)
        for name,value in dict(GetActiveSource=lambda:active[0],GetActiveView=lambda:active[1],
            SetActiveSource=lambda value:active.__setitem__(0,value),SetActiveView=lambda value:active.__setitem__(1,value),
            GetViews=lambda:list(views.values()),GetRepresentations=lambda:dict(reps),GetLayouts=lambda:dict(layouts),
            GetDisplayProperties=lambda src,view:display,Delete=delete,RemoveLayout=remove,Render=render).items():
            monkeypatch.setattr(n.p,name,value,raising=False)
        if fault=='row_noop':monkeypatch.setattr(sys.modules['paraview.selection'],'SelectCompositeDataIDs',lambda **kwargs:None)
        def snapshot():return (tuple(active),source.chosen,dict(views),dict(reps),dict(layouts),
            [(proxy,proxy.values()) for proxy in [*views.values(),*reps.values()]])
        def assert_restored(before):
            assert tuple(active)==before[0] and source.chosen is before[1]
            assert (views,reps,layouts)==before[2:5]
            for proxy,values in before[5]:assert proxy.values()==values
            assert all(proxy not in before[2].values() and proxy not in before[3].values() for proxy in deleted)
            assert all(layout not in before[4].values() for layout in removed)
        return SimpleNamespace(display=display,chart=chart,values=display.values,writes=writes,hierarchy=hierarchy,
            snapshot=snapshot,assert_restored=assert_restored,deleted=deleted,removed=removed,rendered=rendered)
    return setup


@pytest.mark.parametrize('block,flat', [([1,1],4),([1,2],5)])
@pytest.mark.parametrize('point', [False,True])
@pytest.mark.parametrize('component', [0,1,2])
def test_chart62_exact_nested_leaf_component_axis_row(native,chart_scene,block,flat,point,component):
    n=native;source,leaves=nested_source(n,point);scene=chart_scene(source)
    field='POINT' if point else 'ROW'
    leaf=leaves[block[-1]-1];attrs=leaf.GetPointData() if point else leaf.GetRowData()
    row={'block':block,'row':1,'values':{'Time':1.,'F':list(attrs.GetArray('F').GetTuple(1))}}
    selection={'value_array':'F','value_component':component,'axis':{'kind':'array','name':'Time','component':None}}
    assert scene.display.GetProperty('CompositeDataSetIndex') is None
    origin._show_selected(n.ws,n.objects['Aright'],n.objects['Aright']['history'][0],n.bundles['VAright'],selection,row)
    values=scene.values()
    assert values['Assembly']=='Hierarchy' and values['ArraySelectionMode']=='Merged Blocks'
    assert values['BlockSelectors']==["//*[@cid='%d']" % flat]
    assert values['SeriesVisibility']==['F_'+('X','Y','Z')[component]]
    assert values['XArrayName']=='Time' and values['UseIndexForXAxis']==0
    assert values['AttributeType']==('Point Data' if point else 'Row Data')
    assert n.selected[-1]==('composite',{'IDs':[flat,0,1],'FieldType':field})
    assert flat!=block[0] and leaves[0]!=leaves[1]
    # Exercise the real VTK extraction primitive used by the 6.2 chart, not a
    # predicate supplied by Display. There must be only this leaf's original data.
    extract=vtk.vtkExtractBlockUsingDataAssembly();extract.SetInputData(source.data)
    extract.SetAssemblyName(values['Assembly']);extract.PruneDataAssemblyOff()
    for selector in values['BlockSelectors']:extract.AddSelector(selector)
    extract.Update();out=extract.GetOutputDataObject(0)
    iterator=out.NewIterator();iterator.InitTraversal();actual=[]
    while not iterator.IsDoneWithTraversal():
        item=iterator.GetCurrentDataObject()
        if item is not None:
            data=item.GetPointData() if point else item.GetRowData()
            actual.append(list(data.GetArray('F').GetTuple(1)))
        iterator.GoToNextItem()
    assert actual==[row['values']['F']]


@pytest.mark.parametrize('fault', ['selector_noop','assembly_noop','mode_noop','association_noop','axis_noop',
    'series_apply_noop','assembly_missing','mode_missing','selectors_missing','assembly_domain_missing',
    'mode_domain_missing','association_domain_missing','selector_domain_missing','hierarchy_missing',
    'wrong_domain_assembly','wrong_domain_mode','selector_not_found','selector_multiple','selector_branch',
    'selector_dataset_mismatch','series_missing','axis_missing','row_noop','render_error','render_interrupt','late_selector_reset'])
def test_chart62_select_failure_restores_existing_scene_selection_owner(native,chart_scene,fault):
    n=native;source,_=nested_source(n);t=n.comparison()['targets'][2]
    assert t['raw']['identity']['block']==[1,1]
    scene=chart_scene(source,fault=fault);before=scene.snapshot();obj=n.objects['Aright'];saved=deepcopy(obj)
    active=n.ws.state['active_object'];verified=origin.verify(n.ws,target=t,expected_view_generation=6)
    with pytest.raises((ValueError,RuntimeError,KeyboardInterrupt)):
        origin.select(n.ws,target=t,verified=verified,expected_view_generation=6)
    scene.assert_restored(before)
    assert obj==saved and n.ws.state['active_object']==active and n.owner.generation==5
    assert not scene.deleted and not scene.removed


@pytest.mark.parametrize('fault',['selector_domain_missing','row_noop','render_error','render_interrupt'])
def test_chart62_failure_deletes_only_new_view_representation_layout(native,chart_scene,fault):
    n=native;source,_=nested_source(n);t=n.comparison()['targets'][2]
    scene=chart_scene(source,fault=fault,create=True);before=scene.snapshot()
    saved=deepcopy(n.objects['Aright']);verified=origin.verify(n.ws,target=t,expected_view_generation=6)
    with pytest.raises((ValueError,RuntimeError,KeyboardInterrupt)):
        origin.select(n.ws,target=t,verified=verified,expected_view_generation=6)
    scene.assert_restored(before)
    assert scene.deleted==[scene.display,scene.chart] and len(scene.removed)==1
    assert n.objects['Aright']==saved


@pytest.mark.parametrize('fault,property_name,original', [('rollback_noop','SeriesColor',['old',.1,.2,.3]),
    ('series_noop','SeriesVisibility',['old'])])
def test_chart62_rollback_noop_is_reported_as_unconfirmed_not_success(native,chart_scene,fault,property_name,original):
    n=native;source,_=nested_source(n);t=n.comparison()['targets'][2]
    scene=chart_scene(source,fault=fault);before=scene.snapshot()
    verified=origin.verify(n.ws,target=t,expected_view_generation=6)
    with pytest.raises(RuntimeError,match='복원 미확정'):
        origin.select(n.ws,target=t,verified=verified,expected_view_generation=6)
    assert source.chosen is before[1] and (n.p.GetActiveSource(),n.p.GetActiveView())==before[0]
    assert scene.values()[property_name]!=original


@pytest.mark.parametrize('aligned_row,expected_rows',[(1,[0,1]),(2,[1])])
def test_chart62_exact_b_and_both_brackets_open_actual_rows(native,chart_scene,aligned_row,expected_rows):
    n=native;source,_=nested_source(n);n.comparison();scene=chart_scene(source)
    receipt=origin.read(n.ws,object_ref='Acompare',revision='Vcompare',table='aligned',row_index=aligned_row,expected_view_generation=6)
    targets=[t for t in receipt['targets'] if t['selector']['source_ref']=='Aright']
    assert [t['raw']['identity']['row'] for t in targets]==expected_rows
    for t,row in zip(targets,expected_rows):
        verified=origin.verify(n.ws,target=t,expected_view_generation=6)
        answer=origin.select(n.ws,target=t,verified=verified,expected_view_generation=6)
        assert answer['status']=='SOURCE_SELECTED' and 'foreground_confirmed' not in answer
        assert answer['raw']['raw_x']==float(row)  # never the aligned .5 midpoint
        assert n.selected[-1]==('composite',{'IDs':[4,0,row],'FieldType':'ROW'})
        assert scene.values()['BlockSelectors']==["//*[@cid='4']"]


@pytest.mark.parametrize('fault',[None,'legacy_noop','legacy_domain_missing'])
def test_legacy_fallback_requires_real_property_and_domain(native,chart_scene,fault):
    n=native;source,_=nested_source(n);t=n.comparison()['targets'][2]
    scene=chart_scene(source,legacy=True,fault=fault);before=scene.snapshot()
    assert scene.display.GetProperty('BlockSelectors') is None
    verified=origin.verify(n.ws,target=t,expected_view_generation=6)
    if fault:
        with pytest.raises(ValueError):origin.select(n.ws,target=t,verified=verified,expected_view_generation=6)
        scene.assert_restored(before)
    else:
        answer=origin.select(n.ws,target=t,verified=verified,expected_view_generation=6)
        assert answer['status']=='SOURCE_SELECTED' and scene.values()['CompositeDataSetIndex']==[4]


@pytest.mark.parametrize('axis_kind',['array','point_index','unsupported_coordinate'])
def test_chart62_custom_component_and_axis_semantics(native,chart_scene,axis_kind):
    n=native;source,leaves=nested_source(n,point=True);scene=chart_scene(source)
    for leaf in leaves:leaf.GetPointData().GetArray('F').SetComponentName(1,'axial')
    selection={'value_array':'F','value_component':1,'axis':{'kind':axis_kind,'name':'F','component':2}}
    row={'block':[1,1],'row':1,'values':{'Time':1.,'F':[4.,8.,12.]}}
    arguments=(n.ws,n.objects['Aright'],n.objects['Aright']['history'][0],n.bundles['VAright'],selection,row)
    if axis_kind=='unsupported_coordinate':
        with pytest.raises(ValueError,match='좌표'):origin._show_selected(*arguments)
        return
    origin._show_selected(*arguments)
    assert scene.values()['SeriesVisibility']==['F_axial']
    assert scene.values()['UseIndexForXAxis']==int(axis_kind=='point_index')
    if axis_kind=='array':assert scene.values()['XArrayName']=='F_Z'
    assert n.selected[-1]==('composite',{'IDs':[4,0,1],'FieldType':'POINT'})


@pytest.mark.parametrize('fault',['scalar_name_collision','component_name_collision','component_missing','axis_array_missing'])
def test_chart62_ambiguous_or_missing_native_meaning_is_rejected(native,chart_scene,fault):
    n=native;source,leaves=nested_source(n);scene=chart_scene(source)
    attrs=leaves[0].GetRowData()
    if fault=='scalar_name_collision':
        arr=vtk.vtkDoubleArray();arr.SetName('F_X');arr.SetNumberOfTuples(2);attrs.AddArray(arr)
    elif fault=='component_name_collision':attrs.GetArray('F').SetComponentName(1,'X')
    selection={'value_array':'F','value_component':None if fault=='component_missing' else 0,
        'axis':{'kind':'array','name':'MISSING' if fault=='axis_array_missing' else 'Time','component':None}}
    with pytest.raises(ValueError):
        origin._show_selected(n.ws,n.objects['Aright'],n.objects['Aright']['history'][0],n.bundles['VAright'],
            selection,{'block':[1,1],'row':1,'values':{'Time':1.,'F':[4.,8.,12.]}})
    assert not n.selected


@pytest.mark.parametrize('point,collision',[(False,'vtkOriginalIndices'),(True,'Points_X')])
@pytest.mark.parametrize('role',['response','axis'])
def test_chart62_generated_metadata_name_collision_is_rejected(native,chart_scene,point,collision,role):
    n=native;source,leaves=nested_source(n,point);scene=chart_scene(source)
    leaf=leaves[0];attrs=leaf.GetPointData() if point else leaf.GetRowData()
    array=vtk.vtkDoubleArray();array.SetName(collision)
    for value in (91.,92.):array.InsertNextValue(value)
    attrs.AddArray(array)
    # Real VTK decoration introduces coordinates / replaces the original row ID.
    decorate=vtk.vtkAttributeDataToTableFilter();decorate.SetInputData(leaf)
    decorate.SetFieldAssociation(vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS if point else vtk.vtkDataObject.FIELD_ASSOCIATION_ROWS)
    decorate.SetAddMetaData(True);decorate.SetGenerateOriginalIds(True);decorate.Update()
    output=decorate.GetOutput().GetRowData()
    if point:
        assert output.GetArray('Points').GetComponent(1,0)==1.
        assert array.GetValue(1)==92.  # The flattened Points_X would mean coordinate x.
    else:assert output.GetArray(collision).GetValue(1)==1 and array.GetValue(1)==92.
    selection={'value_array':collision if role=='response' else 'F',
        'value_component':None if role=='response' else 0,
        'axis':{'kind':'array','name':collision if role=='axis' else 'Time','component':None}}
    with pytest.raises(ValueError,match='자동 생성 열'):
        origin._show_selected(n.ws,n.objects['Aright'],n.objects['Aright']['history'][0],n.bundles['VAright'],
            selection,{'block':[1,1],'row':1,'values':{'Time':1.,'F':[4.,8.,12.]}})
    assert not n.selected and attrs.GetArray(collision) is array and array.GetValue(1)==92.
    # A raw vector can be overwritten before flattening even when its custom
    # component label differs from every generated coordinate component label.
    attrs.RemoveArray(collision)
    vector=vtk.vtkDoubleArray();vector.SetName('Points' if point else 'vtkOriginalIndices')
    vector.SetNumberOfComponents(3)
    for index,label in enumerate(('radial','axial','normal')):vector.SetComponentName(index,label)
    vector.InsertNextTuple3(91.,92.,93.);vector.InsertNextTuple3(94.,95.,96.);attrs.AddArray(vector)
    if role=='response':selection.update(value_array=vector.GetName(),value_component=1)
    else:selection['axis'].update(name=vector.GetName(),component=1)
    with pytest.raises(ValueError,match='자동 생성 열'):
        origin._show_selected(n.ws,n.objects['Aright'],n.objects['Aright']['history'][0],n.bundles['VAright'],
            selection,{'block':[1,1],'row':1,'values':{'Time':1.,'F':[4.,8.,12.]}})
    assert not n.selected and attrs.GetArray(vector.GetName()) is vector and vector.GetComponent(1,1)==95.


@pytest.mark.parametrize('point,unselected',[(False,'vtkOriginalIndices'),(True,'Points_X')])
def test_chart62_unselected_metadata_collision_keeps_normal_response_axis(native,chart_scene,point,unselected):
    n=native;source,leaves=nested_source(n,point);scene=chart_scene(source)
    attrs=leaves[0].GetPointData() if point else leaves[0].GetRowData()
    array=vtk.vtkDoubleArray();array.SetName(unselected)
    for value in (91.,92.):array.InsertNextValue(value)
    attrs.AddArray(array)
    selection={'value_array':'F','value_component':1,'axis':{'kind':'array','name':'Time','component':None}}
    origin._show_selected(n.ws,n.objects['Aright'],n.objects['Aright']['history'][0],n.bundles['VAright'],
        selection,{'block':[1,1],'row':1,'values':{'Time':1.,'F':[4.,8.,12.]}})
    assert scene.values()['SeriesVisibility']==['F_Y'] and scene.values()['XArrayName']=='Time'
    assert n.selected[-1]==('composite',{'IDs':[4,0,1],'FieldType':'POINT' if point else 'ROW'})
    assert attrs.GetArray(unselected) is array and array.GetValue(1)==92.
