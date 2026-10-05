"""Pure source-bound T10 geometry/topology references; no native qualification.

Official Code_Aster 50ebc13c70ee9df62faf93ddcb746a3757b3042a:
elrfno T10 nodes, elrfvf shapes, elrfdf derivatives and elraga FPG5.
Coordinates/weights returned here are derived expectations, not native fields.
Caller owns mesh/source/body admission, compiled ordering and later verdicts.
"""
from __future__ import annotations

import math

_POINTS = ((.25, .25, .25), (1/6, 1/6, 1/6),
           (1/6, 1/6, .5), (1/6, .5, 1/6), (.5, 1/6, 1/6))
_WEIGHTS = (-2/15, 3/40, 3/40, 3/40, 3/40)
_FACES = (((0, 1, 2), (0, 1, 2, 4, 5, 6)),
          ((0, 1, 3), (0, 1, 3, 4, 7, 8)),
          ((0, 2, 3), (0, 2, 3, 6, 7, 9)),
          ((1, 2, 3), (1, 2, 3, 5, 8, 9)))
_TET_EDGES = (((0, 1), 4), ((1, 2), 5), ((2, 0), 6),
              ((0, 3), 7), ((1, 3), 8), ((2, 3), 9))
_TRI_EDGES = (((0, 1), 3), ((1, 2), 4), ((2, 0), 5))


def _finite(value):
    if not math.isfinite(value):
        raise ValueError("Nonrepresentable geometry arithmetic")
    return value


def _real(value):
    if type(value) not in (int, float):
        raise ValueError("Finite nonboolean JSON real coordinate required")
    try:
        return _finite(float(value))
    except OverflowError as exc:
        raise ValueError("Nonrepresentable coordinate") from exc


def _sum(values):
    try:
        return _finite(math.fsum(_finite(v) for v in values))
    except (OverflowError, ArithmeticError) as exc:
        raise ValueError("Nonrepresentable geometry sum") from exc


def _product(*values):
    result = 1.
    for value in values:
        result = _finite(result * value)
    return result


def _polynomials(x, y, z):
    a = _sum((1., -x, -y, -z))
    shapes = (y*(2*y-1), z*(2*z-1), a*(2*a-1), x*(2*x-1),
              4*z*y, 4*z*a, 4*a*y, 4*x*y, 4*x*z, 4*x*a)
    derivatives = ((0., 4*y-1, 0.), (0., 0., 4*z-1),
                   (1-4*a, 1-4*a, 1-4*a), (4*x-1, 0., 0.),
                   (0., 4*z, 4*y), (-4*z, -4*z, 4*(a-z)),
                   (-4*y, 4*(a-y), -4*y), (4*y, 4*x, 0.),
                   (4*z, 0., 4*x), (4*(a-x), -4*x, -4*x))
    return shapes, derivatives


def tetra10_gauss(ordered_xyz_mm):
    """Return five signed-invalid-preserving geometry expectations in source order."""
    if type(ordered_xyz_mm) is not list or len(ordered_xyz_mm) != 10:
        raise ValueError("Ten native-ordered JSON XYZ lists required")
    xyz = []
    for point in ordered_xyz_mm:
        if type(point) is not list or len(point) != 3:
            raise ValueError("Exactly three JSON coordinates required")
        xyz.append([_real(v) for v in point])
    result = []
    for number, (point, weight) in enumerate(zip(_POINTS, _WEIGHTS), 1):
        shapes, derivatives = _polynomials(*point)
        position = [_sum(_product(shapes[i], xyz[i][axis]) for i in range(10))
                    for axis in range(3)]
        jac = [[_sum(_product(derivatives[i][ref_axis], xyz[i][physical_axis])
                     for i in range(10)) for physical_axis in range(3)]
               for ref_axis in range(3)]
        determinant = _sum((
            _product(jac[0][0], jac[1][1], jac[2][2]),
            _product(jac[0][1], jac[1][2], jac[2][0]),
            _product(jac[0][2], jac[1][0], jac[2][1]),
            -_product(jac[0][2], jac[1][1], jac[2][0]),
            -_product(jac[0][1], jac[1][0], jac[2][2]),
            -_product(jac[0][0], jac[1][2], jac[2][1]),
        ))
        result.append({"point": number, "reference_xyz": list(point),
                       "reference_weight": weight, "xyz_mm": position,
                       "signed_jacobian_mm3": determinant,
                       "native_expected_weight_mm3": _product(abs(determinant), weight)})
    return result


def _indices(value):
    if (type(value) is not list or not value or
            any(type(i) is not int or i < 0 for i in value) or len(set(value)) != len(value)):
        raise ValueError("Nonempty unique nonnegative JSON integer indices required")
    return value


def exterior_nodes(cells, body_cells):
    """Derive complete conforming exterior/interior identity from native topology."""
    if type(cells) is not list or not cells or type(body_cells) is not list or not body_cells:
        raise ValueError("Nonempty JSON cell/body lists required")
    indexed = {}
    for cell in cells:
        if type(cell) is not dict or set(cell) != {"index", "type", "node_indices"}:
            raise ValueError("Exact native cell keys required")
        index, kind = cell["index"], cell["type"]
        if type(index) is not int or index < 0 or index in indexed or type(kind) is not str or kind not in ("TETRA10", "TRIA6"):
            raise ValueError("Unique native cell integer/type identity required")
        nodes = _indices(cell["node_indices"])
        if len(nodes) != (10 if kind == "TETRA10" else 6):
            raise ValueError("Complete native TETRA10/TRIA6 connectivity required")
        indexed[index] = cell
    if set(indexed) != set(range(len(cells))):
        raise ValueError("Native cell indices must cover zero through count minus one")
    owners, component_ids, bodies, used_nodes = set(), set(), [], set()
    for body in body_cells:
        if type(body) is not dict or set(body) != {"component_id", "volume_cell_indices", "face_cell_indices"}:
            raise ValueError("Exact body topology keys required")
        component = body["component_id"]
        if type(component) is not str or not component.strip() or component in component_ids:
            raise ValueError("Unique nonempty component identity required")
        component_ids.add(component)
        volume = _indices(body["volume_cell_indices"])
        faces = _indices(body["face_cell_indices"])
        selected = volume + faces
        if (len(set(selected)) != len(selected) or owners.intersection(selected) or
                any(index not in indexed for index in selected)):
            raise ValueError("Every native cell must have one actual body owner")
        if (any(indexed[i]["type"] != "TETRA10" for i in volume) or
                any(indexed[i]["type"] != "TRIA6" for i in faces)):
            raise ValueError("Volume/face native cell types differ")
        owners.update(selected)
        nodes = {node for i in selected for node in indexed[i]["node_indices"]}
        if used_nodes.intersection(nodes):
            raise ValueError("Distinct bodies may not share native node identity")
        used_nodes.update(nodes)
        bodies.append((component, volume, faces))
    if owners != set(indexed):
        raise ValueError("Complete native cell ownership required")
    output = []
    for component, volume, faces in bodies:
        tetra_keys, face_occurrences, volume_nodes = set(), {}, set()
        corner_nodes = {node for index in volume for node in indexed[index]["node_indices"][:4]}
        midside_nodes = {node for index in volume for node in indexed[index]["node_indices"][4:]}
        if corner_nodes.intersection(midside_nodes):
            raise ValueError("Native node identity may not be both corner and midside")
        edge_midsides, midside_edges = {}, {}
        for index in volume:
            nodes = indexed[index]["node_indices"]
            tetra_key = tuple(sorted(nodes[:4]))
            if tetra_key in tetra_keys:
                raise ValueError("Repeated tetrahedron topology")
            tetra_keys.add(tetra_key)
            volume_nodes.update(nodes)
            for corner_slots, midside_slot in _TET_EDGES:
                edge = tuple(sorted(nodes[i] for i in corner_slots))
                midside = nodes[midside_slot]
                if edge_midsides.setdefault(edge, midside) != midside:
                    raise ValueError("Nonconforming native edge midside identity")
                if midside_edges.setdefault(midside, edge) != edge:
                    raise ValueError("Native midside identity may not name different corner edges")
            for corner_slots, all_slots in _FACES:
                key = tuple(sorted(nodes[i] for i in corner_slots))
                full = frozenset(nodes[i] for i in all_slots)
                previous = face_occurrences.setdefault(key, [])
                if previous and previous[0] != full:
                    raise ValueError("Nonconforming shared face midside identity")
                previous.append(full)
                if len(previous) > 2:
                    raise ValueError("Nonmanifold tetrahedron face")
        exposed = {key: values[0] for key, values in face_occurrences.items() if len(values) == 1}
        supplied, boundary_nodes = set(), set()
        for index in faces:
            nodes = indexed[index]["node_indices"]
            key = tuple(sorted(nodes[:3]))
            if key in supplied or key not in exposed or frozenset(nodes) != exposed[key]:
                raise ValueError("Boundary faces must match exposed full six-node identity exactly")
            for corner_slots, midside_slot in _TRI_EDGES:
                edge = tuple(sorted(nodes[i] for i in corner_slots))
                if edge_midsides.get(edge) != nodes[midside_slot]:
                    raise ValueError("Boundary face native edge midside identity differs")
            supplied.add(key)
            boundary_nodes.update(nodes)
        if supplied != set(exposed):
            raise ValueError("Incomplete exterior face topology")
        output.append({"component_id": component,
                       "exterior_node_indices": sorted(boundary_nodes),
                       "interior_node_indices": sorted(volume_nodes - boundary_nodes),
                       "boundary_face_count": len(exposed)})
    return output
