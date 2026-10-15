"""Lower already-validated dimensioned ASTs to scikit-fem quadrature arrays.

This is expression evaluation, not another parser or FE assembler. Spatial
reference gradients use the analytic chain rule; no design/adjoint gradients
are claimed. P1 trial/test values and gradients come from scikit-fem itself.
"""
import ast


def value(tree, values, gradients):
    import numpy as np
    if isinstance(tree, ast.Constant):
        return tree.value
    if isinstance(tree, ast.Name):
        return values[tree.id]
    if isinstance(tree, ast.UnaryOp):
        result = value(tree.operand, values, gradients)
        return -result if isinstance(tree.op, ast.USub) else result
    if isinstance(tree, ast.BinOp):
        a, b = value(tree.left, values, gradients), value(tree.right, values, gradients)
        if isinstance(tree.op, ast.Add): return a + b
        if isinstance(tree.op, ast.Sub): return a - b
        if isinstance(tree.op, ast.Mult): return a * b
        if isinstance(tree.op, ast.Div): return a / b
        if isinstance(tree.op, ast.Pow): return a ** b
    if isinstance(tree, ast.Call):
        name = tree.func.id
        if name == 'grad': return gradient(tree.args[0], values, gradients)
        args = [value(arg, values, gradients) for arg in tree.args]
        if name == 'inner': return np.sum(args[0] * args[1], axis=0)
        return {'sin': np.sin, 'cos': np.cos, 'exp': np.exp, 'log': np.log, 'sqrt': np.sqrt}[name](*args)
    raise ValueError('Only a previously validated dimensioned expression can be assembled')


def gradient(tree, values, gradients):
    import numpy as np
    zero = np.zeros_like(gradients['x'])
    if isinstance(tree, ast.Constant): return zero
    if isinstance(tree, ast.Name): return gradients.get(tree.id, zero)
    if isinstance(tree, ast.UnaryOp):
        result = gradient(tree.operand, values, gradients)
        return -result if isinstance(tree.op, ast.USub) else result
    if isinstance(tree, ast.BinOp):
        a, b = value(tree.left, values, gradients), value(tree.right, values, gradients)
        ga, gb = gradient(tree.left, values, gradients), gradient(tree.right, values, gradients)
        if isinstance(tree.op, ast.Add): return ga + gb
        if isinstance(tree.op, ast.Sub): return ga - gb
        if isinstance(tree.op, ast.Mult): return ga * b + a * gb
        if isinstance(tree.op, ast.Div): return (ga * b - a * gb) / (b * b)
        if isinstance(tree.op, ast.Pow):
            if b == 0: return zero
            return b * (a ** (b - 1)) * ga
    if isinstance(tree, ast.Call):
        name = tree.func.id
        if name in ('grad', 'inner'):
            raise ValueError('Nested spatial differentiation is not admitted by this P1 capability')
        a = value(tree.args[0], values, gradients)
        ga = gradient(tree.args[0], values, gradients)
        factor = {'sin': lambda: np.cos(a), 'cos': lambda: -np.sin(a),
                  'exp': lambda: np.exp(a), 'log': lambda: 1. / a,
                  'sqrt': lambda: .5 / np.sqrt(a)}[name]()
        return factor * ga
    raise ValueError('Unsupported derivative of an unvalidated expression')
