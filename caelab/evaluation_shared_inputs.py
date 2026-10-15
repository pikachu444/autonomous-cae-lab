"""Identity fan-out through the existing Evaluation binding boundary."""
from copy import deepcopy
import math
from .storage import check_id


def targets(row):
    return deepcopy(row['targets']) if 'targets' in row else [{'stage': row['stage'], 'input_id': row['input_id']}]


def validate_binding(row, stage_ids):
    if not isinstance(row, dict):
        raise ValueError('변수 행을 지정하세요.')
    if 'targets' not in row:
        if set(row) != {'id', 'stage', 'input_id', 'unit'}:
            raise ValueError('Variable binding requires research ID, stage, advertised input ID and unit')
    else:
        if (set(row) - {'bounds','label'} != {'id', 'targets', 'unit', 'value'}
                or not isinstance(row['targets'], list) or not 1 <= len(row['targets']) <= 32):
            raise ValueError('공유 변수는 이름·단위·초기값과 1..32개의 입력 대상을 지정하세요.')
        if type(row['value']) not in (int, float) or not math.isfinite(row['value']):
            raise ValueError('공유 변수 초기값은 유한한 수여야 합니다.')
        if 'bounds' in row:
            b = row['bounds']
            if (not isinstance(b, list) or len(b) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in b)
                    or not b[0] < b[1] or not b[0] <= row['value'] <= b[1]):
                raise ValueError('공유 변수 범위는 하한 < 상한이며 초기값을 포함해야 합니다.')
    if 'label' in row and (not isinstance(row['label'],str) or not row['label'].strip() or len(row['label'])>160):
        raise ValueError('공유 입력 이름은 1..160자의 읽을 수 있는 이름이어야 합니다.')
    check_id(row['id'])
    if not isinstance(row.get('unit'), str) or not row['unit'].strip():
        raise ValueError('변수의 실제 물리 단위를 지정하세요.')
    seen = set()
    for item in targets(row):
        if (not isinstance(item, dict) or set(item) != {'stage', 'input_id'}
                or item['stage'] not in stage_ids or not isinstance(item['input_id'], str)
                or not item['input_id'].strip()):
            raise ValueError('공유 대상은 실제 단계와 advertised 입력을 지정해야 합니다.')
        key = item['stage'], item['input_id']
        if key in seen:
            raise ValueError('같은 입력 대상을 중복 연결할 수 없습니다.')
        seen.add(key)


def compile_bindings(rows, models, describe_inputs, bind_values):
    seen, descriptors = set(), []
    for row in rows:
        originals = []
        for target in targets(row):
            names = {item['id']: item for item in describe_inputs(models[target['stage']])}
            original = names.get(target['input_id'])
            key = target['stage'], target['input_id']
            if original is None or original['unit'] != row['unit'] or key in seen:
                raise ValueError('Binding must select a distinct advertised input with its actual unit: ' + row['id'])
            seen.add(key); originals.append(original)
            if 'targets' in row:
                if original.get('type', original.get('kind', 'continuous')) != 'continuous':
                    raise ValueError('공유 fan-out은 현재 연속 물리 입력만 지원합니다. 단일 혼합 변수는 유지됩니다.')
                for value in [row['value']] + row.get('bounds', []):
                    bind_values(models[target['stage']], {target['input_id']: value})
        descriptor = {**deepcopy(originals[0]), 'id': row['id']}
        if 'targets' in row:
            # A logical fan-out has no single executable settings path. Keep
            # each target's original advertised descriptor separately.
            descriptor.pop('settings_path', None); descriptor.pop('declaration_paths', None)
            descriptor['target_descriptors'] = [{**target, 'descriptor': deepcopy(original)}
                for target, original in zip(targets(row), originals)]
            descriptor.update(targets=targets(row), value=row['value'], label=row.get('label',descriptor.get('label',row['id'])), binding='identity_fan_out',
                              chain_rule='d(target)/d(logical)=1; no scale/offset conversion')
            if 'bounds' in row:
                descriptor.update(lower=row['bounds'][0], upper=row['bounds'][1])
        else:
            descriptor.update(stage=row['stage'], input_id=row['input_id'])
        descriptors.append(descriptor)
    return descriptors


def assign(rows, models, values, describe_inputs, bind_values):
    if set(values) - {row['id'] for row in rows}:
        raise ValueError('Candidate contains an undeclared evaluation input')
    assignments = {stage: {} for stage in models}
    receipts = []
    for row in rows:
        explicit = row['id'] in values or 'targets' in row
        value = values.get(row['id'], row.get('value'))
        if 'targets' in row:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('공유 변수는 유한한 수여야 합니다: ' + row['id'])
            if 'bounds' in row and not row['bounds'][0] <= value <= row['bounds'][1]:
                raise ValueError('공유 변수의 저장된 범위를 벗어났습니다: ' + row['id'])
        bound = []
        for target in targets(row):
            original = next(item for item in describe_inputs(models[target['stage']]) if item['id'] == target['input_id'])
            applied = value if explicit else original['value']
            if explicit:
                assignments[target['stage']][target['input_id']] = deepcopy(applied)
            bound.append({**target, 'unit': original['unit'], 'original_value': original['value'],
                          'applied_value': deepcopy(applied), 'd_target_d_logical': 1})
        receipts.append({'id': row['id'], 'label':row.get('label',row['id']), 'unit': row['unit'], 'value': deepcopy(value if explicit else bound[0]['applied_value']),
                         'source': 'candidate' if row['id'] in values else 'shared_initial' if 'targets' in row else 'stage_default',
                         'targets': bound})
    return ({stage: bind_values(model, assignments[stage]) for stage, model in models.items()}, receipts)
