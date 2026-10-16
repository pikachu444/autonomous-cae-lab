from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from pretension_fixture import model
from apps.desktop_pre import pretension_native as pt


def test_native_metadata_same_request_cas_invalid_draft_and_verified_cold_proof(monkeypatch):
    m=model();draft=deepcopy(m['pretension_sections'][0]['draft']);data={};transactions=[]
    analysis=NS(Name='Analysis',TypeId='Fem::FemAnalysis',Group=[])
    owner=NS(assert_thread=lambda:None,_object=lambda key:analysis,write_metadata=lambda value:data.update(deepcopy(value)))
    fem=NS(owner=owner,_object=lambda target:analysis,_metadata=lambda:deepcopy(data),_assert_idle=lambda:None,
           _transaction=lambda label,fn:(transactions.append(label),fn()))
    binding={'source':{'exact':'source'},'mesh':{'ordered':'mesh'}}
    monkeypatch.setattr(pt,'_mesh',lambda *a:(None,deepcopy(binding),m,'Bolt'))
    args={'id':'Pbolt','request_id':'request001','expected_revision':None,'draft':draft,'mesh_binding':binding}
    first=pt.dispatch(fem,'pre.fem.pretension_set',deepcopy(args),{'object_id':'Analysis'})
    assert not first['state']['sections'][0]['errors']
    assert pt.dispatch(fem,'pre.fem.pretension_set',deepcopy(args),{'object_id':'Analysis'})['replayed']
    assert len(transactions)==1
    changed=deepcopy(args);changed['request_id']='request002';changed['draft']['control']['value']='1e';changed['expected_revision']=first['revision']
    bad=pt.dispatch(fem,'pre.fem.pretension_set',changed,{'object_id':'Analysis'})
    assert bad['state']['sections'][0]['errors'] and data['pretension_sections'][0]['draft']['control']['value']=='1e'
    old=deepcopy(data)
    with pytest.raises(ValueError,match='변경'):pt.dispatch(fem,'pre.fem.pretension_set',{**changed,'request_id':'request003','expected_revision':first['revision']},{'object_id':'Analysis'})
    assert data==old


def test_condition_cold_fallback_requires_exact_original_v3_source_and_proof(monkeypatch):
    from apps.desktop_pre.fem_edit import FEMEditor
    source=NS();mesh=NS(FemMesh=object(),Shape=source)
    original={'object_id':'Bolt','type':'PartDesign::Feature','brep_sha256':'old-sha',
              'global_placement':[0,0,0,0,0,0,1],'subelements':[{'name':'Vertex3','brep_sha256':'c'*64}]}
    current=deepcopy(original);current['brep_sha256']='serialized-differently'
    proof={'schema_version':3,'source':{'name':'Bolt','type':original['type'],'brep_sha256':'old-sha','brep':'retained',
           'global_placement':original['global_placement']},'source_equivalence':{
           'subelement_correspondence':'SAME_FACE_EDGE_VERTEX_ORDER_AND_ORIENTATION'}}
    fem=FEMEditor.__new__(FEMEditor);fem.owner=NS(_object=lambda key:source,doc=NS(Objects=[mesh]),
        mesh_bindings=NS(validate=lambda obj:deepcopy(proof)))
    import hashlib,sys
    class OriginalShape:
        def importBrepFromString(self, text):
            assert text == 'retained'
        Vertexes=[NS(exportBrepToString=lambda value=value:value) for value in ('first','second','third')]
    monkeypatch.setitem(sys.modules,'Part',NS(Shape=OriginalShape))
    original['subelements'][0]['brep_sha256']=hashlib.sha256(b'third').hexdigest()
    current['subelements']=deepcopy(original['subelements'])
    before=deepcopy(original);assert fem._same_condition_target(original,current);assert original==before
    for change in (lambda p:p.update(schema_version=2),lambda p:p['source'].update(brep_sha256='other-source'),
                   lambda p:p.pop('source_equivalence')):
        saved=deepcopy(proof);change(proof);assert not fem._same_condition_target(original,current);proof.clear();proof.update(saved)
    changed=deepcopy(current);changed['subelements'][0]['name']='Vertex4'
    assert not fem._same_condition_target(original,changed)
    changed=deepcopy(current);changed['global_placement'][0]=1
    assert not fem._same_condition_target(original,changed)


@pytest.mark.parametrize('family,count,index',[('Face',2,2),('Edge',2,1),('Solid',1,1),('Vertex',3,3)])
def test_original_child_digest_is_bound_to_exact_retained_index(monkeypatch,family,count,index):
    from apps.desktop_pre.fem_edit import FEMEditor
    import hashlib,sys
    fields={'Face':'Faces','Edge':'Edges','Solid':'Solids','Vertex':'Vertexes'}
    values=[family+'-'+str(i+1) for i in range(count)]
    class OriginalShape:
        def importBrepFromString(self,text):assert text=='authenticated-original-full-brep'
    setattr(OriginalShape,fields[family],[NS(exportBrepToString=lambda value=value:value) for value in values])
    monkeypatch.setitem(sys.modules,'Part',NS(Shape=OriginalShape))
    source=NS();mesh=NS(FemMesh=object(),Shape=source)
    saved={'object_id':'Bolt','type':'PartDesign::Feature','brep_sha256':'a'*64,
        'global_placement':[0,0,0,0,0,0,1],'subelements':[{'name':family+str(index),
        'brep_sha256':hashlib.sha256(values[index-1].encode()).hexdigest()}]}
    current=deepcopy(saved);current['brep_sha256']='b'*64
    proof={'schema_version':3,'source':{'name':'Bolt','type':saved['type'],'brep_sha256':saved['brep_sha256'],
        'brep':'authenticated-original-full-brep','global_placement':saved['global_placement']},
        'source_equivalence':{'subelement_correspondence':'SAME_FACE_EDGE_VERTEX_ORDER_AND_ORIENTATION'}}
    fem=FEMEditor.__new__(FEMEditor);fem.owner=NS(_object=lambda key:source,doc=NS(Objects=[mesh]),
        mesh_bindings=NS(validate=lambda obj:deepcopy(proof)))
    before=deepcopy(saved);assert fem._same_condition_target(saved,current)
    damaged=deepcopy(saved);damaged['subelements'][0]['brep_sha256']='d'*64
    assert not fem._same_condition_target(damaged,current)
    # _region constructs current names from the saved record: retaining the
    # old child digest must not authorize a different original index.
    moved=deepcopy(saved);moved['subelements'][0]['name']=family+str(1 if index!=1 else count+1)
    moved_current=deepcopy(current);moved_current['subelements'][0]['name']=moved['subelements'][0]['name']
    assert not fem._same_condition_target(moved,moved_current)
    assert saved==before
