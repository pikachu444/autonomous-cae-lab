"""Additive condition catalog; the qualified original CAD adapter stays pinned.

Face aliases join exact retained native face IDs. Display triangle indices never
become mechanical selections. Operator mesh admission is separate from CAD.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import re

from .fixture_assembly import FixtureAssemblyAdapter, validate_catalog
from .cad_condition_catalog import GLOBAL, _metadata


class AssemblyConditionsCADAdapter(FixtureAssemblyAdapter):
    def __init__(self, retained_mesh=None):
        super().__init__()
        self.retained_mesh = deepcopy(retained_mesh)

    def conditions_catalog(self, parent_root, parent, proposal):
        original, catalog_sha = _metadata(parent_root, parent, 'cad/assembly_catalog.json')
        surface, surface_sha = _metadata(parent_root, parent, 'cad/surface.json')
        result, result_sha = _metadata(parent_root, parent, 'cad/result.json')
        if (original.get('units') != {'length': 'mm', 'area': 'mm^2', 'volume': 'mm^3'} or original.get('frame') != 'global_assembly_cartesian_mm'
                or original.get('source_sha256') != result.get('source_sha256')
                or original.get('input_sha256') != result.get('input_sha256')
                or result.get('catalog_sha256') != catalog_sha
                or result.get('surface_sha256') != surface_sha
                or result.get('cad_generated') is not True):
            raise ValueError('Assembly catalog/result/native source join differs')
        validate_catalog(original, surface)
        retained = deepcopy(self.retained_mesh)
        retained_matches = retained is not None and retained.get('cad_revision') == parent['cad_revision']
        active = set(retained.get('active_components', [])) if retained_matches else set()
        selections = []
        for body in original['components']:
            component = body['id']
            selections.append({'id': 'B-' + component, 'label': component,
                'kind': 'native_assembly_body', 'roles': ['material'], 'component_id': component,
                'coordinate_system': 'global', 'native_coordinate_system': original['frame'],
                'volume_mm3': body['volume_mm3'], 'bounds_mm': deepcopy(body['bounds']),
                'center_mm': deepcopy(body['center_of_mass_mm']),
                'native_geometry_sha256': body['native_geometry_sha256']})
            for face in body['faces']:
                ordinal = face['local_ordinal']
                if (type(ordinal) is not int or ordinal < 1 or not re.fullmatch(
                        re.escape(component) + r':face:' + str(ordinal) + r':[0-9a-f]{64}', face['id'])):
                    raise ValueError('Native assembly face ordinal/full identity differs')
                row = {'id': f'S-{component}-{ordinal}',
                    'label': f'{component} · native face {ordinal}', 'kind': 'native_assembly_face',
                    'roles': ['boundary', 'load', 'contact'], 'component_id': component,
                    'catalog_face_id': face['id'], 'local_ordinal': ordinal, 'native_ordinal': ordinal,
                    'native_geometry_sha256': face['native_geometry_sha256'],
                    'coordinate_system': 'global', 'native_coordinate_system': original['frame'],
                    'area_mm2': face['area_mm2'], 'center_mm': deepcopy(face['center_of_mass_mm']),
                    'bounds_mm': deepcopy(face['bounds']), 'geom_type': face['geom_type'],
                    'orientation': face['orientation']}
                selections.append(row)
                if component in active:
                    interior = deepcopy(row)
                    interior.update(id=f'I-{component}-{ordinal}', kind='assembly_face_interior_nodes',
                        label=f'{component} · face {ordinal} 내부 절점 · 모서리 제외', roles=['boundary', 'load'],
                        node_scope='FACE_INTERIOR_EXCLUDING_OTHER_FACE_BOUNDARIES',
                        geometry_metadata_scope='ORIGINAL_SOURCE_FACE_NOT_SUBSET')
                    selections.append(interior)
        if len({row['id'] for row in selections}) != len(selections):
            raise ValueError('Ambiguous assembly condition aliases')
        frame = deepcopy(GLOBAL)
        frame['label'] = '원본 조립체 전역 직교 좌표계 · 센서/world 정렬 UNKNOWN'
        catalog = {'schema_version': '1.0', 'cad_backend': self.backend, 'model': 'bending_assembly',
            'cad_revision': parent['cad_revision'], 'native_revision': result['native_revision'],
            'selections': selections, 'coordinate_systems': [frame], 'metadata_sha256': catalog_sha,
            'source_artifacts': {'cad/assembly_catalog.json': catalog_sha, 'cad/surface.json': surface_sha,
                                 'cad/result.json': result_sha},
            'catalog_policy_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'input_semantics_sha256': hashlib.sha256(
                (Path(__file__).resolve().parents[2] / 'plugins/elasticity/conditions.py').read_bytes()).hexdigest(),
            'native_frame_mapping': {'source': original['frame'], 'target': 'global',
                'origin': deepcopy(frame['origin']), 'basis': deepcopy(frame['basis']),
                'sensor_world_alignment': 'UNKNOWN'},
            'interfaces': deepcopy(original['interfaces']),
            'limitations': ['면 ID는 이 보존 CAD 개정에만 속합니다. 화면 삼각형 번호를 사용하지 않습니다.',
                '재료·구속·접촉 입력은 사용자 선언입니다. 실제 물성·체결·강도·내구 자격 UNKNOWN.',
                '지원 메시·solver admission은 별도이며 CAD 15부품 전체가 해석된다는 뜻이 아닙니다.']}
        if retained_matches:
            catalog['retained_mesh'] = retained
        return catalog
