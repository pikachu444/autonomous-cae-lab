"""Typed variables for a saved native Analysis, without executing a candidate.

Model limits are explicit registrations in the native document. Search limits
belong to the Numerical Plan. Native quantities always carry a selected unit.
"""
from copy import deepcopy
import math
import re

from caelab.storage import canonical_hash
from .fem_edit import _native_type

OPERATIONS = ('pre.research.discover', 'pre.research.register',
              'pre.research.remove', 'pre.research.prepare')
GEOMETRY = {'App::PropertyLength', 'App::PropertyDistance', 'App::PropertyAngle'}
LENGTH_NAMES = {'Length', 'Length2', 'Width', 'Height', 'Radius', 'Radius1',
                'Radius2', 'Angle', 'Angle2'}
CONTACT_FIELDS = {'normal_stiffness_MPa_per_mm': ('Normal stiffness', 'MPa/mm'),
                  'stick_stiffness_MPa_per_mm': ('Stick stiffness', 'MPa/mm'),
                  'friction_coefficient': ('Friction coefficient', '1')}

CONTACT_PROPERTIES = {'normal_stiffness_MPa_per_mm': 'Slope',
                      'stick_stiffness_MPa_per_mm': 'StickSlope',
                      'friction_coefficient': 'FrictionCoefficient'}


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Enter a finite numeric value')
    return float(value)


def _quantity(owner, value):
    return value if hasattr(value, 'getValueAs') else owner.App.Units.Quantity(str(value))


def quantity_value(owner, value, unit=None):
    q = _quantity(owner, value)
    if unit is None:
        unit = str(q.getUserPreferred()[2]).strip()
    if not unit:
        raise ValueError('A dimensional native quantity needs an explicit unit')
    return number(q.getValueAs(unit).Value), unit


def _writable(obj, prop):
    if getattr(obj, 'Suppressed', False):
        return 'Suppressed in this Analysis'
    if {'ReadOnly', 'Hidden'} & set(obj.getEditorMode(prop)):
        return 'Read-only native property'
    if any(path == prop or path.startswith(prop + '.') or path.startswith(prop + '[')
           for path, _ in getattr(obj, 'ExpressionEngine', [])):
        return 'Expression driven; edit its native expression'
    return None


def _row(obj, family, field, value, unit, reason=None):
    return {'target': {'object_id': obj.Name, 'native_type': _native_type(obj),
                      'family': family, 'field': field},
            'key': family + ':' + obj.Name + ':' + field,
            'label': obj.Label + ' / ' + field, 'value': value, 'unit': unit,
            'diagnostic': reason, 'writable': reason is None}


def discover(owner, analysis):
    """Expose actual targets; blocked rows remain visible, not guessed bindings."""
    if _native_type(analysis) != 'Fem::FemAnalysis':
        raise ValueError('Select a native FEM Analysis')
    rows = []
    for obj in owner.doc.Objects:
        if hasattr(obj, 'Shape'):
            for prop in obj.PropertiesList:
                if prop not in LENGTH_NAMES or obj.getTypeIdOfProperty(prop) not in GEOMETRY:
                    continue
                try:
                    value, unit = quantity_value(owner, getattr(obj, prop))
                    rows.append(_row(obj, 'geometry', prop, value, unit, _writable(obj, prop)))
                except (ValueError, RuntimeError) as error:
                    rows.append(_row(obj, 'geometry', prop, None, '', str(error)))
        if obj.TypeId == 'Sketcher::SketchObject':
            for index, constraint in enumerate(obj.Constraints):
                if constraint.Type not in {'Distance', 'DistanceX', 'DistanceY', 'Radius', 'Diameter', 'Angle'}:
                    continue
                name = constraint.Name
                reason = None if name else 'Name this driving constraint in Sketcher first'
                if not obj.getDriving(index):
                    reason = 'Reference constraint cannot drive a candidate'
                if any(path in {'Constraints[' + str(index) + ']', 'Constraints.' + name}
                       for path, _ in getattr(obj, 'ExpressionEngine', [])):
                    reason = 'Expression driven; edit its native expression'
                value, unit = quantity_value(owner, obj.getDatum(index))
                rows.append(_row(obj, 'constraint', name or '#' + str(index), value, unit, reason))
    for obj in analysis.Group:
        kind = _native_type(obj)
        if kind == 'Fem::ConstraintForce':
            value, unit = quantity_value(owner, obj.Force)
            rows.append(_row(obj, 'force', 'Force', value, unit, _writable(obj, 'Force')))
        elif kind == 'Fem::ConstraintDisplacement':
            for axis in 'xyz':
                field = axis + 'Displacement'
                value, unit = quantity_value(owner, getattr(obj, field))
                reason = _writable(obj, field)
                if getattr(obj, axis + 'Free'):
                    reason = 'Free component; prescribe it in native FEM first'
                rows.append(_row(obj, 'displacement', field, value, unit, reason))
        elif kind == 'App::MaterialObjectPython' or hasattr(obj, 'Material') and 'YoungsModulus' in obj.Material:
            material = obj.Material
            if 'YoungsModulus' in material:
                value, unit = quantity_value(owner, material['YoungsModulus'])
                rows.append(_row(obj, 'material', 'YoungsModulus', value, unit, _writable(obj, 'Material')))
            if 'PoissonRatio' in material:
                rows.append(_row(obj, 'material', 'PoissonRatio', float(material['PoissonRatio']), '1',
                                 _writable(obj, 'Material')))
    for record in owner.fem.contact._data()['contacts']:
        if record['analysis_id'] != analysis.Name:
            continue
        obj = owner._object(record['object_id'])
        for field, (label, unit) in CONTACT_FIELDS.items():
            reason = _writable(obj, CONTACT_PROPERTIES[field])
            if record['draft'].get('normal_law') != 'linear':
                reason = 'Only the supported linear normal law is bound'
            if field != 'normal_stiffness_MPa_per_mm' and record['draft'].get('tangential_law') != 'coulomb':
                reason = 'Inactive with the frictionless law'
            try:
                value = float(record['draft'][field])
                if not math.isfinite(value):
                    raise ValueError()
            except (ValueError, TypeError):
                value, reason = None, 'Repair the partial contact coefficient'
            rows.append(_row(obj, 'contact', field, value, unit, reason))
    return rows


def value_at(owner, target, unit):
    obj = owner._object(target['object_id'])
    if _native_type(obj) != target['native_type']:
        raise ValueError('Native variable object type changed')
    family, field = target['family'], target['field']
    if family == 'contact':
        raw = getattr(obj, CONTACT_PROPERTIES[field])
        value = number(float(raw)) if unit == '1' else quantity_value(owner, raw, unit)[0]
        if unit != CONTACT_FIELDS[field][1]:
            raise ValueError('Contact coefficient unit differs from its native declaration')
        return value
    if family == 'material':
        raw = obj.Material[field]
        return number(float(raw)) if unit == '1' and field == 'PoissonRatio' else quantity_value(owner, raw, unit)[0]
    if family == 'constraint':
        matches = [i for i, c in enumerate(obj.Constraints) if c.Name == field]
        if len(matches) != 1 or not obj.getDriving(matches[0]):
            raise ValueError('Named driving constraint is absent or ambiguous')
        return quantity_value(owner, obj.getDatum(matches[0]), unit)[0]
    if family in {'geometry', 'force', 'displacement'}:
        return quantity_value(owner, getattr(obj, field), unit)[0]
    raise ValueError('Unsupported typed native variable')


def validate_limits(row, lower, upper, value):
    lower, upper, value = map(number, (lower, upper, value))
    if not lower < upper or not lower <= value <= upper:
        raise ValueError('Model bounds must increase and contain the native value')
    family, field = row['target']['family'], row['target']['field']
    if family == 'material' and field == 'PoissonRatio' and not (-1 < lower < upper < .5):
        raise ValueError('Isotropic Poisson ratio requires -1 < lower < upper < 0.5')
    positive = family == 'force' or family == 'material' and field == 'YoungsModulus' or (
        family == 'contact' and field != 'friction_coefficient')
    if positive and lower <= 0:
        raise ValueError('This native magnitude/coefficient requires a strictly positive model lower bound')
    if family == 'contact' and field == 'friction_coefficient' and lower < 0:
        raise ValueError('Coulomb friction requires nonnegative model bounds')
    # Displacements, angular/coordinate dimensions can be signed or zero.
    return lower, upper


def assign(owner, variable, value):
    """Called only in an independent candidate document."""
    target, unit = variable['target'], variable['unit']
    value = number(value)
    validate_limits(variable, variable['lower'], variable['upper'], value)
    actual = next((row for row in discover(owner, owner._object(variable['analysis_id']))
                   if row['target'] == target), None)
    if actual is None or not actual['writable']:
        raise ValueError((actual or {}).get('diagnostic') or 'Variable target is no longer advertised')
    obj = owner._object(target['object_id'])
    field, family = target['field'], target['family']
    if family == 'contact':
        owner.fem.contact.set(obj, {'draft': {field: value}})
        actual_value = value_at(owner, target, unit)
        draft_value = float(owner.fem.contact._pair(obj.Name)['draft'][field])
        if not math.isclose(actual_value, value, rel_tol=1e-12, abs_tol=0.) or draft_value != value:
            raise ValueError('Native contact coefficient did not round-trip in its declared unit')
        return
    q = None if unit == '1' else owner.App.Units.Quantity(repr(value) + ' ' + unit)
    def change():
        if family == 'material':
            data = dict(obj.Material)
            data[field] = repr(value) if unit == '1' else str(q)
            obj.Material = data
        elif family == 'constraint':
            indices = [i for i, c in enumerate(obj.Constraints) if c.Name == field]
            if len(indices) != 1:
                raise ValueError('Named constraint is absent or ambiguous')
            obj.setDatum(indices[0], q)
        else:
            setattr(obj, field, q)
    owner._transaction('Candidate ' + variable['label'], change)
    actual_value = value_at(owner, target, unit)
    if not math.isclose(actual_value, value, rel_tol=1e-12, abs_tol=0.):
        raise ValueError('Native assignment did not round-trip in the declared unit')


class ResearchInputs:
    def __init__(self, owner):
        self.owner = owner

    def descriptor(self, analysis_id):
        owner = self.owner
        analysis = owner._object(analysis_id)
        rows = discover(owner, analysis)
        registered = deepcopy(owner.read_metadata().get('research_inputs', []))
        for item in registered:
            if item['analysis_id'] != analysis_id:
                continue
            row = next((row for row in rows if row['target'] == item['target']), None)
            item['diagnostic'] = (row or {}).get('diagnostic') or (None if row else 'Target no longer exists')
            try:
                item['value'] = value_at(owner, item['target'], item['unit'])
            except Exception as error:
                item['diagnostic'] = str(error)
        return {'analysis_id': analysis_id, 'candidates': rows,
                'registered': [r for r in registered if r['analysis_id'] == analysis_id],
                'source_stamp': canonical_hash({'generation': owner.generation, 'rows': rows,
                                               'registered': registered})}

    def dispatch(self, operation, args, target):
        if target:
            raise ValueError('Select an Analysis in the research command')
        if operation == 'pre.research.discover':
            if set(args) != {'analysis_id'}:
                raise ValueError('Select the native Analysis')
            return self.descriptor(args['analysis_id'])
        if operation == 'pre.research.register':
            if set(args) != {'analysis_id', 'source_stamp', 'key', 'id', 'label', 'unit', 'lower', 'upper'}:
                raise ValueError('Register a selected typed target with explicit model bounds')
            state = self.descriptor(args['analysis_id'])
            if args['source_stamp'] != state['source_stamp']:
                raise ValueError('Native input changed; refresh before registration')
            row = next((r for r in state['candidates'] if r['key'] == args['key']), None)
            if row is None or not row['writable']:
                raise ValueError((row or {}).get('diagnostic') or 'Choose a writable native target')
            if not re.fullmatch('[a-z][a-z0-9_]{0,47}', args['id']):
                raise ValueError('Use a short lower-case research variable ID')
            if not isinstance(args['label'], str) or not 0 < len(args['label'].strip()) <= 160:
                raise ValueError('Enter a short variable label')
            value = value_at(self.owner, row['target'], args['unit'])
            lower, upper = validate_limits(row, args['lower'], args['upper'], value)
            data = self.owner.read_metadata()
            rows = data.setdefault('research_inputs', [])
            if any(r['id'] == args['id'] and r['target'] != row['target'] for r in rows):
                raise ValueError('Variable ID already belongs to another target')
            item = {'id': args['id'], 'label': args['label'].strip(), 'target': row['target'],
                    'analysis_id': args['analysis_id'], 'unit': args['unit'],
                    'lower': lower, 'upper': upper, 'value': value}
            data['research_inputs'] = [r for r in rows if r['id'] != item['id'] and
                (r['analysis_id'], r['target']) != (item['analysis_id'], item['target'])] + [item]
            self.owner._transaction('Register Analysis variable', lambda: self.owner.write_metadata(data))
            return self.descriptor(args['analysis_id'])
        if operation == 'pre.research.remove':
            if set(args) != {'analysis_id', 'id'}:
                raise ValueError('Select one registered variable')
            data = self.owner.read_metadata()
            data['research_inputs'] = [r for r in data.get('research_inputs', [])
                                      if (r['analysis_id'], r['id']) != (args['analysis_id'], args['id'])]
            self.owner._transaction('Remove Analysis variable', lambda: self.owner.write_metadata(data))
            return self.descriptor(args['analysis_id'])
        if operation == 'pre.research.prepare':
            from .candidate_recipe import prepare_recipe
            return prepare_recipe(self.owner, args)
        raise ValueError('Unsupported native research command')
