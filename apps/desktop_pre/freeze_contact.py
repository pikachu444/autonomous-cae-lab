"""Freeze separate native body meshes and effective contact into one CalculiX deck.

All native lookup happens on the original body mesh before global ID remapping.
No mesh generation, solver execution or contact-result fabrication happens here.
"""
from copy import deepcopy
import io
import json
from pathlib import Path
import threading
import uuid

from caelab.contact import separate_meshes, surface_union, number
from caelab.contact_deck import UNITS, contact_cards, render, validate_model
from .freeze_analysis import _json, _hash, _plain, require_ready_model
from .fem_edit import _native_type, _target, _references
from . import nonlinear_material
from caelab.calculix_material import J2, has_plasticity


def _refs(obj, bodies, *, material=False):
    rows = []
    for source, names in obj.References:
        names = [names] if isinstance(names, str) else list(names)
        if source.Name not in bodies or bodies[source.Name]['object'] is not source:
            raise ValueError(obj.Label + ': references must resolve to one of the separate body meshes')
        if material:
            if names not in ([], [''], ['Solid1']):
                raise ValueError('Material assignment supports complete explicit bodies only')
        elif not names or len(names) != len(set(names)) or any(not name.startswith('Face') for name in names):
            raise ValueError(obj.Label + ': select distinct exact faces')
        rows.append((source, names))
    if not material and (not rows or len({source.Name for source, names in rows}) != 1):
        raise ValueError(obj.Label + ': each support/load must reference faces of one body')
    return rows


def _native_force_table(node_load_table):
    """FreeCAD's face integration already expresses these dimensionless Values in N.

    get_force_obj_face_nodeload_table multiplies converted Force.Value by its
    weights. Calling getValueAs('N') again would reject a valid native table.
    """
    table = {}
    for _, values in node_load_table:
        for node, value in values.items():
            node = int(node)
            table[node] = table.get(node, 0.) + number(value.Value)
    return table


def collect(analysis, solver, fem, *, capture_only=False):
    from caelab.material_fe_transfer import guard_other_export
    guard_other_export(fem.owner, analysis.Name)
    if threading.current_thread() is not threading.main_thread():
        raise ValueError('Contact export requires the native main thread')
    owner, doc = fem.owner, analysis.Document
    require_ready_model(doc, owner=owner)
    import FreeCAD as App
    from femtools import membertools
    from femmesh import meshtools
    from femmesh.meshsetsgetter import MeshSetsGetter
    if doc is not owner.doc or _native_type(analysis) != 'Fem::FemAnalysis':
        raise ValueError('Select this document’s native Analysis')
    if solver not in analysis.Group or _native_type(solver) != 'Fem::SolverCcxTools':
        raise ValueError('Select the Analysis CalculiX solver')
    fem._assert_idle()
    if doc.isTouched() or any(set(obj.State) & {'Touched', 'Invalid', 'Error', 'Recompute'} for obj in doc.Objects):
        raise ValueError('Recompute and repair the native document before Run')
    programs = [r for r in fem._metadata().get('contact_programs', []) if r['analysis_id'] == analysis.Name]
    if len(programs) > 1:
        raise ValueError('Duplicate Analysis step definitions')
    dynamic_record = owner.read_metadata().get('dynamic_programs', {}).get(analysis.Name)
    program = None if capture_only else (deepcopy(dynamic_record['draft']['program']) if dynamic_record else
                                         deepcopy(programs[0]['draft']) if programs else None)
    procedure = program.get('procedure') if program else 'static'
    if procedure not in ('static', 'dynamic', 'mixed'):
        raise ValueError('Repair the Analysis procedure in the Steps page')
    expected = {'AnalysisType': 'static', 'ModelSpace': '3D', 'SplitInputWriter': False}
    if any(getattr(solver, key) != value for key, value in expected.items()):
        raise ValueError('Contact steps require a static-compatible native CalculiX settings object, unsplit 3D isotropic solid bodies; the contact Steps page owns the static/dynamic procedure')
    if solver.GeometricalNonlinearity not in ('linear', 'nonlinear'):
        raise ValueError('Unsupported native geometric formulation')
    records = [row for row in fem.contact._data()['contacts'] if row['analysis_id'] == analysis.Name
               and not getattr(owner._object(row['object_id']), 'Suppressed', False)]
    if not records and procedure != 'static' and not dynamic_record:
        raise ValueError('무접촉 단일 body의 첫 지원은 STATIC입니다.')
    for record in records:
        errors = fem.contact.errors(record)
        if errors:
            raise ValueError(record['draft']['label'] + ': ' + '; '.join(row['message'] for row in errors))
    members = membertools.AnalysisMember(analysis)
    active = [obj for obj in analysis.Group if not getattr(obj, 'Suppressed', False)]
    meshes = [obj for obj in active if hasattr(obj, 'FemMesh')]
    nonlinear = nonlinear_material.native_objects(analysis)
    base_materials = [row['Object'] for row in members.mats_linear]
    if any(obj.LinearBaseMaterial not in base_materials for obj in nonlinear):
        raise ValueError('소성 객체의 기본 재료가 이 해석의 활성 고체 재료가 아닙니다.')
    if solver.MaterialNonlinearity != ('nonlinear' if nonlinear else 'linear'):
        raise ValueError('재료 비선형 설정과 활성 소성 재료가 일치하지 않습니다. 재료를 명시 적용하세요.')
    allowed = [solver, *meshes, *nonlinear, *[owner._object(row['object_id']) for row in records]]
    for group in (members.mats_linear, members.cons_fixed, members.cons_displacement, members.cons_force):
        allowed.extend(row['Object'] for row in group)
    if any(obj not in allowed for obj in active):
        raise ValueError('Unsupported/suppressed Analysis member; no object is silently omitted')
    bodies, source_rows = {}, []
    for mesh in meshes:
        source = getattr(mesh, 'Shape', None)
        if (source is None or source.Document is not doc or not source.Shape.copy(True, False).isValid() or
                len(source.Shape.Solids) != 1 or source.Name in bodies):
            raise ValueError('Use one native mesh per distinct valid solid body')
        binding = owner.mesh_bindings.validate(mesh)
        quality = fem.quality(mesh, offset=0, limit=1)
        if quality['bad_element_count'] or not mesh.FemMesh.Volumes:
            raise ValueError(mesh.Label + ': repair failed C3D10 quality rows and regenerate')
        local_member = membertools.AnalysisMember(analysis)
        getter = MeshSetsGetter(analysis, solver, mesh, local_member)
        solid_ref, volume_ids, is_sub = meshtools.get_ccx_elements(getter, (source, 'Solid1'))
        ids = set(map(int, mesh.FemMesh.Volumes))
        if is_sub or set(map(int, volume_ids)) != ids:
            raise ValueError(mesh.Label + ': native whole-solid mapping does not cover this mesh')
        nodes = [{'node_id': int(n), 'position_mm': [number(p.x), number(p.y), number(p.z)]}
                 for n, p in sorted(mesh.FemMesh.Nodes.items())]
        elements = [{'element_id': int(e), 'type': 'C3D10',
                     'native_node_ids': list(map(int, mesh.FemMesh.getElementNodes(e)))} for e in sorted(ids)]
        bodies[source.Name] = {'object': source, 'mesh': mesh, 'getter': getter, 'binding': binding,
                               'quality': quality, 'target': _target(source, ['Solid1'])}
        source_rows.append({'body_id': source.Name, 'nodes': nodes, 'elements': elements})
    if not records and len(source_rows) != 1:
        raise ValueError('무접촉 첫 지원은 하나의 고체 body와 메시입니다.')
    assembled = separate_meshes(source_rows, minimum_bodies=2 if records else 1)
    for row in assembled['nodes']:
        row['native_position_mm'] = row['position_mm']
        row['position_mm'] = [float(format(v, '.13G')) for v in row['position_mm']]
    for row in assembled['elements']:
        row['type'] = 'C3D10'
    model = dict(assembled, kind='freecad-contact-mesh', schema_version='1', units=dict(UNITS),
                 materials=[], contacts=[], boundary_dofs=[], loads=[], conditions=[],
                 output={'frequency': 1, 'nodal': ['U', 'CDIS', 'CSTR'], 'pair': ['CF', 'CFN', 'CFS']})
    if not records:
        model['analysis_scope'] = 'single_solid_static'
    mappings = assembled['body_maps']
    for record in records:
        pair = {'object_id': record['object_id'], 'draft': deepcopy(record['draft']),
                'definition_sha256': record['definition_sha256']}
        for side in ('a', 'b'):
            target = record[side]['target']
            body = bodies.get(target['object_id'])
            if body is None:
                raise ValueError('Contact references a body without an active separate mesh')
            mapped_faces = []
            for face in target['subelements']:
                _, entries, is_sub = meshtools.get_ccx_elements(body['getter'], (body['object'], face['name']))
                if not is_sub:
                    raise ValueError('Contact must map each CAD face to volume element faces')
                mapped_faces.append({'face': face['name'], 'element_faces': [(int(e), int(f)) for e, f in entries]})
            pair[side] = surface_union(target['object_id'], mapped_faces, mappings)
            pair[side]['source_target'] = deepcopy(target)
        model['contacts'].append(pair)
    for row in members.mats_linear:
        obj = row['Object']
        if _native_type(obj) != 'Fem::MaterialCommon' or obj.Category != 'Solid':
            raise ValueError('Contact supports native isotropic solid material assignments')
        refs = _refs(obj, bodies, material=True)
        assigned = [source.Name for source, names in refs]
        if not refs:
            if len(members.mats_linear) != 1:
                raise ValueError('Multiple materials require explicit body references')
            assigned = list(bodies)
        E = number(App.Units.Quantity(obj.Material['YoungsModulus']).getValueAs('MPa').Value)
        nu = number(obj.Material['PoissonRatio'])
        density = {}
        if procedure == 'dynamic' and not dynamic_record:
            density['density_tonne_per_mm3'] = number(App.Units.Quantity(obj.Material['Density']).getValueAs('kg/m^3').Value) * 1e-12
        constitutive = nonlinear_material.effective(fem, analysis, obj)
        for body in assigned:
            model['materials'].append({'body_id': body, 'object_id': obj.Name,
                'law': 'isotropic_linear_elastic', 'young_modulus_MPa': E, 'poisson_ratio': nu,
                'native_values': _plain(obj.Material), **density, **constitutive})
    constraints, loads = {}, {}
    for group_name in ('cons_fixed', 'cons_displacement', 'cons_force'):
        for member in getattr(members, group_name):
            obj = member['Object']
            refs = _refs(obj, bodies)
            errors = fem._condition_errors(obj, fem._metadata())
            if errors:
                raise ValueError(obj.Label + ': ' + '; '.join(errors))
            body_id = refs[0][0].Name
            body, nmap = bodies[body_id], mappings[body_id]['nodes']
            getter = body['getter']
            # Prove each selected CAD face resolves, before native union/integration.
            for source, names in refs:
                for face in names:
                    _, entries, is_sub = meshtools.get_ccx_elements(getter, (source, face))
                    if not is_sub or not entries:
                        raise ValueError(obj.Label + ': selected face has no mapped elements')
            condition = {'object_id': obj.Name, 'label': obj.Label, 'type': _native_type(obj), 'body_id': body_id,
                         'targets': [_target(source, names) for source, names in refs]}
            if group_name == 'cons_force':
                condition['force_weights'] = []
                if obj.EnableAmplitude:
                    raise ValueError('Contact Force amplitudes require a separate effective mapping')
                direction = [number(v) for v in (obj.DirectionVector.x, obj.DirectionVector.y, obj.DirectionVector.z)]
                if not any(direction):
                    raise ValueError('Force direction is unresolved')
                total = number(obj.Force.getValueAs('N').Value)
                if total == 0 and program is None and not capture_only:
                    condition.update(total_force_N=0., native_integrated_force_N=0.,
                        distribution='explicit_zero_force', direction=direction)
                    model['conditions'].append(condition)
                    continue
                if total == 0:
                    # Native face quadrature is linear in Force. Read a detached 1 N
                    # descriptor; never change the user's native Force or its signature.
                    from types import SimpleNamespace
                    probe = SimpleNamespace(References=obj.References, Force=App.Units.Quantity('1 N'), Name=obj.Name)
                    table = _native_force_table(meshtools.get_force_obj_face_nodeload_table(
                        body['mesh'].FemMesh, meshtools.get_femelement_table(body['mesh'].FemMesh),
                        body['mesh'].FemMesh.Nodes, probe))
                    condition['mapping_reference_force_N'] = 1.
                else:
                    getter.member.cons_force = [dict(member)]
                    getter.get_constraints_force_nodeloads()
                    table = _native_force_table(getter.member.cons_force[0]['NodeLoadTable'])
                total = number(obj.Force.getValueAs('N').Value)
                integrated = sum(table.values())
                if not table or integrated == 0 or any(n not in nmap for n in table):
                    raise ValueError('Native total force needs a nonzero complete body-local node table')
                # One total across the union, using the existing native area weights.
                # This is explicit total-force distribution, not one force per face.
                scale = total / integrated
                condition.update(total_force_N=total, native_integrated_force_N=integrated,
                    distribution='native_face_weights_normalized_to_one_total', direction=direction)
                for n, value in table.items():
                    for axis, factor in enumerate(direction, 1):
                        if factor != 0:
                            key = (nmap[n], axis)
                            loads[key] = loads.get(key, 0.) + value * scale * factor
                            condition['force_weights'].append({'node_id': key[0], 'component': axis,
                                                               'weight': value / integrated * factor})
            else:
                if group_name == 'cons_displacement' and obj.EnableAmplitude:
                    raise ValueError('Contact displacement amplitudes are unsupported')
                # Condition-name mesh groups may predate an explicit face rebind.
                # Resolve the current references on this body, preserving all stored groups.
                local = meshtools.get_femnodes_by_references(body['mesh'].FemMesh, obj.References)
                if not local or any(int(n) not in nmap for n in local):
                    raise ValueError('Support needs exact body-local mesh nodes')
                values = {axis: 0. for axis in (1, 2, 3)} if group_name == 'cons_fixed' else {
                    axis: number(getattr(obj, letter + 'Displacement').getValueAs('mm').Value)
                    for axis, letter in enumerate('xyz', 1) if not getattr(obj, letter + 'Free')}
                if not values:
                    raise ValueError('Displacement condition has no prescribed translational component')
                condition['components_mm'] = values
                condition['boundary_dofs'] = []
                for n in local:
                    for axis, value in values.items():
                        key = (nmap[int(n)], axis)
                        if key in constraints and constraints[key] != value and program is None:
                            raise ValueError('Conflicting displacement values on the same body DOF')
                        # For a stage program, the unique aggregate is a baseline
                        # audit only. Each condition below keeps its own value;
                        # compile_program checks their actual concurrent curves.
                        constraints.setdefault(key, value)
                        condition['boundary_dofs'].append({'node_id': key[0], 'component': axis, 'value_mm': value})
            model['conditions'].append(condition)
    model['boundary_dofs'] = [{'node_id': n, 'component': d, 'value_mm': value}
                             for (n, d), value in sorted(constraints.items())]
    model['loads'] = [{'node_id': n, 'component': d, 'force_N': value} for (n, d), value in sorted(loads.items())]
    model['step'] = {key: number(getattr(solver, native).getValueAs('s').Value) for key, native in (
        ('initial', 'TimeInitialIncrement'), ('period', 'TimePeriod'),
        ('minimum', 'TimeMinimumIncrement'), ('maximum', 'TimeMaximumIncrement'))}
    model['step'].update(increments=int(solver.IncrementsMaximum), geometry=solver.GeometricalNonlinearity,
        automatic=bool(solver.AutomaticIncrementation), matrix_solver=solver.MatrixSolverType,
        axis_semantics='static_load_parameter_not_physical_seconds',
        controls=[solver.IterationsControlParameterIter, solver.IterationsControlParameterCutb]
                 if solver.IterationsControlParameterTimeUse else None)
    from .convergence import effective as convergence_effective
    model['step'].update(convergence_effective(fem, analysis, solver))
    if program is not None:
        model['analysis_steps'] = program
    elif capture_only:
        # A valid initial-condition model need not have an external excitation.
        # Reuse a STATIC baseline program only for complete source validation;
        # this read-only capture is never an executable dynamic input.
        from caelab.contact_steps import default_program
        model['analysis_steps'] = default_program(model['step'], model['conditions'])
    has_tie = any(p['draft']['normal_law'] == 'tie' for p in model['contacts'])
    has_contact = any(p['draft']['normal_law'] != 'tie' for p in model['contacts'])
    if has_tie:
        model['output']['nodal'] = ['U', 'RF', 'S'] + (['CDIS', 'CSTR'] if has_contact else [])
        model['output']['pair'] = ['CF', 'CFN', 'CFS'] if has_contact else []
    if has_plasticity(model) or model.get('analysis_scope') == 'single_solid_static':
        model['output']['nodal'] = ['U', 'RF', 'S', 'E'] + (['PEEQ'] if has_plasticity(model) else []) + (['CDIS', 'CSTR'] if has_contact else [])
        model['output']['pair'] = ['CF', 'CFN', 'CFS'] if has_contact else []
    identity = [{'body_id': identifier, 'mesh_id': row['mesh'].Name, 'target': row['target'],
                 'binding': row['binding']} for identifier, row in sorted(bodies.items())]
    if dynamic_record and not capture_only:
        from .dynamic_native import admitted, base
        # Source provenance uses the same complete native baseline, independent
        # of authored stage curves. No weak centre/volume comparison is used.
        baseline, proof = base(owner, analysis.Name, solver.Name)
        model = admitted(owner, dynamic_record, baseline, proof)
        if proof != identity:
            raise ValueError('동해석 대상이 입력 준비 중 변경됐습니다.')
    validate_model(model)
    return model, identity


def freeze_contact(analysis, solver, output_root, *, fem):
    model, identity = collect(analysis, solver, fem)
    import FreeCAD as App
    from femsolver.calculix import write_constraint_contact
    for material in model['materials']:
        nonlinear_material.verify_native_writer(fem, material)
    # The installed writer is authoritative for these contact cards. Compare its
    # effective output to the bounded headless contract before admitting bytes.
    for pair in model['contacts']:
        native = fem.owner._object(pair['object_id'])
        stream = io.StringIO()
        tied = pair['draft']['normal_law'] == 'tie'
        if tied:
            from femsolver.calculix import write_constraint_tie
        prefix = 'Tie' if tied else 'Contact'
        row = {prefix+'SlaveFaces': [(None, [tuple(v) for v in pair['a']['element_faces']], True)],
               prefix+'MasterFaces': [(None, [tuple(v) for v in pair['b']['element_faces']], True)]}
        writer = write_constraint_tie if tied else write_constraint_contact
        writer.write_meshdata_constraint(stream, row, native, None)
        writer.write_constraint(stream, row, native, None)
        if stream.getvalue() != contact_cards(pair):
            raise ValueError('Installed native contact writer differs from the admitted effective card contract')
    root = Path(output_root).resolve() / ('F' + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    original = analysis.Document.FileName
    original_hash = _hash(Path(original)) if original and Path(original).is_file() else None
    analysis.Document.saveCopy(str(root / 'editable.FCStd'))
    if analysis.Document.FileName != original or not (root / 'editable.FCStd').is_file():
        raise ValueError('Contact export did not retain an independent editable native copy')
    _json(root / 'mesh.json', model)
    (root / 'contact.inp').write_text(render(model), encoding='ascii', newline='\n')
    after, current = collect(analysis, solver, fem)
    if after != model or current != identity or (original_hash and _hash(Path(original)) != original_hash):
        raise ValueError('Native contact model changed during export; no run submitted')
    files = [{'relative': p.name, 'bytes': p.stat().st_size, 'sha256': _hash(p)}
             for p in sorted(root.iterdir()) if p.is_file()]
    manifest = root / 'snapshot.json'
    _json(manifest, {'kind': 'freecad-contact-frozen', 'schema_version': '1', 'id': root.name,
        'input_file': 'contact.inp', 'files': files, 'native_version': list(App.Version()),
        'analysis_id': analysis.Name, 'solver_id': solver.Name, 'bodies': identity,
        'document': {'name': analysis.Document.Name, 'original_sha256': original_hash},
        'solver_execution': 'NOT_PERFORMED', 'qualification': 'UNKNOWN', 'decision': 'NOT_RELEASED'})
    return manifest
