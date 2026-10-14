"""Declared joint-drive relations compiled to native Formula, never Python eval.

Limits are a conservative whole-time-interval check, not a replacement solver.
The relation coordinate is the source drive's DECLARED unit, before native rad conversion.
"""
import ast
from fractions import Fraction
import math
import re

REQUIRED = {'joint_id', 'type', 'formula', 'unit'}
OPTIONAL = {'name', 'dependency', 'limits'}
UNITS = {'Angular': {'rad': 1., 'deg': math.pi/180.}, 'Linear': {'mm': 1.}}


def native_limits(joint):
    result = {}
    for kind, prefix, unit in (('Angular', 'Angle', 'deg'), ('Linear', 'Length', 'mm')):
        lower = getattr(joint, prefix+'Min', None) if getattr(joint, 'Enable'+prefix+'Min', False) else None
        upper = getattr(joint, prefix+'Max', None) if getattr(joint, 'Enable'+prefix+'Max', False) else None
        if lower is not None or upper is not None:
            result[kind] = {'min': float(lower), 'max': float(upper), 'unit': unit} if lower is not None and upper is not None else {
                'min': None if lower is None else float(lower), 'max': None if upper is None else float(upper), 'unit': unit}
    return result


def _finite(value):
    if type(value) not in (int, float) or not math.isfinite(value): raise ValueError('유한한 숫자를 입력하세요.')
    return float(value)


def _formula(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
        or not re.fullmatch(r'[A-Za-z0-9_+*/^()., \-]+', value)
        or set(re.findall(r'[A-Za-z_]+', value)) - {'time', 'pi', 'sin', 'cos', 'tan', 'arctan', 'exp', 'log', 'sqrt', 'e'}):
        raise ValueError('Use an explicit bounded native formula; no Python or native path expressions')
    try:
        parsed = ast.parse(value.replace('^','**'), mode='eval')
        for node in ast.walk(parsed):
            if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or len(node.args)!=1 or node.keywords
                    or node.func.id not in {'sin','cos','tan','arctan','exp','log','sqrt'}): raise ValueError('운동식 함수와 인자를 확인하세요.')
            if isinstance(node,ast.Name) and node.id not in {'time','pi','e','sin','cos','tan','arctan','exp','log','sqrt'}: raise ValueError('운동식 변수를 확인하세요.')
            if isinstance(node,ast.Constant) and (type(node.value) not in (int,float) or not math.isfinite(node.value)): raise ValueError('운동식 숫자는 유한해야 합니다.')
            if not isinstance(node,(ast.Expression,ast.BinOp,ast.UnaryOp,ast.Call,ast.Name,ast.Load,ast.Constant,
                    ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow,ast.UAdd,ast.USub)):
                raise ValueError('지원하는 native 운동식 연산을 사용하세요.')
    except SyntaxError as error: raise ValueError('미완성 운동식입니다. 괄호와 연산자·값을 확인하세요.') from error
    return value


def interval(formula, time):
    # Keep legacy native powers/tan without limits, but do not assert a bounded
    # interval until parser precedence/poles can be established for this input.
    if '^' in formula: raise ValueError('거듭제곱 식의 전구간 범위는 확인할 수 없습니다. 곱셈으로 명시하거나 한계를 편집하세요.')
    tree = ast.parse(formula, mode='eval')
    def outward(value, upper):
        rounded = float(value)
        if not math.isfinite(rounded): raise ValueError('식 범위가 유한하지 않습니다.')
        if (Fraction(rounded) < value if upper else Fraction(rounded) > value):
            rounded = math.nextafter(rounded, math.inf if upper else -math.inf)
        return rounded
    def exact_bounds(values):
        return outward(min(values), False), outward(max(values), True)
    def monotone(function, a, b, exact=None):
        low, high = function(a), function(b)
        return (low if exact and a in exact else math.nextafter(low, -math.inf),
            high if exact and b in exact else math.nextafter(high, math.inf))
    def walk(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            x = _finite(node.value); return x, x
        if isinstance(node, ast.Name):
            if node.id == 'time': return time
            if node.id in ('pi', 'e'): x = getattr(math, node.id); return x, x
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            a,b = walk(node.operand); return (-b,-a) if isinstance(node.op,ast.USub) else (a,b)
        if isinstance(node, ast.BinOp):
            a,b = walk(node.left); c,d = walk(node.right)
            a,b,c,d=map(Fraction,(a,b,c,d))
            if isinstance(node.op,ast.Add): return exact_bounds((a+c,b+d))
            if isinstance(node.op,ast.Sub): return exact_bounds((a-d,b-c))
            if isinstance(node.op,ast.Mult): return exact_bounds((a*c,a*d,b*c,b*d))
            if isinstance(node.op,ast.Div):
                if c <= 0 <= d: raise ValueError('분모가 0을 포함할 수 있습니다.')
                return exact_bounds((a/c,a/d,b/c,b/d))
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and len(node.args)==1 and not node.keywords:
            a,b=walk(node.args[0]); name=node.func.id
            if name in ('sin','cos'): return -1.,1.
            if name=='arctan': return monotone(math.atan,a,b,{0})
            if name=='exp': return monotone(math.exp,a,b,{0})
            if name=='sqrt' and a>=0: return monotone(math.sqrt,a,b,{0,1})
            if name=='log' and a>0: return monotone(math.log,a,b,{1})
        raise ValueError('이 식의 전구간 범위를 확인할 수 없습니다.')
    bounds=walk(tree.body)
    if not all(math.isfinite(v) for v in bounds): raise ValueError('식 범위가 유한하지 않습니다.')
    return bounds


def compile_drives(drives, time, joints):
    """Return native formulas and row issues, leaving stored/raw rows untouched."""
    issues, keys, nodes, declared, compiled, visiting = {}, {}, {}, {}, {}, set()
    def problem(index, message): issues.setdefault(index, []).append(message)
    for index, drive in enumerate(drives):
        try:
            if not isinstance(drive,dict) or not REQUIRED <= set(drive) or set(drive)-REQUIRED-OPTIONAL: raise ValueError('구동 행의 선언을 확인하세요.')
            joint=joints.get(drive['joint_id'])
            if not joint: raise ValueError('관절 참조 없음 — 다시 선택하세요.')
            if drive['type'] not in {'Revolute':{'Angular'},'Slider':{'Linear'},'Cylindrical':{'Angular','Linear'}}.get(joint['type'],set()):
                raise ValueError('이 관절의 운동 종류를 확인하세요.')
            if joint.get('issues'): raise ValueError('; '.join(joint['issues']))
            if drive['unit'] not in UNITS[drive['type']]: raise ValueError('운동 종류에 맞는 rad/deg 또는 mm 단위를 선택하세요.')
            if 'name' in drive and (not isinstance(drive['name'],str) or not drive['name'].strip() or len(drive['name'])>80): raise ValueError('구동 이름을 입력하세요.')
            key=(drive['joint_id'],drive['type'])
            if key in keys:
                problem(keys[key],'같은 관절에 같은 종류의 구동을 중복 지정했습니다.'); raise ValueError('같은 관절에 같은 종류의 구동을 중복 지정했습니다.')
            keys[key]=index; nodes[key]=drive
            if not drive.get('dependency'): _formula(drive['formula'])
        except (ValueError,KeyError,TypeError) as error: problem(index,str(error))
    def resolve(key):
        index=keys[key]; drive=nodes[key]
        if index in issues: raise ValueError('기준 구동의 오류를 먼저 고치세요.')
        if key in declared: return declared[key]
        if key in visiting: raise ValueError('종속 구동이 순환합니다. 기준 구동을 바꾸세요.')
        visiting.add(key)
        try:
            dependency=drive.get('dependency')
            if dependency is None: expression=drive['formula']
            else:
                if not isinstance(dependency,dict) or set(dependency)!={'joint_id','type','ratio','ratio_unit','offset','offset_unit'}: raise ValueError('종속 구동 선언을 확인하세요.')
                source=(dependency['joint_id'],dependency['type'])
                if source not in nodes: raise ValueError('기준 관절의 이 운동 종류에 적용할 구동이 없습니다. 기준 구동을 추가하거나 다시 선택하세요.')
                master=nodes[source]
                if dependency['ratio_unit'] != drive['unit']+'/'+master['unit'] or dependency['offset_unit'] != drive['unit']:
                    raise ValueError('기준/종속 구동 단위가 바뀌었습니다. 비율과 이동의 단위를 다시 지정하세요.')
                ratio,offset=_finite(dependency['ratio']),_finite(dependency['offset'])
                expression='('+repr(ratio)+'*('+resolve(source)+')+'+repr(offset)+')'
            if len(expression)>8192: raise ValueError('종속 식이 너무 깁니다.')
            declared[key]=expression
            compiled[index]=expression if drive['unit']!='deg' else '(('+expression+')*pi/180)'
            return expression
        finally: visiting.discard(key)
    for key,index in keys.items():
        try: resolve(key)
        except (ValueError,KeyError,TypeError) as error: problem(index,str(error))
    for key,index in keys.items():
        drive=nodes[key]
        limits=[]
        if drive.get('limits') is not None: limits.append(('구동 허용 한계',drive['limits']))
        native=joints[key[0]].get('limits',{}).get(key[1])
        if native: limits.append(('관절의 각도 한계' if key[1]=='Angular' else '관절의 길이 한계',native))
        for label,limit in limits:
            try:
                if not isinstance(limit,dict) or set(limit)!={'min','max','unit'} or limit['unit'] not in UNITS[key[1]]: raise ValueError('허용 한계와 단위를 확인하세요.')
                low=None if limit['min'] is None else _finite(limit['min']); high=None if limit['max'] is None else _finite(limit['max'])
                if low is not None and high is not None and low>high: raise ValueError('하한은 상한보다 클 수 없습니다.')
                if low is None and high is None: continue
                if key not in declared: continue
                a,b=interval(declared[key],time)
                # Positive exact quotient of the declared native conversion
                # constants, then outward rounded endpoints; no limit epsilon.
                factor=Fraction(UNITS[key[1]][drive['unit']])/Fraction(UNITS[key[1]][limit['unit']])
                exact_a,exact_b=Fraction(a)*factor,Fraction(b)*factor
                a,b=float(exact_a),float(exact_b)
                if Fraction(a)>exact_a: a=math.nextafter(a,-math.inf)
                if Fraction(b)<exact_b: b=math.nextafter(b,math.inf)
                if low is not None and a<low or high is not None and b>high:
                    raise ValueError('식의 보수적 전구간 범위 ['+format(a,'.6g')+', '+format(b,'.6g')+'] '+limit['unit']+'가 한계 안임을 확인할 수 없습니다. 식/한계를 수정하세요. 자동 제한하지 않습니다.')
            except (ValueError,TypeError,KeyError,SyntaxError,OverflowError) as error: problem(index,'허용 한계 ('+label+'): '+str(error))
    for joint_id,joint in joints.items():
        if joint.get('suppressed'): continue
        for kind in joint.get('limits',{}):
            if (joint_id,kind) not in keys:
                problem(-1,joint.get('label',joint_id)+': 한계가 있는 미구동 좌표의 전구간 운동을 확인할 수 없습니다. 해당 구동을 명시하거나 관절 한계를 편집하세요.')
    return compiled, issues
