"""Injected native-owner doubles: metadata/transaction/reference regressions."""
from copy import deepcopy
from types import SimpleNamespace as NS
import json
import pytest
from apps.desktop_pre.shell_edit import ShellEditor,SETTINGS
from caelab.shell_model import ShellError,digest
if __package__:
    from .test_shell_support import model
else:
    from test_shell_support import model

class OwnerDouble:
    def __init__(self,data):
        self.data=deepcopy(data);self.transactions=[]
        self.doc=NS(Objects=[],getObject=lambda name:None)
    def assert_thread(self):pass
    def read_metadata(self):return deepcopy(self.data)
    def write_metadata(self,value):self.data=deepcopy(value)
    def _transaction(self,title,fn):
        before=deepcopy(self.data)
        try:fn()
        except Exception:self.data=before;raise
        self.transactions.append(title)

class EditorDouble(ShellEditor):
    """Only native accessors are doubles; draft/effective/dispatch logic is real."""
    def __init__(self,owner,data):
        super().__init__(owner);self.current=deepcopy(data['applied']['native']);self.source=model()
    def _binding(self,draft):
        if getattr(self,'lost',False):raise ShellError([{'path':'elements','message':'TEST_DOUBLE reference changed'}])
    def _native_state(self,draft):return deepcopy(self.current)
    def _mesh(self,draft):
        return None,{int(n):p for n,p in self.source['source_nodes'].items()},{int(e):c for e,c in self.source['source_elements'].items()}
    def _fixed(self,draft,mesh):return draft['fixed_nodes']

@pytest.fixture
def editor():
    data=model();data['applied']['native']={'solver':SETTINGS,'pressure_amplitude':False,'material_names':['first']}
    owner=OwnerDouble({'shells':{'ShellAnalysis':{'draft':data['draft'],'applied':data['applied']}}})
    return EditorDouble(owner,data)

@pytest.mark.parametrize('raw',['0','1e'])
def test_invalid_saved_draft_reopens_without_replacing_prior_applied(editor,raw):
    previous=deepcopy(editor.owner.data['shells']['ShellAnalysis']['applied'])
    row=editor.save_draft('ShellAnalysis',{'thickness_mm':raw})['records'][0]
    assert not row['ready'] and any(r['path']=='thickness_mm' for r in row['errors'])
    reopened=EditorDouble(OwnerDouble(json.loads(json.dumps(editor.owner.data))),{'applied':previous})
    assert reopened._record('ShellAnalysis')['draft']['thickness_mm']==raw
    assert reopened._record('ShellAnalysis')['applied']==previous
    with pytest.raises(ShellError):reopened.effective('ShellAnalysis')

def test_active_native_material_change_is_blocked(editor):
    editor.effective('ShellAnalysis')
    editor.current['material_names'].append('unexpected new active material')
    with pytest.raises(ShellError):editor.effective('ShellAnalysis')


def test_native_members_survive_json_metadata_save_and_fresh_editor_reopen(editor):
    """Native member signatures must have the same shape as JSON-saved metadata."""
    def quantity(value):return NS(getValueAs=lambda unit:NS(Value=value))
    objects={
        'solver_id':NS(Name='Solver',**SETTINGS),
        'material_id':NS(Name='Material',Category='Solid',Material={'Name':'Example','YoungsModulus':'210000 MPa'},References=[]),
        'geometry_id':NS(Name='Section',Thickness=quantity(2.),Offset=0.,References=[]),
        'pressure_id':NS(Name='Pressure',Pressure=quantity(.001),Reversed=False,EnableAmplitude=False,References=[])}
    signature_owner=NS(_members=lambda draft,complete:(None,{'native_type':[objects['solver_id'],objects['material_id']]}),
                       _object=lambda key:objects[key],_stamp=lambda draft:{'mesh':'retained binding'})
    signature=ShellEditor._native_state(signature_owner,{key:key for key in objects})
    assert signature['members']==[['native_type','Material'],['native_type','Solver']]
    assert json.loads(json.dumps(signature))==signature
    editor.current=deepcopy(signature)
    editor.owner.data['shells']['ShellAnalysis']['applied']['native']=deepcopy(signature)
    saved=json.dumps(editor.owner.read_metadata())
    reopened=EditorDouble(OwnerDouble(json.loads(saved)),{'applied':{'native':signature}})
    record,_,_=reopened.effective('ShellAnalysis')
    assert record['applied']['native']==signature
    reopened.current['members'].append(['native_type','UnexpectedMaterial'])
    with pytest.raises(ShellError):reopened.effective('ShellAnalysis')

def test_reference_loss_preserves_draft_and_blocks(editor):
    editor.lost=True;before=deepcopy(editor.owner.data)
    with pytest.raises(ShellError):editor.effective('ShellAnalysis')
    assert editor.owner.data==before
    editor.save_draft('ShellAnalysis',{'thickness_mm':'1e'})
    assert editor._record('ShellAnalysis')['draft']['thickness_mm']=='1e'

def test_raw_orientation_edit_cannot_bypass_coupled_reverse(editor):
    with pytest.raises(ValueError):editor.save_draft('ShellAnalysis',{'orientation':'reversed'})
    editor.reverse('ShellAnalysis',True)
    row=editor._record('ShellAnalysis')
    assert row['draft']['orientation']=='reversed' and float(row['draft']['pressure_MPa'])<0
    assert row['applied']['draft']['orientation']=='native'

def test_unknown_command_field_rejected_before_any_edit(editor):
    before=deepcopy(editor.owner.data)
    with pytest.raises(ValueError):editor.dispatch('pre.shell.save_draft',{'analysis_id':'ShellAnalysis','fields':{},'execute':True},{})
    assert editor.owner.data==before

def test_rebind_cancel_never_mutates_committed_draft(editor):
    before=deepcopy(editor.owner.data);editor._pending['selection']=('ShellAnalysis',{'elements':[99]})
    editor.clear_preview=lambda:None
    assert editor.cancel_rebind()=={'cancelled':True}
    assert not editor._pending and editor.owner.data==before


def test_other_document_same_named_face_cannot_rebind(editor):
    selection=NS(Object=NS(Name='Plate',Document=NS()),SubElementNames=['Face1'])
    editor.owner.Gui=NS(Selection=NS(getSelectionEx=lambda:[selection]))
    before=deepcopy(editor.owner.data)
    with pytest.raises(ValueError,match='편집 중인 문서'):
        editor.preview_rebind('ShellAnalysis')
    assert editor.owner.data==before and not editor._pending


def test_preview_requires_its_own_active_document_before_scene_access():
    from apps.desktop_pre.shell_preview import show
    owner=NS(App=NS(ActiveDocument=NS()),doc=NS())
    with pytest.raises(ValueError,match='활성화'):
        show(owner,{})
