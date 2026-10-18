"""Hierarchy reuses flat material/element admission; no solver execution in model tests."""
from copy import deepcopy
from pathlib import Path
import pytest
from caelab.impact_assembly import compile_source, tokenize, target_key, exact_entity
from caelab.impact_model import parse_inp, default_settings, model_from_settings, render
from caelab.impact_source import capture, resolve, SourceError


def flat_source(kind, plastic=False):
    # Same ten-node tetra ordering as the existing flat formulation fixture.
    tetra = [(0,0,0),(10,0,0),(0,10,0),(0,0,10),(5,0,0),(5,5,0),(0,5,0),(0,0,5),(5,0,5),(0,5,5)]
    height = .02 if kind == 'COH3D8' else 10
    brick = [(0,0,0),(10,0,0),(10,10,0),(0,10,0),(0,0,height),(10,0,height),(10,10,height),(0,10,height)]
    points = tetra[:4] if kind == 'C3D4' else tetra if kind == 'C3D10' else brick
    rows = ['*NODE,NSET=BODY'] + [f'{10*i},'+','.join(map(str,p)) for i,p in enumerate(points,1)]
    rows += [f'*ELEMENT,TYPE={kind},ELSET=SOLID', '70,'+','.join(str(10*i) for i in range(1,len(points)+1))]
    section = 'COHESIVE SECTION' if kind == 'COH3D8' else 'SOLID SECTION'
    rows += [f'*{section},ELSET=SOLID,MATERIAL=MAT', '*SURFACE,NAME=FACE,TYPE=ELEMENT', 'SOLID,S4' if '10' in kind or kind=='C3D4' else 'SOLID,S6']
    rows += ['*MATERIAL,NAME=MAT','*DENSITY','7.8e-9','*ELASTIC,TYPE=TRACTION' if kind=='COH3D8' else '*ELASTIC','1000,500,500,0' if kind=='COH3D8' else '210000,.3']
    if plastic: rows += ['*PLASTIC','200,0','210,.01']
    return '\n'.join(rows)+'\n'


def hierarchical(flat, *, second=True):
    blocks = tokenize(flat)
    local = [b for b in blocks if b['card'] not in ('MATERIAL','DENSITY','ELASTIC','PLASTIC','BOUNDARY')]
    global_ = deepcopy([b for b in blocks if b not in local])
    for block in global_:
        if block['card']=='BOUNDARY':
            for row in block['rows']: row['text']='BODY-1.'+row['text']
    def text(items):
        return ''.join('*'+b['card']+''.join(','+k+'='+str(v) for k,v in b['options'].items())+'\n'+''.join(r['text']+'\n' for r in b['rows']) for b in items)
    return ('*PART,NAME=BODY-PART\n'+text(local)+'*END PART\n*ASSEMBLY,NAME=DROP\n*INSTANCE,NAME=BODY-1,PART=BODY-PART\n*END INSTANCE\n'
        + ('*INSTANCE,NAME=BODY-2,PART=BODY-PART\n30,0,0\n0,0,0,0,0,1,90\n*END INSTANCE\n' if second else '')
        + '*END ASSEMBLY\n'+text(global_))


@pytest.mark.parametrize('kind,plastic',[('C3D10',False),('C3D8',True),('C3D8R',True),('COH3D8',False)])
def test_new_families_reuse_exact_flat_material_and_ordered_connectivity(kind,plastic):
    source=flat_source(kind,plastic);flat=parse_inp(source);model=compile_source(hierarchical(source))
    assert len(model['elements'])==2 and len(model['nodes'])==len(flat['nodes'])*2
    assert model['materials']==flat['materials']
    for instance in ('BODY-1','BODY-2'):
        eid=exact_entity(model,'CELLS',instance,70)
        assert model['elements'][eid]['type']==kind
        expected=[exact_entity(model,'POINTS',instance,n) for n in flat['elements'][70]['nodes']]
        assert model['elements'][eid]['nodes']==expected
        assert model['assignment'][eid]=='MAT'
    assert model['nsets'][target_key(model,'nsets','DROP.BODY-1.BODY')].isdisjoint(model['nsets'][target_key(model,'nsets','DROP.BODY-2.BODY')])


def test_tetra_s5_rejected_at_original_source_even_with_hex_in_other_part():
    with pytest.raises(SourceError): compile_source(hierarchical(flat_source('C3D10')).replace('SOLID,S4','SOLID,S5'))

def test_nested_repeated_includes_preserve_material_section_assignment_provenance(tmp_path):
    flat=flat_source('C3D8R',True);blocks=tokenize(flat)
    material=flat[flat.index('*MATERIAL'):]
    mesh=flat[:flat.index('*MATERIAL')]
    (tmp_path/'deep').mkdir()
    (tmp_path/'deep/mesh.inc').write_text(mesh,encoding='ascii')
    (tmp_path/'part.inc').write_text('*INCLUDE,INPUT=deep/mesh.inc\n',encoding='ascii')
    (tmp_path/'deep/material.inc').write_text(material,encoding='ascii')
    (tmp_path/'materials.inc').write_text('*INCLUDE,INPUT=deep/material.inc\n',encoding='ascii')
    root=''.join(f'*PART,NAME={part}\n*INCLUDE,INPUT=part.inc\n*END PART\n' for part in ('BODY-A','BODY_A'))
    root+='*ASSEMBLY,NAME=DROP\n*INSTANCE,NAME=BODY-1,PART=BODY-A\n*END INSTANCE\n*INSTANCE,NAME=BODY_1,PART=BODY_A\n20,0,0\n*END INSTANCE\n*END ASSEMBLY\n*INCLUDE,INPUT=materials.inc\n'
    (tmp_path/'root.inp').write_text(root,encoding='ascii')
    source=capture(tmp_path/'root.inp',tmp_path);text,spans=resolve(source);before=deepcopy(source)
    model=compile_source(text,spans)
    first=model['lineage']['elements']['1'];second=model['lineage']['elements']['2']
    assert first['file']==second['file']=='deep/mesh.inc' and first['occurrence']!=second['occurrence']
    assert first['type']=='C3D8R' and first['local_connectivity']==list(range(10,90,10))
    assert first['material_origin']['file']=='deep/material.inc'
    assert first['section_origin']['file']=='deep/mesh.inc'
    assert len(model['lineage']['materials']['MAT']['assignments'])==2
    cards=model['lineage']['materials']['MAT']['cards']
    assert [b['card'] for b in cards]==['MATERIAL','DENSITY','ELASTIC','PLASTIC']
    assert cards[-1]['rows'][0]['origin']['file']=='deep/material.inc'
    sections=model['lineage']['sections']
    assert [r['instance'] for r in sections]==['BODY-1','BODY_1']
    assert sections[0]['assignments'][0]['element_id']==1 and sections[1]['assignments'][0]['element_id']==2
    assert source==before and set(model['assignment'].values())=={'MAT'}


@pytest.mark.parametrize('old,new',[
    ('*SOLID SECTION,ELSET=SOLID,MATERIAL=MAT','*SOLID SECTION,ELSET=SOLID,MATERIAL=MISSING'),
    ('*SOLID SECTION,ELSET=SOLID,MATERIAL=MAT','*SOLID SECTION,ELSET=ABSENT,MATERIAL=MAT'),
    ('*SOLID SECTION,ELSET=SOLID,MATERIAL=MAT','*SOLID SECTION,ELSET=SOLID,MATERIAL=MAT\n*SOLID SECTION,ELSET=SOLID,MATERIAL=MAT'),
    ('*ELASTIC\n210000,.3','*ELASTIC,TYPE=TRACTION\n1000,500,500,0'),
    ('200,0\n210,.01','200,.1\n210,.01'),
    ('*PLASTIC','*PLASTIC,RATE=1'),
    ('*MATERIAL,NAME=MAT','*MATERIAL,NAME=MAT-BAD'),
    ('70,10,20,30,40,50,60,70,80','70,10,20,30,40,50,60,70,999'),
])
def test_invalid_physical_or_source_assignment_is_not_silently_dropped(old,new):
    with pytest.raises(SourceError): compile_source(hierarchical(flat_source('C3D8R',True)).replace(old,new))


@pytest.mark.parametrize('replacement',[
    '*SOLID SECTION,ELSET=SOLID,MATERIAL=MAT',
    '*COHESIVE SECTION,ELSET=SOLID,MATERIAL=MISSING',
    '*COHESIVE SECTION,ELSET=SOLID,MATERIAL=MAT,RESPONSE=TRACTION SEPARATION',
])
def test_cohesive_section_errors_use_the_existing_flat_physics(replacement):
    source=hierarchical(flat_source('COH3D8')).replace('*COHESIVE SECTION,ELSET=SOLID,MATERIAL=MAT',replacement)
    with pytest.raises(SourceError): compile_source(source)


def test_flat_validation_error_retains_original_line_occurrence_instance(tmp_path):
    # The invalid material assignment is emitted once per instance; the shared
    # flat parser's first offending compiled line must map to BODY-1, not guess.
    source=hierarchical(flat_source('C3D8',True)).replace('MATERIAL=MAT','MATERIAL=MISSING',1)
    (tmp_path/'root.inp').write_text(source,encoding='ascii')
    retained=capture(tmp_path/'root.inp',tmp_path);text,spans=resolve(retained)
    with pytest.raises(SourceError) as caught: compile_source(text,spans)
    error=caught.value
    assert error.file=='root.inp' and error.line==next(i for i,line in enumerate(source.splitlines(),1) if 'MATERIAL=MISSING' in line)
    assert error.occurrence==0 and error.impact['instances']==['BODY-1']
    assert error.impact['card']=='SOLID SECTION' and error.impact['references']['MATERIAL']=='MISSING'


def test_assembly_surface_admission_is_element_specific():
    for kind in ('C3D8','C3D8R','COH3D8'):
        source=hierarchical(flat_source(kind)).replace('*END ASSEMBLY','*SURFACE,NAME=SIDE,TYPE=ELEMENT\nBODY-2.SOLID,S6\n*END ASSEMBLY')
        model=compile_source(source)
        assert model['surfaces'][target_key(model,'surfaces','DROP.SIDE')]==[('2','S6')]
    source=hierarchical(flat_source('C3D10')).replace('*END ASSEMBLY','*SURFACE,NAME=SIDE,TYPE=ELEMENT\nBODY-2.SOLID,S5\n*END ASSEMBLY')
    with pytest.raises(SourceError) as caught:compile_source(source)
    assert caught.value.impact['instances']==['BODY-2']


def test_raw_source_initial_conditions_remains_blocked():
    source=hierarchical(flat_source('C3D10'))+'*INITIAL CONDITIONS,TYPE=VELOCITY\nBODY-1.BODY,1,20\n'
    with pytest.raises(SourceError,match='INITIAL CONDITIONS'):compile_source(source)

def test_scoped_motion_pose_heights_and_existing_unknown_integrals():
    import math
    from caelab.impact_model import validate_settings
    from caelab.impact_initial_state import describe
    definition=default_settings();definition['source']['text']=hierarchical(flat_source('C3D10'))
    model=model_from_settings(definition);key=target_key(model,'nsets','DROP.BODY-2.BODY')
    definition['gravity_mm_s2']=[0.,0.,-9810.]
    definition['motions']=[{'node_set':key,'mode':'release_height','height_mm':12.,
        'velocity_mm_s':[0.,0.,0.],'omega_rad_s':[0.,0.,0.],'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]}]
    _,release=render(definition)
    first=model['nsets'][target_key(model,'nsets','DROP.BODY-1.BODY')]
    assert all(release['nodes'][n]==model['nodes'][n] for n in first)
    assert all(release['nodes'][n][2]==model['nodes'][n][2]+12 for n in model['nsets'][key])
    definition['motions'][0]['mode']='impact_height';_,impact=render(definition)
    assert impact['nodes']==model['nodes']
    assert all(v[2]==-math.sqrt(2*9810*12) for v in impact['velocities_mm_s'].values())
    assert describe(model,impact,definition)['initial']['status']=='UNKNOWN'
    definition['motions'][0]['velocity_mm_s']=[0.,0.,-1.]
    with pytest.raises(ValueError,match='중복'):validate_settings(definition)
    definition['motions'][0].update(mode='velocity',height_mm=None,velocity_mm_s=[1.,0.,0.])
    definition['source']['text']+='*BOUNDARY\nBODY-2.10,1,1,0\n'
    with pytest.raises(ValueError,match='충돌'):validate_settings(definition)


def test_recycled_effective_ids_after_instance_order_edit_require_logical_review():
    from caelab.impact_model import validate_settings
    from caelab.impact_reference_bindings import snapshot, KEY
    definition=default_settings();definition['source']['text']=hierarchical(flat_source('C3D10'))
    model=model_from_settings(definition)
    definition['motions']=[{'node_set':target_key(model,'nsets','DROP.BODY-2.BODY'),'mode':'velocity','height_mm':None,
        'velocity_mm_s':[1.,0.,0.],'omega_rad_s':[0.,0.,0.],'center_mm':[0.,0.,0.],'translation_mm':[0.,0.,0.]}]
    definition['responses']=[{'name':'selected','quantity':'stress','identity':exact_entity(model,'CELLS','BODY-2',70),'component':'xx'}]
    definition[KEY]=snapshot(definition)
    original=definition['source']['text']
    first='*INSTANCE,NAME=BODY-1,PART=BODY-PART\n*END INSTANCE\n'
    second='*INSTANCE,NAME=BODY-2,PART=BODY-PART\n30,0,0\n0,0,0,0,0,1,90\n*END INSTANCE\n'
    definition['source']['text']=original.replace(first+second,second+first)
    changed=model_from_settings(definition)
    assert changed['elements'][2]['type']=='C3D10' and changed['lineage']['elements']['2']['instance']=='BODY-1'
    with pytest.raises(SourceError,match='대응'):validate_settings(definition)

def test_ten_ordered_nodes_two_instances_nested_source_and_shared_edit(tmp_path):
    from caelab.impact_input_edits import replace_range
    from caelab.storage import canonical_hash
    source=flat_source('C3D10');where=source.index('*MATERIAL')
    (tmp_path/'mesh.inc').write_text(source[:where],encoding='ascii')
    (tmp_path/'part.inc').write_text('*INCLUDE,INPUT=mesh.inc\n',encoding='ascii')
    wrapped=hierarchical(source).replace(source[:where],'*INCLUDE,INPUT=part.inc\n')
    (tmp_path/'root.inp').write_text(wrapped,encoding='ascii')
    retained=capture(tmp_path/'root.inp',tmp_path);definition=default_settings();definition['source']=retained
    model=model_from_settings(definition)
    assert len(model['nodes'])==20
    expected=[(0,30,0),(0,40,0),(-10,30,0),(0,30,10),(0,35,0),(-5,35,0),(-5,30,0),(0,30,5),(0,35,5),(-5,30,5)]
    for local,position in zip(range(10,110,10),expected):
        assert model['nodes'][exact_entity(model,'POINTS','BODY-2',local)]==pytest.approx(position,abs=1e-12)
    raw=(tmp_path/'mesh.inc').read_bytes();offset=raw.index(b'20,10,0,0')+3
    edited=replace_range(retained,'mesh.inc',offset,offset+2,'12',reason='shared retained mesh edit',expected_source_sha256=canonical_hash(retained))
    definition['source']=edited;changed=model_from_settings(definition)
    assert (tmp_path/'mesh.inc').read_bytes()==raw and edited['bundle']==retained['bundle']
    assert changed['nodes'][exact_entity(changed,'POINTS','BODY-1',20)]==[12.,0.,0.]
    assert changed['nodes'][exact_entity(changed,'POINTS','BODY-2',20)]==pytest.approx([0.,42.,0.],abs=1e-12)
    with pytest.raises(SourceError,match='바뀌었습니다'):
        replace_range(edited,'mesh.inc',offset,offset+2,'14',reason='stale source edit',expected_source_sha256=canonical_hash(retained))


def test_mixed_local_elset_cannot_admit_hex_six_on_a_tetra_member():
    source=flat_source('C3D10')
    points=[(20,0,0),(30,0,0),(30,10,0),(20,10,0),(20,0,10),(30,0,10),(30,10,10),(20,10,10)]
    extra='*NODE\n'+''.join(str(i)+','+','.join(map(str,p))+'\n' for i,p in zip(range(210,290,10),points))
    extra+='*ELEMENT,TYPE=C3D8,ELSET=SOLID\n80,'+','.join(map(str,range(210,290,10)))+'\n'
    source=source.replace('*SOLID SECTION',extra+'*SOLID SECTION')
    model=compile_source(hierarchical(source))
    assert {r['type'] for r in model['elements'].values()}=={'C3D8','C3D10'}
    with pytest.raises(SourceError):compile_source(hierarchical(source.replace('SOLID,S4','SOLID,S6')))
