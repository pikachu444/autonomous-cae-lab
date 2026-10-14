"""Initial public CAD dimensions/connectivity only. No FreeCAD or solver runs."""
import ast
from collections import Counter
import math
from pathlib import Path
import runpy

import pytest

SOURCE = Path(__file__).resolve().parents[1]/'examples/assembly_closed_loop/create_four_bar.py'
factory = runpy.run_path(str(SOURCE))


def test_exact_four_revolute_connectivity_and_one_closed_cycle():
    joints = factory['JOINTS']; lengths = factory['LENGTHS']
    assert len(joints) == 4
    counts = Counter(bar for _, left, _, right, _ in joints for bar in (left, right))
    assert counts == {name: 2 for name in lengths}
    links = {(left, right) for _, left, _, right, _ in joints}
    assert links == {('ground', 'crank'), ('crank', 'coupler'), ('coupler', 'rocker'), ('rocker', 'ground')}
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    assert 'Cylindrical' not in {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not any(isinstance(node, ast.FunctionDef) and ('solve' in node.name and node.name != 'no_automatic_solve') for node in ast.walk(tree))


@pytest.mark.parametrize('singular', [False, True])
def test_initial_design_is_closed_with_exact_declared_bar_lengths(singular):
    data = factory['design_geometry'](singular)
    points, lengths = data['points'], factory['LENGTHS']
    for name, pair in [('ground', 'AD'), ('crank', 'AB'), ('coupler', 'BC'), ('rocker', 'DC')]:
        a, b = (points[vertex] for vertex in pair)
        assert math.dist(a, b) == pytest.approx(lengths[name], abs=1e-12, rel=0)
    for _, left, left_x, right, right_x in factory['JOINTS']:
        def anchor(bar, x):
            origin, theta = data['origins'][bar], data['angles'][bar]
            return origin[0]+x*math.cos(theta), origin[1]+x*math.sin(theta)
        assert anchor(left, left_x) == pytest.approx(anchor(right, right_x), abs=1e-12, rel=0)


def test_impossible_half_turn_and_collinear_case_are_geometric_inputs_not_fabricated_native_failures():
    normal = factory['design_geometry'](); limit = factory['design_geometry'](True)
    theta = normal['angles']['crank']+math.pi
    pin = (60*math.cos(theta), 60*math.sin(theta))
    assert math.dist(pin, normal['points']['D']) > 70+50
    B, C, D = (limit['points'][name] for name in 'BCD')
    cross = (C[0]-B[0])*(D[1]-B[1])-(C[1]-B[1])*(D[0]-B[0])
    assert abs(cross) < 1e-12
