from pathlib import Path
from copy import deepcopy
import sys
import pytest
from caelab.impact_source import capture, resolve, SourceError
from caelab.impact_model import default_settings, model_from_settings, render
from caelab.impact_assembly import target_key, exact_entity, compile_source
from caelab.impact_input_edits import replace_range, view
from caelab.storage import canonical_hash

ROOT=Path(__file__).resolve().parents[2]/'examples/impact/input_a'

def definition():
    s=default_settings();s['source']=capture(ROOT/'assembly.inp',ROOT);return s

def test_exact_transform_ids_materials_sets_boundaries():
    s=definition();model=model_from_settings(s)
    assert len(model['nodes'])==8 and len(model['elements'])==2
    n=exact_entity(model,'POINTS','BODY-1',10)
    assert model['nodes'][n]==pytest.approx([0,20,0],abs=1e-12)
    assert model['nodes'][exact_entity(model,'POINTS','BODY-1',20)]==pytest.approx([0,30,0],abs=1e-12)
    assert model['nodes'][exact_entity(model,'POINTS','BODY-2',10)]==pytest.approx([0,-40,0],abs=1e-12)
    body1=target_key(model,'nsets','DROP.BODY-1.BODY');body2=target_key(model,'nsets','DROP.BODY-2.BODY')
    assert model['nsets'][body1].isdisjoint(model['nsets'][body2])
    assert model['nsets'][target_key(model,'nsets','DROP.BOTHTIPS')]=={4,8}
    assert model['surfaces'][target_key(model,'surfaces','DROP.UPPER')]==[('2','S2')]
    assert model['elements'][1]['nodes']==[1,2,3,4]
    assert model['lineage']['nodes']['1']['file']=='parts/mesh.inc'
    assert model['lineage']['nodes']['1']['line']==2
    before=canonical_hash(s);out,initial=render(s)
    assert '1,1,1,0' in out and canonical_hash(s)==before

def test_actual_pinned_converter_and_existing_physical_postflight(tmp_path):
    from caelab.execution_control import run_owned_command
    from caelab.adapters.impact import converted_mesh
    from caelab.adapters.impact_admission import normalize_surfaces, global_gravity, validate_physics
    s=definition();m=model_from_settings(s)
    # Body 2 is free. Body 1 retains the explicit source boundary.
    s['motions']=[{'node_set':target_key(m,'nsets','DROP.BODY-2.BODY'),'mode':'velocity','height_mm':None,
                   'velocity_mm_s':[0.,0.,-100.],'omega_rad_s':[0.,0.,2.],
                   'center_mm':[0.,-40.,0.],'translation_mm':[0.,0.,0.]}]
    text,initial=render(s);p=tmp_path/'impact.inp';p.write_text(text)
    from caelab.adapters import inp2rad_worker
    result=run_owned_command([sys.executable,inp2rad_worker.__file__,str(p)],tmp_path,'convert',timeout=30,owned_tree=True)
    assert result.returncode==0
    native=tmp_path/'impact_0000.rad'
    assert converted_mesh(native,m,initial['nodes'])['element_count']==2
    fixed,_=normalize_surfaces(native.read_text(),m);fixed,_=global_gravity(fixed,s['gravity_mm_s2'])
    receipt=validate_physics(fixed,m,initial,s)
    assert receipt['fixed_dof_count']==3 and receipt['velocity_node_count']==4

@pytest.mark.parametrize('old,new',[
    ('0,0,0,0,0,1,90','0,0,0,0,0,0,90'),
    ('*INSTANCE,NAME=Body-2,PART=Body-Part','*INSTANCE,NAME=Body-1,PART=Body-Part'),
    ('*NSET,NSET=Tip','*NSET,NSET=Body'),
    ('*ELSET,ELSET=AllSolids','*ELSET,ELSET=AllSolids,UNSORTED'),
    ('Body-1.40,Body-2.Tip','Body-1.40,Body-3.Tip'),
    ('*BOUNDARY','*CONNECTOR SECTION'),
])
def test_fail_closed_unsupported_and_ambiguous(old,new):
    s=definition();text,spans=resolve(s['source'])
    with pytest.raises(SourceError):compile_source(text.replace(old.upper(),new.upper()).replace(old,new),spans)

def test_repeated_include_occurrence_and_original_range_edit(tmp_path):
    (tmp_path/'mesh.inc').write_bytes((ROOT/'parts/mesh.inc').read_bytes().replace(b'\n',b'\r\n'))
    text=''
    for part in ('A','B'):
        text+=f'*PART,NAME={part}\n*INCLUDE,INPUT=mesh.inc\n*SOLID SECTION,ELSET=SOLID,MATERIAL=STEEL\n*END PART\n'
    text+='*ASSEMBLY,NAME=D\n*INSTANCE,NAME=A1,PART=A\n*END INSTANCE\n*INSTANCE,NAME=B1,PART=B\n20,0,0\n*END INSTANCE\n*END ASSEMBLY\n*MATERIAL,NAME=STEEL\n*DENSITY\n7.8e-9\n*ELASTIC\n210000,.3\n'
    (tmp_path/'root.inp').write_text(text)
    s=default_settings();source=capture(tmp_path/'root.inp',tmp_path);s['source']=source
    m=model_from_settings(s)
    assert m['lineage']['nodes']['1']['occurrence']!=m['lineage']['nodes']['5']['occurrence']
    raw=(tmp_path/'mesh.inc').read_bytes();start=raw.index(b'20,10')+3
    edited=replace_range(source,'mesh.inc',start,start+2,'12',reason='원 공유 part 길이 편집',expected_source_sha256=canonical_hash(source))
    assert (tmp_path/'mesh.inc').read_bytes()==raw
    assert edited['bundle']==source['bundle']
    s['source']=edited;changed=model_from_settings(s)
    assert changed['nodes'][2][0]==12 and changed['nodes'][6][0]==32
    assert view(edited,'mesh.inc')['original'][1]['text'].endswith('\r\n')
    assert model_from_settings(definition())['nodes'] # unchanged separate source
    with pytest.raises(SourceError,match='바뀌었습니다'):
        replace_range(edited,'mesh.inc',start,start+2,'14',reason='stale',expected_source_sha256=canonical_hash(source))
    corrupt=deepcopy(edited);corrupt['bundle']['files'][1]['text']+='** modified\n'
    with pytest.raises(SourceError):resolve(corrupt)

def test_generate_nonintegral_endpoint_rejected():
    s=definition();text,spans=resolve(s['source'])
    with pytest.raises(SourceError,match='끝점'):compile_source(text.replace('10,40,10','10,40,11'),spans)
