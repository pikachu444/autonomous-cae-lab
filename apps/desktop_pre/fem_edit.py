"""Typed edits of the open FreeCAD FEM owner, without a second model or solver.

Native APIs are pinned to FreeCAD 1.1.4: femmesh/gmshtools.py and
femtools/objecttools.py (prepare/compute/update_properties), ObjectsFem.py
(makeMeshRegion), App/FemMeshPyImp.cpp (copy), and femtools/ccxtools.py
(ViewObject.HighlightedNodes). Geometry references are exact BRep snapshots;
native face numbering alone never repairs a changed target.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import uuid

from .contact import ContactEditor, OPERATIONS as CONTACT_OPERATIONS
from . import nonlinear_material
from .freeze_analysis import CCX_FROM_NATIVE_TET10, require_ready_model
from .mesh_binding import PROPERTY_NAME, global_placement


OPERATIONS = (
    'pre.fem.mesh_settings', 'pre.fem.mesh_local_size', 'pre.fem.mesh_generate',
    'pre.fem.mesh_cancel', 'pre.fem.mesh_quality', 'pre.fem.mesh_highlight',
    'pre.fem.region_set', 'pre.fem.region_remove', 'pre.fem.condition_set',
    'pre.fem.condition_repair', 'pre.fem.material_set', 'pre.fem.task_edit',
) + CONTACT_OPERATIONS + nonlinear_material.OPERATIONS
from .law_native_material import OPERATIONS as LAW_NATIVE_OPERATIONS
OPERATIONS += LAW_NATIVE_OPERATIONS
from caelab.periodic_constraints import OPERATIONS as PERIODIC_OPERATIONS
OPERATIONS += PERIODIC_OPERATIONS
from caelab.pretension import OPERATIONS as PRETENSION_OPERATIONS
OPERATIONS += PRETENSION_OPERATIONS
from caelab.initial_field_conditions import OPERATIONS as INITIAL_OPERATIONS
OPERATIONS += INITIAL_OPERATIONS
from caelab.structural_field_ports import OPERATIONS as DISPLACEMENT_OPERATIONS
OPERATIONS += DISPLACEMENT_OPERATIONS
ABSOLUTE_JACOBIAN_FLOOR_MM3 = 1e-10
NORMALIZED_JACOBIAN_FLOOR = 256 * sys.float_info.epsilon
_MESH_FIELDS = {'CharacteristicLengthMin', 'CharacteristicLengthMax', 'ElementOrder',
                'ElementDimension', 'RecombineAll', 'Recombine3DAll', 'SubdivisionAlgorithm'}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('A finite numeric value is required')
    return float(value)


def _positive_id(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Select an exact positive native mesh ID')
    return value


def _native_type(obj):
    # Same native femutils.type_of_obj rule; importing FEM is unnecessary here.
    return getattr(getattr(obj, 'Proxy', None), 'Type', obj.TypeId)


def _brep(shape):
    value = shape.exportBrepToString()
    if not isinstance(value, str) or not value:
        raise ValueError('An exact native BRep is required')
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _target(obj, names):
    if not isinstance(names, list) or len(names) != len(set(names)):
        raise ValueError('Use distinct exact native subelement names')
    entries = []
    for name in names:
        if not isinstance(name, str) or not re.fullmatch(r'(Face|Edge|Solid|Vertex)[1-9][0-9]*', name):
            raise ValueError('Regions support exact body/SolidN, FaceN, EdgeN or VertexN targets')
        family, index = re.match(r'([A-Za-z]+)([0-9]+)', name).groups()
        shapes = getattr(obj.Shape, {'Face': 'Faces', 'Edge': 'Edges', 'Solid': 'Solids', 'Vertex': 'Vertexes'}[family])
        if int(index) > len(shapes):
            raise ValueError('STALE_TARGET: selected native subelement no longer exists')
        entries.append({'name': name, 'brep_sha256': _brep(shapes[int(index) - 1])})
    return {'object_id': obj.Name, 'type': obj.TypeId, 'brep_sha256': _brep(obj.Shape),
            'global_placement': global_placement(obj), 'subelements': entries}


def _references(obj):
    return [{'object_id': source.Name, 'subelements': list([names] if isinstance(names, str) else names)}
            for source, names in obj.References]


def _mesh_hash(native, *, node_table=None):
    nodes = []
    node_table = native.Nodes if node_table is None else node_table
    for key, point in sorted(node_table.items()):
        nodes.append([_positive_id(key), [_number(float(v)) for v in (point.x, point.y, point.z)]])
    elements = {family: [[_positive_id(key), list(native.getElementNodes(key))]
                         for key in sorted(getattr(native, family))]
                for family in ('Volumes', 'Faces', 'Edges')}
    return _hash({'nodes': nodes, 'elements': elements})


def _det(a):
    return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
            - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
            + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))


def _element_quality(native, identifier, *, node_table=None, family='Volumes'):
    """Same four C3D10 samples/floors as frozen_fem._gates, native mm/order."""
    node_table = native.Nodes if node_table is None else node_table
    ids = [_positive_id(key) for key in native.getElementNodes(identifier)]
    types = {'Volumes': {4:'C3D4', 6:'C3D6', 8:'C3D8', 10:'C3D10', 15:'C3D15', 20:'C3D20'},
             'Faces': {3:'S3', 4:'S4', 6:'S6', 8:'S8'}, 'Edges': {2:'B31', 3:'B32'}}[family]
    row = {'element_id': identifier, 'node_ids': ids, 'node_count': len(ids),
           'element_type': types.get(len(ids), 'UNSUPPORTED'), 'errors': []}
    if len(ids) not in types or len(set(ids)) != len(ids) or any(key not in node_table for key in ids):
        row['errors'].append('INVALID_OR_UNSUPPORTED_CONNECTIVITY')
        return row
    if family != 'Volumes' or len(ids) not in (4, 10):
        points = [(node_table[key].x, node_table[key].y, node_table[key].z) for key in ids]
        if any(not math.isfinite(float(v)) for point in points for v in point):
            row['errors'].append('NONFINITE_NATIVE_COORDINATES')
        row['jacobian_assessment'] = 'NOT_ASSESSED'
        return row
    points = [[float(v) for v in (node_table[key].x, node_table[key].y, node_table[key].z)]
              for key in (ids[slot] for slot in (CCX_FROM_NATIVE_TET10 if len(ids) == 10 else (1, 0, 2, 3)))]
    if any(not math.isfinite(v) for point in points for v in point):
        row['errors'].append('NONFINITE_NATIVE_COORDINATES')
        return row
    scale = max(max(p[axis] for p in points) - min(p[axis] for p in points) for axis in range(3))
    if not math.isfinite(scale) or scale <= 0:
        row['errors'].append('DEGENERATE_COORDINATE_SCALE')
        return row
    normalized = [[(p[axis] - points[0][axis]) / scale for axis in range(3)] for p in points]
    dL = ((-1., -1., -1.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
    sampled = []
    for corner in range(4 if len(ids) == 10 else 1):
        L = [.1381966011250105] * 4
        L[corner] = .5854101966249685
        deriv = [[(4 * L[a] - 1) * v for v in dL[a]] for a in range(4)] if len(ids) == 10 else dL
        if len(ids) == 10:
            deriv.extend([[4 * (L[a] * dL[b][r] + L[b] * dL[a][r]) for r in range(3)]
                          for a, b in ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))])
        sampled.append(_det([[sum(p[c] * d[r] for p, d in zip(normalized, deriv))
                              for r in range(3)] for c in range(3)]))
    scaled = min(sampled)
    try:
        absolute = scaled * scale ** 3
    except OverflowError:
        absolute = math.inf
    row.update(minimum_sampled_jacobian_mm3=absolute if math.isfinite(absolute) else None,
               minimum_scaled_sampled_jacobian=scaled if math.isfinite(scaled) else None)
    if not math.isfinite(absolute) or absolute <= ABSOLUTE_JACOBIAN_FLOOR_MM3:
        row['errors'].append('JACOBIAN_AT_OR_BELOW_1E_10_MM3')
    if not math.isfinite(scaled) or scaled <= NORMALIZED_JACOBIAN_FLOOR:
        row['errors'].append('NORMALIZED_JACOBIAN_SINGULAR')
    return row


def _distribution(values):
    if not values:
        return {'count': 0, 'minimum': None, 'maximum': None, 'bins': []}
    low, high = min(values), max(values)
    counts = [0] * (1 if low == high else 12)
    for value in values:
        index = 0 if low == high else min(11, int((value - low) / (high - low) * 12))
        counts[index] += 1
    width = (high - low) / len(counts)
    return {'count': len(values), 'minimum': low, 'maximum': high,
            'bins': [{'lower': low + i * width, 'upper': low + (i + 1) * width, 'count': n}
                     for i, n in enumerate(counts)]}


class FEMEditor:
    def __init__(self, owner):
        self.owner = owner
        self._pending = {}
        self._outcome_errors = {}
        self.contact = ContactEditor(self)

    def close(self):
        """Call before discarding the native owner; terminate only owned mesh work."""
        self.owner.assert_thread()
        self.contact.close()
        for pending in list(self._pending.values()):
            pending['cancelled'] = True
            if pending['tool'] is not None:
                pending['tool'].process.kill()

    def _metadata(self):
        data = deepcopy(self.owner.read_metadata())
        for key in ('regions', 'conditions', 'mesh_history'):
            data.setdefault(key, [])
            if not isinstance(data[key], list):
                raise ValueError('Malformed persisted FEM metadata: ' + key)
        return data

    def _object(self, target):
        if not isinstance(target, dict) or set(target) != {'object_id'}:
            raise ValueError('Select an exact target.object_id')
        obj = self.owner._object(target['object_id'])
        if obj.Document is not self.owner.doc:
            raise ValueError('Target belongs to another native document')
        return obj

    def _mesh(self, target):
        obj = self._object(target)
        if _native_type(obj) != 'Fem::FemMeshGmsh':
            raise ValueError('Select the actual native Gmsh mesh')
        if obj.Shape is None or obj.Shape.Document is not self.owner.doc:
            raise ValueError('Mesh needs an exact source in this document')
        return obj

    def _transaction(self, title, change):
        self.owner._transaction('CAE Lab FEM ' + title, change)

    def _assert_idle(self):
        if self._pending:
            raise ValueError('MESH_RUNNING: cancel or finish mesh generation before editing')
        gui = self.owner.Gui
        if gui.Control.activeDialog() or (gui.activeDocument() and gui.activeDocument().getInEdit()):
            raise ValueError('BUSY_EDIT: finish or cancel the native FEM task first')

    def _region(self, identifier):
        rows = [row for row in self._metadata()['regions'] if row['id'] == identifier]
        if len(rows) != 1:
            raise ValueError('Select an exact named region ID')
        row = rows[0]
        source = self.owner._object(row['target']['object_id'])
        names = [item['name'] for item in row['target']['subelements']]
        if source.Document is not self.owner.doc or not self._same_condition_target(row['target'], _target(source, names)):
            raise ValueError('STALE_REGION: geometry changed; explicitly repair the named region')
        return row, source, names

    def _record_condition(self, obj, region_id, direction_region_id=None):
        targets = []
        for ref in _references(obj):
            source = self.owner._object(ref['object_id'])
            if source.Document is not self.owner.doc:
                raise ValueError('Condition references another document')
            targets.append(_target(source, ref['subelements']))
        direction = None
        if _native_type(obj) == 'Fem::ConstraintForce' and getattr(obj, 'Direction', None):
            source, names = obj.Direction
            direction = _target(source, list([names] if isinstance(names, str) else names))
        data = self._metadata()
        old = next((row for row in data['conditions'] if row['object_id'] == obj.Name), None)
        record = {'object_id': obj.Name, 'native_type': _native_type(obj), 'region_id': region_id,
                  'targets': targets, 'direction_target': direction,
                  'direction_region_id': direction_region_id, 'qualification': 'UNKNOWN'}
        if old:
            record['previous_target_sha256'] = _hash(old)
        data['conditions'] = [row for row in data['conditions'] if row['object_id'] != obj.Name] + [record]
        self.owner.write_metadata(data)
        return record

    def _same_condition_target(self, saved, current):
        if saved == current:
            return True
        # Reuse an original v3 mesh/source proof; never rebind the saved target.
        if (not isinstance(saved, dict) or not isinstance(current, dict) or
                set(saved) != set(current) or any(saved.get(k) != current.get(k)
                for k in ('object_id', 'type', 'global_placement')) or
                [v.get('name') for v in saved.get('subelements', [])] !=
                [v.get('name') for v in current.get('subelements', [])]):
            return False
        if any(set(v) != {'name', 'brep_sha256'} or
                not isinstance(v['brep_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', v['brep_sha256'])
                for v in saved.get('subelements', [])):
            return False
        source = self.owner._object(saved['object_id'])
        for mesh in self.owner.doc.Objects:
            if not hasattr(mesh, 'FemMesh') or getattr(mesh, 'Shape', None) is not source:
                continue
            try:
                proof = self.owner.mesh_bindings.validate(mesh)
                origin = proof['source']
                if (proof['schema_version'] == 3 and origin['brep_sha256'] == saved['brep_sha256'] and
                        origin['name'] == saved['object_id'] and origin['type'] == saved['type'] and
                        origin['global_placement'] == saved['global_placement'] and
                        proof.get('source_equivalence', {}).get('subelement_correspondence') ==
                        'SAME_FACE_EDGE_VERTEX_ORDER_AND_ORIENTATION'):
                    # Bind each historical child digest to that exact original
                    # full BRep, not merely to a valid-looking digest/name.
                    import Part
                    reference = Part.Shape()
                    reference.importBrepFromString(origin['brep'])
                    for child in saved['subelements']:
                        match = re.fullmatch(r'(Face|Edge|Solid|Vertex)([1-9][0-9]*)', child['name'])
                        if match is None:
                            raise ValueError('Invalid original subelement name')
                        shapes = getattr(reference, {'Face':'Faces', 'Edge':'Edges',
                            'Solid':'Solids', 'Vertex':'Vertexes'}[match[1]])
                        index = int(match[2])-1
                        if index >= len(shapes) or _brep(shapes[index]) != child['brep_sha256']:
                            raise ValueError('Original subelement digest differs from retained BRep')
                    return True
            except (ValueError, KeyError, TypeError, AttributeError, RuntimeError, ImportError):
                continue
        return False

    def _condition_errors(self, obj, data):
        row = next((row for row in data['conditions'] if row['object_id'] == obj.Name), None)
        if row is None:
            return ['UNTRACKED_TARGET: explicitly confirm/repair this condition target']
        try:
            current = [_target(self.owner._object(ref['object_id']), ref['subelements']) for ref in _references(obj)]
            if not current or len(current) != len(row['targets']) or not all(
                    self._same_condition_target(old, now) for old, now in zip(row['targets'], current)):
                return ['STALE_CONDITION_TARGET: explicitly select and repair references after geometry changes']
            direction = None
            if _native_type(obj) == 'Fem::ConstraintForce' and getattr(obj, 'Direction', None):
                source, names = obj.Direction
                direction = _target(source, list([names] if isinstance(names, str) else names))
            if not self._same_condition_target(row.get('direction_target'), direction):
                return ['STALE_FORCE_DIRECTION: explicitly repair the direction target']
        except Exception as error:
            return [str(error)]
        return []

    def descriptor(self):
        self.owner.assert_thread()
        data = self._metadata()
        active = {item['id'] for item in self._pending.values()}
        for row in data['mesh_history']:
            if row['state'] in ('RUNNING', 'CANCELLING') and row['id'] not in active:
                row.update(state='INTERRUPTED', error='No matching live native Gmsh process; explicitly generate again')
            if row['id'] in self._outcome_errors:
                row.update(state='OUTCOME_UNCONFIRMED', error=self._outcome_errors[row['id']])
        for row in data['regions']:
            try:
                self._region(row['id'])
                row['validation'] = 'EXACT_TARGET_MATCH'
            except Exception as error:
                row['validation'], row['error'] = 'UNRESOLVED', str(error)
        for row in data['conditions']:
            try:
                obj = self.owner._object(row['object_id'])
                row['errors'] = self._condition_errors(obj, data)
            except Exception as error:
                row['errors'] = [str(error)]
        for obj in self.owner.doc.Objects:
            if (_native_type(obj) in ('Fem::ConstraintFixed', 'Fem::ConstraintForce', 'Fem::ConstraintDisplacement')
                    and not any(row['object_id'] == obj.Name for row in data['conditions'])):
                data['conditions'].append({'object_id': obj.Name, 'native_type': _native_type(obj),
                    'qualification': 'UNKNOWN', 'errors': self._condition_errors(obj, data)})
        for row in data['conditions']:
            try:
                obj = self.owner._object(row['object_id'])
                row['native_references'] = _references(obj)
                if _native_type(obj) == 'Fem::ConstraintForce':
                    row.update(force=str(obj.Force), reversed=bool(obj.Reversed),
                               direction=str(obj.Direction), amplitude=bool(obj.EnableAmplitude))
            except Exception:
                pass  # Missing targets remain editable unresolved records.
        return {**data, 'contact': self.contact.descriptor(), 'mesh_busy': bool(self._pending),
            'meshes': [{'object_id': obj.Name, 'settings': self._mesh_settings(obj),
                'element_orders': list(obj.getEnumerationsOfProperty('ElementOrder')),
                'element_dimensions': list(obj.getEnumerationsOfProperty('ElementDimension')),
                'source_id': getattr(getattr(obj, 'Shape', None), 'Name', None),
                'refinement_ids': [ref.Name for ref in obj.MeshRegionList]}
                for obj in self.owner.doc.Objects if _native_type(obj) == 'Fem::FemMeshGmsh'],
            'active_mesh_generations': [{'history_id': item['id'], 'mesh_id': name,
            'state': 'CANCELLING' if item['cancelled'] else 'RUNNING'} for name, item in self._pending.items()],
            'execution_scope': 'FreeCAD CalculiX static analysis; native writer support is checked for the selected model',
            'engineering_release': 'NOT_RELEASED'}

    def quality(self, mesh, *, offset=0, limit=200):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 4096:
            raise ValueError('Quality table needs offset>=0 and 1<=limit<=4096')
        rows, bad, invalid, absolute, scaled = [], [], [], [], []
        native = mesh.FemMesh
        # FreeCAD materializes the entire node dictionary on each property read.
        # Keep one local snapshot for this synchronous quality/hash call only.
        node_table = native.Nodes
        family = 'Volumes' if native.Volumes else 'Faces' if native.Faces else 'Edges'
        volumes = sorted(getattr(native, family))
        for index, identifier in enumerate(volumes):
            row = _element_quality(native, _positive_id(identifier), node_table=node_table, family=family)
            if row['errors']:
                bad.append(identifier)
            # Legacy quality floors remain observations. Native admission uses
            # connectivity, finite coordinates and the measured Jacobian sign.
            input_errors = set(row['errors']) - {'JACOBIAN_AT_OR_BELOW_1E_10_MM3', 'NORMALIZED_JACOBIAN_SINGULAR'}
            if row['element_type'] in {'C3D4', 'C3D10'}:
                determinant = row.get('minimum_scaled_sampled_jacobian')
                if determinant is None or determinant <= 0:
                    input_errors.add('INVALID_SIGNED_JACOBIAN')
            if input_errors:
                invalid.append(identifier)
            for key, values in (('minimum_sampled_jacobian_mm3', absolute), ('minimum_scaled_sampled_jacobian', scaled)):
                if row.get(key) is not None:
                    values.append(row[key])
            if offset <= index < offset + limit:
                rows.append(row)
        try:
            mesh_hash = _mesh_hash(native, node_table=node_table)
        except ValueError:
            mesh_hash = None  # Preserve quality rows/reasons even for invalid native coordinates.
        return {'mesh_id': mesh.Name, 'mesh_sha256': mesh_hash, 'offset': offset,
                'total_elements': len(volumes), 'rows': rows, 'bad_element_count': len(bad),
                'invalid_input_element_count': len(invalid), 'invalid_input_element_ids': invalid[:4096],
                'bad_element_ids': bad[:4096], 'bad_ids_truncated': len(bad) > 4096,
                'absolute_jacobian_mm3': _distribution(absolute), 'normalized_jacobian': _distribution(scaled),
                'gates': {'absolute_jacobian_floor_mm3': ABSOLUTE_JACOBIAN_FLOOR_MM3,
                          'normalized_jacobian_floor': NORMALIZED_JACOBIAN_FLOOR},
                'limitation': 'Tetrahedra have sampled Jacobians; other native element families have connectivity checks only.',
                'engineering_release': 'NOT_RELEASED'}

    def dispatch(self, operation, arguments, target):
        self.owner.assert_thread()
        if operation in DISPLACEMENT_OPERATIONS:
            from .structural_transfer_native import dispatch
            from caelab.structural_field_ports import consume_displacement_source
            arguments, source = consume_displacement_source(arguments)
            return dispatch(self, operation, arguments, target, source=source)
        if operation in LAW_NATIVE_OPERATIONS:
            from .law_native_material import dispatch
            return dispatch(self, operation, arguments, target)
        if operation not in OPERATIONS or not isinstance(arguments, dict):
            raise ValueError('Unsupported typed FEM operation')
        args = deepcopy(arguments)
        if operation in INITIAL_OPERATIONS:
            from .initial_field_native import dispatch
            return dispatch(self, operation, arguments, target)
        if operation in PRETENSION_OPERATIONS:
            from .pretension_native import dispatch
            return dispatch(self, operation, arguments, target)
        if operation in PERIODIC_OPERATIONS:
            from .periodic_native import dispatch
            return dispatch(self, operation, args, target)
        if operation in CONTACT_OPERATIONS:
            return self.contact.dispatch(operation, args, target)
        if operation in nonlinear_material.OPERATIONS:
            obj = self._object(target)
            if operation == 'pre.fem.nonlinear_settings':
                self._assert_idle()
                return nonlinear_material.settings(self, obj, args)
            expected = {'analysis_id'} if operation.endswith('_read') else {'analysis_id', 'draft'}
            if set(args) != expected:
                raise ValueError('기본 재료와 해석, 소성 표 초안을 지정하세요.')
            if operation.endswith('_read'):
                return nonlinear_material.read(self, obj, args['analysis_id'])
            self._assert_idle()
            action = nonlinear_material.save if operation.endswith('_save') else nonlinear_material.apply
            return action(self, obj, args['analysis_id'], args['draft'])
        if operation == 'pre.fem.mesh_quality':
            if set(args) - {'offset', 'limit'}:
                raise ValueError('Quality accepts only offset and limit')
            return self.quality(self._mesh(target), **args)
        if operation == 'pre.fem.mesh_cancel':
            if set(args) != {'history_id'}:
                raise ValueError('Cancel needs the exact mesh generation history_id')
            mesh = self._mesh(target)
            pending = self._pending.get(mesh.Name)
            if pending is None or pending['id'] != args['history_id']:
                raise ValueError('No matching active native mesh generation')
            pending['cancelled'] = True
            pending['tool'].process.kill()  # Native QProcess termination; finish signal owns cleanup.
            return {'history_id': pending['id'], 'state': 'CANCELLING'}
        self._assert_idle()
        if operation == 'pre.fem.mesh_highlight':
            if set(args) - {'element_ids', 'node_ids', 'mesh_sha256'}:
                raise ValueError('Highlight needs exact element/node IDs and optional quality mesh hash')
            mesh = self._mesh(target)
            if 'mesh_sha256' in args and args['mesh_sha256'] != _mesh_hash(mesh.FemMesh):
                raise ValueError('STALE_QUALITY: mesh changed after the displayed quality table')
            nodes = set()
            for key in ('element_ids', 'node_ids'):
                if not isinstance(args.get(key, []), list) or len(args.get(key, [])) > 4096:
                    raise ValueError('Highlight accepts bounded explicit ID lists')
            for identifier in args.get('element_ids', []):
                if _positive_id(identifier) not in mesh.FemMesh.Volumes:
                    raise ValueError('Selected native volume no longer exists')
                nodes.update(mesh.FemMesh.getElementNodes(identifier))
            nodes.update(_positive_id(identifier) for identifier in args.get('node_ids', []))
            if not nodes <= set(mesh.FemMesh.Nodes):
                raise ValueError('Selected native node no longer exists')
            mesh.ViewObject.HighlightedNodes = sorted(nodes)
            return {'mesh_id': mesh.Name, 'highlighted_node_ids': sorted(nodes)}
        if operation == 'pre.fem.mesh_settings':
            return self._settings(self._mesh(target), args)
        if operation == 'pre.fem.mesh_local_size':
            return self._local_size(self._mesh(target), args)
        if operation == 'pre.fem.mesh_generate':
            if args:
                raise ValueError('Generate uses the selected mesh native settings, no hidden overrides')
            return self._generate(self._mesh(target))
        if operation == 'pre.fem.region_set':
            return self._region_set(self._object(target), args)
        if operation == 'pre.fem.region_remove':
            if target or set(args) != {'region_id'}:
                raise ValueError('Remove needs only an exact region_id')
            data = self._metadata()
            if not any(row['id'] == args['region_id'] for row in data['regions']):
                raise ValueError('Region no longer exists')
            if any(row.get('region_id') == args['region_id'] or row.get('direction_region_id') == args['region_id']
                   for row in data['conditions']):
                raise ValueError('Region is used by a condition; repair that condition explicitly first')
            if any(row.get('region_id') == args['region_id'] for row in data.get('mesh_local_sizes', [])):
                raise ValueError('Region is used by native mesh refinement')
            data['regions'] = [row for row in data['regions'] if row['id'] != args['region_id']]
            self._transaction('remove region', lambda: self.owner.write_metadata(data))
            return {'removed': args['region_id']}
        if operation in {'pre.fem.condition_set', 'pre.fem.condition_repair'}:
            return self._condition(self._object(target), args, repair=operation.endswith('repair'))
        if operation == 'pre.fem.material_set':
            return self._material(self._object(target), args)
        if args:
            raise ValueError('Native task edit needs only its exact object target')
        obj = self._object(target)
        if _native_type(obj) not in {'Fem::FemMeshGmsh', 'Fem::MeshRegion', 'Fem::MaterialCommon',
                                    'Fem::ConstraintFixed', 'Fem::ConstraintForce'}:
            raise ValueError('Use native FEM Tasks only for supported mesh/material/Fixed/Force objects')
        if self.owner.Gui.activeDocument() is None or self.owner.App.ActiveDocument is not self.owner.doc:
            raise ValueError('Activate this native document before opening its task')
        if self.owner.Gui.activeDocument().setEdit(obj.Name) is False:
            raise ValueError('The native FEM task could not be opened')
        return {'object_id': obj.Name, 'state': 'NATIVE_TASK_OPEN', 'executed': False}

    def _settings(self, mesh, args):
        allowed = {'min_size', 'max_size', 'unit', 'element_order', 'element_dimension', 'element_type'}
        if set(args) - allowed or not args:
            raise ValueError('Use explicit global size/order/dimension/type fields')
        updates = {}
        if 'min_size' in args or 'max_size' in args:
            if not isinstance(args.get('unit'), str) or not args['unit'].strip():
                raise ValueError('Declare the mesh size unit')
            for key, prop in (('min_size', 'CharacteristicLengthMin'), ('max_size', 'CharacteristicLengthMax')):
                if key in args:
                    value = self.owner.App.Units.Quantity(str(_number(args[key])) + ' ' + args['unit'])
                    mm = float(value.getValueAs('mm').Value)
                    if mm < 0:
                        raise ValueError('Mesh size must be nonnegative; native zero means automatic/unbounded')
                    updates[prop] = value
            minimum = float(updates.get('CharacteristicLengthMin', mesh.CharacteristicLengthMin).Value)
            maximum = float(updates.get('CharacteristicLengthMax', mesh.CharacteristicLengthMax).Value)
            if maximum and minimum > maximum:
                raise ValueError('Minimum mesh size exceeds the maximum')
        for key, prop in (('element_order', 'ElementOrder'), ('element_dimension', 'ElementDimension')):
            if key in args:
                if args[key] not in mesh.getEnumerationsOfProperty(prop):
                    raise ValueError('Choose a native advertised ' + prop)
                updates[prop] = args[key]
        if 'element_type' in args:
            if args['element_type'] not in ('C3D4', 'C3D10'):
                raise ValueError('Use the native Gmsh properties for shell, beam, wedge or hexahedral meshing')
            order = '2nd' if args['element_type'] == 'C3D10' else '1st'
            if 'ElementOrder' in updates and updates['ElementOrder'] != order:
                raise ValueError('Element type and native order conflict')
            updates.update(ElementOrder=order, ElementDimension='3D', RecombineAll=False,
                           Recombine3DAll=False, SubdivisionAlgorithm='None')
            if 'element_dimension' in args and args['element_dimension'] != '3D':
                raise ValueError('Solid tetrahedral element type requires explicit 3D dimension')
        if not updates:
            raise ValueError('No native mesh setting was supplied')
        def change():
            for name, value in updates.items():
                if any(path == name for path, expression in getattr(mesh, 'ExpressionEngine', [])):
                    raise ValueError('Mesh setting is expression-driven; edit its native expression')
                setattr(mesh, name, value)
        self._transaction('mesh settings', change)
        return {'mesh_id': mesh.Name, 'settings': self._mesh_settings(mesh), 'mesh_generated': False,
                'run_admissibility': 'CHECK_NATIVE_WRITER_INPUT'}

    def _mesh_settings(self, mesh):
        return {name: str(getattr(mesh, name)) for name in sorted(_MESH_FIELDS) if hasattr(mesh, name)}

    def _region_set(self, obj, args):
        if set(args) - {'region_id', 'label', 'subelements', 'expected_target_sha256'} or 'label' not in args or 'subelements' not in args:
            raise ValueError('Named region requires label and explicit body/face/edge subelements')
        if not isinstance(args['label'], str) or not args['label'].strip() or len(args['label']) > 160:
            raise ValueError('Region label requires 1..160 characters')
        identifier = args.get('region_id') or 'R' + uuid.uuid4().hex
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,95}', identifier):
            raise ValueError('Invalid exact region identity')
        data = self._metadata()
        old = next((row for row in data['regions'] if row['id'] == identifier), None)
        if old and args.get('expected_target_sha256') != _hash(old['target']):
            raise ValueError('Repair needs the exact previous region target hash')
        record = {'id': identifier, 'label': args['label'], 'target': _target(obj, args['subelements']),
                  'qualification': 'UNKNOWN'}
        if old:
            record['previous_target_sha256'] = _hash(old['target'])
        record['target_sha256'] = _hash(record['target'])
        data['regions'] = [row for row in data['regions'] if row['id'] != identifier] + [record]
        self._transaction('named region', lambda: self.owner.write_metadata(data))
        return deepcopy(record)

    def _local_size(self, mesh, args):
        if set(args) - {'region_id', 'size', 'unit', 'refinement_id'} or not {'region_id', 'size', 'unit'} <= set(args):
            raise ValueError('Local sizing needs named region, size and explicit unit')
        region, source, names = self._region(args['region_id'])
        if source is not mesh.Shape:
            raise ValueError('Refinement must target this exact mesh source; native nearest rebinding is forbidden')
        if not names:
            if len(source.Shape.Solids) != 1:
                raise ValueError('Body refinement requires one exact solid or explicit SolidN targets')
            names = ['Solid1']
        value = self.owner.App.Units.Quantity(str(_number(args['size'])) + ' ' + args['unit'])
        if float(value.getValueAs('mm').Value) <= 0:
            raise ValueError('Local mesh size must be positive')
        existing = None
        if args.get('refinement_id'):
            existing = self.owner._object(args['refinement_id'])
            if existing not in mesh.MeshRegionList or _native_type(existing) != 'Fem::MeshRegion':
                raise ValueError('Select an exact native refinement belonging to this mesh')
        result = {}
        def change():
            nonlocal existing
            if existing is None:
                import ObjectsFem
                existing = ObjectsFem.makeMeshRegion(self.owner.doc, mesh, value, name='MeshRegion')
            existing.References = [(source, names)]
            existing.CharacteristicLength = value
            data = self._metadata()
            data.setdefault('mesh_local_sizes', [])
            record = {'mesh_id': mesh.Name, 'object_id': existing.Name, 'region_id': region['id'],
                      'target': deepcopy(region['target']), 'size_mm': float(value.getValueAs('mm').Value)}
            data['mesh_local_sizes'] = [row for row in data['mesh_local_sizes'] if row['object_id'] != existing.Name] + [record]
            self.owner.write_metadata(data)
            result.update(record)
        self._transaction('local mesh size', change)
        return result

    def _condition(self, obj, args, *, repair):
        if repair and 'use_native_references' in args:
            if set(args) != {'use_native_references'} or args['use_native_references'] is not True:
                raise ValueError('현재 native 대상 확인만 명시적으로 요청하세요.')
            return self._confirm_native_condition(obj)
        allowed = {'region_id', 'kind', 'analysis_id', 'force', 'unit', 'direction_region_id', 'reversed'}
        if set(args) - allowed or 'region_id' not in args:
            raise ValueError('Condition edit/repair requires an explicit named region')
        if repair and set(args) - {'region_id', 'direction_region_id'}:
            raise ValueError('Target repair changes only explicitly selected references')
        region, source, names = self._region(args['region_id'])
        kind = _native_type(obj)
        creating = kind == 'Fem::FemAnalysis' and not repair
        if creating:
            if args.get('kind') not in ('Fixed', 'Force', 'Displacement'):
                raise ValueError('Create only a native Fixed, Force or Displacement condition in the selected Analysis')
            kind = 'Fem::Constraint' + args['kind']
        elif kind not in ('Fem::ConstraintFixed', 'Fem::ConstraintForce', 'Fem::ConstraintDisplacement'):
            raise ValueError('Select a native Fixed/Force/Displacement condition, or its Analysis to create one')
        faces = bool(names) and all(name.startswith('Face') for name in names)
        vertices = bool(names) and all(name.startswith('Vertex') for name in names)
        if not faces and not (vertices and kind in ('Fem::ConstraintFixed', 'Fem::ConstraintDisplacement')):
            raise ValueError('Fixed/Displacement는 정확한 Face 또는 Vertex, Force는 Face를 선택하세요.')
        if 'kind' in args and kind != 'Fem::Constraint' + args['kind']:
            raise ValueError('Condition kind differs from the selected native object')
        if 'analysis_id' in args and self.owner._object(args['analysis_id']) is not (obj if creating else obj.getParentGroup()):
            raise ValueError('Condition belongs to another Analysis')
        force = None
        if 'force' in args:
            if kind != 'Fem::ConstraintForce' or not isinstance(args.get('unit'), str):
                raise ValueError('Force edit requires an explicit native force unit')
            force = self.owner.App.Units.Quantity(str(_number(args['force'])) + ' ' + args['unit'])
            if float(force.getValueAs('N').Value) <= 0:
                raise ValueError('Use a positive native force and explicit direction/reversal')
        if creating and kind == 'Fem::ConstraintForce' and force is None:
            raise ValueError('Creating Force requires an explicit force magnitude and unit')
        if kind != 'Fem::ConstraintForce' and set(args) & {'force', 'unit', 'direction_region_id', 'reversed'}:
            raise ValueError('This support does not accept force settings')
        if 'reversed' in args and type(args['reversed']) is not bool:
            raise ValueError('Native reversal must be boolean')
        direction = None
        if args.get('direction_region_id'):
            _, direction_source, direction_names = self._region(args['direction_region_id'])
            if len(direction_names) != 1 or not direction_names[0].startswith('Edge'):
                raise ValueError('Force direction requires one explicitly selected native edge')
            direction = (direction_source, direction_names)
        if not creating and kind == 'Fem::ConstraintForce' and getattr(obj, 'Direction', None) and 'direction_region_id' not in args:
            record = next((row for row in self._metadata()['conditions'] if row['object_id'] == obj.Name), None)
            direction_source, direction_names = obj.Direction
            current_direction = _target(direction_source, list([direction_names] if isinstance(direction_names, str) else direction_names))
            if record is None or record.get('direction_target') != current_direction:
                raise ValueError('Explicitly confirm/repair the Force direction region too, or select native reference normal')
        result = {}
        def change():
            condition = obj
            if creating:
                import ObjectsFem
                factory = {'Fem::ConstraintFixed': ObjectsFem.makeConstraintFixed,
                           'Fem::ConstraintForce': ObjectsFem.makeConstraintForce,
                           'Fem::ConstraintDisplacement': getattr(ObjectsFem, 'makeConstraintDisplacement', None)}[kind]
                if factory is None:
                    raise ValueError('Installed native displacement factory is unavailable')
                condition = factory(self.owner.doc)
                obj.addObject(condition)
            condition.References = [(source, names)]
            if kind == 'Fem::ConstraintForce':
                if force is not None:
                    condition.Force = force
                if 'direction_region_id' in args:
                    condition.Direction = direction  # Explicit None resets to native reference normal.
                if 'reversed' in args:
                    condition.Reversed = args['reversed']
                condition.EnableAmplitude = False
            result.update(self._record_condition(condition, region['id'], args.get('direction_region_id')))
        self._transaction('repair condition target' if repair else 'condition settings', change)
        return result

    def _confirm_native_condition(self, obj):
        """Explicitly adopt reviewed native targets; leave native condition values intact."""
        kind = _native_type(obj)
        if kind not in ('Fem::ConstraintFixed', 'Fem::ConstraintForce'):
            raise ValueError('현재 대상 확인은 native 고정과 힘 조건에서 지원합니다.')
        data = self._metadata()
        old = next((row for row in data['conditions'] if row['object_id'] == obj.Name), None)
        # A task may change references, but cannot serve as proof that edited CAD
        # still identifies the old faces. Geometry repair remains a separate action.
        if old:
            for saved in old['targets'] + ([old['direction_target']] if old.get('direction_target') else []):
                source = self.owner._object(saved['object_id'])
                names = [row['name'] for row in saved['subelements']]
                if not self._same_condition_target(saved, _target(source, names)):
                    raise ValueError('형상이 변경됐습니다. 3D에서 면을 선택하고 선택한 면으로 변경을 사용하세요.')
        for source, names in obj.References:
            if (source.Document is not self.owner.doc or self.owner._object(source.Name) is not source
                    or not source.Shape.isValid()):
                raise ValueError('현재 문서의 유효한 형상을 적용 대상으로 지정하세요.')
        refs = _references(obj)
        if not refs:
            raise ValueError('FreeCAD에서 조건의 적용 대상을 지정하세요.')
        targets = []
        for ref in refs:
            source, names = self.owner._object(ref['object_id']), ref['subelements']
            if source.Document is not self.owner.doc or not names:
                raise ValueError('현재 문서의 정확한 면 또는 꼭짓점을 지정하세요.')
            faces = all(re.fullmatch(r'Face[1-9][0-9]*', name) for name in names)
            vertices = all(re.fullmatch(r'Vertex[1-9][0-9]*', name) for name in names)
            if not faces and not (kind == 'Fem::ConstraintFixed' and vertices):
                raise ValueError('힘은 면, 고정은 면 또는 꼭짓점에 적용하세요.')
            targets.append(_target(source, names))
        direction = None
        if kind == 'Fem::ConstraintForce' and getattr(obj, 'Direction', None):
            source, names = obj.Direction
            names = [names] if isinstance(names, str) else list(names)
            if (source.Document is not self.owner.doc or self.owner._object(source.Name) is not source
                    or not source.Shape.isValid() or len(names) != 1 or
                    not re.fullmatch(r'Edge[1-9][0-9]*', names[0])):
                raise ValueError('힘 방향은 현재 문서의 모서리 하나로 지정하세요.')
            direction = _target(source, names)
        def matching_region(target):
            if target is None:
                return None
            for row in data['regions']:
                try:
                    self._region(row['id'])
                    if self._same_condition_target(row['target'], target):
                        return row['id']
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
            return None
        result = {}
        def change():
            result.update(self._record_condition(obj,
                matching_region(targets[0]) if len(targets) == 1 else None, matching_region(direction)))
        self._transaction('confirm native condition targets', change)
        return result

    def _material(self, obj, args):
        if _native_type(obj) != 'Fem::MaterialCommon' or obj.Category != 'Solid':
            raise ValueError('Select the native isotropic solid material')
        if set(args) != {'young_modulus', 'unit', 'poisson_ratio'} or not isinstance(args['unit'], str):
            raise ValueError('Material edit requires Young modulus, explicit unit and Poisson ratio')
        modulus = self.owner.App.Units.Quantity(str(_number(args['young_modulus'])) + ' ' + args['unit'])
        ratio = _number(args['poisson_ratio'])
        if float(modulus.getValueAs('MPa').Value) <= 0 or not -1 < ratio < .5:
            raise ValueError('Isotropic elasticity requires E>0 and -1<nu<0.5')
        values = dict(obj.Material)
        values.update(YoungsModulus=str(modulus), PoissonRatio=str(ratio))
        self._transaction('isotropic material', lambda: setattr(obj, 'Material', values))
        return {'object_id': obj.Name, 'material': dict(obj.Material), 'executed': False}

    def _refinement_errors(self, mesh):
        data, errors = self._metadata(), []
        for refinement in mesh.MeshRegionList:
            record = next((row for row in data.get('mesh_local_sizes', []) if row['object_id'] == refinement.Name), None)
            try:
                if record is None:
                    raise ValueError('Untracked refinement; explicitly confirm named region and local size')
                _, source, names = self._region(record['region_id'])
                reference_names = names or ['Solid1']
                if (source is not mesh.Shape or _target(source, names) != record['target']
                        or _references(refinement) != [{'object_id': source.Name, 'subelements': reference_names}]):
                    raise ValueError('Refinement target changed; explicitly repair its local sizing')
            except Exception as error:
                errors.append(refinement.Name + ': ' + str(error))
        if getattr(mesh, 'MeshBoundaryLayerList', []):
            errors.append('Boundary layers are outside the admitted tetrahedral mesh edit scope')
        if getattr(mesh, 'MeshGroupList', []):
            errors.append('External mesh groups require native review; no implicit target rebinding is admitted')
        return errors

    def _generation_stamp(self, mesh):
        return _hash({'source': _target(mesh.Shape, []), 'settings': self._mesh_settings(mesh),
                      'mesh_sha256': _mesh_hash(mesh.FemMesh),
                      'refinements': [{'id': obj.Name, 'references': _references(obj),
                                      'length': str(obj.CharacteristicLength)} for obj in mesh.MeshRegionList]})

    def _history(self, identifier, **updates):
        data = self._metadata()
        record = next(row for row in data['mesh_history'] if row['id'] == identifier)
        record.update(updates)
        self.owner.write_metadata(data)

    def _generate(self, mesh, *, owned_directory=None):
        require_ready_model(self.owner.doc, owner=self.owner)
        errors = self._refinement_errors(mesh)
        if errors:
            raise ValueError(errors[0])
        shape = mesh.Shape.Shape.copy(True, False)
        if not shape.isValid() or not any(getattr(shape, family) for family in ('Solids', 'Faces', 'Edges')):
            raise ValueError('메시를 만들 유효한 고체·면·선을 지정하세요.')
        from femmesh.gmshtools import GmshTools
        identifier = 'G' + uuid.uuid4().hex
        pending = {'id': identifier, 'mesh': mesh, 'old_mesh': mesh.FemMesh.copy(),
                   'old_binding': getattr(mesh, PROPERTY_NAME, None), 'cancelled': False,
                   'document': self.owner.doc, 'session_id': getattr(self.owner, 'session_id', None), 'tool': None}
        self._pending[mesh.Name] = pending
        try:
            def prepare():
                tool = GmshTools(mesh)
                pending['tool'] = tool
                # Prevent unguarded native automatic replacement. The same native
                # update_properties implementation is called in our completion txn.
                tool.process.finished.disconnect(tool._process_finished)
                if owned_directory is None:
                    tool.prepare()
                else:
                    directory = Path(owned_directory).resolve(strict=True)
                    if not directory.is_dir() or any(directory.iterdir()):
                        raise ValueError('Candidate mesh requires a fresh owned directory')
                    # Same FreeCAD 1.1.4 prepare steps; supply its supported path
                    # argument instead of inheriting desktop meshing preferences.
                    tool.load_properties()
                    tool.update_mesh_data()
                    tool.get_tmp_file_paths(str(directory))
                    paths = [tool.working_dir, tool.temp_file_geometry,
                             tool.temp_file_geo, tool.temp_file_mesh]
                    if any(not Path(path).resolve().is_relative_to(directory) for path in paths):
                        raise ValueError('Native meshing files escaped the candidate directory')
                    tool.get_gmsh_command()
                    tool.write_gmsh_input_files()
                    pending['owned_directory'] = str(directory)
                pending['stamp'] = self._generation_stamp(mesh)
                data = self._metadata()
                data['mesh_history'].append({'id': identifier, 'mesh_id': mesh.Name, 'state': 'RUNNING',
                    'source': _target(mesh.Shape, []), 'settings': self._mesh_settings(mesh),
                    'previous_mesh_sha256': _mesh_hash(pending['old_mesh']), 'engineering_release': 'NOT_RELEASED'})
                self.owner.write_metadata(data)
            self._transaction('prepare native Gmsh', prepare)
            tool = pending['tool']
            tool.process.finished.connect(lambda code, status: self._finish(mesh.Name, code, status))
            tool.process.errorOccurred.connect(lambda error: self._process_error(mesh.Name, error))
            tool.compute()
        except Exception as error:
            self._pending.pop(mesh.Name, None)
            data = self._metadata()
            if any(row['id'] == identifier for row in data['mesh_history']):
                self._transaction('record mesh start failure', lambda: self._history(identifier,
                    state='FAILED', error=str(error), prior_mesh_preserved=True))
            raise ValueError('Native Gmsh preparation failed; existing mesh preserved: ' + str(error)) from error
        record = next(row for row in self._metadata()['mesh_history'] if row['id'] == identifier)
        return {'history_id': identifier, 'mesh_id': mesh.Name, 'state': record['state'],
                'solver_execution': 'NOT_PERFORMED'}

    def _process_error(self, name, error):
        # QProcess.ProcessError.FailedToStart is 0; crashes also emit finished.
        value = getattr(error, 'value', error)
        if value == 0:
            self._finish(name, -1, None)

    def _finish(self, name, code, status):
        self.owner.assert_thread()
        pending = self._pending.get(name)
        if pending is None:
            return
        mesh, tool = pending['mesh'], pending['tool']
        if (getattr(self.owner, 'closed', False) or self.owner.doc is not pending['document']
                or getattr(self.owner, 'session_id', None) != pending['session_id']):
            self._pending.pop(name, None)
            return  # Never dereference a deleted/reopened native document.
        error, terminal, quality = None, 'FAILED', None
        try:
            if self.owner._object(name) is not mesh:
                raise ValueError('Selected native mesh was replaced/deleted during generation')
            if pending['cancelled']:
                terminal = 'CANCELLED'
                raise ValueError('Native Gmsh generation was cancelled; prior mesh retained')
            if code != 0 or getattr(status, 'value', status) != 0:
                raise ValueError('Native Gmsh did not exit successfully')
            require_ready_model(self.owner.doc, owner=self.owner)
            if self._generation_stamp(mesh) != pending['stamp']:
                raise ValueError('STALE_GENERATION: source, mesh or settings changed; generated output not applied')
            def apply():
                nonlocal quality
                tool.update_properties()
                if not mesh.FemMesh.Nodes or not any(getattr(mesh.FemMesh, family) for family in ('Volumes', 'Faces', 'Edges')):
                    raise ValueError('Native Gmsh produced an empty mesh; prior mesh retained')
                self.owner.mesh_bindings.slotChangedObject(mesh, 'FemMesh')
                quality = self.quality(mesh, limit=1)
                try:
                    self.owner.mesh_bindings.validate(mesh)
                    binding_error = None
                except Exception as error:
                    binding_error = str(error)
                # A generated invalid/unsupported mesh is an editable native draft.
                # Preserve its predecessor in the same FCStd, outside Analysis.Group.
                archive = self.owner.doc.addObject('Fem::FemMeshObject', 'CAELabMeshHistory' + pending['id'])
                archive.Label = mesh.Label + ' 이전 메시'
                archive.FemMesh = pending['old_mesh']
                archive.ViewObject.Visibility = False
                self._history(pending['id'], state='SUCCEEDED', mesh_sha256=quality['mesh_sha256'],
                              previous_mesh_object_id=archive.Name, previous_binding=pending['old_binding'],
                              run_admissibility='BLOCKED' if quality['bad_element_count'] or binding_error else 'QUALITY_GATES_PASSED',
                              binding_error=binding_error,
                              quality={key: quality[key] for key in ('total_elements', 'bad_element_count', 'invalid_input_element_count',
                                       'absolute_jacobian_mm3', 'normalized_jacobian')})
            try:
                self._transaction('apply generated native mesh', apply)
            except Exception:
                # Native abortTransaction is authoritative. Restore only if the
                # generated replacement survived abort, never overwrite late edits.
                if (_mesh_hash(mesh.FemMesh) != _mesh_hash(pending['old_mesh'])
                        or getattr(mesh, PROPERTY_NAME, None) != pending['old_binding']):
                    def restore():
                        if _mesh_hash(mesh.FemMesh) != _mesh_hash(pending['old_mesh']):
                            mesh.FemMesh = pending['old_mesh']
                        if pending['old_binding'] is not None:
                            setattr(mesh, PROPERTY_NAME, pending['old_binding'])
                        elif PROPERTY_NAME in mesh.PropertiesList:
                            mesh.removeProperty(PROPERTY_NAME)
                    self._transaction('restore prior native mesh', restore)
                raise
            terminal = 'SUCCEEDED'
        except Exception as exc:
            error = str(exc)
            try:
                log = bytes(tool.process.readAllStandardError()).decode('utf-8', errors='replace')[-4000:]
            except Exception:
                log = ''
            try:
                preserved = (self.owner._object(name) is mesh
                             and _mesh_hash(mesh.FemMesh) == _mesh_hash(pending['old_mesh']))
            except Exception:
                preserved = None  # Deleted/replaced native target cannot be claimed preserved.
            try:
                self._transaction('record mesh outcome', lambda: self._history(pending['id'], state=terminal,
                    error=error, native_log=log, prior_mesh_preserved=preserved))
            except Exception as publication_error:
                self._outcome_errors[pending['id']] = error + '; native outcome metadata could not be committed: ' + str(publication_error)
        finally:
            self._pending.pop(name, None)

    def validate_for_run(self, analysis, *, for_displacement_transfer=False):
        """Return admission errors; native freeze/writer/headless gates still apply."""
        self.owner.assert_thread()
        errors = []
        def fail(path, message):
            errors.append({'path': path, 'message': message, 'severity': 'error', 'blocks_evaluation': True})
        try:
            require_ready_model(self.owner.doc, owner=self.owner)
        except Exception as error:
            fail('assembly_pose_candidate', str(error))
            return errors
        if self._pending:
            fail('mesh', 'Native mesh generation is still running')
        if analysis.Document is not self.owner.doc or _native_type(analysis) != 'Fem::FemAnalysis':
            fail('analysis', 'Select the exact native Analysis in this document')
            return errors
        if for_displacement_transfer:
            solvers = [obj for obj in analysis.Group if _native_type(obj) == 'Fem::SolverCcxTools'
                       and not getattr(obj, 'Suppressed', False)]
            if len(solvers) != 1:
                fail('solver', '변위를 적용할 CalculiX 해석을 하나 선택하세요.')
                return errors
            try:
                from .freeze_contact import collect
                collect(analysis, solvers[0], self, capture_only=True, for_displacement_transfer=True)
            except Exception as error:
                fail('displacement_transfer', str(error))
            # accepted_definition binds and strictly validates the final union
            # before any input is packaged. This capture alone cannot run.
            return errors
        data = self._metadata()
        specialized = (analysis.Name in data.get('initial_fields', {})
            or analysis.Name in data.get('pretension_editors', {})
            or any(row.get('analysis_id') == analysis.Name for row in self.contact._data().get('contacts', []))
            or any(row.get('analysis_id') == analysis.Name
                   for key in ('pretension_sections', 'contact_programs', 'periodic_constraints',
                               'convergence_drafts') for row in data.get(key, [])))
        if not specialized:
            solvers = [obj for obj in analysis.Group if _native_type(obj) == 'Fem::SolverCcxTools'
                       and not getattr(obj, 'Suppressed', False)]
            if len(solvers) != 1:
                fail('solver', 'CalculiX 솔버를 하나 지정하세요.')
                return errors
            try:
                from .native_calculix import validate_analysis
                from .mesh_binding import PROPERTY_NAME
                mesh, _ = validate_analysis(analysis, solvers[0])
                if PROPERTY_NAME in getattr(mesh, 'PropertiesList', []):
                    self.owner.mesh_bindings.validate(mesh)
                quality = self.quality(mesh, limit=1)
                if not quality['total_elements'] or quality['invalid_input_element_count']:
                    fail(mesh.Name, '메시의 연결·좌표 또는 사면체의 비양수 Jacobian을 확인하세요.')
            except Exception as error:
                fail(analysis.Name, str(error))
            for obj in analysis.Group:
                if any(row.get('object_id') == obj.Name for row in data.get('conditions', [])):
                    for message in self._condition_errors(obj, data):
                        fail(obj.Name, message)
            return errors
        programs = [row for row in self._metadata().get('contact_programs', [])
                    if row.get('analysis_id') == analysis.Name]
        active_contact = any(_native_type(obj) in ('Fem::ConstraintContact', 'Fem::ConstraintTie')
                             and not getattr(obj, 'Suppressed', False) for obj in analysis.Group)
        if not active_contact and any(row.get('draft', {}).get('procedure') != 'static' for row in programs):
            fail('steps', '무접촉 단일 고체의 첫 지원은 정적 단계입니다. 동적 단계는 이 경로에서 실행하지 않습니다.')
            return errors
        if nonlinear_material.uses_solid_route(analysis, self._metadata()):
            solvers = [obj for obj in analysis.Group if _native_type(obj) == 'Fem::SolverCcxTools'
                       and not getattr(obj, 'Suppressed', False)]
            if len(solvers) != 1:
                fail('solver', 'Contact requires one active native CalculiX solver')
                return errors
            try:
                # Reuse the exact export admission without saving or exporting.
                # collect performs body-local mappings and has no solver side effect.
                from .freeze_contact import collect
                collect(analysis, solvers[0], self)
            except Exception as error:
                fail('contact', str(error))
            return errors
        if any(row.get('analysis_id') == analysis.Name
               for row in self._metadata().get('contact_programs', [])):
            fail('steps', '저장된 해석 단계는 활성 접촉 해석이 필요합니다. 접촉쌍을 적용한 뒤 다시 확인하세요')
            return errors
        meshes = [obj for obj in analysis.Group if hasattr(obj, 'FemMesh')]
        if len(meshes) != 1:
            fail('mesh', 'The admitted execution requires exactly one existing solid mesh')
            return errors
        mesh, data = meshes[0], self._metadata()
        try:
            self.owner.mesh_bindings.validate(mesh)
            if mesh.Shape.Document is not self.owner.doc or not mesh.Shape.Shape.copy(True, False).isValid() or len(mesh.Shape.Shape.Solids) != 1:
                fail('mesh', 'Execution requires one valid exact source solid')
            quality = self.quality(mesh, limit=1)
            if not quality['total_elements'] or quality['bad_element_count']:
                fail('mesh', 'Actual C3D10 mesh fails absolute/normalized sampled Jacobian/type gates')
        except Exception as error:
            fail('mesh', str(error))
        for obj in analysis.Group:
            if _native_type(obj) in ('Fem::ConstraintFixed', 'Fem::ConstraintForce', 'Fem::ConstraintDisplacement'):
                for message in self._condition_errors(obj, data):
                    fail(obj.Name, message)
        return errors
