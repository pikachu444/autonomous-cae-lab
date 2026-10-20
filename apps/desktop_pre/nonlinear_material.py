"""NS1 editing on the existing FreeCAD material and document metadata owner.

Drafts are literal user input. Only Apply changes native material/solver objects;
Check/freeze never silently repairs an unfinished or stale draft.
"""
from copy import deepcopy
import json
import re

from caelab.calculix_material import (
    J2, LINEAR, default_plasticity, native_plasticity, native_yield_points,
    normalize_plasticity, plasticity_errors,
)

OPERATIONS = ('pre.fem.plasticity_read', 'pre.fem.plasticity_save',
              'pre.fem.plasticity_apply', 'pre.fem.nonlinear_settings')
KIND = 'Fem::MaterialMechanicalNonlinear'


def native_type(obj):
    return getattr(getattr(obj, 'Proxy', None), 'Type', obj.TypeId)


def native_objects(analysis, base=None, *, include_suppressed=False):
    return [obj for obj in analysis.Group if native_type(obj) == KIND
            and (base is None or getattr(obj, 'LinearBaseMaterial', None) is base)
            and (include_suppressed or not getattr(obj, 'Suppressed', False))]


def uses_custom_static(analysis, metadata):
    """Sidecar options that the official writer cannot read from native objects."""
    return any(row.get('analysis_id') == analysis.Name
        for key in ('contacts', 'contact_programs', 'convergence_drafts', 'periodic_constraints')
        for row in metadata.get(key, []))


def uses_solid_route(analysis, metadata=None):
    """Keep legacy single-solid linear inputs unchanged; reuse the contact runner."""
    active = [obj for obj in analysis.Group if not getattr(obj, 'Suppressed', False)]
    if any(native_type(obj) in (KIND, 'Fem::ConstraintContact', 'Fem::ConstraintTie') for obj in active):
        return True
    if any(native_type(obj) == 'Fem::SolverCcxTools' and
           (getattr(obj, 'MaterialNonlinearity', 'linear') != 'linear' or
            getattr(obj, 'GeometricalNonlinearity', 'linear') != 'linear') for obj in active):
        return True
    if analysis.Name in (metadata or {}).get('initial_fields',{}):return True
    if analysis.Name in (metadata or {}).get('pretension_editors',{}):return True
    return any(row.get('analysis_id') == analysis.Name for key in ('plasticity_drafts', 'contact_programs', 'convergence_drafts', 'periodic_constraints', 'pretension_sections')
               for row in (metadata or {}).get(key, []))


def _selection(fem, base, analysis_id):
    if native_type(base) != 'Fem::MaterialCommon' or getattr(base, 'Category', None) != 'Solid':
        raise ValueError('표를 적용할 기본 고체 재료를 선택하세요.')
    analysis = fem.owner._object(analysis_id)
    if (native_type(analysis) != 'Fem::FemAnalysis' or analysis.Document is not fem.owner.doc
            or base not in analysis.Group or getattr(base, 'Suppressed', False)):
        raise ValueError('선택한 해석에 속한 활성 기본 재료를 선택하세요.')
    return analysis


def _record(fem, analysis, base):
    rows = [row for row in fem._metadata().get('plasticity_drafts', [])
            if row.get('analysis_id') == analysis.Name and row.get('material_id') == base.Name]
    if len(rows) > 1:
        raise ValueError('이 재료의 소성 초안이 중복됩니다. 원 자료를 확인하세요.')
    return deepcopy(rows[0]) if rows else None


def _signature(obj):
    return {'object_id': obj.Name, 'base_id': obj.LinearBaseMaterial.Name,
            'hardening': str(obj.MaterialModelNonlinearity),
            'yield_points': list(obj.YieldPoints), 'suppressed': bool(getattr(obj, 'Suppressed', False))}


def _application_matches(record, objects):
    """Compare the applied law AND the complete active set for this base material.

    The first support permits zero (elastic) or one (J2) active object. Therefore
    the existing applied_draft/applied_native snapshot unambiguously defines
    the expected active set, including older saved records; no migration or
    inference from the *current* native set is needed.
    """
    applied = record.get('applied_draft')
    signature = record.get('applied_native')
    if not isinstance(applied, dict):
        return False
    if applied.get('law') == LINEAR:
        expected = []
    elif (applied.get('law') == J2 and isinstance(signature, dict)
          and signature.get('suppressed') is False):
        expected = [signature]
    else:
        return False
    active = [_signature(obj) for obj in objects if not getattr(obj, 'Suppressed', False)]
    if active != expected:
        return False
    # Retain the existing check on an intentionally suppressed native curve too.
    # An added active object must not be certified by this unchanged old object.
    if signature is not None:
        if not isinstance(signature, dict):
            return False
        current = [obj for obj in objects if obj.Name == signature.get('object_id')]
        if len(current) != 1 or _signature(current[0]) != signature:
            return False
    return True


def draft_errors(draft):
    if not isinstance(draft, dict) or draft.get('law') not in (LINEAR, J2):
        return [{'path': 'law', 'message': '등방 탄성 또는 J2 등방 경화를 선택하세요.',
                 'severity': 'error', 'blocks_evaluation': True}]
    if draft['law'] == LINEAR:
        return []  # An explicitly inactive curve remains in the editing draft.
    errors = plasticity_errors(draft.get('plasticity'))
    if draft.get('definitions_confirmed') is not True:
        errors.append({'path': 'definitions_confirmed', 'message': '진응력–등가 소성변형률 표임을 확인하세요.',
                       'severity': 'error', 'blocks_evaluation': True})
    if not errors:
        try:
            native_yield_points(draft['plasticity'])
        except ValueError as error:
            match = re.search(r'plasticity\.yield_points\.\d+(?:\.\d+)?', str(error))
            errors.append({'path': match.group(0) if match else 'plasticity.yield_points', 'message': str(error),
                           'severity': 'error', 'blocks_evaluation': True})
    return errors


def read(fem, base, analysis_id):
    analysis = _selection(fem, base, analysis_id)
    record = _record(fem, analysis, base)
    objects = native_objects(analysis, base, include_suppressed=True)
    active = [obj for obj in objects if not getattr(obj, 'Suppressed', False)]
    if record:
        draft = deepcopy(record['draft'])
    else:
        curve = default_plasticity()
        if len(active) == 1:
            curve['hardening'] = ('isotropic' if active[0].MaterialModelNonlinearity == 'isotropic hardening'
                                  else str(active[0].MaterialModelNonlinearity))
            curve['yield_points'] = [row.split(',') for row in active[0].YieldPoints]
        draft = {'law': J2 if active else LINEAR, 'plasticity': curve,
                 'definitions_confirmed': bool(active)}
    errors = draft_errors(draft)
    if len(active) > 1:
        errors.append({'path': 'material', 'message': '같은 기본 재료에 활성 소성 객체가 여러 개입니다.',
                       'severity': 'error', 'blocks_evaluation': True})
    matches = bool(record and record.get('applied_draft') == draft and
                   _application_matches(record, objects))
    if record and record.get('applied_draft') == draft and not matches:
        errors.append({'path': 'material', 'message': 'native 소성 재료가 변경됐습니다. 표를 확인하고 명시 적용하세요.',
                       'severity': 'error', 'blocks_evaluation': True})
    return {'analysis_id': analysis.Name, 'material_id': base.Name,
            'draft': draft, 'errors': errors, 'native': [_signature(obj) for obj in objects],
            'applied': matches,
            'source': 'saved_draft' if record else 'native_material', 'executed': False}


def save(fem, base, analysis_id, draft):
    analysis = _selection(fem, base, analysis_id)
    # A bounded JSON envelope, not constitutive admission. 201 rows and "1e" survive.
    if not isinstance(draft, dict) or len(json.dumps(draft, allow_nan=False).encode('utf-8')) > 2 * 1024**2:
        raise ValueError('소성 초안은 2 MiB 이하의 표 정의로 저장하세요.')
    value = deepcopy(draft)
    def change():
        data = fem._metadata()
        record = _record(fem, analysis, base) or {'analysis_id': analysis.Name, 'material_id': base.Name}
        record['draft'] = value
        data['plasticity_drafts'] = [row for row in data.get('plasticity_drafts', [])
            if (row.get('analysis_id'), row.get('material_id')) != (analysis.Name, base.Name)] + [record]
        fem.owner.write_metadata(data)
    fem._transaction('소성 초안 저장', change)
    return read(fem, base, analysis_id)


def apply(fem, base, analysis_id, draft):
    analysis = _selection(fem, base, analysis_id)
    errors = draft_errors(draft)
    if errors:
        raise ValueError('; '.join(row['path'] + ': ' + row['message'] for row in errors))
    # Resolve all native targets before the transaction; never pick the first duplicate.
    solvers = [obj for obj in analysis.Group if native_type(obj) == 'Fem::SolverCcxTools'
               and not getattr(obj, 'Suppressed', False)]
    objects = native_objects(analysis, base, include_suppressed=True)
    if len(solvers) != 1 or len(objects) > 1:
        raise ValueError('CalculiX 설정 하나와 기본 재료당 소성 객체 하나를 지정하세요.')
    rows = native_yield_points(draft['plasticity']) if draft['law'] == J2 else None
    def change():
        obj = objects[0] if objects else None
        if rows is not None:
            if obj is None:
                import ObjectsFem
                obj = ObjectsFem.makeMaterialMechanicalNonlinear(fem.owner.doc, base)
                analysis.addObject(obj)
            obj.LinearBaseMaterial = base
            obj.MaterialModelNonlinearity = 'isotropic hardening'
            obj.YieldPoints = rows
            obj.Suppressed = False
        elif obj is not None:
            obj.Suppressed = True  # Keep the native curve; explicit elastic choice only.
        solvers[0].MaterialNonlinearity = 'nonlinear' if native_objects(analysis) else 'linear'
        data = fem._metadata()
        record = {'analysis_id': analysis.Name, 'material_id': base.Name,
                  'draft': deepcopy(draft), 'applied_draft': deepcopy(draft),
                  'applied_native': _signature(obj) if obj is not None else None}
        data['plasticity_drafts'] = [row for row in data.get('plasticity_drafts', [])
            if (row.get('analysis_id'), row.get('material_id')) != (analysis.Name, base.Name)] + [record]
        fem.owner.write_metadata(data)
    fem._transaction('소성 재료 적용', change)
    return read(fem, base, analysis_id)


def effective(fem, analysis, base):
    """Run boundary: stale/invalid/unapplied saved input must not reuse an old curve."""
    record = _record(fem, analysis, base)
    all_objects = native_objects(analysis, base, include_suppressed=True)
    objects = [obj for obj in all_objects if not getattr(obj, 'Suppressed', False)]
    if len(objects) > 1:
        raise ValueError(base.Label + ': 활성 소성 객체가 중복됩니다.')
    if record:
        errors = draft_errors(record['draft'])
        if errors:
            raise ValueError(base.Label + ': ' + '; '.join(e['path'] + ': ' + e['message'] for e in errors))
        if record.get('applied_draft') != record['draft']:
            raise ValueError(base.Label + ': 저장한 소성 초안을 적용한 뒤 계산하세요.')
        if not _application_matches(record, all_objects):
            raise ValueError(base.Label + ': native 소성 재료가 변경됐습니다. 표를 확인하고 명시 적용하세요.')
    if not objects:
        return {'law': LINEAR}
    obj = objects[0]
    curve = native_plasticity(list(obj.YieldPoints), str(obj.MaterialModelNonlinearity))
    # Verify serialization at freeze as well as editing and final render.
    native_yield_points(curve)
    return {'law': J2, 'plasticity': curve, 'native_nonlinear_id': obj.Name,
            'source_native_yield_points': list(obj.YieldPoints),
            'source_curve': deepcopy(record['applied_draft']['plasticity']) if record else None}


def validate_applied_materials(analysis, solver, metadata):
    """Keep saved plasticity edits bound to the exact native writer objects.

    Native-only materials remain the installed writer's responsibility. Only
    bases with an application-owned draft use this editor's J2 admission.
    """
    from types import SimpleNamespace
    rows = [row for row in metadata.get('plasticity_drafts', [])
            if row.get('analysis_id') == analysis.Name]
    fem = SimpleNamespace(_metadata=lambda: metadata)
    for row in rows:
        bases = [obj for obj in analysis.Group if obj.Name == row.get('material_id')]
        if (len(bases) != 1 or bases[0].Document is not analysis.Document
                or native_type(bases[0]) != 'Fem::MaterialCommon'
                or getattr(bases[0], 'Category', None) != 'Solid'
                or getattr(bases[0], 'Suppressed', False)):
            raise ValueError(str(row.get('material_id')) + ': 소성 표의 활성 기본 재료 연결을 확인하세요.')
        effective(fem, analysis, bases[0])
    if rows and ((solver.MaterialNonlinearity == 'nonlinear') != bool(native_objects(analysis))):
        raise ValueError(solver.Name + ': 소성 재료와 CalculiX 재료 비선형 설정이 일치하지 않습니다.')
    return deepcopy(rows)


def settings(fem, solver, args):
    if native_type(solver) != 'Fem::SolverCcxTools' or set(args) != {'nlgeom'} or type(args['nlgeom']) is not bool:
        raise ValueError('CalculiX 설정과 기하 비선형 선택을 지정하세요.')
    fem._transaction('기하 비선형 적용', lambda: setattr(solver, 'GeometricalNonlinearity',
                                                          'nonlinear' if args['nlgeom'] else 'linear'))
    return {'solver_id': solver.Name, 'nlgeom': args['nlgeom'], 'executed': False}


def verify_native_writer(fem, material):
    """Run the installed FreeCAD writer; never mutate raw native/user curve input."""
    if material['law'] != J2:
        return
    import io
    from types import SimpleNamespace
    from femsolver.calculix.write_femelement_material import write_femelement_material
    obj = fem.owner._object(material['object_id'])
    values = dict(obj.Material)
    values.setdefault('Name', obj.Label)
    base = SimpleNamespace(Name=obj.Name, Label=obj.Label, Category='Solid', Material=values)
    rows = native_yield_points(material['plasticity'])
    nonlinear = SimpleNamespace(LinearBaseMaterial=base, MaterialModelNonlinearity='isotropic hardening',
                                YieldPoints=rows)
    writer = SimpleNamespace(analysis_type='static', solver_obj=SimpleNamespace(MaterialNonlinearity='nonlinear'),
        member=SimpleNamespace(mats_linear=[{'Object': base}], mats_nonlinear=[{'Object': nonlinear}],
                               cons_centrif=[], cons_selfweight=[]))
    stream = io.StringIO()
    write_femelement_material(stream, writer)
    lines = stream.getvalue().splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().upper().startswith('*PLASTIC')]
    if len(starts) != 1 or lines[starts[0]].replace(' ', '').upper() not in ('*PLASTIC', '*PLASTIC,HARDENING=ISOTROPIC'):
        raise ValueError('Installed native PLASTIC writer differs from the admitted J2 contract.')
    start = starts[0] + 1
    written = []
    for line in lines[start:]:
        if not line.strip() or line.startswith('*'):
            break
        written.append(line)
    if written != rows:
        raise ValueError('Installed native PLASTIC rows differ from the verified 20-character output.')
