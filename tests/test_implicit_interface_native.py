"""Owner/CAS/source boundaries with explicit native doubles; no FreeCAD run."""
from copy import deepcopy
from types import SimpleNamespace as NS
import json
import sys
import pytest

from test_implicit_interface import input_pair,loaded_input
from apps.desktop_pre import implicit_interface_native as native


@pytest.fixture
def owner_case(loaded_input,monkeypatch):
    model = loaded_input
    data = {'regions':[]}
    bodies,objects,proofs = {},{},{}
    for index,body_id in enumerate(model['body_maps'],1):
        body = NS(Name=body_id,Label='사용자 고체 '+str(index),TypeId='Part::Feature')
        mesh = NS(Name='UserMesh'+str(index),Label='사용자 메시 '+str(index),TypeId='Fem::FemMeshObjectPython',
                  Shape=body,FemMesh=NS(Nodes={n:None for n in range(1,9)}))
        binding = dict(schema_version=3,source=dict(name=body_id,brep='retained-original-'+body_id),mesh='native-mesh-'+body_id)
        proofs[mesh.Name] = binding
        face = 'Face2' if index == 1 else 'Face1'
        target = dict(object_id=body_id,subelements=[dict(name=face,brep_sha256='a'*64)])
        data['regions'].append(dict(id='UserRegion'+str(index),label='선택한 접합면 '+str(index),target=target))
        bodies[body_id] = dict(object=body,mesh=mesh,binding=binding,getter=NS(body=body),target=target)
        objects[body_id],objects[mesh.Name] = body,mesh
    analysis = NS(Name='UserAnalysis73',Label='접합부 계산',TypeId='Fem::FemAnalysis',
                  Group=[r['mesh'] for r in bodies.values()])
    objects[analysis.Name] = analysis
    owner = NS(assert_thread=lambda:None,_object=lambda key:objects[key],
               write_metadata=lambda value:(data.clear(),data.update(deepcopy(value))),
               mesh_bindings=NS(validate=lambda mesh:deepcopy(proofs[mesh.Name])))
    def named_region(identifier):
        row, = [r for r in data['regions'] if r['id'] == identifier]
        return deepcopy(row),objects[row['target']['object_id']],[s['name'] for s in row['target']['subelements']]
    fem = NS(owner=owner,_metadata=lambda:deepcopy(data),_region=named_region,
             _object=lambda target:objects[target['object_id']],_assert_idle=lambda:None,
             _transaction=lambda label,fn:fn())
    mesh_tools = NS(get_femnodes_by_references=lambda mesh,refs:[1,2,3,4] if refs[0][0].Name.startswith('Lower') else [5,6,7,8],
        get_ccx_elements=lambda getter,ref:(None,[(91,2 if ref[0].Name.startswith('Lower') else 1)],True))
    monkeypatch.setitem(sys.modules,'femmesh',NS(meshtools=mesh_tools))
    identity = lambda:[dict(body_id=body,mesh_id=row['mesh'].Name,binding=deepcopy(proofs[row['mesh'].Name]))
                      for body,row in bodies.items()]
    def base(*args):
        captured = deepcopy(model)
        current = {body:{**row,'binding':deepcopy(proofs[row['mesh'].Name])} for body,row in bodies.items()}
        native.freeze(fem,analysis,current,captured,capture_only=True)
        return captured,identity()
    monkeypatch.setattr(native,'base',base)
    draft = dict(interfaces=[deepcopy(model['interfaces'][0])])
    for index,side in enumerate(('a','b'),1):
        draft['interfaces'][0][side] = native.region(fem,analysis,'UserRegion'+str(index))
    return NS(fem=fem,owner=owner,analysis=analysis,data=data,model=model,draft=draft,bodies=bodies,proofs=proofs)


def command(c,operation,args):
    return native.dispatch(c.fem,'pre.interface.'+operation,args,dict(object_id=c.analysis.Name))


def test_raw_invalid_draft_apply_cancel_and_json_reopen_keep_old_accepted_definition(owner_case):
    c = owner_case
    draft = deepcopy(c.draft)
    draft['interfaces'][0]['material']['SIGM_C'] = '1e'
    saved = command(c,'save_draft',dict(draft=draft,expected_revision=None))
    assert saved['errors'] and saved['record']['draft']['interfaces'][0]['material']['SIGM_C'] == '1e'
    assert saved['record']['applied'] is None
    with pytest.raises(ValueError,match='미적용'):
        native.freeze(c.fem,c.analysis,c.bodies,deepcopy(c.model))
    restored = json.loads(json.dumps(c.data))
    c.data.clear();c.data.update(restored)
    assert command(c,'read',{})['record']['draft'] == draft
    saved = command(c,'save_draft',dict(draft=c.draft,expected_revision=saved['record']['revision']))
    applied = command(c,'apply',dict(expected_revision=saved['record']['revision']))
    assert applied['record']['applied']['definition'][0]['material']['SIGM_C'] == 15.
    accepted = deepcopy(applied['record']['applied'])
    saved = command(c,'save_draft',dict(draft=draft,expected_revision=applied['record']['revision']))
    assert saved['record']['applied'] == accepted
    with pytest.raises(ValueError):
        command(c,'apply',dict(expected_revision=saved['record']['revision']))
    assert command(c,'read',{})['record']['draft'] == draft
    cancelled = command(c,'discard',dict(expected_revision=saved['record']['revision']))
    assert cancelled['record']['draft'] == accepted['native_draft']
    captured = deepcopy(c.model)
    original_metadata = deepcopy(c.data)
    native.freeze(c.fem,c.analysis,c.bodies,captured)
    assert captured['interfaces'] == accepted['definition'] and c.data == original_metadata
    stale = deepcopy(c.data)
    with pytest.raises(ValueError,match='다른 곳'):
        command(c,'discard',dict(expected_revision='stale'))
    assert c.data == stale


def test_capture_normalizes_without_applying_and_changed_source_needs_explicit_reselection(owner_case):
    c = owner_case
    saved = command(c,'save_draft',dict(draft=c.draft,expected_revision=None))
    before = deepcopy(c.data)
    captured = deepcopy(c.model)
    native.freeze(c.fem,c.analysis,c.bodies,captured,capture_only=True)
    assert captured['interfaces'][0]['material']['GC'] == .8 and c.data == before
    assert command(c,'read',{})['record']['applied'] is None
    applied = command(c,'apply',dict(expected_revision=saved['record']['revision']))
    # A reload-equivalence receipt adds no new geometry/mesh identity.
    for proof in c.proofs.values():
        proof['source_equivalence'] = dict(observed='exact original geometry proof')
    current = {body:{**row,'binding':deepcopy(c.proofs[row['mesh'].Name])} for body,row in c.bodies.items()}
    native.freeze(c.fem,c.analysis,current,deepcopy(c.model))
    c.proofs['UserMesh1']['mesh'] = 'replaced-native-mesh'
    current = {body:{**row,'binding':deepcopy(c.proofs[row['mesh'].Name])} for body,row in c.bodies.items()}
    with pytest.raises(ValueError,match='메시가 바뀌었습니다'):
        native.freeze(c.fem,c.analysis,current,deepcopy(c.model))
    assert command(c,'read',{})['record']['applied'] == applied['record']['applied']
    fresh = deepcopy(c.draft)
    fresh['interfaces'][0]['a'] = native.region(c.fem,c.analysis,'UserRegion1')
    saved = command(c,'save_draft',dict(draft=fresh,expected_revision=applied['record']['revision']))
    reapplied = command(c,'apply',dict(expected_revision=saved['record']['revision']))
    assert reapplied['record']['applied']['source_identity'] != applied['record']['applied']['source_identity']


def test_explicit_empty_apply_removes_joint_metadata_and_other_backend_cannot_drop_it(owner_case):
    c = owner_case
    saved = command(c,'save_draft',dict(draft=c.draft,expected_revision=None))
    applied = command(c,'apply',dict(expected_revision=saved['record']['revision']))
    other = deepcopy(c.model)
    other['backend'] = 'structure.calculix.contact'
    with pytest.raises(ValueError,match='생략하지 않습니다'):
        native.freeze(c.fem,c.analysis,c.bodies,other)
    saved = command(c,'save_draft',dict(draft={'interfaces':[]},expected_revision=applied['record']['revision']))
    removed = command(c,'apply',dict(expected_revision=saved['record']['revision']))
    assert removed['record'] is None
    original = deepcopy(c.model)
    native.freeze(c.fem,c.analysis,c.bodies,original)
    assert original == c.model
