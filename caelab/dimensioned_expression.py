"""Bounded dimensioned scalar/vector expressions; no Python eval or native imports.

SI base exponents are (kg, m, s, K). Labels never scale numeric values.
The weak-form adapter additionally checks scalar rank and trial/test degree.
"""
import ast
from dataclasses import dataclass
from fractions import Fraction
import math

ZERO = (0, 0, 0, 0)
UNITS = {'kg': (1,0,0,0), 'm': (0,1,0,0), 's': (0,0,1,0),
         'K': (0,0,0,1), 'Pa': (1,-1,-2,0), 'N': (1,1,-2,0),
         'J': (1,2,-2,0), 'W': (1,2,-3,0), 'Hz': (0,0,-1,0)}
FUNCTIONS = {'sin', 'cos', 'exp', 'log', 'sqrt', 'grad', 'inner'}


class ExpressionError(ValueError):
    def __init__(self, message, *, path='settings', node=None):
        self.path = path
        self.line = getattr(node, 'lineno', None)
        self.column = getattr(node, 'col_offset', None)
        suffix = '' if self.line is None else f' (줄 {self.line}, 열 {self.column + 1})'
        super().__init__(message + suffix)


def add_dim(a, b, factor=1):
    return tuple(x + factor*y for x,y in zip(a,b))


def unit_dimension(source, *, path='settings'):
    try:return _unit_dimension(source)
    except ExpressionError as error:
        error.path=path
        raise


def _unit_dimension(source):
    if not isinstance(source, str) or not source or len(source) > 128:
        raise ExpressionError('단위를 입력하세요.')
    try:
        tree = ast.parse(source, mode='eval').body
    except (SyntaxError, ValueError, RecursionError) as error:
        err=ExpressionError('단위는 SI 곱셈·나눗셈·정수 거듭제곱으로 입력하세요.')
        err.line=getattr(error,'lineno',None)
        offset=getattr(error,'offset',None);err.column=max(0,offset-1) if offset is not None else None
        raise err from error
    def read(node):
        if isinstance(node, ast.Name) and node.id in UNITS:
            return UNITS[node.id]
        if isinstance(node, ast.Constant) and type(node.value) is int and node.value == 1:
            return ZERO
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
            return add_dim(read(node.left), read(node.right), -1 if isinstance(node.op, ast.Div) else 1)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            power = numeric_constant(node.right)
            if int(power) != power or abs(power) > 8:
                raise ExpressionError('단위 지수는 -8~8 정수만 지원합니다.',node=node.right)
            return tuple(x*int(power) for x in read(node.left))
        raise ExpressionError('지원 단위: kg, m, s, K, Pa, N, J, W, Hz. 다른 단위로 자동 변환하지 않습니다.',node=node)
    return read(tree)


def numeric_constant(node):
    sign = 1
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        sign = -1 if isinstance(node.op, ast.USub) else 1
        node = node.operand
    if (not isinstance(node, ast.Constant) or type(node.value) not in (int,float)
            or not math.isfinite(node.value)):
        raise ExpressionError('유한한 수 상수가 필요합니다.', node=node)
    return sign*node.value


@dataclass(frozen=True)
class Meaning:
    dimension: tuple = ZERO
    rank: int = 0
    degree: tuple = (0,0)


def parse(source, symbols, *, path='settings', weak=False):
    if not isinstance(source,str) or not source.strip() or len(source)>2048:
        raise ExpressionError('식은 1~2048자로 입력하세요.', path=path)
    try:
        tree=ast.parse(source, mode='eval').body
    except (SyntaxError, ValueError, RecursionError) as error:
        err=ExpressionError('식 문법을 확인하세요.', path=path)
        err.line=getattr(error,'lineno',None)
        offset=getattr(error,'offset',None);err.column=max(0,offset-1) if offset is not None else None
        raise err from error
    if len(list(ast.walk(tree)))>256:
        raise ExpressionError('식이 너무 복잡합니다.',path=path)
    def fail(message,node):
        raise ExpressionError(message,path=path,node=node)
    def visit(node):
        if isinstance(node,ast.Constant) and type(node.value) in (int,float) and math.isfinite(node.value):
            return Meaning()
        if isinstance(node,ast.Name) and node.id in symbols:
            return symbols[node.id]
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return visit(node.operand)
        if isinstance(node,ast.BinOp):
            a=visit(node.left)
            if isinstance(node.op,ast.Pow):
                try: p=numeric_constant(node.right)
                except ExpressionError: fail('지수는 수 상수여야 합니다.',node.right)
                if abs(p)>8 or a.rank or (a.degree!=(0,0) and p not in (0,1)):
                    fail('이 지수/함수공간은 지원하지 않습니다.',node)
                q=Fraction(str(p))
                return Meaning(tuple(x*q for x in a.dimension),0,tuple(int(x*p) for x in a.degree))
            b=visit(node.right)
            if isinstance(node.op,(ast.Add,ast.Sub)):
                if a!=b: fail('더하는 항의 차원·성분·시험/해 차수가 다릅니다.',node)
                return a
            if isinstance(node.op,(ast.Mult,ast.Div)):
                if isinstance(node.op,ast.Div):
                    if b.rank or b.degree!=(0,0): fail('분모는 해/시험함수에 독립인 스칼라여야 합니다.',node)
                    return Meaning(add_dim(a.dimension,b.dimension,-1),a.rank,a.degree)
                if a.rank and b.rank: fail('벡터 내적은 inner(a,b)를 사용하세요.',node)
                degree=tuple(x+y for x,y in zip(a.degree,b.degree))
                if weak and max(degree)>1: fail('현재 약형식은 선형 해/시험함수만 지원합니다.',node)
                return Meaning(add_dim(a.dimension,b.dimension),max(a.rank,b.rank),degree)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords:
            name=node.func.id
            args=[visit(arg) for arg in node.args]
            if name=='grad' and weak and len(args)==1 and args[0].rank==0:
                return Meaning(add_dim(args[0].dimension,UNITS['m'],-1),1,args[0].degree)
            if name=='inner' and weak and len(args)==2 and args[0].rank==args[1].rank==1:
                return Meaning(add_dim(args[0].dimension,args[1].dimension),0,
                               tuple(x+y for x,y in zip(args[0].degree,args[1].degree)))
            if name in ('sin','cos','exp','log','sqrt') and len(args)==1 and args[0].rank==0 and args[0].degree==(0,0):
                if name=='sqrt':
                    return Meaning(tuple(Fraction(x,2) for x in args[0].dimension))
                if args[0].dimension!=ZERO: fail('초월함수의 인수는 무차원이어야 합니다.',node)
                return Meaning()
        fail('허용되지 않은 이름/연산입니다. 속성·색인·Python 호출은 사용할 수 없습니다.',node)
    try: meaning=visit(tree)
    except RecursionError as error: raise ExpressionError('식 깊이 제한을 초과했습니다.',path=path) from error
    return tree,meaning


def evaluate(tree, values, functions=None):
    functions=functions or {name:getattr(math,name) for name in ('sin','cos','exp','log','sqrt')}
    if isinstance(tree,ast.Constant): return tree.value
    if isinstance(tree,ast.Name): return values[tree.id]
    if isinstance(tree,ast.UnaryOp):
        value=evaluate(tree.operand,values,functions)
        return -value if isinstance(tree.op,ast.USub) else value
    if isinstance(tree,ast.BinOp):
        a=evaluate(tree.left,values,functions); b=evaluate(tree.right,values,functions)
        if isinstance(tree.op,ast.Add): return a+b
        if isinstance(tree.op,ast.Sub): return a-b
        if isinstance(tree.op,ast.Mult): return a*b
        if isinstance(tree.op,ast.Div): return a/b
        if isinstance(tree.op,ast.Pow): return a**b
    if isinstance(tree,ast.Call):
        return functions[tree.func.id](*(evaluate(a,values,functions) for a in tree.args))
    raise ExpressionError('검사하지 않은 식입니다.')
