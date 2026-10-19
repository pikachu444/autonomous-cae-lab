"""Bounded static contact deck from body-resolved native sets, without native imports."""
import math
import re
from .contact import law_errors, number
from .calculix_material import material_errors, plastic_cards, has_plasticity

UNITS = {'position': 'mm', 'displacement': 'mm', 'force': 'N', 'stress': 'MPa'}
# CalculiX C3D10 face order: corners followed by midside nodes in that orientation.
FACES = {1: (0, 2, 1, 6, 5, 4), 2: (0, 1, 3, 4, 8, 7),
         3: (1, 2, 3, 5, 9, 8), 4: (2, 0, 3, 6, 7, 9)}


def num(value):
    return format(number(value), '.13G')


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value):
        raise ValueError('Deck identities require bounded native names')
    return value


def contact_cards(pair):
    """Exact native FreeCAD 1.1.4 surface/contact writer syntax for this capability."""
    identifier, draft = name(pair['object_id']), pair['draft']
    errors = law_errors(draft)
    if errors:
        raise ValueError('; '.join(row['message'] for row in errors))
    if draft['normal_law'] == 'tie':
        lines = []
        for side, prefix in [('a', 'TIE_DEP'), ('b', 'TIE_IND')]:
            lines.append('*SURFACE, NAME=' + prefix + identifier)
            lines.extend(str(element) + ',S' + str(face) for element, face in pair[side]['element_faces'])
        lines.extend(['*TIE, POSITION TOLERANCE=' + num(draft['tie_tolerance_mm']) +
                      ('' if draft.get('tie_adjust', False) else ', ADJUST=NO') +
                      ', NAME=TIE' + identifier, 'TIE_DEP' + identifier + ', TIE_IND' + identifier])
        return '\n'.join(lines) + '\n'
    lines = []
    for side, prefix in [('a', 'DEP'), ('b', 'IND')]:
        lines.append('*SURFACE, NAME=' + prefix + identifier)
        lines.extend(str(element) + ',S' + str(face) for element, face in pair[side]['element_faces'])
    lines.extend(['*CONTACT PAIR, INTERACTION=INT' + identifier + ', TYPE=SURFACE TO SURFACE',
        'DEP' + identifier + ', IND' + identifier, '*SURFACE INTERACTION, NAME=INT' + identifier,
        '*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR', num(draft['normal_stiffness_MPa_per_mm'])])
    if draft['tangential_law'] == 'coulomb':
        lines.extend(['*FRICTION', num(draft['friction_coefficient']) + ', ' + num(draft['stick_stiffness_MPa_per_mm'])])
    return '\n'.join(lines) + '\n'


def validate_model(model, *, allow_unrestrained_capture=False, _profile=None):
    if _profile not in (None, 'aster_hard', 'aster_interface'):
        raise ValueError('Unsupported contact validation profile')
    interface = _profile == 'aster_interface'
    hard = _profile in ('aster_hard','aster_interface')
    if hard:
        if allow_unrestrained_capture:
            raise ValueError('Aster contact cannot defer restraints for displacement capture')
        from .adapters.contact_aster_model import face_slots, element_slots, law_errors as hard_errors
        if interface:
            from .implicit_interface import profile
        else:
            from .adapters.contact_aster_model import profile
        profile(model)
    else:
        face_slots = lambda row: FACES
        from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10
        element_slots = lambda row: CCX_FROM_NATIVE_TET10
    effective_errors = hard_errors if hard else law_errors
    # A displacement import may supply the first restraint. Only its read-only
    # linear STATIC capture can defer this requirement; render remains strict.
    if allow_unrestrained_capture:
        program = model.get('analysis_steps', {})
        stages = program.get('steps', [])
        if (model.get('analysis_scope') != 'single_solid_static'
                or model.get('step', {}).get('geometry') != 'linear'
                or model.get('contacts') or program.get('procedure') != 'static'
                or len(stages) != 1 or stages[0].get('procedure', 'static') != 'static'
                or any(model.get(k) for k in ('restart', 'dynamic', 'periodic_constraints',
                    'pretension_sections', 'initial_fields'))
                or any(m.get('law') != 'isotropic_linear_elastic' or m.get('plasticity')
                       for m in model.get('materials', []))):
            raise ValueError('Displacement capture requires one linear elastic STATIC solid without coupled state.')
    if model.get('kind') != 'freecad-contact-mesh' or model.get('schema_version') != '1' or model.get('units') != UNITS:
        raise ValueError('Unsupported contact mesh/units')
    nodes, elements, bodies = {}, {}, {}
    native_nodes, native_elements = set(), set()
    for row in model['nodes']:
        identifier, body, native = row['node_id'], name(row['body_id']), row['native_node_id']
        if type(identifier) is not int or identifier <= 0 or identifier in nodes or type(native) is not int or native <= 0:
            raise ValueError('Invalid contact node identity')
        if (body, native) in native_nodes or len(row['position_mm']) != 3:
            raise ValueError('Duplicate body-local node')
        native_nodes.add((body, native))
        nodes[identifier] = [number(v) for v in row['position_mm']]
        from apps.desktop_pre.freeze_analysis import _serialized_coordinate_close
        if (len(row.get('native_position_mm', [])) != 3 or
                any(not _serialized_coordinate_close(native, written)
                    for native, written in zip(row['native_position_mm'], nodes[identifier]))):
            raise ValueError('Contact coordinates differ from the retained native body mesh')
        bodies.setdefault(body, {'nodes': set(), 'elements': set()})['nodes'].add(identifier)
    for row in model['elements']:
        identifier, body, native = row['element_id'], name(row['body_id']), row['native_element_id']
        ids = row['node_ids']
        if (type(identifier) is not int or identifier <= 0 or identifier in elements or
                type(native) is not int or native <= 0 or (body, native) in native_elements or
                row.get('type') not in (('C3D10', 'C3D8') if hard else ('C3D10',)) or body not in bodies or
                len(ids) != (8 if row.get('type') == 'C3D8' else 10) or len(set(ids)) != len(ids) or
                any(type(n) is not int or n not in bodies[body]['nodes'] for n in ids)):
            raise ValueError('Invalid contact element or cross-body connectivity')
        elements[identifier] = list(ids)
        native_elements.add((body, native))
        bodies[body]['elements'].add(identifier)
    if model.get('analysis_scope') not in (None, 'single_solid_static', 'single_solid_dynamic'):
        raise ValueError('Unsupported solid analysis scope')
    single = model.get('analysis_scope') in ('single_solid_static', 'single_solid_dynamic')
    from .dynamic_model import enabled, has_dynamic, validate_effective
    if model.get('analysis_scope') == 'single_solid_dynamic' and not enabled(model):
        raise ValueError('Dynamic solid requires its complete frozen settings')
    if (single and len(bodies) != 1) or (not single and len(bodies) < 2) or not elements or set(nodes) != {n for ids in elements.values() for n in ids}:
        raise ValueError('Contact needs complete separate body meshes')
    from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10
    if model.get('native_to_deck_slots') != ({k:list(element_slots({'type':k})) for k in ('C3D10','C3D8')} if hard else list(CCX_FROM_NATIVE_TET10)) or model.get('interface_policy') != 'independent_body_dofs':
        raise ValueError('Contact mesh lost its explicit native ordering/separate DOFs')
    for body, membership in bodies.items():
        mapping = model['body_maps'][body]
        nmap = {int(k): v for k, v in mapping['nodes'].items()}
        emap = {int(k): v for k, v in mapping['elements'].items()}
        expected_n = {r['native_node_id']: r['node_id'] for r in model['nodes'] if r['body_id'] == body}
        expected_e = {r['native_element_id']: r['element_id'] for r in model['elements'] if r['body_id'] == body}
        if nmap != expected_n or emap != expected_e:
            raise ValueError('Contact inverse map differs from retained native identities')
        for row in model['elements']:
            if row['body_id'] == body and row['node_ids'] != [nmap[row['native_node_ids'][i]] for i in element_slots(row)]:
                raise ValueError('Contact ordered connectivity differs from native mesh')
        visited, remaining = set(), set(membership['elements'])
        seed = next(iter(remaining))
        frontier = set(elements[seed])
        while remaining:
            connected = {e for e in remaining if frontier.intersection(elements[e])}
            if not connected:
                raise ValueError('A body mesh contains a disconnected island')
            visited.update(connected)
            remaining -= connected
            frontier.update(n for e in connected for n in elements[e])
    materials = model['materials']
    if {row['body_id'] for row in materials} != set(bodies) or len(materials) != len(bodies):
        raise ValueError('Every body requires one explicit complete material/section assignment')
    for index, row in enumerate(materials):
        errors = material_errors(row, 'materials.' + str(index))
        if errors:
            raise ValueError('; '.join(e['path'] + ': ' + e['message'] for e in errors))
        plastic_cards(row)  # Check exact serialized curve, including the 200-point cap.
    if (single or has_plasticity(model)) and model.get('analysis_steps', {}).get('procedure', 'static') != 'static' and not enabled(model):
        raise ValueError('NS1 first support is STATIC; nonlinear dynamic material input is not admitted.')
    element_records = {row['element_id']:row for row in model['elements']}
    pair_ids = set()
    for pair in model['contacts']:
        if name(pair['object_id']).upper() in pair_ids or effective_errors(pair['draft']):
            raise ValueError('Duplicate or invalid effective contact law')
        pair_ids.add(pair['object_id'].upper())
        if pair['a']['body_id'] == pair['b']['body_id']:
            raise ValueError('Self-contact is outside this adapter')
        for side in ('a', 'b'):
            surface = pair[side]
            body = surface['body_id']
            rows = surface['element_faces']
            if body not in bodies or not rows or len({tuple(v) for v in rows}) != len(rows):
                raise ValueError('Contact side requires one nonempty deduplicated body surface')
            for e, face in rows:
                if e not in bodies[body]['elements'] or type(face) is not int or face not in face_slots(element_records[e]):
                    raise ValueError('Contact side is outside its owning body')
            mapped = {tuple(v) for cad in surface['cad_faces'] for v in cad['element_faces']}
            if (mapped != {tuple(v) for v in rows} or not surface['cad_faces'] or
                    any(not cad['element_faces'] for cad in surface['cad_faces'])):
                raise ValueError('A selected CAD face has no exact mapped union')
    if not pair_ids and not single and not (interface and model.get('interfaces')):
        raise ValueError('This capability requires an explicit contact pair')
    if single and pair_ids:
        raise ValueError('A single-solid no-contact scope cannot contain a contact pair')
    boundaries, loads = {}, {}
    for row in model['boundary_dofs']:
        key, value = (row['node_id'], row['component']), number(row['value_mm'])
        if type(key[0]) is not int or type(key[1]) is not int or key[0] not in nodes or key[1] not in (1, 2, 3) or key in boundaries:
            raise ValueError('Duplicate/invalid displacement DOF; repair the boundary conditions')
        boundaries[key] = value
    for row in model['loads']:
        key, value = (row['node_id'], row['component']), number(row['force_N'])
        if type(key[0]) is not int or type(key[1]) is not int or key[0] not in nodes or key[1] not in (1, 2, 3) or key in loads or ('analysis_steps' not in model and key in boundaries and value != 0):
            raise ValueError('Force overlaps a prescribed displacement DOF or duplicates a load')
        loads[key] = value
    if (not boundaries and not allow_unrestrained_capture) or ('analysis_steps' not in model and not (any(value != 0 for value in loads.values()) or any(value != 0 for value in boundaries.values()))):
        raise ValueError('Provide explicit restraints and a nonzero force or prescribed displacement')
    dependent = set()
    for pair in model['contacts']:
        if pair['draft']['normal_law'] != 'tie':
            continue
        slave = {elements[e][slot] for e, face in pair['a']['element_faces'] for slot in FACES[face]}
        if slave & dependent or any(n in slave for n, d in boundaries):
            raise ValueError('묶음 A면의 절점은 다른 묶음의 종속 절점이나 변위 구속과 겹칠 수 없습니다. A/B 또는 구속 면을 다시 선택하세요.')
        dependent.update(slave)
    step = model['step']
    if set(step) - {'initial', 'period', 'minimum', 'maximum', 'increments', 'geometry',
                    'automatic', 'matrix_solver', 'axis_semantics', 'controls', 'field_controls', 'line_search_controls'}:
        raise ValueError('Unsupported static controls: STABILIZE and generic line search are not generated.')
    times = [number(step[key]) for key in ('initial', 'period', 'minimum', 'maximum')]
    if any(value <= 0 for value in times) or not times[2] <= times[0] <= min(times[1], times[3]):
        raise ValueError('Invalid static increment settings')
    if type(step['increments']) is not int or step['increments'] < 1 or step['geometry'] not in ('linear', 'nonlinear'):
        raise ValueError('Invalid native static step')
    if type(step['automatic']) is not bool or step['matrix_solver'] not in ('default', 'spooles', 'pastix', 'pardiso', 'iterativescaling', 'iterativecholesky'):
        raise ValueError('Unsupported native static solver')
    from .calculix_controls import validate_step_controls
    procedures = {s.get('procedure', model['analysis_steps']['procedure'])
                  for s in model.get('analysis_steps', {}).get('steps', [])} or {'static'}
    for procedure in procedures:
        validate_step_controls(step, procedure=procedure,
            penalty=any(p['draft']['normal_law'] == 'linear' for p in model['contacts']))
    if 'analysis_steps' in model:
        from .contact_steps import compile_program, validate_contributions
        validate_contributions(model)
        compile_program(model['analysis_steps'], model['conditions'],
                        allow_unrestrained_capture=allow_unrestrained_capture)
        if has_dynamic(model['analysis_steps']):
            for material in model['materials']:
                if number(material.get('density_tonne_per_mm3')) <= 0:
                    raise ValueError('Implicit dynamics requires positive density for every body')
    if any(p['draft'].get('tie_adjust',False) and p['draft']['normal_law']=='tie' for p in model['contacts']):
        from .adapters.tie_adjustment import cases
        cases(model,nodes,elements)
    from .periodic_constraints import compile_constraints
    compile_constraints(model, nodes, elements)
    from .contact_activation import compile_states
    compile_states(model)
    if enabled(model):
        validate_effective(model)
    from .pretension import sections
    sections(model)
    from .initial_field_conditions import effective
    effective(model)
    return nodes, elements, bodies


def _render(model):
    nodes, elements, bodies = validate_model(model)
    if 'restart' in model:
        from .calculix_dynamic import render_restart
        return render_restart(model)
    lines = ['*HEADING', 'CAE Lab separate-body native contact', '*NODE,NSET=Nall']
    lines += [str(n) + ',' + ','.join(num(v) for v in nodes[n]) for n in sorted(nodes)]
    for index, (body, membership) in enumerate(sorted(bodies.items()), 1):
        lines.append('*ELEMENT,TYPE=C3D10,ELSET=B' + str(index))
        lines += [str(e) + ',' + ','.join(map(str, elements[e])) for e in sorted(membership['elements'])]
        material = next(row for row in model['materials'] if row['body_id'] == body)
        lines.extend(['*MATERIAL,NAME=M' + str(index), '*ELASTIC',
            num(material['young_modulus_MPa']) + ',' + num(material['poisson_ratio']),
            *plastic_cards(material),
            '*SOLID SECTION,ELSET=B' + str(index) + ',MATERIAL=M' + str(index)])
    # Density is only effective in the explicitly selected dynamic capability.
    from .dynamic_model import has_dynamic
    if has_dynamic(model.get('analysis_steps', {})):
        # Insert inside each material definition, before its section.
        for index, body in enumerate(sorted(bodies), 1):
            material = next(r for r in model['materials'] if r['body_id'] == body)
            at = lines.index('*SOLID SECTION,ELSET=B'+str(index)+',MATERIAL=M'+str(index))
            lines[at:at] = ['*DENSITY', num(material['density_tonne_per_mm3'])]
    for pair in model['contacts']:
        lines.extend(contact_cards(pair).splitlines())
        if pair['draft']['gap_policy'] == 'prescribed':
            identifier = pair['object_id']
            lines.append('*CLEARANCE,MASTER=IND'+identifier+',SLAVE=DEP'+identifier+
                         ',VALUE='+num(pair['draft']['nominal_gap_mm']))
    from .calculix_dynamic import model_cards
    lines += model_cards(model)
    from .periodic_constraints import cards as periodic_cards
    lines += periodic_cards(model)
    from .pretension_deck import model_cards as pretension_cards
    lines += pretension_cards(model)
    if 'analysis_steps' in model:
        from .contact_steps import render_steps
        return '\n'.join(lines + render_steps(model) + [''])
    step = model['step']
    lines.append('*STEP,INC=' + str(step['increments']) + (',NLGEOM' if step['geometry'] == 'nonlinear' else ''))
    from .calculix_controls import cards as convergence_cards
    lines.extend(convergence_cards(step))
    solvers = {'default': '', 'spooles': 'SPOOLES', 'pastix': 'PASTIX', 'pardiso': 'PARDISO',
               'iterativescaling': 'ITERATIVE SCALING', 'iterativecholesky': 'ITERATIVE CHOLESKY'}
    selected = solvers[step['matrix_solver']]
    lines.append('*STATIC' + (',SOLVER=' + selected if selected else '') + ('' if step['automatic'] else ',DIRECT'))
    lines.append(','.join(num(step[key]) for key in ('initial', 'period', 'minimum', 'maximum')))
    lines.append('*BOUNDARY')
    lines += [str(row['node_id']) + ',' + str(row['component']) + ',' + str(row['component']) + ',' + num(row['value_mm'])
              for row in model['boundary_dofs']]
    if model['loads']:
        lines.append('*CLOAD')
        lines += [str(row['node_id']) + ',' + str(row['component']) + ',' + num(row['force_N']) for row in model['loads']]
    has_tie = any(pair['draft']['normal_law'] == 'tie' for pair in model['contacts'])
    lines.extend(solid_output_cards(model))
    from .contact_activation import output_cards
    lines.extend(output_cards(model['contacts']))
    lines.extend(['*END STEP', ''])
    return '\n'.join(lines)


def render(model):
    from .adapters.initial_field_deck import decorate
    return decorate(model, _render(model))


def solid_output_cards(model, frequency=''):
    """Request the real native nodal recovery; PE is the FRD name of scalar PEEQ."""
    ns1 = has_plasticity(model) or model.get('analysis_scope') == 'single_solid_static' or bool(model.get('pretension_sections'))
    tie = any(pair['draft']['normal_law'] == 'tie' for pair in model['contacts'])
    lines = ['*NODE FILE,GLOBAL=YES' + frequency, 'U,RF' if ns1 or tie else 'U']
    if ns1:
        lines += ['*EL FILE' + frequency, 'S,E,PEEQ' if has_plasticity(model) else 'S,E']
    elif tie:
        lines += ['*EL FILE' + frequency, 'S']
    return lines
