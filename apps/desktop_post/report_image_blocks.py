"""Bounded single-field block-color audit, using native SM properties.

Source reviewed: ParaView v5.13.2 and v6.2.0 vtkSMColorMapEditorHelper.cxx
(GetBlocksColorArrays, GetBlocksLookupTables, SetBlocksScalarColoringInternal),
v5.13.2 views_and_representations.xml and v6.2.0
representationsinternal_remotingviews.xml. Never use SelectedBlockSelectors: it describes
what the inspector selects, NOT all configured selectors affecting the image.
"""
from __future__ import annotations

SUPPORTED_VERSIONS = frozenset(((5, 13, 2), (6, 2, 0)))
PROFILE = 'ParaView-SM-single-field-blocks/1'
# The XML exposes these on the surface representation. Runtime widths/types are
# checked before use; unsupported APIs cannot silently look like empty vectors.
VECTOR_WIDTHS = {'BlockColorArrayNames': 3, 'BlockColors': 4, 'BlockMapScalars': 2,
                 'BlockInterpolateScalarsBeforeMappings': 2, 'BlockOpacities': 2,
                 'BlockUseSeparateColorMaps': 2}
MAX_ELEMENTS = 16384


def _raw(proxy):
    return getattr(proxy, 'SMProxy', proxy)


def _id(proxy):
    if proxy is None:
        return None
    return str(_raw(proxy).GetGlobalIDAsString())


def _vector(rep, name, width):
    prop = _raw(rep).GetProperty(name)
    if prop is None or not prop.IsA('vtkSMStringVectorProperty'):
        raise ValueError('블록 색상 검증 API가 없습니다: ' + name)
    if prop.GetNumberOfElementsPerCommand() != width:
        raise ValueError('지원하지 않는 블록 색상 property 구조입니다: ' + name)
    count = prop.GetNumberOfElements()
    if not 0 <= count <= MAX_ELEMENTS or count % width:
        raise ValueError('블록 색상 설정의 길이가 잘못되었습니다: ' + name)
    data = [prop.GetElement(i) for i in range(count)]
    rows = [data[i:i + width] for i in range(0, count, width)]
    seen = set()
    for row in rows:
        if not isinstance(row[0], str) or not row[0] or row[0] in seen:
            raise ValueError('블록 selector가 비어 있거나 중복됩니다: ' + name)
        seen.add(row[0])
    return rows


def inspect(rep, lookup, *, association, field_name, representation_properties, version=None):
    """Reject differing configured overrides, including potentially inactive ones.

    This deliberately avoids guessing selector reachability/inheritance. Every
    configured override must be globally equivalent, so parent/child selectors,
    hidden legends, or the inspector's current selection cannot bypass the gate.
    A dormant incompatible override also blocks until explicitly removed.
    """
    if version is None:
        from paraview import servermanager
        manager = servermanager.vtkSMProxyManager
        version = (manager.GetVersionMajor(), manager.GetVersionMinor(), manager.GetVersionPatch())
    version = tuple(version)
    if version not in SUPPORTED_VERSIONS:
        raise ValueError('이 ParaView 버전의 블록별 색상 계약은 미확인입니다. 원이미지는 유지됩니다: ' + str(version))
    values = {name: _vector(rep, name, width) for name, width in VECTOR_WIDTHS.items()}
    lut_prop = _raw(rep).GetProperty('BlockLookupTables')
    if lut_prop is None or not lut_prop.IsA('vtkSMProxyProperty'):
        raise ValueError('블록별 LookupTable 검증 API가 없습니다.')
    rows = values['BlockColorArrayNames']
    if lut_prop.GetNumberOfProxies() != len(rows):
        raise ValueError('블록 필드와 LookupTable 대응이 불완전합니다.')
    global_id = _id(lookup)
    if global_id is None:
        raise ValueError('선택한 물리 필드의 LookupTable이 없습니다.')
    association_id = {'POINTS': 0, 'CELLS': 1}[association]
    lookup_ids = []
    for i, (selector, declared_association, array) in enumerate(rows):
        if str(declared_association) != str(association_id) or array != field_name:
            raise ValueError('블록별 다른 배열/association 또는 단색 설정은 단일 필드 그림으로 채택하지 않습니다: ' + selector)
        identity = _id(lut_prop.GetProxy(i)); lookup_ids.append(identity)
        # Components, ranges, and color maps are properties of the shared LUT.
        # Independent-but-currently-similar LUTs are deliberately not equated.
        if identity != global_id:
            raise ValueError('블록별 성분 또는 LookupTable이 전역 필드와 다릅니다: ' + selector)
    if values['BlockColors']:
        raise ValueError('블록별 고정 RGB 색상은 물리 필드값으로 표시할 수 없습니다. 블록 색상 override를 해제하세요.')
    for selector, value in values['BlockMapScalars']:
        if value != '1':
            raise ValueError('블록별 직접 RGB 색상을 단일 물리 필드로 표시할 수 없습니다: ' + selector)
    for prop_name, global_name in (('BlockInterpolateScalarsBeforeMappings', 'InterpolateScalarsBeforeMapping'),
                                   ('BlockOpacities', 'Opacity')):
        global_value = representation_properties.get(global_name)
        for selector, value in values[prop_name]:
            try:
                same = global_value is not None and float(value) == float(global_value)
            except (ValueError, TypeError, OverflowError):
                same = False
            if not same:
                raise ValueError('블록별 표시 설정이 전역 필드와 다릅니다: ' + prop_name + ' / ' + selector)
    # This flag has no independent coloring effect without a block LUT. Validate
    # its shape; any *actual* independent LUT was rejected above.
    if any(value not in ('0', '1') for _, value in values['BlockUseSeparateColorMaps']):
        raise ValueError('블록별 독립 색상표 설정을 확인하지 못했습니다.')
    return {'profile': PROFILE, 'version': list(version), 'status': 'SINGLE_GLOBAL_FIELD',
            'policy': 'ALL_CONFIGURED_SELECTORS_EQUIVALENT', 'properties': values,
            'global_lut_id': global_id, 'block_lut_ids': lookup_ids}
