"""Mesh surface load integration, including invalid topology cases."""

from math import cos, pi, sin
from pathlib import Path
from types import SimpleNamespace

import pytest

from caelab.adapters.fixture_saddle_load import saddle_nodal_forces


RADIUS = 4.15
BBOX = SimpleNamespace(xmin=-16, xmax=16, ymin=-20, ymax=20, zmax=26)


def mesh(tmp_path: Path):
    """Half-cylinder CPS6 shell with Gmsh's straight midside placement."""
    nodes = {}
    corners = {}
    midpoints = {}
    next_node = 1
    for row, y in enumerate((-20., 0., 20.)):
        for column in range(5):
            angle = column * pi / 4
            corners[row, column] = next_node
            nodes[next_node] = (RADIUS * cos(angle), y, 26 - RADIUS * sin(angle))
            next_node += 1

    def midpoint(a, b):
        nonlocal next_node
        edge = tuple(sorted((a, b)))
        if edge not in midpoints:
            midpoints[edge] = next_node
            nodes[next_node] = tuple((nodes[a][i] + nodes[b][i]) / 2 for i in range(3))
            next_node += 1
        return midpoints[edge]

    faces = []
    for row in range(2):
        for col in range(4):
            a, b = corners[row, col], corners[row, col + 1]
            c, d = corners[row + 1, col + 1], corners[row + 1, col]
            for u, v, w in ((a, b, c), (a, c, d)):
                faces.append((u, v, w, midpoint(u, v), midpoint(v, w), midpoint(w, u)))
    path = tmp_path / "gmsh.inp"

    def write(data):
        path.write_text("*ELEMENT, type=CPS6, ELSET=Surface8\n" +
                        "\n".join(f"{i}, " + ", ".join(map(str, face))
                                  for i, face in enumerate(data, 1)) + "\n")

    write(faces)
    return path, nodes, faces, write


def test_clip_and_consistent_nodal_load_preserve_force(tmp_path):
    path, nodes, _, _ = mesh(tmp_path)
    result = saddle_nodal_forces(path, nodes, BBOX, RADIUS, 160.)
    assert result["surface_group"] == "SURFACE8"
    assert result["face_count"] == 16
    assert result["patch_area_mm2"] == pytest.approx(pi * RADIUS * 24, rel=.05)
    assert result["total_applied_force_N"] == pytest.approx(160.)
    assert sum(result["nodal_loads"].values()) == pytest.approx(-160.)
    assert result["loaded_node_ids"] == sorted(result["nodal_loads"])
    assert result["loaded_node_count"] == len(result["nodal_loads"])
    assert all(force < 0 for force in result["nodal_loads"].values())
    assert 0 < result["lip_force_fraction"] < .5
    assert 0 < result["outside_patch_force_fraction"] < .2
    assert len(set(round(force, 9) for force in result["nodal_loads"].values())) > 2


def test_ambiguous_or_incomplete_cylindrical_surface_fails_closed(tmp_path):
    path, nodes, faces, write = mesh(tmp_path)
    with path.open("a") as stream:
        stream.write("*ELEMENT, type=CPS6, ELSET=Surface9\n")
        stream.write("\n".join(f"{i + 100}, " + ", ".join(map(str, face))
                               for i, face in enumerate(faces, 1)) + "\n")
    with pytest.raises(ValueError, match="one cylindrical CPS6"):
        saddle_nodal_forces(path, nodes, BBOX, RADIUS, 160.)
    write(faces[:-1])
    with pytest.raises(ValueError, match="Open interior edge"):
        saddle_nodal_forces(path, nodes, BBOX, RADIUS, 160.)


def test_bad_midpoint_and_duplicate_face_are_rejected(tmp_path):
    path, nodes, faces, write = mesh(tmp_path)
    mid = faces[0][3]
    nodes[mid] = (nodes[mid][0], nodes[mid][1] + .1, nodes[mid][2])
    with pytest.raises(ValueError, match="midside node"):
        saddle_nodal_forces(path, nodes, BBOX, RADIUS, 160.)
    nodes[mid] = (nodes[mid][0], nodes[mid][1] - .1, nodes[mid][2])
    write([*faces, faces[0]])
    with pytest.raises(ValueError, match="Duplicate saddle surface triangle"):
        saddle_nodal_forces(path, nodes, BBOX, RADIUS, 160.)


def test_shared_edge_must_share_midside_node_id(tmp_path):
    path, nodes, faces, write = mesh(tmp_path)
    # Faces 0 and 1 share the diagonal from corner 0 to corner 2.
    replacement = max(nodes) + 1
    shared = faces[0][5]
    assert shared == faces[1][3]
    nodes[replacement] = nodes[shared]
    changed = list(faces[0])
    changed[5] = replacement
    write([tuple(changed), *faces[1:]])
    with pytest.raises(ValueError, match="share their midside node"):
        saddle_nodal_forces(path, nodes, BBOX, RADIUS, 160.)


def test_load_and_unsupported_surface_input_are_rejected(tmp_path):
    path, nodes, _, _ = mesh(tmp_path)
    with pytest.raises(ValueError, match="Positive finite"):
        saddle_nodal_forces(path, nodes, BBOX, RADIUS, 0)
    path.write_text("*ELEMENT, type=C3D10, ELSET=Volume1\n1, 1,2,3,4,5,6,7,8,9,10\n")
    with pytest.raises(ValueError, match="No CPS6"):
        saddle_nodal_forces(path, nodes, BBOX, RADIUS, 160.)
