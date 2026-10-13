"""Contact edits on the existing native FEM owner and its metadata/transactions."""
from copy import deepcopy
import json
import math
import uuid

from caelab.contact import CONTACT_FIELDS, default_contact, law_errors, number

OPERATIONS = ('pre.contact.set', 'pre.contact.remove', 'pre.contact.swap',
    'pre.contact.highlight', 'pre.contact.preview_rebind', 'pre.contact.apply_rebind',
    'pre.contact.cancel_rebind', 'pre.contact.prepare_meshes', 'pre.contact.inspect')


class ContactEditor:
    def __init__(self, fem):
        self.fem, self.owner = fem, fem.owner
        self.previews, self._overlays = {}, []

    def close(self):
        self._clear_overlay()
        self.previews.clear()

    def _data(self):
        data = self.fem._metadata()
        data.setdefault('contacts', [])
        data.setdefault('contact_history', [])
        if not isinstance(data['contacts'], list) or not isinstance(data['contact_history'], list):
            raise ValueError('Malformed contact metadata is retained; restore a valid saved draft')
        return data

    def _pair(self, object_id):
        rows = [row for row in self._data()['contacts'] if row['object_id'] == object_id]
        if len(rows) != 1:
            raise ValueError('Select an exact contact pair')
        return rows[0]

    def snapshot(self, source, names, *, region_id=None):
        from .fem_edit import _target
        from femmesh.meshtools import sub_shape_at_global_placement
        if (not names or len(names) > 256 or any(not name.startswith('Face') for name in names)
                or not source.Shape.isValid() or len(source.Shape.Solids) != 1):
            raise ValueError('Select nonempty faces on one valid solid body per side')
        target = _target(source, names)
        faces = []
        for name in names:
            face = sub_shape_at_global_placement(source, name)
            center = face.CenterOfMass
            uv = face.Surface.parameter(center)
            normal = face.normalAt(*uv)
            points, triangles = face.tessellate(max(1e-6, face.BoundBox.DiagonalLength / 200))
            if len(points) > 30000 or len(triangles) > 50000:
                raise ValueError('Face preview exceeds the bounded tessellation size')
            faces.append({'name': name, 'area_mm2': float(face.Area),
                'centroid_mm': [float(center.x), float(center.y), float(center.z)],
                'center_normal': [float(normal.x), float(normal.y), float(normal.z)],
                'preview_points_mm': [[float(p.x), float(p.y), float(p.z)] for p in points],
                'preview_triangles': [list(row) for row in triangles]})
        return {'region_id': region_id, 'label': source.Label, 'target': target, 'faces': faces}

    def _from_region(self, identifier):
        region, obj, names = self.fem._region(identifier)
        result = self.snapshot(obj, names, region_id=identifier)
        result['label'] = region['label']
        return result

    def _native_signature(self, obj):
        from .fem_edit import _hash, _references
        return _hash({'references': _references(obj),
            **{key: str(getattr(obj, key)) for key in ('SurfaceBehavior', 'Slope', 'Friction',
                'FrictionCoefficient', 'StickSlope', 'Adjust', 'EnableThermalContact')}})

    def _native(self, obj, record):
        """Update the effective native object when valid; raw invalid text stays saved."""
        refs = []
        for side in ('a', 'b'):
            value = record.get(side)
            if value:
                try:
                    source = self.owner._object(value['target']['object_id'])
                    refs.append((source, [face['name'] for face in value['target']['subelements']]))
                except ValueError:
                    pass
        obj.References = refs
        draft = record['draft']
        if not law_errors(draft):
            obj.SurfaceBehavior = 'Linear'
            obj.Slope = self.owner.App.Units.Quantity(str(number(draft['normal_stiffness_MPa_per_mm'])) + ' MPa/mm')
            obj.Friction = draft['tangential_law'] == 'coulomb'
            if obj.Friction:
                obj.FrictionCoefficient = number(draft['friction_coefficient'])
                obj.StickSlope = self.owner.App.Units.Quantity(str(number(draft['stick_stiffness_MPa_per_mm'])) + ' MPa/mm')
            obj.Adjust = self.owner.App.Units.Quantity('0 mm')
            obj.EnableThermalContact = False
        obj.Label = draft['label']
        record['native_signature'] = self._native_signature(obj)

    def _persist(self, obj, record, title):
        from .fem_edit import _hash
        result = {}
        def change():
            data = self._data()
            old = next((row for row in data['contacts'] if row['object_id'] == obj.Name), None)
            if old:
                data['contact_history'].append(deepcopy(old))
            self._native(obj, record)
            record['definition_sha256'] = _hash({key: record[key] for key in ('draft', 'a', 'b')})
            data['contacts'] = [row for row in data['contacts'] if row['object_id'] != obj.Name] + [record]
            self.owner.write_metadata(data)
            result.update(deepcopy(record))
        self.fem._transaction(title, change)
        return result

    def set(self, obj, arguments):
        from .fem_edit import _native_type
        if set(arguments) != {'draft'} or not isinstance(arguments['draft'], dict):
            raise ValueError('Contact edit requires a draft object')
        patch = arguments['draft']
        if set(patch) - CONTACT_FIELDS:
            raise ValueError('Unknown contact field: ' + ', '.join(sorted(set(patch) - CONTACT_FIELDS)))
        creating = _native_type(obj) == 'Fem::FemAnalysis'
        previous = None if creating else self._pair(obj.Name)
        draft = deepcopy(previous['draft']) if previous else default_contact()
        draft.update(deepcopy(patch))
        if not isinstance(draft['label'], str) or not draft['label'].strip() or len(draft['label']) > 160:
            raise ValueError('Contact name requires 1..160 characters')
        # Arbitrary partial numeric text is a draft; non-JSON values are not.
        json.dumps(draft, allow_nan=False)
        record = deepcopy(previous) if previous else {'analysis_id': obj.Name, 'a': None, 'b': None}
        record['draft'] = draft
        for side in ('a', 'b'):
            key = side + '_region_id'
            if key in patch and (not previous or patch[key] != previous['draft'].get(key)):
                record[side] = self._from_region(patch[key]) if patch[key] else None
        if creating:
            result = {}
            def create():
                import ObjectsFem
                contact = ObjectsFem.makeConstraintContact(self.owner.doc)
                obj.addObject(contact)
                record['object_id'] = contact.Name
                self._native(contact, record)
                from .fem_edit import _hash
                record['definition_sha256'] = _hash({key: record[key] for key in ('draft', 'a', 'b')})
                data = self._data()
                data['contacts'].append(record)
                self.owner.write_metadata(data)
                result.update(deepcopy(record))
            self.fem._transaction('new contact', create)
            return result
        return self._persist(obj, record, 'contact settings')

    def errors(self, record):
        from .fem_edit import _target
        errors = law_errors(record['draft'])
        def fail(path, message):
            errors.append({'path': path, 'message': message, 'severity': 'error', 'blocks_evaluation': True})
        for side in ('a', 'b'):
            value = record.get(side)
            if not value:
                fail(side, 'Select a nonempty face set')
                continue
            try:
                target = value['target']
                obj = self.owner._object(target['object_id'])
                names = [face['name'] for face in target['subelements']]
                if not names or any(not name.startswith('Face') for name in names):
                    raise ValueError('Contact requires explicit solid faces')
                if _target(obj, names) != target:
                    raise ValueError('UNRESOLVED: geometry changed; Preview and explicitly Apply a rebind')
                if not obj.Shape.isValid() or len(obj.Shape.Solids) != 1:
                    raise ValueError('Contact side requires one valid solid')
            except Exception as error:
                fail(side, str(error))
        if record.get('a') and record.get('b') and record['a']['target']['object_id'] == record['b']['target']['object_id']:
            fail('b', 'This route requires separate bodies; self-contact is not admitted')
        try:
            obj = self.owner._object(record['object_id'])
            analysis = self.owner._object(record['analysis_id'])
            if obj not in analysis.Group:
                raise ValueError('Contact no longer belongs to the selected Analysis')
            if self._native_signature(obj) != record.get('native_signature'):
                raise ValueError('Native contact changed outside this definition. Review and Apply its effective settings explicitly.')
        except Exception as error:
            fail('native', str(error))
        return errors

    def descriptor(self):
        rows = []
        for record in self._data()['contacts']:
            row = deepcopy(record)
            row['diagnostics'] = self.errors(record)
            # Geometry tessellations are retained for old/new preview, not copied to every UI poll.
            for side in ('a', 'b'):
                if row.get(side):
                    for face in row[side]['faces']:
                        face.pop('preview_points_mm', None)
                        face.pop('preview_triangles', None)
            rows.append(row)
        return {'pairs': rows, 'backend': 'structure.calculix.contact',
                'engineering_release': 'NOT_RELEASED'}

    def _clear_overlay(self):
        for scene, node in self._overlays:
            try:
                scene.removeChild(node)
            except (RuntimeError, ReferenceError):
                pass
        self._overlays.clear()

    def _overlay(self, snapshot, color):
        if not snapshot or not getattr(self.owner.App, 'GuiUp', False):
            return
        from pivy import coin
        scene = self.owner.Gui.activeDocument().activeView().getSceneGraph()
        root = coin.SoSeparator()
        material = coin.SoMaterial()
        material.diffuseColor = color
        material.transparency = .65
        root.addChild(material)
        for face in snapshot['faces']:
            coordinates, triangles = coin.SoCoordinate3(), coin.SoIndexedFaceSet()
            coordinates.point.setValues(0, len(face['preview_points_mm']), face['preview_points_mm'])
            indices = [index for triangle in face['preview_triangles'] for index in [*triangle, -1]]
            triangles.coordIndex.setValues(0, len(indices), indices)
            part = coin.SoSeparator()
            part.addChild(coordinates)
            part.addChild(triangles)
            root.addChild(part)
        scene.addChild(root)
        self._overlays.append((scene, root))

    def preview(self, obj, args):
        from .fem_edit import _hash
        if set(args) != {'side', 'selection'} or args['side'] not in ('a', 'b'):
            raise ValueError('Preview requires side A/B and explicit current face selection')
        selection = args['selection']
        if not isinstance(selection, dict) or set(selection) != {'object_id', 'subelements'}:
            raise ValueError('Select the new body and exact faces')
        record = self._pair(obj.Name)
        candidate = self.snapshot(self.owner._object(selection['object_id']), selection['subelements'])
        old = record.get(args['side'])
        def summary(value):
            faces = value['faces'] if value else []
            area = sum(face['area_mm2'] for face in faces)
            center = [sum(face['area_mm2'] * face['centroid_mm'][axis] for face in faces) / area
                      for axis in range(3)] if area else None
            return {'face_count': len(faces), 'area_mm2': area, 'centroid_mm': center,
                    'face_normals': [face['center_normal'] for face in faces]}
        token = 'P' + uuid.uuid4().hex
        self.previews.clear()
        self.previews[token] = {'object_id': obj.Name, 'definition_sha256': record['definition_sha256'],
            'side': args['side'], 'candidate': candidate}
        self._clear_overlay()
        self._overlay(old, (1., .6, .15))
        self._overlay(candidate, (.1, .6, 1.))
        self.owner.Gui.Selection.clearSelection()
        for face in selection['subelements']:
            self.owner.Gui.Selection.addSelection(self.owner.doc.Name, selection['object_id'], face)
        return {'preview_id': token, 'old': summary(old), 'new': summary(candidate),
            'normal_samples': 'CAD face-center normals; effective solver normals come from mapped element faces',
            'mesh_action': 'Rebind does not admit or refresh a mesh', 'applied': False}

    def apply_preview(self, obj, args):
        from .fem_edit import _target
        if set(args) != {'preview_id'} or args['preview_id'] not in self.previews:
            raise ValueError('Preview the explicitly selected replacement faces first')
        pending = self.previews[args['preview_id']]
        record = deepcopy(self._pair(obj.Name))
        if pending['object_id'] != obj.Name or pending['definition_sha256'] != record['definition_sha256']:
            raise ValueError('Contact changed after Preview; inspect it again')
        candidate = pending['candidate']
        target = candidate['target']
        source = self.owner._object(target['object_id'])
        if _target(source, [row['name'] for row in target['subelements']]) != target:
            raise ValueError('Candidate geometry changed after Preview')
        record[pending['side']] = deepcopy(candidate)
        record['draft'][pending['side'] + '_region_id'] = None
        result = self._persist(obj, record, 'apply contact rebind')
        self.close()
        return result

    def prepare_meshes(self, analysis):
        from .fem_edit import _native_type
        if _native_type(analysis) != 'Fem::FemAnalysis':
            raise ValueError('Select the contact Analysis')
        ids = sorted({record[side]['target']['object_id'] for record in self._data()['contacts']
                      if record['analysis_id'] == analysis.Name for side in ('a', 'b') if record.get(side)})
        if len(ids) < 2:
            raise ValueError('Select at least two separate contact bodies')
        result = []
        def create():
            import ObjectsFem
            for identifier in ids:
                body = self.owner._object(identifier)
                if not body.Shape.isValid() or len(body.Shape.Solids) != 1:
                    raise ValueError('Body mesh requires one valid solid')
                existing = [mesh for mesh in analysis.Group if hasattr(mesh, 'FemMesh') and getattr(mesh, 'Shape', None) is body]
                if len(existing) > 1:
                    raise ValueError('Choose one active mesh per body; duplicate body meshes are ambiguous')
                mesh = existing[0] if existing else ObjectsFem.makeMeshGmsh(self.owner.doc)
                if not existing:
                    mesh.Shape = body
                    mesh.ElementOrder = '2nd'
                    mesh.ElementDimension = '3D'
                    mesh.Label = body.Label + ' mesh'
                    analysis.addObject(mesh)
                result.append({'body_id': identifier, 'mesh_id': mesh.Name})
        self.fem._transaction('separate contact body meshes', create)
        return {'meshes': result, 'generated': False, 'next': 'Generate each body with the existing Mesh tab'}

    def dispatch(self, operation, args, target):
        if operation == 'pre.contact.inspect':
            if args or target:
                raise ValueError('Contact inspection takes no arguments')
            return self.descriptor()
        self.fem._assert_idle()
        if operation == 'pre.contact.cancel_rebind':
            if set(args) != {'preview_id'} or target:
                raise ValueError('Cancel needs only the preview identity')
            self.previews.pop(args['preview_id'], None)
            self._clear_overlay()
            return {'cancelled': True, 'applied': False}
        obj = self.fem._object(target)
        if operation == 'pre.contact.set':
            return self.set(obj, args)
        if operation == 'pre.contact.preview_rebind':
            return self.preview(obj, args)
        if operation == 'pre.contact.apply_rebind':
            return self.apply_preview(obj, args)
        if operation == 'pre.contact.prepare_meshes':
            if args:
                raise ValueError('Body mesh creation uses the selected contact Analysis')
            return self.prepare_meshes(obj)
        if args:
            raise ValueError('This contact action takes only the selected object')
        record = deepcopy(self._pair(obj.Name))
        if operation == 'pre.contact.swap':
            record['a'], record['b'] = record['b'], record['a']
            draft = record['draft']
            draft['a_region_id'], draft['b_region_id'] = draft['b_region_id'], draft['a_region_id']
            return self._persist(obj, record, 'swap contact A and B')
        if operation == 'pre.contact.highlight':
            self.owner.Gui.Selection.clearSelection()
            for side in ('a', 'b'):
                if record.get(side):
                    target = record[side]['target']
                    for face in target['subelements']:
                        self.owner.Gui.Selection.addSelection(self.owner.doc.Name, target['object_id'], face['name'])
            return {'selected': obj.Name}
        if operation == 'pre.contact.remove':
            def remove():
                data = self._data()
                data['contact_history'].append(record)
                data['contacts'] = [row for row in data['contacts'] if row['object_id'] != obj.Name]
                self.owner.write_metadata(data)
                self.owner.doc.removeObject(obj.Name)
            self.fem._transaction('remove contact', remove)
            return {'removed': record['object_id']}
        raise ValueError('Unsupported contact command')
