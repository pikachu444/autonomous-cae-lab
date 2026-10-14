"""Read preserved and current meshes with the existing FEM quality definition.

No element correspondence is inferred across remeshing. Histogram differences
are available only when the two existing quality reports have identical edges.
"""
from copy import deepcopy
import re

from .fem_edit import _native_type


_STATISTICS = ('absolute_jacobian_mm3', 'normalized_jacobian')
_COUNTS = ('total_elements', 'bad_element_count')


def _summary(quality):
    return {key: deepcopy(quality[key]) for key in
            ('mesh_id', 'mesh_sha256', *_COUNTS, *_STATISTICS, 'gates', 'limitation')}


def _distribution_change(previous, current):
    same_edges = ([(b['lower'], b['upper']) for b in previous['bins']] ==
                  [(b['lower'], b['upper']) for b in current['bins']])
    result = {key: None if previous[key] is None or current[key] is None
              else current[key] - previous[key] for key in ('count', 'minimum', 'maximum')}
    result['bin_boundaries_equal'] = same_edges
    result['bins'] = ([{'lower': new['lower'], 'upper': new['upper'],
                       'count': new['count'] - old['count']}
                      for old, new in zip(previous['bins'], current['bins'])]
                     if same_edges else None)
    return result


def _source_relationship(owner, mesh):
    try:
        binding = owner.mesh_bindings.validate(mesh)
        if binding.get('binding_validation') != 'CURRENT_SOURCE_AND_MESH_MATCH':
            raise ValueError('Native source relationship was not confirmed')
        return {'state': 'MATCH',
                'message': '메시와 현재 형상의 연결이 일치합니다. 해석 적합성 판정은 별도입니다.'}
    except Exception as error:
        return {'state': 'UNCONFIRMED',
                'message': '현재 형상과 연결을 확인하지 못한 메시입니다. 값 비교는 가능하지만 현재 형상 해석에는 다시 메시를 생성하세요.',
                'diagnostic': str(error)}


def compare_mesh_quality(editor, mesh, history_id, expected_mesh_sha256):
    """Return previous/current statistics and current-minus-previous changes.

    ``history_id`` selects its exact preserved predecessor, including an older
    generation. ``expected_mesh_sha256`` belongs to the currently selected mesh,
    independently of that history's generated successor. No model writes occur.
    """
    owner = editor.owner
    owner.assert_thread()
    if getattr(owner, 'closed', False):
        raise ValueError('문서가 닫혔습니다. 열린 문서에서 메시를 다시 선택하세요.')
    if editor._mesh({'object_id': mesh.Name}) is not mesh:
        raise ValueError('선택한 메시가 바뀌었습니다. 메시를 다시 선택하세요.')
    if not isinstance(history_id, str) or not history_id:
        raise ValueError('비교할 이전 메시 기록을 선택하세요.')
    if not isinstance(expected_mesh_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_mesh_sha256):
        raise ValueError('현재 메시를 확인할 수 없습니다. 품질을 다시 읽으세요.')
    records = [record for record in editor._metadata()['mesh_history']
               if isinstance(record, dict) and record.get('id') == history_id]
    if len(records) != 1:
        raise ValueError('이전 메시 기록을 찾을 수 없거나 기록이 중복됐습니다.')
    record = records[0]
    if record.get('mesh_id') != mesh.Name or record.get('state') != 'SUCCEEDED':
        raise ValueError('선택한 메시의 완료된 재메시 기록을 선택하세요.')
    previous_id = record.get('previous_mesh_object_id')
    if not isinstance(previous_id, str) or not previous_id:
        raise ValueError('이 기록의 이전 메시가 보관되어 있지 않습니다.')
    previous = editor._object({'object_id': previous_id})
    if previous is mesh or _native_type(previous) != 'Fem::FemMeshObject':
        raise ValueError('보관된 이전 메시를 확인할 수 없습니다.')
    # quality computes full statistics even when only one element row is requested.
    current_quality = editor.quality(mesh, limit=1)
    if current_quality['mesh_sha256'] != expected_mesh_sha256:
        raise ValueError('현재 메시가 바뀌었습니다. 품질을 다시 읽은 뒤 비교하세요.')
    previous_quality = editor.quality(previous, limit=1)
    if (previous_quality['mesh_sha256'] is None or
            previous_quality['mesh_sha256'] != record.get('previous_mesh_sha256')):
        raise ValueError('보관된 이전 메시가 기록과 다릅니다. 다른 기록을 선택하세요.')
    before, after = _summary(previous_quality), _summary(current_quality)
    changes = {key: after[key] - before[key] for key in _COUNTS}
    changes.update({key: _distribution_change(before[key], after[key]) for key in _STATISTICS})
    return {'history_id': history_id, 'mesh_id': mesh.Name,
            'previous_mesh_object_id': previous_id, 'previous': before, 'current': after,
            'changes': changes, 'element_correspondence': 'NOT_ASSUMED_AFTER_REMESH',
            'current_source_relationship': _source_relationship(owner, mesh)}
