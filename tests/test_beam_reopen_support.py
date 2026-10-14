"""Scoped source-method loader; not a native Owner or a FreeCAD emulator.

The metadata transaction tests need the actual Owner._transaction body but not
imports/initialization of unrelated shell, motion or convergence subsystems.
FreeCAD document/storage/Undo boundaries in these tests remain explicit doubles.
"""
import ast
from pathlib import Path


def transaction(owner, title, change):
    path = Path(__file__).resolve().parents[1] / 'apps/desktop_pre/bridge.py'
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    klass = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Owner')
    method = next(node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name == '_transaction')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['_transaction'](owner, title, change)
