"""Small typed algebra for explicit native joint-drive relations (M1).

This is not a unit framework or a solver. Coordinate dimensions are angle,
length and time; scalars are lowered to FreeCAD's rad/mm/s before substitution.
The persisted binding includes the native occurrence path AND the source's
acknowledged declared unit. No label-based lookup and no evaluation of code.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass
import math
import re
from typing import Callable

from apps.desktop_pre.motion_formula import UNITS

DIMENSIONLESS = (0, 0, 0)
ANGLE, LENGTH, TIME = (1, 0, 0), (0, 1, 0), (0, 0, 1)
COORDINATE_DIMENSIONS = {'Angular': ANGLE, 'Linear': LENGTH}
# Keep this native subset aligned with pinned SymbolicParser and observation
# checking. Legacy time formulas retain their own, historically wider contract.
FUNCTIONS = frozenset(('sin', 'cos', 'arctan'))
RESERVED = FUNCTIONS | {'time', 'pi', 'e', 'tan', 'exp', 'log', 'sqrt'}
SOURCE_FIELDS = {'alias', 'joint_id', 'type', 'path', 'unit'}
CONSTANT_FIELDS = {'name', 'value', 'unit'}
RELATION_FIELDS = {'expression', 'sources', 'constants'}
MAX_EXPRESSION = 256
MAX_NATIVE = 8192
MAX_SYMBOLS = 32


@dataclass(frozen=True)
class Unit:
    dimension: tuple[int, int, int]
    factor: float
    scale: str  # expression in native rad/mm/s; no approximate deg/rad rewrite


BASE_UNITS = {'1': Unit(DIMENSIONLESS, 1., '1'),
              'rad': Unit(ANGLE, 1., '1'),
              'deg': Unit(ANGLE, UNITS['Angular']['deg'], '(pi/180)'),
              'mm': Unit(LENGTH, 1., '1'),
              's': Unit(TIME, 1., '1')}
UNIT_CHOICES = tuple(BASE_UNITS) + tuple(a+'/'+b for a in BASE_UNITS
    for b in BASE_UNITS if b != '1')


def unit(value: str) -> Unit:
    """Only 1/rad/deg/mm/s and one quotient of those units, not arbitrary units."""
    if not isinstance(value, str):
        raise ValueError('상수의 단위를 선택하세요.')
    if value in BASE_UNITS:
        return BASE_UNITS[value]
    parts = value.split('/')
    if len(parts) != 2 or parts[0] not in BASE_UNITS or parts[1] not in BASE_UNITS or parts[1] == '1':
        raise ValueError('지원 단위는 1, rad, deg, mm, s와 이들의 비율입니다: '+value)
    a, b = (BASE_UNITS[p] for p in parts)
    return Unit(tuple(x-y for x, y in zip(a.dimension, b.dimension)), a.factor/b.factor,
                '1' if a.scale == b.scale else '('+a.scale+'/'+b.scale+')')


def finite(value) -> float:
    try:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('상수 값은 유한한 숫자여야 합니다.')
        return float(value)
    except OverflowError as error:
        raise ValueError('상수 값은 유한한 숫자여야 합니다.') from error


def symbol(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', value) or value in RESERVED:
        raise ValueError('식 이름은 영문자로 시작하는 32자 이내 이름이어야 하며 time·함수명은 사용할 수 없습니다.')
    return value


def _identifier(value):
    return value is None or isinstance(value, str)


def _path(value, *, raw=False):
    return (raw and value is None) or (isinstance(value, list) and
        (raw or 2 <= len(value) <= 65) and all(isinstance(p, str) and (raw or 0 < len(p) <= 256) for p in value))


def validate_raw_relation(value) -> None:
    """Validate serializable SHAPE, not validity; retain '1e', missing paths, etc."""
    if (not isinstance(value, dict) or set(value) != RELATION_FIELDS
            or not isinstance(value['expression'], str)
            or not isinstance(value['sources'], list) or not isinstance(value['constants'], list)):
        raise ValueError('Invalid raw drive relation structure')
    for source in value['sources']:
        if (not isinstance(source, dict) or set(source) != SOURCE_FIELDS
                or not isinstance(source['alias'], str)
                or not _identifier(source['joint_id']) or not _identifier(source['type'])
                or not _path(source['path'], raw=True) or not isinstance(source['unit'], str)):
            raise ValueError('Invalid raw relation source structure')
    for constant in value['constants']:
        if (not isinstance(constant, dict) or set(constant) != CONSTANT_FIELDS
                or any(not isinstance(v, str) for v in constant.values())):
            raise ValueError('Invalid raw relation constant structure')


def relation_values(value, *, raw: bool):
    """Deep-copy table values for draft/apply without normalizing raw user text."""
    result = deepcopy(value)
    if not isinstance(result, dict):
        return result
    for constant in result.get('constants', []):
        if not isinstance(constant, dict) or 'value' not in constant:
            continue
        number = constant['value']
        if raw:
            constant['value'] = str(number) if number is not None else ''
        elif isinstance(number, str):
            try:
                constant['value'] = float(number)
            except ValueError:
                pass  # keep the invalid text; compile reports it on this row
    return result


def binding_problem(source, drives, joints) -> str:
    """Read-only source row diagnostic, shared by compiler and Qt source table."""
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
        return '기준 구동 선언을 확인하세요.'
    try:
        symbol(source['alias'])
        if not isinstance(source['joint_id'], str) or not isinstance(source['type'], str):
            return '기준 구동을 다시 선택하세요.'
        joint = joints.get(source['joint_id'])
        if not joint:
            return '기준 관절 참조 없음 — 다시 선택하세요.'
        if joint.get('suppressed'):
            return '억제된 기준 관절입니다. 활성화하거나 다시 선택하세요.'
        if joint.get('issues'):
            return '; '.join(joint['issues'])
        current = joint.get('path')
        if not _path(current):
            return '기준 관절의 배치 경로가 없거나 모호합니다. 다시 읽고 선택하세요.'
        if not _path(source['path']) or source['path'] != current:
            return '기준 관절의 배치 경로가 바뀌었습니다. 원문을 보존했으니 다시 선택하세요.'
        rows = [d for d in drives if isinstance(d, dict) and
                (d.get('joint_id'), d.get('type')) == (source['joint_id'], source['type'])]
        if len(rows) != 1:
            return '기준 좌표의 구동이 없습니다.' if not rows else '기준 좌표의 구동이 중복되어 모호합니다.'
        master = rows[0]
        allowed = {'Angular': ('rad', 'deg'), 'Linear': ('mm',)}.get(source['type'], ())
        if master.get('unit') not in allowed or source['unit'] not in allowed:
            return '기준 좌표와 선언 단위를 확인하세요.'
        if source['unit'] != master['unit']:
            return ('기준 구동 단위가 '+source['unit']+'에서 '+master['unit']+
                    '로 바뀌었습니다. 계수 값과 단위는 유지됩니다. 기준 단위를 명시적으로 재확인하세요.')
    except (ValueError, TypeError, KeyError) as error:
        return str(error)
    return ''


def sources(value) -> list[dict]:
    if not isinstance(value, dict) or set(value) != RELATION_FIELDS:
        raise ValueError('관계식의 expression, sources, constants를 선언하세요.')
    if not isinstance(value['sources'], list) or not 1 <= len(value['sources']) <= MAX_SYMBOLS:
        raise ValueError('관계식의 기준 구동을 1개에서 32개까지 선택하세요.')
    if not isinstance(value['constants'], list) or len(value['constants']) > MAX_SYMBOLS:
        raise ValueError('관계식 상수는 32개까지 선언할 수 있습니다.')
    return value['sources']


@dataclass(frozen=True)
class Scalar:
    expression: str
    dimension: tuple[int, int, int]

    def __post_init__(self):
        if len(self.expression) > MAX_NATIVE:
            raise ValueError('전개한 관계식이 8192자를 넘습니다. 관계를 줄이세요.')


def _parse(expression, limit=MAX_EXPRESSION):
    if (not isinstance(expression, str) or not 1 <= len(expression) <= limit
            or not re.fullmatch(r'[A-Za-z0-9_+*/^()., \-]+', expression)):
        raise ValueError('관계식은 256자 이내의 이름·숫자·허용 연산으로 입력하세요. 속성·경로·첨자식은 사용할 수 없습니다.')
    try:
        tree = ast.parse(expression.strip().replace('^', '**'), mode='eval')
    except (SyntaxError, RecursionError) as error:
        raise ValueError('미완성 관계식입니다. 괄호와 연산자·값을 확인하세요.') from error
    if sum(1 for _ in ast.walk(tree)) > 4096:
        raise ValueError('관계식의 검사 범위를 초과했습니다.')
    return tree.body


def native_subset(expression: str) -> str:
    """Normalize native scalar operands, rejecting unverified source functions.

    Native does not accept a bare leading decimal point. Render each numeric
    AST literal with repr(float), and fully parenthesize operators. Powers and
    tan remain legacy-only; never guess their whole-interval/parser semantics.
    """
    def walk(node):
        if isinstance(node, ast.Constant):
            return repr(finite(node.value))
        if isinstance(node, ast.Name) and node.id in ('time', 'pi'):
            return node.id
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return '('+('+' if isinstance(node.op, ast.UAdd) else '-')+walk(node.operand)+')'
        if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
            op = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}[type(node.op)]
            return '('+walk(node.left)+op+walk(node.right)+')'
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
                node.func.id in FUNCTIONS and len(node.args) == 1 and not node.keywords):
            return node.func.id+'('+walk(node.args[0])+')'
        raise ValueError('기준 시간식의 함수·거듭제곱 의미를 이 관계식에서 확인할 수 없습니다. sin, cos, arctan과 사칙연산을 사용하세요.')
    try:
        result = walk(_parse(expression, MAX_NATIVE))
    except RecursionError as error:
        raise ValueError('전개한 관계식의 중첩이 너무 깊습니다.') from error
    if len(result) > MAX_NATIVE:
        raise ValueError('전개한 관계식이 8192자를 넘습니다.')
    return result


def compile_relation(value: dict, output_kind: str,
                     resolve_source: Callable[[dict], str]) -> str:
    """Return rad or mm native expression. Caller owns identity/graph/interval."""
    selected = sources(value)
    symbols = {'time': Scalar('time', TIME), 'pi': Scalar('pi', DIMENSIONLESS)}
    used_sources = set()
    for index, source in enumerate(selected):
        try:
            alias = symbol(source['alias'])
            if alias in symbols:
                raise ValueError('관계식 이름이 중복되었습니다: '+alias)
            symbols[alias] = Scalar(native_subset(resolve_source(source)),
                                    COORDINATE_DIMENSIONS[source['type']])
            used_sources.add(alias)
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError('기준 '+str(index+1)+'행: '+str(error)) from error
    for index, constant in enumerate(value['constants']):
        try:
            if not isinstance(constant, dict) or set(constant) != CONSTANT_FIELDS:
                raise ValueError('상수 이름·값·단위를 선언하세요.')
            name = symbol(constant['name'])
            if name in symbols:
                raise ValueError('관계식 이름이 중복되었습니다: '+name)
            quantity = unit(constant['unit'])
            number = repr(finite(constant['value']))
            expression = number if quantity.scale == '1' else '('+number+'*'+quantity.scale+')'
            symbols[name] = Scalar(expression, quantity.dimension)
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError('상수 '+str(index+1)+'행: '+str(error)) from error
    referenced = set()
    def walk(node):
        if isinstance(node, ast.Constant):
            return Scalar(repr(finite(node.value)), DIMENSIONLESS)
        if isinstance(node, ast.Name):
            if node.id not in symbols:
                raise ValueError('선언하지 않은 식 이름입니다: '+node.id)
            referenced.add(node.id)
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            a = walk(node.operand)
            return Scalar('('+('+' if isinstance(node.op, ast.UAdd) else '-')+a.expression+')', a.dimension)
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow):
                raise ValueError('거듭제곱의 전구간 범위는 확인할 수 없습니다. 관계식에서는 곱셈을 명시하세요.')
            if type(node.op) not in (ast.Add, ast.Sub, ast.Mult, ast.Div):
                raise ValueError('지원하는 관계식 연산을 사용하세요.')
            a, b = walk(node.left), walk(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                if a.dimension != b.dimension:
                    raise ValueError('합·차의 물리 차원이 다릅니다. 단위가 있는 계수 또는 영점 상수를 선언하세요.')
                dimension = a.dimension
            else:
                sign = -1 if isinstance(node.op, ast.Div) else 1
                dimension = tuple(x+sign*y for x, y in zip(a.dimension, b.dimension))
            op = {ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/'}[type(node.op)]
            return Scalar('('+a.expression+op+b.expression+')', dimension)
        if isinstance(node, ast.Call):
            if (not isinstance(node.func, ast.Name) or len(node.args) != 1 or node.keywords
                    or node.func.id not in FUNCTIONS):
                raise ValueError('이 관계식의 native 함수/정의역 지원은 미확인입니다. sin, cos, arctan만 사용하세요.')
            a = walk(node.args[0])
            expected = DIMENSIONLESS if node.func.id == 'arctan' else ANGLE
            if a.dimension != expected:
                raise ValueError(node.func.id+' 인자의 물리 차원이 잘못되었습니다. '+
                    ('무차원 비율을 입력하세요.' if expected == DIMENSIONLESS else '각도를 입력하세요. rad 변환은 자동입니다.'))
            return Scalar(node.func.id+'('+a.expression+')', ANGLE if expected == DIMENSIONLESS else DIMENSIONLESS)
        raise ValueError('관계식에서 속성·첨자·임의 호출·Python 구문은 사용할 수 없습니다.')
    try:
        result = walk(_parse(value['expression']))
    except RecursionError as error:
        raise ValueError('관계식의 중첩이 너무 깊습니다.') from error
    if unused := used_sources - referenced:
        raise ValueError('선언했지만 식에 쓰이지 않은 기준 이름입니다: '+', '.join(sorted(unused)))
    if result.dimension != COORDINATE_DIMENSIONS[output_kind]:
        raise ValueError('관계식 결과의 물리 차원이 출력 좌표와 다릅니다. 회전은 각도, 이동은 길이여야 합니다.')
    return result.expression
