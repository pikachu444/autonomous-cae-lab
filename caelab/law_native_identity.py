"""LAW-C1: native *physical* identity, never a Python allocation address.

This module imports no FreeCAD/runtime and reads no files. It recognizes only
FreeCAD 1.1.4's two supported specimen Proxy classes. Legacy normalization is
comparison-only: the hash-bound assignment/review/source is NEVER edited/rehashed.
Legacy local Material References use the retained owner document_id, not the
FreeCAD runtime document name (which is derived from the opened filename).
All other target data (including physical PropertiesList values) is retained.
"""
from copy import deepcopy
import re

FREECAD_VERSION = ('1', '1', '4')
PROXY_SCHEMA = 'freecad-specimen-proxy/1'
PROXY_CLASSES = {
    'Fem::MaterialCommon': 'femobjects.material_common.MaterialCommon',
    'Fem::SolverCcxTools': 'femobjects.solver_ccxtools.SolverCcxTools',
}
# An exact CPython default instance repr, not an arbitrary text/address stripper.
_LEGACY = re.compile(r'<([A-Za-z_][A-Za-z_0-9.]*) object at 0x[0-9a-fA-F]+>\Z')
_RUNTIME_REPR = re.compile(r'\bobject at 0x[0-9a-fA-F]+>')


def require_native_version(version):
    """Capture/re-freeze only in the explicitly supported native ABI."""
    if tuple(str(v) for v in version[:3]) != FREECAD_VERSION:
        raise ValueError('LAW_NATIVE_VERSION_UNSUPPORTED: expected FreeCAD 1.1.4')


def _descriptor(native_type):
    if native_type not in PROXY_CLASSES:
        raise ValueError('LAW_NATIVE_PROXY_UNSUPPORTED: ' + str(native_type))
    return {'schema': PROXY_SCHEMA, 'python_class': PROXY_CLASSES[native_type],
            'native_type': native_type}


def capture_proxy(value, native_type):
    """Capture only the supported proxy declaration, not str/repr(instance).

FreeCAD stores physical settings as document properties; the caller still
captures ALL of the previous physical PropertiesList fields separately. An
unknown proxy implementation is rejected, not treated as the supported one.
"""
    expected = _descriptor(native_type)
    cls = type(value)
    actual = cls.__module__ + '.' + cls.__qualname__
    if actual != expected['python_class'] or getattr(value, 'Type', None) != native_type:
        raise ValueError('LAW_NATIVE_PROXY_UNSUPPORTED: class/type declaration differs for ' + native_type)
    return expected


def stable_native_text(value):
    """Keep existing typed Quantity/Placement text, fail closed on other objects."""
    text = str(value)
    if _RUNTIME_REPR.search(text):
        raise ValueError('LAW_NATIVE_VALUE_UNSUPPORTED: runtime object is not a physical property')
    return text


def _normalize_object(row):
    value = deepcopy(row)
    if not isinstance(value, dict) or not isinstance(value.get('properties'), dict):
        raise ValueError('LAW_NATIVE_IDENTITY_INVALID: expected captured native properties')
    props = value['properties']
    native_type = value.get('type')
    if 'Proxy' in props:
        expected = _descriptor(native_type)
        proxy = props['Proxy']
        if isinstance(proxy, str):
            match = _LEGACY.fullmatch(proxy)
            if match is None or match.group(1) != expected['python_class']:
                raise ValueError('LAW_NATIVE_PROXY_UNSUPPORTED: unrecognized retained Proxy declaration')
        elif proxy != expected:
            raise ValueError('LAW_NATIVE_PROXY_UNSUPPORTED: retained proxy descriptor differs')
        props['Proxy'] = expected
    elif native_type in PROXY_CLASSES:
        raise ValueError('LAW_NATIVE_PROXY_MISSING: supported scripted native object needs its declaration')
    return value


def _local_material_references(target):
    """Normalize ONLY the already-admitted whole-solid material reference slot.

    Legacy capture allowed [] or one exact whole-solid reference. New capture
    independently rejects cross-document objects BEFORE serialization and uses
    the owner's persistent document_id. This legacy interpretation never looks
    up/rebinds by an object/document name and never rewrites a stored record.
    Arbitrary solver links, metadata and external references are NOT normalized.
    """
    if 'material' not in target:
        return  # Existing controlled non-native test targets are not native proof.
    docid = target.get('document_id')
    shape = target.get('geometry', {}).get('object_id')
    if not isinstance(docid, str) or not docid or not isinstance(shape, str) or not shape:
        raise ValueError('LAW_NATIVE_IDENTITY_INVALID: local reference needs persistent document/shape IDs')
    material = target['material']
    rows = [material] + [row for row in target.get('native_analysis_members', [])
                        if row.get('object_id') == material.get('object_id')]
    legacy_names = set()
    for row in rows:
        refs = row.get('properties', {}).get('References', [])
        if refs == []:
            continue
        if (not isinstance(refs, list) or len(refs) != 1 or
                not isinstance(refs[0], list) or len(refs[0]) != 2):
            raise ValueError('LAW_NATIVE_IDENTITY_INVALID: whole-solid material reference required')
        link, names = refs[0]
        if not isinstance(link, dict) or link.get('object_id') != shape or names not in ([], ['Solid1']):
            raise ValueError('LAW_NATIVE_IDENTITY_INVALID: material reference differs from admitted local solid')
        if set(link) == {'object_id', 'document'}:
            if not isinstance(link['document'], str) or not link['document']:
                raise ValueError('LAW_NATIVE_IDENTITY_INVALID: missing legacy local document name')
            legacy_names.add(link['document'])
        elif set(link) != {'object_id', 'document_id'} or link['document_id'] != docid:
            raise ValueError('LAW_NATIVE_IDENTITY_INVALID: different document or unsupported reference')
        refs[0][0] = {'object_id': shape, 'document_id': docid}
    if len(legacy_names) > 1:
        raise ValueError('LAW_NATIVE_IDENTITY_INVALID: contradictory legacy local document names')


def semantic_target(target):
    """Stable target comparison; full physics/IDs/mesh/step remain significant.

Only session_id/generation are live CAS data. Only Proxy properties at these
three exact native-capture locations are legacy-normalized. No recursive regex,
no address hashing, no mutation of the retained target/receipt, no current-value
rebasing. Apply still compares the full live target in verify_review.
"""
    if not isinstance(target, dict):
        raise ValueError('LAW_NATIVE_IDENTITY_INVALID: target must be an object')
    result = {k: deepcopy(v) for k, v in target.items()
              if k not in ('session_id', 'generation')}
    for key in ('material', 'native_context_solver'):
        if key in result:
            result[key] = _normalize_object(result[key])
    if 'native_analysis_members' in result:
        if not isinstance(result['native_analysis_members'], list):
            raise ValueError('LAW_NATIVE_IDENTITY_INVALID: Analysis membership must be a list')
        result['native_analysis_members'] = [_normalize_object(row) for row in result['native_analysis_members']]
    _local_material_references(result)
    return result
