"""Exact logical selections across source edits, within the existing settings.

An effective number/name can be recycled when an assembly is recompiled. This
receipt binds a selected response/motion/contact to its original logical entity;
it is not a second identity system, store or geometry-matching heuristic.
"""
from copy import deepcopy
from .storage import canonical_hash
from .impact_source import SourceError

KEY = 'source_reference_bindings'


def _entity(model, association, identity):
    kind = 'nodes' if association == 'POINTS' else 'elements'
    if type(identity) is not int or identity not in model[kind]:
        raise SourceError('선택한 원 절점/요소 번호가 없습니다')
    row = model.get('lineage', {}).get(kind, {}).get(str(identity), {})
    if row.get('instance') is not None:
        return {'association': association, 'part': row['part'],
                'instance': row['instance'], 'local_id': row['local_id']}
    return {'association': association, 'native_id': identity}


def _target(model, kind, key):
    if key not in model[kind]:
        raise SourceError('선택한 원 집합/면이 없습니다: ' + str(key))
    row = model.get('lineage', {}).get(kind, {}).get(key, {})
    label = row.get('qualified_name', row.get('qualified', row.get('label', key)))
    if kind == 'surfaces':
        members = []
        for target, side in model[kind][key]:
            ids = [int(target)] if str(target).isdigit() else model['elsets'][target]
            members.extend({'element': _entity(model, 'CELLS', n), 'side': side} for n in ids)
    else:
        association = 'POINTS' if kind == 'nsets' else 'CELLS'
        members = [_entity(model, association, n) for n in model[kind][key]]
    return {'kind': kind, 'label': label, 'members': sorted(members, key=canonical_hash)}


def snapshot(settings, model=None):
    if model is None:
        from .impact_model import model_from_settings
        model = model_from_settings(settings)
    from .impact_responses import QUANTITIES
    rows = []
    for index, motion in enumerate(settings.get('motions', [])):
        rows.append({'selection': ['motions', index, 'node_set'], 'value': motion['node_set'],
                     'source': _target(model, 'nsets', motion['node_set'])})
    histories=settings.get('interface_histories', [])
    if not isinstance(histories,list):
        raise SourceError('명시 계면 하중 이력은 목록이어야 합니다')
    for index, history in enumerate(histories):
        rows.append({'selection': ['interface_histories', index, 'node_set'], 'value': history['node_set'],
            'source': {**_target(model, 'nsets', history['node_set']),
                'history_name': history['name'], 'component': history['component']}})
    for index, pair in enumerate(settings.get('contacts', [])):
        for side in ('a', 'b'):
            rows.append({'selection': ['contacts', index, side], 'value': pair[side],
                         'source': _target(model, 'surfaces', pair[side])})
    for index, response in enumerate(settings.get('responses', [])):
        quantity = response['quantity']
        if quantity not in QUANTITIES:
            raise SourceError('응답 물리량을 확인하세요')
        association = QUANTITIES[quantity][1]
        rows.append({'selection': ['responses', index, 'identity'], 'value': response['identity'],
                     'source': _entity(model, association, response['identity'])})
    def pair_target(index):
        pairs=settings.get('contacts', [])
        if type(index) is not int or not 0<=index<len(pairs):
            raise SourceError('선택한 원 접촉쌍이 없습니다')
        return {side:_target(model,'surfaces',pairs[index][side]) for side in ('a','b')}
    for index,response in enumerate(settings.get('b_responses', [])):
        scope=response['scope'];identity=response['identity']
        if scope not in ('bulk','interface','pair'):
            raise SourceError('벌크·계면·접촉쌍의 원 대상을 확인하세요')
        source=pair_target(identity) if scope=='pair' else _entity(model,'CELLS',identity)
        rows.append({'selection':['b_responses',index,'identity'],'value':identity,'source':source})
    for kind in ('cohesive','bulk_damage','interface_controls','interface_histories'):
        for index,item in enumerate(settings.get(kind, [])):
            material=item['material']
            members=[_entity(model,'CELLS',e) for e,name in model['assignment'].items() if name==material]
            if not members:raise SourceError('손상/계면 재료에 배정된 원 요소가 없습니다: '+material)
            rows.append({'selection':[kind,index,'material'],'value':material,
                         'source':{'kind':'material_assignment','material':material,
                                   'members':sorted(members,key=canonical_hash)}})
            if kind=='interface_controls' and item.get('contact_index') is not None:
                rows.append({'selection':[kind,index,'contact_index'],'value':item['contact_index'],
                             'source':pair_target(item['contact_index'])})
    return {'schema': 'impact-logical-selection-v1', 'rows': rows}


def preserve_before_edit(settings):
    """Keep the original bindings across invalid intermediate source drafts."""
    if KEY in settings:
        return deepcopy(settings[KEY])
    return snapshot(settings)


def validate(settings, model):
    if KEY not in settings:
        return  # existing unedited definitions remain compatible
    receipt = settings[KEY]
    if (not isinstance(receipt, dict) or set(receipt) != {'schema', 'rows'}
            or receipt.get('schema') != 'impact-logical-selection-v1'):
        raise SourceError('원 대상 선택의 보존 기록을 확인하세요')
    current = snapshot(settings, model)
    if canonical_hash(receipt) != canonical_hash(current):
        raise SourceError('원문 편집 뒤 운동·접촉·결과·손상/계면 배정의 원 대상 대응이 바뀌었습니다. '
                          '변경 전/후 표를 확인하고 정확한 원 대상을 다시 선택하세요')


def review(settings):
    """Readable before/after rows; preparing a review does not authorize a run."""
    old = deepcopy(settings.get(KEY, {'schema': 'impact-logical-selection-v1', 'rows': []}))
    current = snapshot(settings)
    return {'before': old['rows'], 'after': current['rows'],
            'changed': canonical_hash(old) != canonical_hash(current),
            'review_sha256': canonical_hash({'before': old, 'after': current}),
            'definition_sha256': canonical_hash(settings)}


def accept_review(settings, *, expected_definition_sha256, expected_review_sha256, acknowledged):
    """Explicit user acceptance only, after selecting the intended CURRENT rows."""
    if acknowledged is not True or canonical_hash(settings) != expected_definition_sha256:
        raise SourceError('현재 대상 대응 표를 읽고 명시적으로 적용하세요')
    report = review(settings)
    if report['review_sha256'] != expected_review_sha256:
        raise SourceError('대상 대응 표가 바뀌었습니다. 다시 읽고 적용하세요')
    result = deepcopy(settings)
    result[KEY] = snapshot(settings)
    return result
