"""Adapter-owned catalog of the exported CAD revision, without native execution.

The first contract names one final solid and existing support-screen regions.
Adapter regions are declared derivations verified again by native preflight;
they are never advertised as native face IDs or tessellation triangle indices.
"""

import hashlib
from pathlib import Path, PurePosixPath

from ..storage import load_json


GLOBAL = {'id': 'global', 'type': 'cartesian', 'unit': 'mm',
          'basis': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
          'origin': [0, 0, 0], 'label': 'CAD의 전역 직교 좌표계'}


def _metadata(parent_root, parent, name):
    entries = [a for a in parent['artifacts'] if a['path'] == name]
    if len(entries) != 1:
        raise ValueError('Exactly one manifested CAD metadata artifact is required')
    root = Path(parent_root).resolve()
    item = entries[0]
    path = root / PurePosixPath(name)
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('CAD catalog metadata is missing or outside its experiment')
    raw = path.read_bytes()
    if (item['sha256'] != hashlib.sha256(raw).hexdigest() or item['size_bytes'] != len(raw)
            or item['revision'] != parent['cad_revision']):
        raise ValueError('CAD catalog metadata differs from its manifest or revision')
    return load_json(path), item['sha256']


def final_solid_catalog(parent_root, parent, *, backend):
    cad, cad_sha = _metadata(parent_root, parent, 'cad/result.json')
    bom = cad.get('bom')
    if (cad.get('cad_generated') is not True or cad.get('decision') != 'REVIEW_REQUIRED'
            or not isinstance(bom, list) or len(bom) != 1 or not isinstance(bom[0], dict)):
        raise ValueError('This catalog requires one verified final CAD solid; assembly catalog is separate')
    from plugins.elasticity.conditions import _finite
    if not _finite(bom[0].get('volume_mm3')) or bom[0]['volume_mm3'] <= 0:
        raise ValueError('Final CAD solid has no positive declared volume')
    catalog = {
        'schema_version': '1.0', 'cad_backend': backend,
        'model': parent['provenance'].get('cad_model') or cad.get('model') or cad.get('design'),
        'selections': [{'id': 'B-final', 'label': '이 개정의 전체 최종 솔리드',
                        'kind': 'whole_final_solid', 'roles': ['material', 'boundary', 'load'],
                        'part': bom[0].get('part'), 'volume_mm3': bom[0]['volume_mm3']}],
        'coordinate_systems': [GLOBAL.copy()],
        'metadata_sha256': cad_sha,
        'catalog_policy_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_semantics_sha256': hashlib.sha256(
            (Path(__file__).resolve().parents[2] / 'plugins/elasticity/conditions.py').read_bytes()).hexdigest(),
        'limitations': ['선택 ID는 이 CAD 개정에만 속합니다. 일반 면·physical group catalog는 아직 지원하지 않습니다.',
                        '전체 솔리드에 선언한 하중·구속은 native 표면 분포가 검증되었다는 뜻이 아닙니다.']
    }
    if backend == 'fixture.cadquery' and cad.get('model') == 'roller_support':
        source, source_sha = _metadata(parent_root, parent, 'cad/input.json')
        if source.get('model') != 'roller_support' or source.get('parameters') != cad.get('parameters'):
            raise ValueError('Support catalog input and CAD result disagree')
        catalog['model'] = 'roller_support'
        catalog['input_sha256'] = source_sha
        catalog['parameters'] = source['parameters']
        catalog['selections'].extend([
            {'id': 'S-base', 'label': '바닥 전체 고정 영역', 'kind': 'adapter_region',
             'roles': ['boundary'], 'owner': 'fixture.support.fixed_base',
             'definition': '기존 adapter의 전역 최저 Z 바닥 절점; UX/UY/UZ 고정'},
            {'id': 'S-saddle', 'label': '중앙 24 mm 새들 하중 영역', 'kind': 'adapter_region',
             'roles': ['load'], 'owner': 'fixture.support.central_saddle',
             'definition': '기존 adapter가 검증하는 반경 4.15 mm의 원통 새들 중앙 24 mm 영역'}
        ])
        from .fixture_calculix import SCREEN
        saddle_source = Path(__file__).with_name('fixture_saddle_load.py')
        catalog['region_source_sha256'] = {
            'fixture_screen': hashlib.sha256(SCREEN.read_bytes()).hexdigest(),
            'saddle_region': hashlib.sha256(saddle_source.read_bytes()).hexdigest()
        }
        catalog['limitations'].append('명명된 adapter 영역이며 native face ID가 아닙니다. 실제 STEP·절점 영역은 해석 preflight에서 재검증합니다.')
    return catalog
