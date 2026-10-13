"""Native mapped-element correspondence for independent candidate copies.

Exact unchanged geometry reuses its explicit target. Changed geometry requires
FreeCAD's mapped name and an unambiguous mapped-element history. No proximity,
face-count, index matching or fingerprint refresh is an identity rule.
"""
from copy import deepcopy
import re

from caelab.storage import canonical_hash
from .fem_edit import _target, _references, _native_type


def _history(shape, mapped):
    value = shape.getElementHistory(mapped)
    if value is None:
        return None
    # The tag is a native shape identity, not a current face index.
    tag, original, intermediate = value
    return {'tag': int(tag), 'original': str(original),
            'intermediate': [str(item) for item in intermediate]}


def anchor(obj, name):
    shape = obj.Shape
    resolved = obj.resolveSubElement(name)
    if (not resolved or resolved[0] is not obj or not resolved[1] or
            str(resolved[2]).startswith('?')):
        raise ValueError('No unambiguous native mapped-element identity for ' + obj.Label + '.' + name)
    mapped = str(shape.getElementMappedName(resolved[1]))
    mapping = dict(shape.ElementMap)
    if not mapped or re.fullmatch(r'(Face|Edge|Vertex|Solid)\d+', mapped) or mapped not in mapping:
        raise ValueError('No native mapped-element identity for ' + obj.Label + '.' + name)
    indexed = str(shape.getElementIndexedName(mapped))
    if indexed != name or str(mapping[mapped]) != name:
        raise ValueError('Native mapped-element identity does not resolve to the selected element')
    return {'mapped': mapped, 'subname': str(resolved[1]), 'kind': re.match('[A-Za-z]+', name)[0],
            'history': _history(shape, mapped)}


def validate_original_contacts(owner, analysis_id=None):
    """Before any candidate write: never normalize an externally edited pair."""
    for record in owner.fem.contact._data()['contacts']:
        if analysis_id is not None and record['analysis_id'] != analysis_id:
            continue
        obj = owner._object(record['object_id'])
        if getattr(obj, 'Suppressed', False):
            # Suppressed definitions remain untouched by candidate preparation.
            continue
        errors = owner.fem.contact.errors(record)
        if errors:
            raise ValueError('Repair contact ' + obj.Label + ': ' + errors[0]['message'])


def capture(owner):
    data, targets = owner.fem._metadata(), {}
    def add(target):
        key = canonical_hash(target)
        if key in targets:
            return key
        source = owner._object(target['object_id'])
        names = [row['name'] for row in target['subelements']]
        if _target(source, names) != target:
            raise ValueError('Repair the current named face/condition before making a candidate recipe')
        identities, unavailable = [], None
        try:
            identities = [anchor(source, name) for name in names]
        except (ValueError, RuntimeError, AttributeError, TypeError) as error:
            unavailable = str(error)
        from .occurrence_fem import capture_element
        occurrence = capture_element(owner, source, names)
        targets[key] = {'target': deepcopy(target), 'elements': identities,
                        'history_unavailable': unavailable}
        if occurrence:
            targets[key]['occurrence'] = occurrence
        return key
    validate_original_contacts(owner)
    for row in data.get('mesh_local_sizes', []):
        add(row['target'])
    for row in data['regions']:
        add(row['target'])
    for row in data['conditions']:
        for target in row['targets']:
            add(target)
        if row.get('direction_target'):
            add(row['direction_target'])
    for row in owner.fem.contact._data()['contacts']:
        for side in ('a', 'b'):
            if row.get(side):
                add(row[side]['target'])
    # Preserve material references and native refinement references as well.
    links = []
    for obj in owner.doc.Objects:
        if 'References' in getattr(obj, 'PropertiesList', []):
            entries = []
            for ref in _references(obj):
                source = owner._object(ref['object_id'])
                names = ref['subelements']
                if names in ([], [''], ['Solid1']):
                    entries.append({'body': source.Name, 'names': names})
                else:
                    entries.append({'target': add(_target(source, names))})
            links.append({'object_id': obj.Name, 'property': 'References', 'entries': entries})
        if _native_type(obj) == 'Fem::ConstraintForce' and getattr(obj, 'Direction', None):
            source, names = obj.Direction
            names = [names] if isinstance(names, str) else list(names)
            links.append({'object_id': obj.Name, 'property': 'Direction',
                          'entries': [{'target': add(_target(source, names))}]})
    return {'policy': 'freecad-mapped-element-v1', 'targets': targets, 'links': links}


def resolve(owner, record):
    old = record['target']
    obj = owner._object(old['object_id'])
    if obj.TypeId != old['type']:
        raise ValueError('Native source object type changed')
    names = [row['name'] for row in old['subelements']]
    try:
        unchanged = _target(obj, names) == old
    except ValueError:
        unchanged = False
    if record.get('occurrence'):
        from .occurrence_fem import resolve_element
        return resolve_element(owner, record['occurrence'])
    if unchanged:
        return obj, names, 'unchanged'
    if record['history_unavailable'] or len(record['elements']) != len(names):
        raise ValueError('REFERENCE_UNRESOLVED: ' + str(record['history_unavailable']))
    return obj, resolve_names(obj, record['elements']), 'native_mapped_element'


def resolve_names(obj, elements):
    """Exact mapped native history, also used for Assembly connector vertices."""
    mapping, resolved = dict(obj.Shape.ElementMap), []
    for item in elements:
        mapped = item['mapped']
        if mapped not in mapping:
            raise ValueError('REFERENCE_DELETED: mapped element no longer exists')
        native = obj.resolveSubElement(item['subname'])
        if not native or native[0] is not obj or not native[1] or str(native[2]).startswith('?'):
            raise ValueError('REFERENCE_UNRESOLVED: native mapping was deleted, split or changed owner')
        if str(obj.Shape.getElementMappedName(native[1])) != mapped:
            raise ValueError('REFERENCE_OWNER_CHANGED: native mapped identity changed')
        element = obj.Shape.getElement(native[1])
        if element.isNull():
            raise ValueError('REFERENCE_DELETED: mapped native element is unavailable')
        name = str(obj.Shape.getElementIndexedName(mapped))
        if (name != str(mapping[mapped]) or
                not re.fullmatch(re.escape(item['kind']) + r'\d+', name)):
            raise ValueError('REFERENCE_AMBIGUOUS: mapped name has no exact native element')
        # Direct resolution is the admission rule. Inspect exact descendants
        # of the saved mapped key, not faces sharing some earlier ancestor.
        descendants = {name}
        for candidate, indexed in mapping.items():
            if not str(indexed).startswith(item['kind']):
                continue
            h = _history(obj.Shape, str(candidate))
            if h and (h['original'] == mapped or mapped in h['intermediate']):
                descendants.add(str(indexed))
        if descendants != {name}:
            raise ValueError('REFERENCE_SPLIT: exact mapped history has multiple current descendants')
        resolved.append(name)
    if len(set(resolved)) != len(resolved):
        raise ValueError('REFERENCE_MERGED: distinct selected elements resolve to the same native element')
    return resolved


def apply(owner, saved):
    if saved.get('policy') != 'freecad-mapped-element-v1':
        raise ValueError('Unsupported candidate correspondence policy')
    resolved = {key: resolve(owner, row) for key, row in saved['targets'].items()}
    def change():
        for link in saved['links']:
            obj = owner._object(link['object_id'])
            if _native_type(obj) == 'Fem::ConstraintContact':
                continue  # Contact editor owns the effective pair and signature.
            refs = []
            for entry in link['entries']:
                if 'target' in entry:
                    source, names, _ = resolved[entry['target']]
                else:
                    source, names = owner._object(entry['body']), entry['names']
                    if not source.Shape.copy(True, False).isValid() or len(source.Shape.Solids) != 1:
                        raise ValueError('Material/refinement body is no longer one valid solid')
                refs.append((source, list(names)))
            setattr(obj, link['property'], refs[0] if link['property'] == 'Direction' else refs)
        data = owner.fem._metadata()
        for region in data['regions']:
            obj, names, _ = resolved[canonical_hash(region['target'])]
            region['target'] = _target(obj, names)
        for sizing in data.get('mesh_local_sizes', []):
            prior = deepcopy(sizing['target'])
            obj, names, method = resolved[canonical_hash(prior)]
            sizing['target'] = _target(obj, names)
            if sizing['target'] != prior:
                data.setdefault('candidate_reference_history', []).append({
                    'object_id': sizing['object_id'], 'prior_target': prior,
                    'target': deepcopy(sizing['target']), 'method': method})
        owner.write_metadata(data)
    owner._transaction('Candidate native correspondence', change)
    for row in list(owner.fem._metadata()['conditions']):
        obj = owner._object(row['object_id'])
        owner._transaction('Record mapped condition',
            lambda obj=obj, row=row: owner.fem._record_condition(obj, row.get('region_id'), row.get('direction_region_id')))
    for old in list(owner.fem.contact._data()['contacts']):
        if getattr(owner._object(old['object_id']), 'Suppressed', False):
            continue
        record = deepcopy(old)
        for side in ('a', 'b'):
            if not old.get(side):
                continue
            obj, names, _ = resolved[canonical_hash(old[side]['target'])]
            record[side] = owner.fem.contact.snapshot(obj, names, region_id=old[side].get('region_id'))
        owner.fem.contact._persist(owner._object(old['object_id']), record, 'candidate mapped contact')
    return [{'object_id': row['target']['object_id'],
             'old': [e['name'] for e in row['target']['subelements']],
             'new': resolved[key][1], 'method': resolved[key][2]}
            for key, row in saved['targets'].items()]
