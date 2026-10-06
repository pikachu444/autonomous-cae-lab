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
    if not contact['source'].strip() or (contact['mode'] == 'none' and pairs):
        raise ValueError('Contact-none must explicitly declare no contact pairs')
    if contact['mode'] != 'none' and not pairs:
        raise ValueError('A contact declaration needs named pairs')
    for pair in pairs:
        if (pair['selection_a'] == pair['selection_b'] or
                any(key not in selections for key in pair.values())):
            raise ValueError('Contact pair needs two distinct catalog selections')
    size = declaration['mesh']['max_size_mm']
    if not _finite(size) or size <= 0:
        raise ValueError('Selected mesh size must be finite and positive')
