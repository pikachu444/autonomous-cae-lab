"""Contact declarations and ID-preserving mesh assembly; no solver or document owner."""
import math

BACKEND = 'structure.calculix.contact'
CONTACT_FIELDS = {'label', 'normal_law', 'tangential_law', 'friction_coefficient',
    'normal_stiffness_MPa_per_mm', 'stick_stiffness_MPa_per_mm', 'gap_policy',
    'nominal_gap_mm', 'adjustment_mm', 'normal', 'sliding', 'step', 'activation',
    'a_region_id', 'b_region_id'}


def default_contact():
    return {'label': 'Contact', 'normal_law': None, 'tangential_law': None,
        'friction_coefficient': '', 'normal_stiffness_MPa_per_mm': '',
        'stick_stiffness_MPa_per_mm': '', 'gap_policy': 'geometry',
        'nominal_gap_mm': '', 'adjustment_mm': 0, 'normal': 'outward_solid',
        'sliding': 'surface_to_surface', 'step': 'Step1', 'activation': 'whole_step',
        'a_region_id': None, 'b_region_id': None}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError('Enter a finite number')
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError('Enter a complete finite number') from error
    if not math.isfinite(result):
        raise ValueError('Enter a finite number')
    return result


def law_errors(draft):
    """Invalid/unsupported choices stay in the draft; only export is gated."""
    errors = []
    def fail(field, message):
        errors.append({'path': field, 'message': message, 'severity': 'error', 'blocks_evaluation': True})
    if draft.get('normal_law') != 'linear':
        fail('normal_law', 'This contact adapter requires explicit linear pressure-overclosure stiffness; hard, tie and cohesive remain unsupported choices.')
    if draft.get('tangential_law') not in {'frictionless', 'coulomb'}:
        fail('tangential_law', 'Select frictionless or Coulomb contact; no law is inferred.')
    fields = [('normal_stiffness_MPa_per_mm', True)]
    if draft.get('tangential_law') == 'coulomb':
        fields += [('friction_coefficient', False), ('stick_stiffness_MPa_per_mm', True)]
    for field, positive in fields:
        try:
            value = number(draft.get(field))
            if value < 0 or positive and value == 0:
                raise ValueError('Use a positive stiffness' if positive else 'Friction coefficient must be nonnegative')
        except ValueError as error:
            fail(field, str(error))
    if draft.get('gap_policy') != 'geometry':
        fail('gap_policy', 'Only the actual geometric gap is admitted. An independently prescribed clearance needs an effective solver mapping.')
    if draft.get('nominal_gap_mm') not in ('', None):
        fail('nominal_gap_mm', 'A typed nominal gap is not a mesh adjustment; clear it to use actual geometry.')
    try:
        if number(draft.get('adjustment_mm')) != 0:
            fail('adjustment_mm', 'This route uses unadjusted nodes. Native Adjust is a different operation, not a nominal gap.')
    except ValueError as error:
        fail('adjustment_mm', str(error))
    if draft.get('normal') != 'outward_solid':
        fail('normal', 'Physical normal reversal is not implemented by the native contact writer. Change the effective face/role, not a display arrow.')
    if draft.get('sliding') != 'surface_to_surface':
        fail('sliding', 'The admitted native card is TYPE=SURFACE TO SURFACE; other formulations need a separate mapping.')
    if draft.get('step') != 'Step1' or draft.get('activation') != 'whole_step':
        fail('step', 'The admitted route has one static Step1, contact active throughout. Interval activation is unsupported.')
    return errors


def separate_meshes(bodies):
    """Remap each body's local IDs independently, including coincident coordinates.

    Input rows use native C3D10 connectivity; the explicit pinned permutation
    converts it to deck order.
    This preserves body membership; it never merges by coordinates.
    """
    from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10
    known, nodes, elements, mappings = set(), [], [], {}
    if not isinstance(bodies, list) or len(bodies) < 2:
        raise ValueError('Contact needs at least two separately meshed bodies')
    for body in bodies:
        identifier = body['body_id']
        if not isinstance(identifier, str) or not identifier or identifier in known:
            raise ValueError('Body identities must be distinct')
        known.add(identifier)
        local_nodes, local_elements = {}, {}
        for row in body['nodes']:
            native_id = row['node_id']
            if type(native_id) is not int or native_id <= 0 or native_id in local_nodes:
                raise ValueError('Duplicate or invalid body node ID')
            point = row['position_mm']
            if not isinstance(point, (tuple, list)) or len(point) != 3:
                raise ValueError('Body node needs three coordinates')
            point = [number(value) for value in point]
            global_id = len(nodes) + 1
            local_nodes[native_id] = global_id
            nodes.append({'node_id': global_id, 'body_id': identifier,
                          'native_node_id': native_id, 'position_mm': point})
        used = set()
        for row in body['elements']:
            native_id, connectivity = row['element_id'], row['native_node_ids']
            if (type(native_id) is not int or native_id <= 0 or native_id in local_elements
                    or row['type'] != 'C3D10' or len(connectivity) != 10
                    or len(set(connectivity)) != 10 or any(node not in local_nodes for node in connectivity)):
                raise ValueError('Body needs distinct, complete native C3D10 elements')
            global_id = len(elements) + 1
            local_elements[native_id] = global_id
            used.update(connectivity)
            elements.append({'element_id': global_id, 'body_id': identifier,
                'native_element_id': native_id, 'native_node_ids': list(connectivity),
                'node_ids': [local_nodes[connectivity[slot]] for slot in CCX_FROM_NATIVE_TET10]})
        if not local_elements or used != set(local_nodes):
            raise ValueError('A body mesh has missing or unused volume nodes')
        mappings[identifier] = {'nodes': local_nodes, 'elements': local_elements}
    return {'nodes': nodes, 'elements': elements, 'body_maps': mappings,
            'native_to_deck_slots': list(CCX_FROM_NATIVE_TET10),
            'interface_policy': 'independent_body_dofs'}


def surface_union(body_id, face_rows, mappings):
    """One physical surface is a deduplicated union, never pair multiplication."""
    if body_id not in mappings or not face_rows:
        raise ValueError('Select a nonempty surface on an admitted body')
    result, sources = set(), []
    for face in face_rows:
        mapped = []
        for element, side in face['element_faces']:
            if type(element) is not int or element not in mappings[body_id]['elements']:
                raise ValueError('Surface element is outside its owning body')
            if type(side) is not int or side not in (1, 2, 3, 4):
                raise ValueError('C3D10 surface needs an exact CalculiX side 1..4')
            entry = (mappings[body_id]['elements'][element], side)
            mapped.append(list(entry))
            result.add(entry)
        if not mapped:
            raise ValueError('A selected CAD face has no mapped element faces')
        sources.append({'face': face['face'], 'element_faces': mapped})
    return {'body_id': body_id, 'element_faces': [list(row) for row in sorted(result)],
            'cad_faces': sources}
