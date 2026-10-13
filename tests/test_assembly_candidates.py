"""Assembly contracts; native classes below are explicit test doubles.

Run the separate native probe for FreeCAD Motion, persistent shapes and Gmsh.
These tests do not claim native kinematics or solver acceptance.
"""
from copy import deepcopy
import math
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre import assembly_candidates as pose
from apps.desktop_pre import occurrence_fem as occurrence
from caelab.adapters.cad_analysis import CADAnalysisAdapter, validate_recipe
from caelab.model_parameters import bind
from test_cad_numerical import recipe as cad_recipe


class Quantity:
    scales = {'rad': 1., 'deg': math.pi / 180., 'mm': 1., 'm': 1000.}
    def __init__(self, text):
        value, self.unit = str(text).split()
        self.Value = float(value)
    def getValueAs(self, unit):
        if (self.unit in {'rad', 'deg'}) != (unit in {'rad', 'deg'}):
            raise ValueError('unit family')
        return NS(Value=self.Value * self.scales[self.unit] / self.scales[unit])


class Rotation:
    def __init__(self, angle=0., tilt=0.):
        self.Angle = abs(angle)
        self.angle, self.tilt = angle, tilt
        self.Q = (0., 0., math.sin(angle / 2), math.cos(angle / 2))
    def multVec(self, vector):
        if vector.z == 1:
            return NS(x=self.tilt, y=0., z=1.)
        return NS(x=math.cos(self.angle), y=math.sin(self.angle), z=0.)


class Placement:
    def __init__(self, xyz=(0., 0., 0.), angle=0., tilt=0.):
        self.Base = NS(x=xyz[0], y=xyz[1], z=xyz[2])
        self.Rotation = Rotation(angle, tilt)
    def inverse(self):
        return self  # Explicit first-frame identity in these measurement cases.
    def __mul__(self, other):
        return other


def measure_owner(kind, *, xyz=(0., 0., 0.), angle=0., tilt=0.):
    app = NS(Vector=lambda x, y, z: NS(x=x, y=y, z=z), Units=NS(Quantity=Quantity))
    joint = NS(JointType=kind, Placement1=Placement(), Placement2=Placement(xyz, angle, tilt),
               Reference1=('ground', ['']), Reference2=('moving', ['']))
    utils = NS(getJcsGlobalPlc=lambda placement, reference: placement)
    return NS(App=app, motion=NS(_api=lambda: (utils, None, None))), joint


def test_signed_coordinates_use_relative_jcs_and_explicit_units():
    owner, joint = measure_owner('Revolute', angle=math.radians(-25))
    assert pose.coordinate(owner, joint, 'deg') == pytest.approx(-25)
    assert pose.coordinate(owner, joint, 'rad') == pytest.approx(math.radians(-25))
    owner, joint = measure_owner('Slider', xyz=(0., 0., -2.5))
    assert pose.coordinate(owner, joint, 'm') == pytest.approx(-.0025)
    assert pose.measure(owner, joint)['axis_direction'] == [0., 0., 1.]
    joint.Placement2 = Placement((1., 0., -2.5))
    with pytest.raises(ValueError, match='residual'):
        pose.measure(owner, joint)
    owner, joint = measure_owner('Revolute', angle=.2, tilt=.01)
    with pytest.raises(ValueError, match='residual'):
        pose.measure(owner, joint)


@pytest.mark.parametrize('kind,unit,lower,upper', [('Revolute', 'deg', -20., 30.), ('Slider', 'm', -.002, .003)])
def test_native_limits_not_angle_or_distance_properties(kind, unit, lower, upper):
    owner, joint = measure_owner(kind)
    prefix = 'Angle' if kind == 'Revolute' else 'Length'
    setattr(joint, 'Enable' + prefix + 'Min', True)
    setattr(joint, 'Enable' + prefix + 'Max', True)
    setattr(joint, prefix + 'Min', Quantity(str(lower) + ' ' + unit))
    setattr(joint, prefix + 'Max', Quantity(str(upper) + ' ' + unit))
    joint.Angle, joint.Distance = 91., 82.  # Unrelated native properties.
    owner._object = lambda name: joint
    row = {'target': {'object_id': 'Joint'}}
    pose.validate_bound(owner, row, lower, upper, unit)
    with pytest.raises(ValueError, match='limits'):
        pose.validate_bound(owner, row, lower - 1., upper, unit)
    assert (joint.Angle, joint.Distance) == (91., 82.)


def assembly_recipe(kind='Revolute'):
    result = cad_recipe()
    result.update(route='contact', pairs=[{'id': 'Contact', 'label': 'Surface contact'}])
    unit = 'deg' if kind == 'Revolute' else 'm'
    result['variables'] = [{'id': 'pose', 'label': 'Angle' if kind == 'Revolute' else 'Travel',
        'analysis_id': 'Analysis', 'target': {'object_id': 'Joint', 'native_type': 'App::FeaturePython',
        'family': 'joint_coordinate', 'field': 'angle' if kind == 'Revolute' else 'travel'},
        'lower': -.1, 'upper': .1, 'value': 0., 'unit': unit}]
    result['meshes'] = [{'object_id': 'MeshA', 'body_id': 'BodyA', 'settings': {}},
                        {'object_id': 'MeshB', 'body_id': 'BodyB', 'settings': {}}]
    result['assembly'] = {'policy': pose.POLICY, 'variable_id': 'pose', 'unit': unit,
        'definition': {'assembly_id': 'Assembly', 'joint_id': 'Joint', 'joint_type': kind,
                       'grounded_occurrence': 'Ground', 'moving_occurrence': 'Moving'},
        'connection': {'assembly_id': 'Assembly', 'bodies': [
            {'occurrence_id': 'Ground', 'source_id': 'Part', 'body_id': 'BodyA', 'mesh_id': 'MeshA'},
            {'occurrence_id': 'Moving', 'source_id': 'Part', 'body_id': 'BodyB', 'mesh_id': 'MeshB'}]}}
    return result


@pytest.mark.parametrize('kind', ['Revolute', 'Slider'])
def test_existing_evaluator_binds_coordinate_without_losing_occurrence_recipe(kind):
    recipe = assembly_recipe(kind)
    settings = {'data_id': 'Dsource', 'source_sha256': 'a' * 64, 'recipe': recipe, 'values': {'pose': 0.}}
    result = bind(CADAnalysisAdapter(), settings, {'pose': -.05})
    assert result['values']['pose'] == -.05
    assert result['recipe'] == recipe and settings['values'] == {'pose': 0.}
    assert CADAnalysisAdapter().describe_inputs(result)[0]['unit'] == recipe['variables'][0]['unit']
    broken = deepcopy(recipe)
    broken['assembly']['connection']['bodies'][1]['occurrence_id'] = 'Ground'
    with pytest.raises(ValueError, match='one-to-one'):
        validate_recipe(broken)


def test_native_feature_history_keeps_two_occurrences_distinct(monkeypatch):
    source = NS(Shape=NS(Faces=[object(), object()], getElementIndexedName=lambda name: name))
    body = NS(Shape=NS(Faces=[object(), object()]))
    body.getElementHistory = lambda name, **kw: [(source, {'Face1': 'Face2', 'Face2': 'Face1'}[name], [])]
    monkeypatch.setattr(occurrence, 'validate_body', lambda *_: (object(), body, source))
    assert occurrence.element_pairs(None, None, {'occurrence_id': 'One'}) == {'Face1': 'Face2', 'Face2': 'Face1'}
    body.getElementHistory = lambda name, **kw: [(source, 'Face1', [])]
    with pytest.raises(ValueError, match='split or duplicates'):
        occurrence.element_pairs(None, None, {})
    body.getElementHistory = lambda name, **kw: [(123, 'Face1', [])]
    with pytest.raises(ValueError, match='unresolved'):
        occurrence.element_pairs(None, None, {})


def test_connector_origin_is_explicit_but_changed_mapless_face_is_not(monkeypatch):
    source = NS(Name='Part')
    link = NS(Name='Moving')
    owner = NS(_object=lambda name: link)
    monkeypatch.setattr(occurrence, 'source_of', lambda obj: source)
    monkeypatch.setattr(pose, '_target', lambda *_: {'shape': 'changed'})
    saved = {'connectors': [{'occurrence_id': 'Moving', 'source_id': 'Part',
        'source_target': {'shape': 'old'}, 'names': [''], 'anchors': [None]}]}
    assert pose._connector_expected(owner, saved) == [['Moving', ['']]]
    saved['connectors'][0]['names'] = ['Face1']
    with pytest.raises(ValueError, match='exact native element history'):
        pose._connector_expected(owner, saved)


@pytest.mark.parametrize('unit,target', [('rad', .2), ('mm', -.3)])
def test_reopen_measures_before_normal_solve_and_never_redrives(monkeypatch, unit, target):
    calls = []
    joint = object()
    assembly = NS(solve=lambda _flag: calls.append('solve') or 0)
    owner = NS(App=NS(Units=NS(Quantity=Quantity)),
               doc=NS(recompute=lambda: calls.append('recompute')), _object=lambda _: object())
    saved = {'variable_id': 'q', 'unit': unit, 'connection': {}}
    recipe = {'analysis_id': 'Analysis', 'assembly': saved}
    monkeypatch.setattr(pose, 'validate_definition', lambda *_: (assembly, joint))
    monkeypatch.setattr(occurrence, 'refresh_bindings', lambda *a, **kw: calls.append('bindings'))
    monkeypatch.setattr(pose, 'measure', lambda *_: {'value': target, 'unit': unit})
    result = pose.verify(owner, recipe, {'q': target}, solve=True)
    assert calls == ['solve', 'recompute', 'bindings']
    assert result['before_solve']['value'] == result['measured']['value'] == target
    calls.clear()
    monkeypatch.setattr(pose, 'measure', lambda *_: {'value': 0., 'unit': unit})
    with pytest.raises(ValueError, match='not retained'):
        pose.verify(owner, recipe, {'q': target}, solve=True)
    assert calls == []


def test_changed_native_binding_is_not_repaired_by_readback(monkeypatch):
    assembly, body = NS(Name='Assembly'), NS(Name='Body', recompute=lambda: True)
    owner = NS(_object=lambda _: assembly, doc=NS(recompute=lambda: None))
    record = {'assembly_id': 'Assembly', 'bodies': [{'body_id': 'Body'}]}
    monkeypatch.setattr(occurrence, 'binding', lambda *_: record)
    monkeypatch.setattr(occurrence, 'validate_body', lambda *_: (object(), body, object()))
    targets = iter([{'shape': 'saved'}, {'shape': 'different'}])
    monkeypatch.setattr(occurrence, '_target', lambda *_: next(targets))
    with pytest.raises(ValueError, match='differs'):
        occurrence.refresh_bindings(owner, NS(Name='Analysis'), require_unchanged=True)


def test_motion_cleanup_and_final_measurement_are_explicit(monkeypatch):
    calls, objects = [], {}
    owner, joint = measure_owner('Revolute')
    joint.Name = 'Joint'
    current = {'value': 0., 'unit': 'rad'}
    def add(kind, name):
        obj = NS(Name=name)
        objects[name] = obj
        return obj
    doc = NS(addObject=add, removeObject=lambda name: calls.append(('remove', name)),
             recompute=lambda: calls.append(('recompute',)))
    def native_motion(obj, kind, selected, formula):
        assert kind == 'Angular' and selected is joint
        assert formula == '0.0+(0.2)*time'
    native = NS(Simulation=lambda obj: None, Motion=native_motion)
    owner.doc, owner.motion = doc, NS(_api=lambda: (None, None, native))
    assembly = NS(generateSimulation=lambda sim: calls.append(('generate', sim.cTimeStepOutput)) or 0,
                  numberOfFrames=lambda: 4,
                  updateForFrame=lambda index: current.update(value=.2))
    saved = {'variable_id': 'q', 'unit': 'rad', 'definition': {'limits': {'min': -.3, 'max': .3}}}
    recipe = {'assembly': saved, 'variables': [{'id': 'q', 'unit': 'rad', 'lower': -.3, 'upper': .3}]}
    monkeypatch.setattr(pose, 'rebind_connectors', lambda *_: calls.append(('correspondence',)))
    monkeypatch.setattr(pose, 'validate_definition', lambda *_: (assembly, joint))
    monkeypatch.setattr(pose, 'measure', lambda *_: deepcopy(current))
    monkeypatch.setattr(pose, 'validate_bound', lambda *_: None)
    monkeypatch.setattr(pose, 'verify', lambda *a, **kw: {'after_normal_solve': kw['solve']})
    assert pose.drive(owner, recipe, {'q': .2}) == {'after_normal_solve': True}
    assert [item for item in calls if item[0] == 'remove'] == [
        ('remove', 'CandidateJointDrive'), ('remove', 'CandidatePosePath')]
    assert objects['CandidatePosePath'].Group == []
    assert not hasattr(joint, 'Angle') and not hasattr(joint, 'Distance')


def test_whole_solid_support_does_not_invent_a_solid_element_map(monkeypatch):
    source, body = NS(Shape=NS(Solids=[object()])), NS(Shape=NS(Solids=[object()]))
    monkeypatch.setattr(occurrence, 'validate_body', lambda *_: (object(), body, source))
    assert occurrence.element_pairs(None, None, {}, 'Solid') == {'Solid1': 'Solid1'}
    body.Shape.Solids.append(object())
    with pytest.raises(ValueError, match='exactly one'):
        occurrence.element_pairs(None, None, {}, 'Solid')
