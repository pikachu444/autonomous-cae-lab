"""The existing bounded scalar AST with one trusted time binding; no eval."""

import ast
import copy
import math

if __package__:
    from . import fenicsx_worker as base
else:
    import fenicsx_expression as base

PDEInputError = base.PDEInputError
finite_number = base.finite_number


class _TimeBinding(ast.NodeTransformer):
    def __init__(self, replacement):
        self.replacement = replacement

    def visit_Name(self, node):
        return ast.copy_location(copy.deepcopy(self.replacement), node) if node.id == "t" else node


def _replace(tree, replacement):
    return ast.fix_missing_locations(_TimeBinding(replacement).visit(copy.deepcopy(tree)))


def parse_expression(source):
    if not isinstance(source, str) or not source.strip() or len(source) > base.MAX_EXPRESSION_LENGTH:
        raise PDEInputError("Time expression exceeds the existing scalar source bound")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise PDEInputError("Malformed time expression") from exc
    # Original x[2] must never gain access to the trusted time slot.
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and (not isinstance(node.value, ast.Name) or node.value.id != "x" or
                not isinstance(node.slice, ast.Constant) or type(node.slice.value) is not int or node.slice.value not in (0, 1)):
            raise PDEInputError("Only original spatial x[0] and x[1] are admitted")
    placeholder = ast.Subscript(value=ast.Name(id="x", ctx=ast.Load()), slice=ast.Constant(value=0), ctx=ast.Load())
    base.parse_expression(ast.unparse(_replace(tree, placeholder)))
    slot = ast.Subscript(value=ast.Name(id="x", ctx=ast.Load()), slice=ast.Constant(value=2), ctx=ast.Load())
    tree.body._time_binding_tree = _replace(tree.body, slot)
    return tree.body


def interpret_expression(tree, x, time, functions):
    return base.interpret_expression(tree._time_binding_tree, (x[0], x[1], time), functions)


def bind_expression(source, time):
    if not finite_number(time):
        raise PDEInputError("Numeric time binding must be finite")
    return ast.unparse(_replace(parse_expression(source), ast.Constant(value=time)))


def scalar_value(tree, x, y, time):
    if not all(finite_number(value) for value in (x, y, time)):
        raise PDEInputError("Scalar coordinates and time must be finite")
    try:
        value = interpret_expression(tree, (x, y), time, {name: getattr(math, name) for name in base.FUNCTION_NAMES})
    except (ArithmeticError, ValueError) as exc:
        raise PDEInputError("Time expression is undefined at a required sample") from exc
    if not finite_number(value):
        raise PDEInputError("Time expression produced a nonfinite required value")
    return float(value)
