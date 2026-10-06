"""Engineering input semantics for revision-bound mechanical declarations.

This checks declared units, finite constants and named selections. It neither
qualifies measurements nor supplies a structural/strength/release verdict.
"""

import math


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_declaration(catalog, declaration):
    selections = {item['id']: item for item in catalog['selections']}
    if len(selections) != len(catalog['selections']):
        raise ValueError('Ambiguous model selection catalog')
    frames = {item['id'] for item in catalog['coordinate_systems']}
    if declaration['coordinate_system'] not in frames:
        raise ValueError('Coordinate system is not declared by this model revision')
    identities, assigned = set(), set()
    for group, role in (('materials', 'material'), ('boundary_conditions', 'boundary'), ('loads', 'load')):
        for item in declaration[group]:
            if item['id'] in identities:
                raise ValueError('Duplicate material/load/boundary identity')
            identities.add(item['id'])
            selection = selections.get(item['selection_id'])
            if selection is None or role not in selection['roles']:
                raise ValueError('Selection is absent or cannot carry this condition')
            if group == 'materials':
                if item['selection_id'] in assigned:
                    raise ValueError('Conflicting material assignments')
                assigned.add(item['selection_id'])
                e, nu = item['young_modulus_MPa'], item['poisson_ratio']
                if not _finite(e) or e <= 0 or not _finite(nu) or not -1 < nu < .5:
                    raise ValueError('Isotropic elastic constants require E>0 and -1<nu<0.5')
                if not item['source']['description'].strip():
                    raise ValueError('Material source description is required')
            else:
                if item['coordinate_system'] not in frames:
                    raise ValueError('Condition coordinate system is not in the model catalog')
                if any(not _finite(value) for value in item['components'].values()):
                    raise ValueError('Load/displacement components must be finite')
                if not item['source'].strip():
                    raise ValueError('Load/boundary source is required')
    contact = declaration['contact']
    pairs = contact.get('pairs', [])
    if 'initial_state' in contact and (not isinstance(contact['initial_state'], str) or contact['mode'] not in {'frictionless', 'mixed'} or
            contact['initial_state'] not in {'OPEN', 'GEOMETRIC', 'CLOSED_ASSUMED'}):
        raise ValueError('Initial contact state requires an explicit supported frictionless declaration')
    if not contact['source'].strip() or (contact['mode'] == 'none' and pairs):
        raise ValueError('Contact-none must explicitly declare no contact pairs')
    if contact['mode'] != 'none' and not pairs:
        raise ValueError('A contact declaration needs named pairs')
    for pair in pairs:
        if (pair['selection_a'] == pair['selection_b'] or
                any(pair[key] not in selections for key in ('selection_a', 'selection_b'))):
            raise ValueError('Contact pair needs two distinct catalog selections')
        if contact['mode'] == 'mixed':
            if (pair.get('law') not in {'bonded', 'frictionless'} or pair.get('master') not in {'a', 'b'}
                    or not isinstance(pair.get('source'), str) or not pair['source'].strip()):
                raise ValueError('Mixed pairs need an explicit law, master side and source')
        if 'distance_max_mm' in pair and (not _finite(pair['distance_max_mm']) or pair['distance_max_mm'] <= 0):
            raise ValueError('Bonded search distance must be finite and positive')
    mesh = declaration['mesh']
    if mesh['mode'] == 'selected':
        size = mesh['max_size_mm']
        if not _finite(size) or size <= 0:
            raise ValueError('Selected mesh size must be finite and positive')
    elif mesh['mode'] == 'retained':
        retained = catalog.get('retained_mesh')
        if not isinstance(retained, dict) or retained.get('mesh_revision') != mesh['mesh_revision']:
            raise ValueError('Retained mesh must be explicitly bound to this catalog')
    else:
        raise ValueError('Unknown declared mesh mode')
