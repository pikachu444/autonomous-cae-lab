"""Pure ownership/target/transaction doubles; not a FreeCAD execution receipt."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from test_dynamic_support import base_model
from apps.desktop_pre.dynamic_edit import DynamicEditor
from apps.desktop_pre import dynamic_native
from apps.desktop_pre.dynamic_buffer import Buffer
from caelab.dynamic_model import NAMESPACE


class Quantity:
    def __init__(self,value):self.Value=float(str(value).split()[0])
    def getValueAs(self,unit):assert unit=='kg/m^3';return self


@pytest.fixture
def editor(monkeypatch):
    class Owner:
        def __init__(self):
            self.data={};self.transactions=[];self.material=NS(Material={'Density':'7800 kg/m^3'})
            self.App=NS(Units=NS(Quantity=Quantity));self.doc=NS(recompute=lambda:None)
            self.fem=NS(_metadata=lambda:self.data);self.binding={'complete_shape':'source-proof','mesh_sha256':'original'}
            self.changed_coordinate=False
        def assert_thread(self):pass
        def read_metadata(self):return deepcopy(self.data)
        def write_metadata(self,data):self.data=deepcopy(data)
        def _object(self,key):
            if key=='Material':return self.material
            raise ValueError('deleted or foreign object')
        def _transaction(self,title,action):
            old=deepcopy((self.data,self.material.Material))
            try:action()
            except Exception:self.data,self.material.Material=old;raise
            self.transactions.append(title)
    owner=Owner()
    def base(owner,analysis_id,solver_id):
        assert analysis_id=='Analysis' and solver_id=='Solver'
        m=base_model();m['materials'][0]['native_values']=deepcopy(owner.material.Material)
        if owner.changed_coordinate:m['nodes'][0]['position_mm'][0]+=1
        return m,[{'body_id':'Solid','mesh_id':'Mesh','target':{'object_id':'Solid','shape':'EXACT'},'binding':deepcopy(owner.binding)}]
    monkeypatch.setattr(dynamic_native,'base',base)
    e=DynamicEditor(owner);monkeypatch.setattr(e,'discover',lambda:[{'id':'Analysis','label':'해석','solvers':[{'id':'Solver','label':'CalculiX'}]}])
    e.create('Analysis','Solver');return e


def captured(editor):
    return editor.dispatch('pre.dynamic.capture',{'analysis_id':'Analysis','body_id':'Solid','native_node_ids':[51],'faces':None},{})['target']


def applied(editor):
    d=editor._get('Analysis')['draft'];d['initial_conditions']=[{'id':'V1','label':'자유 끝 속도','kind':'V','component':1,'value':'1','target':captured(editor)}]
    info=editor.apply('Analysis',d);assert info['can_freeze'],info;return d


def test_initial_target_source_binding_and_read_only_inspection(editor):
    d=applied(editor);before=deepcopy(editor.owner.data);count=len(editor.owner.transactions)
    assert editor.inspect('Analysis')['can_freeze']
    assert editor.owner.data==before and len(editor.owner.transactions)==count
    editor.owner.binding['mesh_sha256']='replaced'
    info=editor.inspect('Analysis');assert not info['can_freeze']
    assert info['errors'][0]['path']=='initial_conditions.0.target'
    assert editor.owner.data==before
    with pytest.raises(ValueError):editor.apply('Analysis',d)


def test_invalid_numeric_draft_survives_new_editor_and_blocks_execution(editor,monkeypatch):
    d=applied(editor);d['densities'][0]['kg_m3']='1e'
    info=editor.save_draft('Analysis',d);assert not info['can_freeze']
    fresh=DynamicEditor(editor.owner);monkeypatch.setattr(fresh,'discover',editor.discover)
    assert fresh.inspect('Analysis')['record']['draft']['densities'][0]['kg_m3']=='1e'
    before=deepcopy(editor.owner.data);material=deepcopy(editor.owner.material.Material)
    with pytest.raises(ValueError):fresh.apply('Analysis',d)
    assert editor.owner.data==before and editor.owner.material.Material==material
    d['densities'][0]['kg_m3']='7800';assert fresh.apply('Analysis',d)['can_freeze']


def test_no_target_substitution_or_shared_record_mutation(editor):
    d=applied(editor);editor.owner.changed_coordinate=True
    info=editor.inspect('Analysis');assert not info['can_freeze']
    assert info['errors'][0]['path']=='native'
    info['record']['draft']['initial_conditions'].clear()
    assert editor._get('Analysis')['draft']==d
    with pytest.raises(ValueError):editor.dispatch('pre.dynamic.capture',{'analysis_id':'Analysis','body_id':'Other','native_node_ids':[51],'faces':None},{})


def test_buffer_late_save_selection_close_and_payload_snapshot():
    b=Buffer();b.select({'number':'1'});b.value['number']='1e'
    ticket=b.begin();assert ticket[1]['number']=='1e'
    b.value['number']='2';assert not b.complete(ticket,{'number':'1e'})
    assert b.value['number']=='2' and b.pending()
    ticket=b.begin();b.select({'other':'selected'})
    assert not b.complete(ticket,{'number':'stale'}) and b.value=={'other':'selected'}
    ticket=b.begin();b.close()
    assert not b.complete(ticket,{'late':'destroyed'})
    with pytest.raises(ValueError):b.begin()


def test_buffer_saved_invalid_draft_is_not_auto_applied():
    b=Buffer();b.select({'number':'1'});b.value['number']='1e';ticket=b.begin()
    assert b.complete(ticket,{'number':'1e'}) and not b.pending()
    # Buffer tracks edit persistence only, never assigns solver validity.
    assert not hasattr(b,'can_freeze')
