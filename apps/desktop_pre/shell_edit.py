"""Native FreeCAD shell editing, draft persistence, explicit reference recovery.

Owned by E1. This file does not change the solid/contact/nonlinear editors.
All public mutations run in the existing owner's main-thread transaction.
"""
from copy import deepcopy
import math
import re
import uuid

from caelab.shell_model import (DEFAULTS, FIELDS, ShellError, issue, digest,
    number, prepare_mesh, validate_draft, reverse, check_supports)

OPERATIONS = ('pre.shell.inspect', 'pre.shell.begin', 'pre.shell.repair_objects', 'pre.shell.save_draft',
              'pre.shell.preview_rebind', 'pre.shell.apply_rebind', 'pre.shell.cancel_rebind',
              'pre.shell.preview', 'pre.shell.reverse', 'pre.shell.apply', 'pre.shell.freeze',
              'pre.shell.region_selection', 'pre.shell.import_regions', 'pre.shell.reverse_region')
READ_ONLY = {'pre.shell.region_selection', 'pre.shell.inspect', 'pre.shell.preview_rebind', 'pre.shell.cancel_rebind', 'pre.shell.preview'}
SETTINGS = {'AnalysisType':'static', 'ModelSpace':'3D', 'GeometricalNonlinearity':'linear',
            'MaterialNonlinearity':'linear', 'SplitInputWriter':False,
            'ExcludeBendingStiffness':False, 'BeamShellResultOutput3D':True}
INPUT_KINDS = {'Fem::SolverCcxTools', 'Fem::MaterialCommon', 'Fem::ElementGeometry2D',
               'Fem::ConstraintFixed', 'Fem::ConstraintPressure', 'Fem::FemMeshGmsh', 'Fem::FemMeshObject'}
RESULT_PREFIXES = ('Fem::FemResult', 'Fem::ResultMechanical', 'Fem::FemPost')


def native_type(obj):
    # Pinned femutils.type_of_obj rule; no second FEM object abstraction.
    return getattr(getattr(obj, 'Proxy', None), 'Type', obj.TypeId)


def _refs(obj):
    return [{'object_id': source.Name, 'subelements': [names] if isinstance(names,str) else list(names)}
            for source, names in getattr(obj, 'References', [])]


# Only exact signed zeros in supported analytic plane axes are normalized.
# All nonzero digits, topology/flags, ordering, orientation and whitespace stay
# exact. A historical digest alone is NOT enough: its preimage is required.
_BREP_V1 = '\nCASCADE Topology V1, (c) Matra-Datavision\n'
_BREP_EVIDENCE_SCHEMA = 'caelab-shell-brep-evidence/1'
_MAX_BREP_BYTES = 64 * 1024 * 1024
_MAX_RETAINED_BREP_BYTES = 2 * 1024 * 1024
_FIXED_REAL = re.compile(r'(?<!\S)[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?(?=\s|$)')


def _brep_zero_identity(text):
    """Normalize plane axis signed zeros, not topology or arbitrary BREP tokens.

    No float conversion/rounding is used. Only a complete simple analytic
    Surfaces table is recognized; unknown/variable-length surface records stay
    byte-exact. Plane origin, type, nonzero axis values, cylinder records and
    every token outside these plane axes remain unchanged.
    """
    if (not isinstance(text, str) or not text.startswith(_BREP_V1)
            or len(text) > _MAX_BREP_BYTES or not text.isascii()):
        raise ValueError('검증 가능한 native BREP V1 원문이 없습니다.')
    lines = text.splitlines(keepends=True)
    headers = [i for i, line in enumerate(lines) if line.startswith('Surfaces ')]
    if len(headers) != 1:
        return text
    start = headers[0]
    header = re.fullmatch(r'Surfaces ([0-9]+)\s*', lines[start])
    if header is None:
        return text
    count = int(header[1])
    end = start + 1 + count
    if end >= len(lines) or not lines[end].startswith(
            ('Polygon3D ', 'PolygonOnTriangulations ', 'Triangulations ', 'TShapes ')):
        return text
    rows = []
    for index in range(start + 1, end):
        tokens = list(re.finditer(r'\S+', lines[index]))
        values = [m[0] for m in tokens]
        # V1 plane = type + origin(3) + direction/X/Y axes(9).
        # Cylinder has the same frame plus radius, but is kept exact here.
        if not values or (values[0], len(values)) not in (('1', 13), ('2', 14)):
            return text
        if any(not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', v)
               for v in values[1:]):
            return text
        rows.append((index, tokens))
    for index, tokens in rows:
        if tokens[0][0] == '1':
            for token in reversed(tokens[4:13]):
                if token[0] == '-0':
                    line = lines[index]
                    lines[index] = line[:token.start()] + '0' + line[token.end():]
    return ''.join(lines)


def _saved_brep_export_candidate(text):
    """Recover a possible *old export string*, never infer physical equality.

    FreeCAD 1.1.4 exportBrepToString uses an unformatted stringstream and
    TopoShape::exportBrep's V1 ShapeSet. An FCStd ASCII member can instead have
    fixed-point stream formatting (15 digits, 17 in the geometry tables).
    Re-render just that formatting. The caller MUST authenticate the resulting
    string against the already recorded JSON-string digest, or refuse it.
    Unknown formatting, lost digits, flags changed by a reader, etc. therefore
    do not authorize a binding. No CAD objects are read/created/recomputed here.
    """
    _brep_zero_identity(text)  # Bound the input and require the actual V1 header.
    precision, locations, output = 15, False, []
    for line in text.splitlines(keepends=True):
        if line.startswith('Locations '):
            locations = True
        if line.startswith(('Curve2ds ', 'Curves ', 'Surfaces ')):
            locations = False
            precision = 17
        if line.startswith(('Polygon3D ', 'PolygonOnTriangulations ', 'Triangulations ', 'TShapes ')):
            locations = False
            precision = 15
        def render(match):
            value = float(match[0])
            if not math.isfinite(value):
                raise ValueError('비유한 저장 BREP 수치입니다.')
            return format(value, f'.{precision}g')
        # Location matrix rows use setw(15) and precision(15), not fixed(15).
        tokens = line.split()
        if locations and len(tokens) == 4 and all(_FIXED_REAL.fullmatch(t) for t in tokens):
            values = [float(t) for t in tokens]
            if not all(math.isfinite(v) for v in values):
                raise ValueError('비유한 저장 BREP 배치입니다.')
            line = ' '.join(format(v, '15.15g') for v in values) + ' \n'
        else:
            line = _FIXED_REAL.sub(render, line)
        output.append(line)
    return ''.join(output)


def _saved_shape_brep(obj):
    """Read the exact named Shape property from this document's FCStd, read-only.

    This is the existing native project working copy, not a guessed Windows
    source path, a new document, a save, or an unrelated frozen result. Even a
    valid archive is only a candidate until its export digest authenticates it.
    """
    from pathlib import Path
    import zipfile
    from caelab import native_cad
    filename = getattr(obj.Document, 'FileName', '')
    if not filename or Path(filename).suffix.lower() != '.fcstd':
        raise ValueError('현재 문서의 저장 FCStd가 없습니다.')
    with zipfile.ZipFile(filename) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('저장 FCStd에 중복 member가 있습니다.')
        tree = native_cad._xml(archive)
        objects = [o for o in tree.findall('./ObjectData/Object') if o.get('name') == obj.Name]
        if len(objects) != 1:
            raise ValueError('저장 FCStd의 형상 객체가 모호하거나 없습니다.')
        properties = [p for p in objects[0].findall('./Properties/Property')
                      if p.get('name') == 'Shape' and p.get('type') == 'Part::PropertyPartShape']
        if len(properties) != 1 or len(properties[0].findall('Part')) != 1:
            raise ValueError('저장된 native Shape 속성의 원문을 확인할 수 없습니다.')
        member = native_cad._safe_member(properties[0].find('Part').get('file'))
        info = archive.getinfo(member)
        if info.file_size > _MAX_BREP_BYTES:
            raise ValueError('저장 BREP 검증 크기를 초과했습니다.')
        return archive.read(info).decode('ascii')


def _geometry(obj):
    from .mesh_binding import global_placement
    if not obj.Shape.isValid():
        raise ShellError([issue(obj.Label, '형상이 유효하지 않습니다.')])
    return {'object_id':obj.Name, 'brep':digest(obj.Shape.exportBrepToString()),
            'placement':global_placement(obj)}


def _global_shape(obj, subelement):
    if not re.fullmatch(r'(Face|Edge|Vertex)[1-9][0-9]*', subelement):
        raise ValueError('실제 면, 모서리 또는 꼭짓점을 선택하세요.')
    shape = obj.Shape.copy()
    shape.Placement = obj.getGlobalPlacement()
    return shape.getElement(subelement)


class ShellEditor:
    def __init__(self, owner):
        self.owner = owner
        self._pending = {}
        self._overlay = None
        self._binding_breps = {}

    def close(self):
        self.clear_preview()
        self._pending.clear()
        self._binding_breps.clear()

    def _object(self, name):
        obj = self.owner.doc.getObject(name) if isinstance(name,str) else None
        if obj is None or obj.Document is not self.owner.doc:
            raise ShellError([issue(str(name), '참조 대상을 찾지 못했습니다. 명시적으로 다시 선택하세요.')])
        return obj

    def _all(self):
        data = deepcopy(self.owner.read_metadata())
        data.setdefault('shells', {})
        if not isinstance(data['shells'], dict):
            raise ValueError('저장된 셸 편집 정보를 읽을 수 없습니다.')
        return data

    def _record(self, analysis_id):
        records = self._all()['shells']
        if analysis_id not in records:
            raise ShellError([issue('analysis', '해석과 셸 메시를 먼저 선택하세요.')])
        return records[analysis_id]

    def _store(self, analysis_id, record, title):
        def change():
            data = self._all()
            data['shells'][analysis_id] = deepcopy(record)
            self.owner.write_metadata(data)
        self.owner._transaction('CAE Lab '+title, change)

    def _mesh(self, draft):
        mesh = self._object(draft['mesh_id'])
        if not hasattr(mesh, 'FemMesh') or mesh.FemMesh.Volumes:
            raise ShellError([issue(mesh.Label, '체적 요소가 없는 native 셸 메시를 선택하세요.')])
        from .mesh_binding import global_placement
        pose=global_placement(mesh)
        if pose[:3]!=[0.,0.,0.] or pose[3:6]!=[0.,0.,0.] or abs(pose[6])!=1.:
            raise ShellError([issue(mesh.Label,'첫 S8 경로는 전역 좌표로 저장된 메시를 사용합니다. mesh 객체/상위 조립의 Placement를 좌표에 반영한 native 메시로 교체하세요.')])
        nodes = {int(n): [float(p.x),float(p.y),float(p.z)] for n,p in mesh.FemMesh.Nodes.items()}
        elements = {int(e): list(map(int,mesh.FemMesh.getElementNodes(e))) for e in mesh.FemMesh.Faces}
        if not elements or any(len(c) != 8 for c in elements.values()):
            raise ShellError([issue(mesh.Label, '첫 실행은 전체 source mesh가 S8이어야 합니다. 삼각형/막/체적 요소를 분리하세요.')])
        return mesh, nodes, elements

    def _stamp(self, draft):
        from .fem_edit import _mesh_hash
        from .mesh_binding import global_placement
        mesh, _, _ = self._mesh(draft)
        analysis = self._object(draft['analysis_id'])
        refs = list(draft.get('face_refs', []))
        for row in draft.get('regions', []):
            refs.extend(row.get('face_refs', []))
        for obj in analysis.Group:
            if native_type(obj) == 'Fem::ConstraintFixed' and not getattr(obj,'Suppressed',False):
                refs.extend(_refs(obj))
        geometry = {}
        for row in refs:
            obj = self._object(row['object_id'])
            for name in row['subelements']:
                _global_shape(obj, name)  # Refuse stale subelement names as well.
            geometry[obj.Name] = _geometry(obj)
        source = getattr(mesh, 'Shape', None)
        source_value = _geometry(source) if source is not None else None
        return {'mesh_id':mesh.Name, 'mesh_sha256':_mesh_hash(mesh.FemMesh),
                'mesh_placement':global_placement(mesh), 'mesh_source':source_value,
                'reference_geometry':geometry,
                'fixed_references':{o.Name:_refs(o) for o in analysis.Group
                    if native_type(o)=='Fem::ConstraintFixed' and not getattr(o,'Suppressed',False)}}

    def restore_binding_evidence(self, evidence):
        """Attach only hash-authenticated historical text from verified open.

        This cache contains old BREP preimages, NEVER a current stamp/fingerprint.
        It cannot replace a binding, an applied model, or a newer raw edit.
        """
        if (not isinstance(evidence, dict) or set(evidence) != {'schema', 'breps'}
                or evidence.get('schema') != _BREP_EVIDENCE_SCHEMA
                or not isinstance(evidence['breps'], dict)):
            raise ValueError('저장된 셸 BREP 증거 형식이 잘못됐습니다.')
        checked = {}
        size = 0
        for key, text in evidence['breps'].items():
            _brep_zero_identity(text)
            size += len(text.encode('ascii'))
            if size > _MAX_RETAINED_BREP_BYTES or digest(text) != key:
                raise ValueError('저장된 셸 BREP 증거의 원 확인값이 다릅니다.')
            checked[key] = text
        # Retain previously verified evidence, rather than replacing it with a
        # late response. None of it authorizes a different draft/target/shape.
        self._binding_breps.update(checked)

    def _binding_brep(self, geometry):
        """Return an authenticated preimage of this exact historical digest."""
        key = geometry['brep']
        retained = self._binding_breps.get(key)
        if retained is not None and digest(retained) == key:
            return retained
        obj = self._object(geometry['object_id'])
        current = obj.Shape.exportBrepToString()
        if digest(current) == key:
            _brep_zero_identity(current)
            return current
        import zipfile
        from xml.etree.ElementTree import ParseError
        try:
            saved = _saved_shape_brep(obj)
            for candidate in (saved, _saved_brep_export_candidate(saved)):
                if digest(candidate) == key:
                    return candidate
        except (OSError, ValueError, KeyError, UnicodeError, zipfile.BadZipFile, ParseError):
            pass  # Missing proof is a stale binding, not a new baseline.
        raise ValueError('이전 BREP 확인값에 일치하는 원문 증거가 없어 대상 동등성을 확인할 수 없습니다.')

    def _same_geometry(self, previous, current):
        if previous == current:
            return True
        if (not isinstance(previous, dict) or not isinstance(current, dict)
                or set(previous) != {'object_id', 'brep', 'placement'}
                or set(current) != set(previous)
                or any(previous[k] != current[k] for k in ('object_id', 'placement'))):
            return False
        try:
            old_text = self._binding_brep(previous)
            obj = self._object(current['object_id'])
            new_text = obj.Shape.exportBrepToString()
            # Do not compare a later, changed observation to an earlier stamp.
            return (digest(new_text) == current['brep'] and
                    _brep_zero_identity(old_text) == _brep_zero_identity(new_text))
        except (ValueError, KeyError, TypeError, AttributeError, RuntimeError):
            return False

    def _same_binding(self, previous, current):
        if previous == current:
            return True
        if not isinstance(previous, dict) or not isinstance(current, dict) or set(previous) != set(current):
            return False
        geometric = {'mesh_source', 'reference_geometry'}
        if (not geometric <= set(previous) or
                any(previous[k] != current[k] for k in set(previous) - geometric)):
            return False
        old_refs, new_refs = previous['reference_geometry'], current['reference_geometry']
        if not isinstance(old_refs, dict) or not isinstance(new_refs, dict) or set(old_refs) != set(new_refs):
            return False
        return (self._same_geometry(previous['mesh_source'], current['mesh_source']) and
                all(self._same_geometry(old_refs[k], new_refs[k]) for k in old_refs))

    def export_binding_evidence(self):
        """Existing Project.save retains proofs, not a rewritten model or stamp.

        Unavailable/oversized old evidence is omitted, not invented; such a
        record remains an editable invalid draft and cannot use this bridge.
        Duplicate source/reference preimages are retained only once.
        """
        wanted = {}
        for record in self._all()['shells'].values():
            applied = record.get('applied') or {}
            for binding in (record.get('draft', {}).get('binding'),
                            applied.get('draft', {}).get('binding'),
                            applied.get('native', {}).get('binding')):
                if not isinstance(binding, dict):
                    continue
                refs = binding.get('reference_geometry', {})
                for geometry in [binding.get('mesh_source'), *refs.values()]:
                    if isinstance(geometry, dict) and isinstance(geometry.get('brep'), str):
                        wanted.setdefault(geometry['brep'], geometry)
        breps, size = {}, 0
        for key, geometry in sorted(wanted.items()):
            try:
                text = self._binding_brep(geometry)
                length = len(text.encode('ascii'))
            except (ValueError, KeyError, TypeError, AttributeError, RuntimeError, UnicodeError):
                continue
            if size + length <= _MAX_RETAINED_BREP_BYTES:
                breps[key] = text
                size += length
        return {'schema': _BREP_EVIDENCE_SCHEMA, 'breps': breps}

    def _binding(self, draft):
        if not self._same_binding(draft.get('binding'), self._stamp(draft)):
            raise ShellError([issue('elements',
                '메시 또는 참조 형상이 바뀌었습니다. 해당 면/요소를 다시 선택하고 대상을 명시적으로 복구하세요.')])

    def _members(self, draft, *, complete=False):
        analysis = self._object(draft['analysis_id'])
        if native_type(analysis) != 'Fem::FemAnalysis':
            raise ShellError([issue('analysis','native FEM 해석을 선택하세요.')])
        active = [o for o in analysis.Group if not getattr(o,'Suppressed',False)]
        unsupported = [o for o in active if native_type(o) not in INPUT_KINDS
                       and not native_type(o).startswith(RESULT_PREFIXES)]
        if unsupported:
            raise ShellError([issue(o.Label, '첫 S8 경로에서 지원하지 않는 활성 해석 객체입니다. native 해석에서 명시적으로 분리하세요.')
                              for o in unsupported])
        by = {k:[o for o in active if native_type(o)==k] for k in INPUT_KINDS}
        for key, kind in [('solver_id','Fem::SolverCcxTools'),('material_id','Fem::MaterialCommon'),
                          ('geometry_id','Fem::ElementGeometry2D'),('pressure_id','Fem::ConstraintPressure')]:
            objects = by[kind]
            if 'regions' in draft and key in ('geometry_id', 'pressure_id'):
                expected = [row[key] for row in draft['regions'] if row[key]]
                if len(set(expected)) != len(expected) or set(expected) != {o.Name for o in objects}:
                    raise ShellError([issue('regions/'+key, '영역의 native 속성 할당이 중복되거나 해석 소속과 다릅니다. 제거한 영역 객체는 native 해석에서도 명시적으로 분리하세요.')])
                if complete and len(expected) != len(draft['regions']):
                    raise ShellError([issue('regions/'+key, '모든 영역 속성을 먼저 적용하세요.')])
                continue
            if len(objects)>1 or objects and objects[0].Name != draft.get(key):
                raise ShellError([issue(key, '활성 native 객체와 저장된 적용 대상이 다릅니다. 해석 객체를 확인하세요.')])
            if (complete or key=='solver_id') and not objects:
                raise ShellError([issue(key, '필수 native 객체가 없습니다. 속성을 명시적으로 적용하세요.')])
        meshes = [o for o in active if hasattr(o,'FemMesh') and not native_type(o).startswith(RESULT_PREFIXES)]
        if len(meshes)!=1 or meshes[0].Name != draft['mesh_id']:
            raise ShellError([issue('mesh_id','현재 해석에는 선택한 셸 메시 하나만 참여해야 합니다.')])
        return analysis, by

    def _fixed(self, draft, selected_mesh):
        analysis = self._object(draft['analysis_id'])
        mesh = self._object(draft['mesh_id'])
        nodes = set(draft.get('fixed_nodes', []))
        for obj in analysis.Group:
            if native_type(obj)!='Fem::ConstraintFixed' or getattr(obj,'Suppressed',False):
                continue
            refs = _refs(obj)
            if not refs:
                raise ShellError([issue(obj.Label,'native 고정 조건의 참조가 비어 있습니다. 고정 대상을 복구하세요.')])
            for row in refs:
                source = self._object(row['object_id'])
                for name in row['subelements']:
                    shape = _global_shape(source, name)
                    family = re.match('[A-Za-z]+',name).group()
                    method = getattr(mesh.FemMesh, 'getNodesBy'+family)
                    found = set(map(int,method(shape)))
                    if not found or not found <= set(selected_mesh['nodes']):
                        raise ShellError([issue(obj.Label+'/'+name,
                            '고정 대상에 대응하는 참여 메시 절점이 없거나 제외된 절점이 있습니다.')])
                    nodes.update(found)
        return check_supports(selected_mesh, nodes)

    def _native_state(self, draft):
        if 'regions' in draft:
            from .shell_region_native import state
            return state(self, draft)
        _, by = self._members(draft, complete=True)
        solver = self._object(draft['solver_id'])
        material = self._object(draft['material_id'])
        geometry = self._object(draft['geometry_id'])
        pressure = self._object(draft['pressure_id'])
        if material.Category != 'Solid':
            raise ShellError([issue(material.Label,'균질 등방 탄성 고체 재료를 선택하세요.')])
        return {'members':sorted([k,o.Name] for k,items in by.items() for o in items),
                'solver':{k:getattr(solver,k) for k in SETTINGS},
                'material':dict(material.Material), 'material_refs':_refs(material),
                'thickness_mm':float(geometry.Thickness.getValueAs('mm').Value),
                'offset':float(geometry.Offset), 'section_refs':_refs(geometry),
                'pressure_MPa':float(pressure.Pressure.getValueAs('MPa').Value),
                'pressure_reversed':bool(pressure.Reversed),
                'pressure_amplitude':bool(pressure.EnableAmplitude),
                'pressure_refs':_refs(pressure), 'binding':self._stamp(draft)}

    def begin(self, args):
        if set(args) != {'analysis_id','mesh_id','solver_id'}:
            raise ValueError('Select the native analysis, mesh and solver')
        analysis = self._object(args['analysis_id'])
        if native_type(analysis)!='Fem::FemAnalysis':
            raise ValueError('Select the actual native FEM analysis')
        if args['analysis_id'] in self._all()['shells']:
            # Opening an existing editor never resets a saved invalid draft.
            return self.inspect(args['analysis_id'])
        draft = dict(deepcopy(DEFAULTS), **args, elements=[], face_refs=[])
        if sum(native_type(o)=='Fem::ElementGeometry2D' and not getattr(o,'Suppressed',False) for o in analysis.Group)>1:
            from .shell_region_native import begin_regions
            return begin_regions(self, draft, analysis)
        for key,kind in [('material_id','Fem::MaterialCommon'),('geometry_id','Fem::ElementGeometry2D'),
                         ('pressure_id','Fem::ConstraintPressure')]:
            objects = [o for o in analysis.Group if native_type(o)==kind and not getattr(o,'Suppressed',False)]
            if len(objects)>1:
                raise ShellError([issue(key,'첫 경로는 균질 재료/단면/압력 각 하나를 사용합니다.')])
            draft[key] = objects[0].Name if objects else None
        self._members(draft)
        self._mesh(draft)
        if draft['material_id']:
            m=self._object(draft['material_id'])
            try:
                draft['young_MPa']=str(self.owner.App.Units.Quantity(m.Material['YoungsModulus']).getValueAs('MPa').Value)
                draft['poisson']=str(m.Material['PoissonRatio'])
            except (KeyError,ValueError,TypeError):
                draft['young_MPa']=draft['poisson']=''
        if draft['geometry_id']:
            g=self._object(draft['geometry_id'])
            draft['thickness_mm']=str(g.Thickness.getValueAs('mm').Value)
            draft['offset']=str(g.Offset)
        if draft['pressure_id']:
            p=self._object(draft['pressure_id'])
            draft['pressure_MPa']=str(p.Pressure.getValueAs('MPa').Value*(-1 if p.Reversed else 1))
        self._store(analysis.Name, {'draft':draft,'applied':None}, '셸 초안 시작')
        return self.inspect(analysis.Name)

    def repair_objects(self, analysis_id, objects):
        """Explicit draft repair; native objects and prior applied state stay unchanged."""
        types={'solver_id':'Fem::SolverCcxTools','material_id':'Fem::MaterialCommon',
               'geometry_id':'Fem::ElementGeometry2D','pressure_id':'Fem::ConstraintPressure'}
        if not isinstance(objects,dict) or not objects or set(objects)-set(types):
            raise ValueError('복구할 native 솔버/재료/단면/압력 객체를 선택하세요.')
        record=deepcopy(self._record(analysis_id)); draft=record['draft']
        analysis=self._object(analysis_id)
        for key,name in objects.items():
            if name is None and key!='solver_id':
                draft[key]=None  # Create only when the user explicitly applies later.
                continue
            obj=self._object(name)
            if native_type(obj)!=types[key] or obj not in analysis.Group or getattr(obj,'Suppressed',False):
                raise ValueError('이 해석의 활성 native 객체를 선택하세요: '+key)
            draft[key]=name
        self._members(draft)
        self._store(analysis_id,record,'셸 native 대상 복구')
        return self.inspect(analysis_id)

    def save_draft(self, analysis_id, fields):
        allowed = set(FIELDS)|{'orientation','fixed_nodes','regions'}
        if not isinstance(fields,dict) or set(fields)-allowed:
            raise ValueError('Only editable shell properties may be changed here')
        for k,v in fields.items():
            if k=='regions':
                from caelab.shell_regions import check_shape
                check_shape(v)
            elif k=='fixed_nodes':
                if not isinstance(v,list) or len(v)>100000 or any(type(n)!=int or n<=0 for n in v) or len(v)!=len(set(v)):
                    raise ValueError('Fixed nodes must be distinct positive native integer IDs')
            elif not isinstance(v,str) or len(v)>80:
                raise ValueError('Keep shell numeric drafts as bounded raw text')
        record=self._record(analysis_id)
        old=record['draft'].get('orientation','')
        new=fields.get('orientation',old)
        if new and new!=old and (old or new!='native'):
            raise ValueError('방향 반전은 법선 반전 명령으로 offset/압력과 함께 적용하세요.')
        if 'regions' in fields and 'regions' in record['draft']:
            from .shell_region_native import check_reversal_edit
            check_reversal_edit(record['draft']['regions'], fields['regions'])
        record['draft'].update(deepcopy(fields))
        self._store(analysis_id,record,'셸 초안 편집')
        return self.inspect(analysis_id)

    def preview_rebind(self, analysis_id, *, elements=None, face_refs=None, mesh_id=None):
        record=self._record(analysis_id)
        draft=deepcopy(record['draft'])
        if mesh_id is not None:
            draft['mesh_id']=mesh_id
            self._members(draft)
        mesh, _, native_elements=self._mesh(draft)
        if elements is not None and face_refs is not None:
            raise ValueError('Choose native elements or native faces, not both')
        if elements is None and face_refs is None:
            face_refs=[]
            for selection in self.owner.Gui.Selection.getSelectionEx():
                if selection.Object.Document is not self.owner.doc:
                    raise ValueError('셸을 편집 중인 문서에서 면 또는 메시를 선택하세요.')
                names=list(selection.SubElementNames)
                if selection.Object is mesh and not names:
                    elements=sorted(native_elements)
                elif names:
                    face_refs.append({'object_id':selection.Object.Name,'subelements':names})
            if elements is not None and face_refs:
                raise ValueError('메시 전체 또는 면 중 한 가지 방식으로 선택하세요.')
        if elements is None:
            elements=set()
            if not face_refs:
                raise ValueError('native 3D 화면에서 참여 면 또는 메시를 선택하세요.')
            for row in face_refs:
                source=self._object(row['object_id'])
                for name in row['subelements']:
                    if not re.fullmatch(r'Face[1-9][0-9]*',name):
                        raise ValueError('셸 참여 영역은 실제 면을 선택하세요.')
                    node_ids=set(map(int,mesh.FemMesh.getNodesByFace(_global_shape(source,name))))
                    chosen={e for e,c in native_elements.items() if set(c)<=node_ids}
                    if not chosen:
                        raise ShellError([issue(source.Label+'/'+name,'대응하는 완전한 S8 요소가 없습니다.')])
                    elements.update(chosen)
            elements=sorted(elements)
        if (not isinstance(elements,list) or not elements or len(elements)!=len(set(elements))
                or any(type(e)!=int or e not in native_elements for e in elements)):
            raise ValueError('참여할 실제 native S8 요소를 선택하세요.')
        draft.update(elements=sorted(elements),face_refs=deepcopy(face_refs or []))
        stamp=self._stamp(draft)
        old=record['draft'].get('binding')
        if (old and not self._same_geometry(old['mesh_source'],stamp['mesh_source'])
                and old['mesh_sha256']==stamp['mesh_sha256']):
            raise ShellError([issue(mesh.Label,'원 형상이 바뀌었지만 메시가 그대로입니다. native 메시를 재생성한 뒤 복구하세요.')])
        draft['binding']=stamp
        draft['orientation']=''  # Direction must be acknowledged after recovery.
        key='S'+uuid.uuid4().hex
        self._pending.clear()
        self._pending[key]=(analysis_id,draft)
        self._highlight(mesh,elements)
        return {'token':key, 'selected_count':len(elements), 'previous_count':len(record['draft'].get('elements',[])),
                'mesh_label':mesh.Label, 'faces':[self._object(r['object_id']).Label+'/'+','.join(r['subelements'])
                                               for r in draft['face_refs']]}

    def apply_rebind(self, key):
        if key not in self._pending:
            raise ValueError('대상 미리보기가 만료되었습니다. 다시 선택하세요.')
        analysis_id,draft=self._pending[key]
        if not self._same_binding(draft['binding'],self._stamp(draft)):
            raise ValueError('미리보기 이후 대상이 바뀌었습니다. 다시 선택하세요.')
        record=self._record(analysis_id)
        # Preserve newer property edits made while the target was being previewed.
        for name in (*FIELDS,'fixed_nodes'):
            draft[name]=deepcopy(record['draft'][name])
        if 'regions' in record['draft']:
            draft['regions']=deepcopy(record['draft']['regions'])
            # Numeric edits survive a late preview. New face targets invalidate
            # that preview instead of silently authorising another geometry.
            if not self._same_binding(draft['binding'],self._stamp(draft)):
                raise ValueError('영역 참조가 미리보기 뒤 바뀌었습니다. 편집을 유지하고 다시 선택하세요.')
        record['draft']=draft
        self._store(analysis_id,record,'셸 대상 복구')
        self._pending.clear()
        return self.inspect(analysis_id)

    def cancel_rebind(self):
        self._pending.clear()
        self.clear_preview()
        return {'cancelled':True}

    def reverse(self, analysis_id, keep_physical_load=True):
        if type(keep_physical_load) is not bool:
            raise ValueError('Select an explicit reversal rule')
        record=self._record(analysis_id)
        if 'regions' in record['draft']:
            from caelab.shell_regions import reverse_region
            for row in list(record['draft']['regions']):
                record['draft'] = reverse_region(record['draft'], row['id'], keep_physical_load=keep_physical_load)
        else:
            record['draft']=reverse(record['draft'],keep_physical_load=keep_physical_load)
        self._store(analysis_id,record,'셸 법선 반전')
        return self.inspect(analysis_id)

    def _highlight(self, mesh, elements):
        nodes=sorted({n for e in elements for n in mesh.FemMesh.getElementNodes(e)})
        with self.owner.preview_changes():
            previous=getattr(self,'_highlighted_mesh',None)
            if previous is not mesh:
                if previous is not None:
                    previous.ViewObject.HighlightedNodes=getattr(self,'_highlight_original',[])
                self._highlight_original=list(getattr(mesh.ViewObject,'HighlightedNodes',[]))
            mesh.ViewObject.HighlightedNodes=nodes
        self._highlighted_mesh=mesh

    def clear_preview(self):
        if self._overlay is not None:
            view,root=self._overlay
            try: view.getSceneGraph().removeChild(root)
            except (RuntimeError,AttributeError): pass
            self._overlay=None
        mesh=getattr(self,'_highlighted_mesh',None)
        if mesh is not None:
            try:
                with self.owner.preview_changes(): mesh.ViewObject.HighlightedNodes=getattr(self,'_highlight_original',[])
            except (RuntimeError,AttributeError): pass
        self._highlighted_mesh=None

    def preview(self, analysis_id):
        record=self._record(analysis_id); draft=deepcopy(record['draft'])
        self._binding(draft)
        confirmed=bool(draft.get('orientation'))
        if not confirmed: draft['orientation']='native'
        mesh,nodes,elements=self._mesh(draft)
        prepared=prepare_mesh(nodes,elements,draft)
        self._highlight(mesh,draft['elements'])
        from .shell_preview import show
        self._overlay=show(self.owner,prepared,previous=self._overlay)
        return {'selected_count':len(prepared['elements']),
                'surface_preview':'geometric_normal_preview_not_solver_averaged_normals',
                'direction_confirmed':confirmed,
                **({'regions':deepcopy(draft['regions'])} if 'regions' in draft else
                   {'thickness_mm':prepared['values']['thickness_mm'],'offset':prepared['values']['offset']})}

    def apply(self, analysis_id):
        if 'regions' in self._record(analysis_id)['draft']:
            from .shell_region_native import apply
            return apply(self, analysis_id)
        import ObjectsFem
        record=self._record(analysis_id); draft=record['draft']
        self._binding(draft)
        analysis,_=self._members(draft)
        _,nodes,elements=self._mesh(draft)
        prepared=prepare_mesh(nodes,elements,draft)
        self._fixed(draft,prepared)
        values=prepared['values']
        def change():
            constructors={'material_id':ObjectsFem.makeMaterialSolid,
                          'geometry_id':ObjectsFem.makeElementGeometry2D,
                          'pressure_id':ObjectsFem.makeConstraintPressure}
            labels={'material_id':'판재 재료','geometry_id':'판재 단면','pressure_id':'판재 압력'}
            for key,constructor in constructors.items():
                if not draft.get(key):
                    obj=constructor(self.owner.doc)
                    obj.Label=labels[key]
                    analysis.addObject(obj); draft[key]=obj.Name
            material=self._object(draft['material_id'])
            current=dict(material.Material)
            current.setdefault('Name', material.Label)
            current.update(YoungsModulus=format(values['young_MPa'],'.17g')+' MPa',
                           PoissonRatio=format(values['poisson'],'.17g'))
            material.Material=current
            material.References=[]  # One homogeneous material, selected elements are explicit.
            geometry=self._object(draft['geometry_id'])
            geometry.Thickness=format(values['thickness_mm'],'.17g')+' mm'
            geometry.Offset=values['offset']
            pressure=self._object(draft['pressure_id'])
            pressure.Pressure=format(abs(values['pressure_MPa']),'.17g')+' MPa'
            pressure.Reversed=values['pressure_MPa']<0
            pressure.EnableAmplitude=False
            references=[(self._object(r['object_id']),tuple(r['subelements'])) for r in draft.get('face_refs',[])]
            geometry.References=references; pressure.References=references
            solver=self._object(draft['solver_id'])
            for k,v in SETTINGS.items(): setattr(solver,k,v)
            observed=self._native_state(draft)
            for field,actual,expected in (
                    ('thickness_mm',observed['thickness_mm'],values['thickness_mm']),
                    ('offset',observed['offset'],values['offset']),
                    ('pressure_MPa',observed['pressure_MPa'],abs(values['pressure_MPa']))):
                if abs(actual-expected)>8*math.ulp(expected):
                    raise ShellError([issue(field,'native 속성이 입력값을 그대로 받지 않았습니다. 허용 범위를 확인하세요.')])
            record['draft']=draft
            record['applied']={'draft':deepcopy(draft),'native':observed}
            data=self._all(); data['shells'][analysis_id]=record
            self.owner.write_metadata(data)
        self.owner._transaction('CAE Lab 셸 속성 적용',change)
        return self.inspect(analysis_id)

    def effective(self, analysis_id):
        record=self._record(analysis_id); draft=record['draft']
        errors,_=validate_draft(draft)
        if errors: raise ShellError(errors)
        self._binding(draft)
        applied=record.get('applied')
        if applied is None or applied['draft']!=draft:
            raise ShellError([issue('apply','편집한 셸 속성을 명시적으로 적용하세요.')])
        observed = self._native_state(draft)
        previous = applied['native']
        # Compare actual native state without replacing either recorded stamp.
        same_native = (set(observed) == set(previous) and
            all(observed[k] == previous[k] for k in set(previous) - {'binding'}) and
            self._same_binding(previous.get('binding'), observed.get('binding')))
        if not same_native:
            raise ShellError([issue('apply','활성 native 단면/재료/하중/조건이 적용 상태와 다릅니다. 확인 후 다시 적용하세요.')])
        if applied['native']['solver']!=SETTINGS or applied['native']['pressure_amplitude']:
            raise ShellError([issue('solver_id','선형 정적 S8 해석 설정을 다시 적용하세요.')])
        if any(set(o.State)&{'Invalid','Error','Recompute'} for o in self.owner.doc.Objects):
            raise ShellError([issue('document','native 문서의 오류 객체를 수정하고 재계산하세요.')])
        _,nodes,elements=self._mesh(draft)
        prepared=prepare_mesh(nodes,elements,draft)
        fixed=self._fixed(draft,prepared)
        return deepcopy(record),prepared,fixed

    def inspect(self, analysis_id=None):
        self.owner.assert_thread()
        data=self._all()
        objects=list(self.owner.doc.Objects)
        result={'analyses':[{'id':o.Name,'label':o.Label} for o in objects if native_type(o)=='Fem::FemAnalysis'],
                'meshes':[{'id':o.Name,'label':o.Label} for o in objects if hasattr(o,'FemMesh') and not native_type(o).startswith(RESULT_PREFIXES)],
                'solvers':[{'id':o.Name,'label':o.Label} for o in objects if native_type(o)=='Fem::SolverCcxTools'],
                'records':[]}
        for key,record in data['shells'].items():
            if analysis_id is not None and key!=analysis_id: continue
            row={'analysis_id':key,'draft':deepcopy(record['draft']),'applied':bool(record.get('applied')),'ready':False,'errors':[]}
            try:
                self.effective(key); row['ready']=True
            except ShellError as exc: row['errors']=exc.errors
            except (ValueError,KeyError,TypeError,AttributeError,RuntimeError) as exc:
                row['errors']=[issue('shell',str(exc))]
            result['records'].append(row)
        return result

    def dispatch(self, operation, args, target):
        self.owner.assert_thread()
        if target: raise ValueError('Shell commands use explicit native analysis arguments')
        allowed={
            'pre.shell.region_selection':({'analysis_id'},{'analysis_id'}),
            'pre.shell.import_regions':({'analysis_id'},{'analysis_id'}),
            'pre.shell.reverse_region':({'analysis_id','region_id','keep_physical_load'},{'analysis_id','region_id'}),
            'pre.shell.inspect':({'analysis_id'},set()),
            'pre.shell.begin':({'analysis_id','mesh_id','solver_id'},{'analysis_id','mesh_id','solver_id'}),
            'pre.shell.repair_objects':({'analysis_id','objects'},{'analysis_id','objects'}),
            'pre.shell.save_draft':({'analysis_id','fields'},{'analysis_id','fields'}),
            'pre.shell.preview_rebind':({'analysis_id','elements','face_refs','mesh_id'},{'analysis_id'}),
            'pre.shell.apply_rebind':({'token'},{'token'}),
            'pre.shell.cancel_rebind':(set(),set()),
            'pre.shell.preview':({'analysis_id'},{'analysis_id'}),
            'pre.shell.reverse':({'analysis_id','keep_physical_load'},{'analysis_id'}),
            'pre.shell.apply':({'analysis_id'},{'analysis_id'}),
            'pre.shell.freeze':({'analysis_id','solver_id'},{'analysis_id'}),
        }
        permitted,required=allowed.get(operation,(set(),set()))
        if operation not in allowed or set(args)-permitted or not required<=set(args):
            raise ValueError('Unknown or incomplete shell command arguments')
        aid=args.get('analysis_id')
        if operation=='pre.shell.region_selection':
            from .shell_region_native import selection
            return selection(self, aid)
        if operation=='pre.shell.import_regions':
            from .shell_region_native import import_properties
            return import_properties(self, aid)
        if operation=='pre.shell.reverse_region':
            from caelab.shell_regions import reverse_region
            keep = args.get('keep_physical_load', True)
            if type(keep) is not bool:
                raise ValueError('Select an explicit reversal rule')
            record = self._record(aid)
            record['draft'] = reverse_region(record['draft'], args['region_id'], keep_physical_load=keep)
            self._store(aid, record, '셸 영역 법선 반전')
            return self.inspect(aid)
        if operation=='pre.shell.inspect': return self.inspect(aid)
        if operation=='pre.shell.begin': return self.begin(args)
        if operation=='pre.shell.repair_objects': return self.repair_objects(aid,args['objects'])
        if operation=='pre.shell.save_draft': return self.save_draft(aid,args['fields'])
        if operation=='pre.shell.preview_rebind':
            return self.preview_rebind(aid,elements=args.get('elements'),face_refs=args.get('face_refs'),mesh_id=args.get('mesh_id'))
        if operation=='pre.shell.apply_rebind': return self.apply_rebind(args['token'])
        if operation=='pre.shell.cancel_rebind': return self.cancel_rebind()
        if operation=='pre.shell.preview': return self.preview(aid)
        if operation=='pre.shell.reverse': return self.reverse(aid,args.get('keep_physical_load',True))
        if operation=='pre.shell.apply': return self.apply(aid)
        if operation=='pre.shell.freeze':
            if 'solver_id' in args and args['solver_id']!=self._record(aid)['draft']['solver_id']:
                raise ValueError('선택한 솔버가 셸 초안의 솔버와 다릅니다.')
            from .shell_freeze import freeze
            return freeze(self,aid)
        raise ValueError('Unknown shell operation')
