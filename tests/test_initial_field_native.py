from copy import deepcopy
from types import SimpleNamespace as NS
import json,sys
import pytest
from initial_field_fixture import model,draft,snapshot
from apps.desktop_pre import initial_field_native as native
from caelab.adapters.initial_fields import InitialFieldsCalculixAdapter,InitialFieldsCodeAsterAdapter,prepare_aster,parse_aster


class Quantity:
    def __init__(self,value):self.Value=float(str(value).split()[0])
    def getValueAs(self,unit):assert unit=='K';return self
class Temperature:
    TypeId='Fem::ConstraintInitialTemperature';Name='InitialTemperature';Label='기존 온도';References=[]
    def __init__(self):self.initialTemperature=293.15;self.FinalTemperature=393.15;self.EnableFinalTemperature=True;self.EnableAmplitude=False
    def __setattr__(self,k,v):object.__setattr__(self,k,Quantity(v) if k in ('initialTemperature','FinalTemperature') else v)


@pytest.fixture
def owner_case(monkeypatch):
    m=model();data={};doc=NS(Name='Source');source=NS(Name='Solid');mesh=NS(Name='Mesh',TypeId='Fem::FemMeshObjectPython',Label='원 메시',Shape=source,FemMesh=NS(Nodes={r['node_id']:r['position_mm'] for r in m['nodes']},Volumes=[1]))
    analysis=NS(Name='Analysis',TypeId='Fem::FemAnalysis',Document=doc,Group=[mesh]);objects={'Analysis':analysis,'Mesh':mesh,'Solid':source}
    analysis.addObject=lambda o:analysis.Group.append(o);analysis.removeObject=lambda o:analysis.Group.remove(o)
    proof={'schema_version':3,'source':'retained-source','mesh':'ordered-mesh'}
    owner=NS(doc=doc,_object=lambda key:objects[key],assert_thread=lambda:None,read_metadata=lambda:deepcopy(data),
        write_metadata=lambda v:(data.clear(),data.update(deepcopy(v))),mesh_bindings=NS(validate=lambda o:deepcopy(proof)))
    fem=NS(owner=owner,_metadata=lambda:deepcopy(data),_object=lambda t:analysis,_assert_idle=lambda:None,
        _transaction=lambda label,fn:fn());owner.fem=fem
    selection={'mesh_id':'Mesh','body_id':'Solid','node_ids':[r['node_id'] for r in m['nodes']],'element_ids':[1],
        'mesh_binding':proof,'targets':[],'selection':'explicit_whole_body'}
    monkeypatch.setattr(native,'base',lambda *a:(deepcopy(m),[{'body_id':'Solid','binding':deepcopy(proof)}]))
    def create(doc,name):obj=Temperature();objects[obj.Name]=obj;return obj
    monkeypatch.setitem(sys.modules,'ObjectsFem',NS(makeConstraintInitialTemperature=create))
    return NS(model=m,data=data,owner=owner,fem=fem,analysis=analysis,selection=selection)


def test_raw_draft_save_reload_cancel_and_valid_apply_do_not_invent_state(owner_case):
    c=owner_case;d=draft();d['temperature']['expansion_per_K']='1e'
    result=native.dispatch(c.fem,'pre.initial.save_draft',{'draft':d,'region':c.selection,'expected_revision':None},{'object_id':'Analysis'})
    assert result['errors'] and result['record']['applied'] is None
    retained=json.loads(json.dumps(c.data));c.data.clear();c.data.update(retained)
    assert native.read(c.fem,c.analysis)['record']['draft']['temperature']['expansion_per_K']=='1e'
    with pytest.raises(ValueError,match='미적용'):native.freeze(c.fem,c.analysis,{},deepcopy(c.model))
    result=native.dispatch(c.fem,'pre.initial.discard',{'expected_revision':result['record']['revision']},{'object_id':'Analysis'})
    assert result['record'] is None
    result=native.dispatch(c.fem,'pre.initial.save_draft',{'draft':draft(),'region':c.selection,'expected_revision':None},{'object_id':'Analysis'})
    applied=native.dispatch(c.fem,'pre.initial.apply',{'expected_revision':result['record']['revision']},{'object_id':'Analysis'})
    assert not applied['errors'] and applied['record']['applied']['temperature_object']=='InitialTemperature'
    assert native.allowed_members(c.fem,c.analysis)==[c.analysis.Group[-1]]
    c.analysis.Group[-1].FinalTemperature=400.
    with pytest.raises(ValueError,match='원 FreeCAD'):native.allowed_members(c.fem,c.analysis)
    c.analysis.Group[-1].Suppressed=True
    with pytest.raises(ValueError,match='비활성화'):native.allowed_members(c.fem,c.analysis)


def test_changed_binding_and_stale_revision_preserve_original_inputs(owner_case):
    c=owner_case;original=deepcopy(c.model);sel=deepcopy(c.selection);sel['mesh_binding']['source']='other'
    result=native.dispatch(c.fem,'pre.initial.save_draft',{'draft':draft(),'region':sel,'expected_revision':None},{'object_id':'Analysis'})
    assert result['errors'];before=deepcopy(c.data)
    with pytest.raises(ValueError,match='다른 곳'):native.dispatch(c.fem,'pre.initial.discard',{'expected_revision':'old'},{'object_id':'Analysis'})
    assert c.data==before and c.model==original


def test_user_sparse_native_mesh_ids_map_once_without_case_names(owner_case,monkeypatch):
    c=owner_case;m=deepcopy(c.model)
    m['body_maps']['Solid']={'nodes':{n['node_id']+500:n['node_id'] for n in m['nodes']},'elements':{70:1}}
    for n in m['nodes']:n['native_node_id']=n['node_id']+500
    m['elements'][0]['native_element_id']=70
    m['elements'][0]['native_node_ids']=[n+500 for n in m['elements'][0]['native_node_ids']]
    mesh=c.analysis.Group[0]
    mesh.FemMesh.Nodes={n['native_node_id']:n['position_mm'] for n in m['nodes']};mesh.FemMesh.Volumes=[70]
    monkeypatch.setattr(native,'base',lambda *a:(deepcopy(m),[]))
    d=draft('stress');d['node_ids']=[n+500 for n in d['node_ids']];d['element_ids']=[70]
    d['stress']['ip_rows']=[{'element_id':70,'point':p,'values':[100.,0.,0.,0.,0.,0.]} for p in range(1,5)]
    selection=deepcopy(c.selection);selection['node_ids']=d['node_ids'];selection['element_ids']=[70]
    saved=native.dispatch(c.fem,'pre.initial.save_draft',{'draft':d,'region':selection,'expected_revision':None},{'object_id':'Analysis'})
    result=native.dispatch(c.fem,'pre.initial.apply',{'expected_revision':saved['record']['revision']},{'object_id':'Analysis'})
    applied=result['record']['applied']
    assert applied['native_draft']['element_ids']==[70] and applied['draft']['element_ids']==[1]
    assert [r['element_id'] for r in applied['definition']['stress_rows']]==[1]*4
    assert applied['native_draft']['node_ids'][0]==501 and not result['errors']


def test_aster_input_keeps_same_mesh_and_actual_etat_init_worker_before_runtime(tmp_path):
    source=snapshot(tmp_path/'source','compatible');out=tmp_path/'prepared';out.mkdir()
    before={p.name:p.read_bytes() for p in source.parent.iterdir()}
    manifest,mesh,pins,gates,workers,budgets=prepare_aster(source,out)
    conf=json.loads((out/'solver/input.json').read_text(encoding='utf-8'))
    assert conf['initial_field_definition']['compatible']['stress_MPa'][0]==pytest.approx(210.)
    assert mesh['elements'][0]['node_ids']==model()['elements'][0]['node_ids']
    text=(out/'initial_field_aster_worker.py').read_text(encoding='utf-8');assert 'ETAT_INIT=_F(DEPL=u0,SIGM=sig0)' in text
    assert 'ETAT_INIT=_F(DEPL=u0,SIGM=sig0,INST' not in text and 'CHAM_GD=field' in text
    assert before=={p.name:p.read_bytes() for p in source.parent.iterdir()}


@pytest.mark.parametrize('adapter',[InitialFieldsCalculixAdapter(),InitialFieldsCodeAsterAdapter()])
def test_public_validator_never_reads_arbitrary_snapshot_paths(adapter,tmp_path):
    with pytest.raises(ValueError):adapter.validate_settings({'data_id':'Dexample','snapshot_path':str(tmp_path/'secret')})
    assert adapter.validate_settings({'data_id':'Dexample'})=={'data_id':'Dexample'}
