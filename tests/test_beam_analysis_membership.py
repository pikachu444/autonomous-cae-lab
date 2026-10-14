"""Real collect/freeze gates with labelled native object and geometry doubles."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from apps.desktop_pre import beam_native
from caelab.beam_model import BeamInputError
from caelab.storage import canonical_hash
from test_beam_support import model


@pytest.fixture
def current(monkeypatch):
    value = model(); draft = value['draft']
    quantity = lambda value: NS(getValueAs=lambda unit: NS(Value=value))
    def obj(name, kind, **values):
        return NS(Name=name, Label=name, TypeId=kind, Suppressed=False, State=[], References=[], **values)
    items = {
        'Mesh':obj('Mesh','Fem::FemMeshObject'),
        'Section':obj('Section','Fem::ElementGeometry1D', SectionType='Rectangular',RectWidth=quantity(10),RectHeight=quantity(20)),
        'Rotation':obj('Rotation','Fem::ElementRotation1D', Rotation=quantity(0)),
        'Material':obj('Material','Fem::MaterialCommon', Category='Solid', Material={'YoungsModulus':'210000 MPa','PoissonRatio':'0.3'}),
        'Solver':obj('Solver','Fem::SolverCcxTools', AnalysisType='static', GeometricalNonlinearity='linear',
            MaterialNonlinearity='linear', ModelSpace='3D', ExcludeBendingStiffness=False, BeamReducedIntegration=True),
    }
    for name in ('End1','End2'):
        end = obj(name,'App::FeaturePython',Proxy=NS(Type='CAELab::BeamEnd'),CoordinateSystem='global')
        for axis in 'XYZ':
            for key in ('Force','Moment','Displacement','Rotation'):setattr(end,key+axis,quantity(0))
            for key in ('TranslationFree','RotationFree'):setattr(end,key+axis,False)
        items[name] = end
    analysis = obj('Analysis','Fem::FemAnalysis',Group=list(items.values())); items['Analysis']=analysis
    owner = NS(App=NS(Version=lambda:['1','1','4']),doc=NS(Name='Doc',getObject=items.get),document_id='Ptest')
    monkeypatch.setattr(beam_native,'native_type',lambda o:getattr(getattr(o,'Proxy',None),'Type',o.TypeId))
    record = {'draft':draft,'end_object_ids':['End1','End2'],'binding':{'test':'geometry-double',
                  'mesh_sha256':canonical_hash({'nodes':value['nodes'],'elements':value['elements']})},
              'applied_draft_hash':canonical_hash(draft)}
    record['native_property_stamp']=beam_native.property_stamp(owner, record)
    monkeypatch.setattr(beam_native,'geometry',lambda *args:(deepcopy(value),deepcopy(record['binding'])))
    return owner, record, items


def test_current_membership_is_accepted(current):
    owner, record, items = current
    value, solver = beam_native.collect(owner,record)
    assert solver is items['Solver'] and value['element']=='B32R'


@pytest.mark.parametrize('name',['Section','Material','Rotation','End1','End2','Mesh','Solver'])
def test_removing_any_required_member_blocks_freeze_with_unchanged_properties(current,name):
    owner, record, items = current
    before=deepcopy(record)
    items['Analysis'].Group.remove(items[name])
    assert owner.doc.getObject(name) is items[name]  # Still exists in the native document.
    assert beam_native.property_stamp(owner,record)==record['native_property_stamp']
    owner.project=NS(save=lambda:pytest.fail('Invalid membership must block before save/export'))
    with pytest.raises(BeamInputError):beam_native.freeze(owner,record)
    assert record==before  # No auto-add, no draft/result deletion.
    assert items[name] not in items['Analysis'].Group
    items['Analysis'].Group.append(items[name])  # Explicit user repair only.
    assert beam_native.collect(owner,record)[0]['element']=='B32R'


@pytest.mark.parametrize('name',['Section','Material','Rotation','End1','End2','Mesh'])
def test_same_named_wrong_native_type_never_admits_by_name_or_stamp(current,name):
    owner, record, items=current
    if name.startswith('End'):items[name].Proxy.Type='Other::End'
    else:items[name].TypeId='App::FeaturePython'
    assert beam_native.property_stamp(owner,record)==record['native_property_stamp']
    with pytest.raises(BeamInputError,match='종류'):beam_native.collect(owner,record)


@pytest.mark.parametrize('suppressed',[False,True])
def test_new_unsupported_analysis_condition_is_not_silently_omitted(current,suppressed):
    owner,record,items=current
    items['Analysis'].Group.append(NS(Name='NewForce',Label='추가 하중',TypeId='Fem::ConstraintForce',Suppressed=suppressed,State=[]))
    with pytest.raises(BeamInputError):beam_native.collect(owner,record)


@pytest.mark.parametrize('damage',['duplicate_end','missing_end','extra_end','duplicate_member','invalid_member'])
def test_invalid_membership_lists_are_read_only_gates(current,damage):
    owner,record,items=current
    if damage=='duplicate_end':record['end_object_ids']=['End1','End1']
    elif damage=='missing_end':record['end_object_ids']=[]
    elif damage=='extra_end':record['end_object_ids'].append('End1')
    elif damage=='duplicate_member':items['Analysis'].Group.append(items['Section'])
    else:items['End2'].State=['Invalid']
    before=deepcopy(record)
    with pytest.raises(BeamInputError):beam_native.collect(owner,record)
    assert record==before
