"""Real beam handler/metadata/transaction code with a labelled native-document double."""
from copy import deepcopy
import json
from types import SimpleNamespace as NS
import pytest
from apps.desktop_pre import beam_edit,beam_native,metadata
from test_beam_reopen_support import transaction
from caelab.beam_model import NAMESPACE,BeamInputError,native_axis_formula,frame
from caelab.storage import canonical_hash
from test_beam_support import model,refresh


class Doc:
    """Only native metadata/Undo storage protocol; never geometry or FE emulation."""
    def __init__(self):self.objects={};self.old=[];self.future=[];self.pending=None
    def getObject(self,name):return self.objects.get(name)
    def addObject(self,kind,name):
        obj=NS(PropertiesList=[],Definition='',Label=name)
        def add(kind,prop,*_):obj.PropertiesList.append(prop)
        obj.addProperty=add;obj.setEditorMode=lambda *_:None;self.objects[name]=obj;return obj
    def openTransaction(self,title):self.pending=deepcopy(metadata.read(self))
    def recompute(self):pass
    def commitTransaction(self):self.old.append(self.pending);self.pending=None;self.future=[]
    def abortTransaction(self):metadata.write(self,self.pending);self.pending=None
    def undo(self):self.future.append(metadata.read(self));metadata.write(self,self.old.pop())
    def redo(self):self.old.append(metadata.read(self));metadata.write(self,self.future.pop())


@pytest.fixture
def editor(monkeypatch):
    doc=Doc();native={'width':10.,'property':'initial','values':'initial','binding':'initial'}
    owner=NS(doc=doc,document_id='Pbeam',assert_thread=lambda:None,before_design_action=lambda _:None)
    owner.read_metadata=lambda:metadata.read(doc);owner.write_metadata=lambda data:metadata.write(doc,data)
    owner._transaction=lambda title,change:transaction(owner,title,change)
    metadata.write(doc,{'shell_models':{'keep':'shell'},'motion_editors':{'keep':'motion'},'links':['old-job'],
        NAMESPACE:{'Analysis':{'draft':model()['draft'],'end_object_ids':['End1','End2']}}})
    def geometry(owner,draft):
        value=model(draft['section']['rotation_deg']);value['draft']=deepcopy(draft)
        refresh(value);return value,{'id':native['binding'],
            'mesh_sha256':canonical_hash({'nodes':value['nodes'],'elements':value['elements']})}
    monkeypatch.setattr(beam_native,'geometry',geometry)
    monkeypatch.setattr(beam_edit.BeamEditor,'discover',lambda _:[{'id':'Analysis','label':'beam','meshes':[]}])
    monkeypatch.setattr(beam_native,'collect',lambda *_:(model(),None))
    monkeypatch.setattr(beam_native,'property_stamp',lambda *_a,values_only=False:native['values' if values_only else 'property'])
    def project(owner,record):native['width']=float(record['draft']['section']['width_mm'])
    monkeypatch.setattr(beam_edit,'project_properties',project)
    handler=beam_edit.BeamEditor(owner);handler.apply('Analysis',model()['draft'])
    return handler,native


@pytest.mark.parametrize('text',['0','1e'])
def test_invalid_save_new_owner_reopen_and_explicit_correction(editor,text):
    handler,native=editor;d=deepcopy(handler._get('Analysis')['draft']);d['section']['width_mm']=text
    result=handler.save_draft('Analysis',d)
    assert not result['can_freeze'] and native['width']==10
    new=beam_edit.BeamEditor(handler.owner)
    assert new.inspect('Analysis')['record']['draft']['section']['width_mm']==text
    assert new.owner.read_metadata()['shell_models']=={'keep':'shell'} and new.owner.read_metadata()['links']==['old-job']
    with pytest.raises(BeamInputError):new.apply('Analysis',d)
    d['section']['width_mm']='12';new.apply('Analysis',d);assert native['width']==12


def test_native_undo_redo_restore_raw_draft_with_unrelated_namespace(editor):
    handler,_=editor;d=deepcopy(handler._get('Analysis')['draft']);d['section']['width_mm']='1e'
    handler.save_draft('Analysis',d);handler.owner.doc.undo()
    assert handler._get('Analysis')['draft']['section']['width_mm']=='10'
    handler.owner.doc.redo();assert handler._get('Analysis')['draft']['section']['width_mm']=='1e'
    assert handler.owner.read_metadata()['motion_editors']=={'keep':'motion'}


def test_changed_binding_requires_explicit_rebind(editor):
    handler,native=editor;native['binding']='new-shape';d=deepcopy(handler._get('Analysis')['draft'])
    with pytest.raises(BeamInputError,match='참조'):handler.apply('Analysis',d)
    handler.apply('Analysis',d,rebind=True)
    assert handler._get('Analysis')['binding']['id']=='new-shape'


def test_rebind_repairs_dangling_reference_not_unseen_native_value_edits(editor):
    handler,native=editor;d=deepcopy(handler._get('Analysis')['draft'])
    native['property']='reference-deleted'
    with pytest.raises(BeamInputError):handler.apply('Analysis',d)
    handler.apply('Analysis',d,rebind=True)
    native['values']='material-changed';native['property']='material-changed'
    with pytest.raises(BeamInputError,match='속성'):handler.apply('Analysis',d,rebind=True)


def test_invalid_command_cannot_change_analysis_identity_or_erase_other_owner(editor):
    handler,_=editor;d=deepcopy(handler._get('Analysis')['draft']);before=handler.owner.read_metadata()
    d['analysis_id']='Other'
    with pytest.raises(ValueError):handler.save_draft('Analysis',d)
    assert before==handler.owner.read_metadata()
    with pytest.raises(ValueError):handler.dispatch('pre.beam.inspect',{'analysis_id':'Analysis'},{'object_id':'Other'})


def test_native_property_transaction_failure_keeps_prior_draft(editor,monkeypatch):
    handler,_=editor;before=handler.owner.read_metadata();d=deepcopy(handler._get('Analysis')['draft']);d['section']['width_mm']='12'
    def fail(owner,record):
        owner.write_metadata({'bad':'interrupted'});raise RuntimeError('synthetic native setter error')
    monkeypatch.setattr(beam_edit,'project_properties',fail)
    with pytest.raises(RuntimeError):handler.apply('Analysis',d)
    assert handler.owner.read_metadata()==before
