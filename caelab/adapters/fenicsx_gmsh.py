"""Pure, bounded MSH2 syntax and separate dense native input copies.

This module never imports Gmsh, touches a native model or owns scientific
geometry/reference verdicts. Original bytes and identifiers are immutable.
"""

import copy
import hashlib
import math
import re

if __name__ == "mesh_syntax":
    from fenicsx_expression import PDEInputError, finite_number
else:
    from .fenicsx_worker import PDEInputError, finite_number

MAX_BYTES = 96 * 1024
MAX_ID = 2**31 - 1
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _integer(token):
    if not re.fullmatch(r"[0-9]+", token):
        raise PDEInputError("MSH integers must be positive decimal identifiers")
    if len(token.lstrip("0")) > 10:
        raise PDEInputError("MSH identifier is outside the bounded positive range")
    value = int(token.lstrip("0") or "0")
    if not 1 <= value <= MAX_ID:
        raise PDEInputError("MSH identifier is outside the bounded positive range")
    return value


def _bytes(data, sha256, limit=MAX_BYTES):
    if not isinstance(data, str) or not data or not isinstance(sha256, str) or not SHA.fullmatch(sha256):
        raise PDEInputError("MSH content and exact lower-case SHA256 are required")
    try:
        raw = data.encode("ascii")
    except UnicodeError as exc:
        raise PDEInputError("Only ASCII MSH input is supported") from exc
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != sha256:
        raise PDEInputError("MSH byte count or original byte hash differs")
    return raw


def parse_msh(data, sha256):
    """Return sorted normalized metadata from exact supported source bytes."""
    return _parse_msh(data, sha256, MAX_BYTES)


def _parse_msh(data, sha256, limit):
    raw = _bytes(data, sha256, limit)
    lines = raw.decode("ascii").splitlines()
    cursor = 0
    sections = {}
    for name in ("MeshFormat", "PhysicalNames", "Nodes", "Elements"):
        if cursor >= len(lines) or lines[cursor] != "$" + name:
            raise PDEInputError("Exactly the four ordered supported MSH2 sections are required")
        cursor += 1
        stop = "$End" + name
        entries = []
        while cursor < len(lines) and lines[cursor] != stop:
            if not lines[cursor] or lines[cursor].startswith("$"):
                raise PDEInputError("Malformed or unexpected MSH section")
            entries.append(lines[cursor])
            cursor += 1
        if cursor >= len(lines):
            raise PDEInputError("Truncated MSH section")
        cursor += 1
        sections[name] = entries
    if cursor != len(lines) or sections["MeshFormat"] != ["2.2 0 8"]:
        raise PDEInputError("Only exact MSH2.2 ASCII format without extra sections is supported")

    def rows(name):
        values = sections[name]
        if not values or _integer(values[0]) != len(values) - 1:
            raise PDEInputError("MSH declared section count differs from complete rows")
        return values[1:]

    groups, names = {}, set()
    for row in rows("PhysicalNames"):
        match = re.fullmatch(r'([12])\s+([0-9]+)\s+"([A-Za-z][A-Za-z0-9_-]{0,63})"', row)
        if not match:
            raise PDEInputError("MSH physical names require supported dimensions and ASCII identifiers")
        dim, tag, name = int(match[1]), _integer(match[2]), match[3]
        if (dim, tag) in groups or name in names:
            raise PDEInputError("MSH physical tags/names must be unique, including across dimensions")
        groups[dim, tag] = name
        names.add(name)
    bodies = [(tag, name) for (dim, tag), name in groups.items() if dim == 2]
    if len(bodies) != 1 or not any(dim == 1 for dim, _ in groups):
        raise PDEInputError("MSH requires exactly one body and nonempty named line groups")
    nodes = {}
    for row in rows("Nodes"):
        tokens = row.split()
        if len(tokens) != 4:
            raise PDEInputError("Malformed MSH node row")
        identifier = _integer(tokens[0])
        try:
            x, y, z = map(float, tokens[1:])
        except ValueError as exc:
            raise PDEInputError("Malformed MSH coordinate") from exc
        if identifier in nodes or not all(finite_number(value) for value in (x, y, z)) or z != 0 or max(abs(x), abs(y)) > 1000:
            raise PDEInputError("Duplicate, nonfinite or unsupported planar MSH coordinate")
        nodes[identifier] = [x, y]
    if len(nodes) < 3 or any(not .001 <= max(p[a] for p in nodes.values()) - min(p[a] for p in nodes.values()) <= 1000 for a in range(2)):
        raise PDEInputError("MSH bounding-box extents must be within 0.001..1000")
    cells, boundaries, seen, entities = [], {name: {"tag": tag, "elements": []} for (dim, tag), name in groups.items() if dim == 1}, set(), {}
    for row in rows("Elements"):
        tokens = row.split()
        if len(tokens) < 5 or tokens[1] not in ("1", "2") or tokens[2] != "2":
            raise PDEInputError("Only linear lines/triangles with exactly two tags are supported")
        identifier, kind = _integer(tokens[0]), int(tokens[1])
        if len(tokens) != (7 if kind == 1 else 8) or identifier in seen:
            raise PDEInputError("Duplicate or malformed MSH element row")
        seen.add(identifier)
        physical, entity = _integer(tokens[3]), _integer(tokens[4])
        node_ids = [_integer(token) for token in tokens[5:]]
        if len(set(node_ids)) != len(node_ids) or not set(node_ids) <= set(nodes) or (kind, physical) not in groups:
            raise PDEInputError("MSH element nodes or physical membership differ")
        previous = entities.setdefault((kind, entity), physical)
        if previous != physical:
            raise PDEInputError("One elementary entity cannot mix physical tags")
        if kind == 2:
            cells.append({"id": identifier, "node_ids": node_ids, "physical_tag": physical, "entity_tag": entity})
        else:
            boundaries[groups[kind, physical]]["elements"].append({"id": identifier, "node_ids": node_ids, "entity_tag": entity})
    if not cells or any(not group["elements"] for group in boundaries.values()):
        raise PDEInputError("All declared physical groups require actual elements")
    return {"source_sha256": sha256, "body": {"name": bodies[0][1], "tag": bodies[0][0]},
            "nodes": [{"id": identifier, "coordinates": nodes[identifier]} for identifier in sorted(nodes)],
            "cells": sorted(cells, key=lambda row: row["id"]),
            "boundaries": {name: {"tag": group["tag"], "elements": sorted(group["elements"], key=lambda row: row["id"])} for name, group in sorted(boundaries.items())}}


def prepare(settings):
    """Check inline transport identities, then expose only normalized meshes."""
    if not isinstance(settings, dict) or set(settings) != {"problem", "mesh", "validation"}:
        raise PDEInputError("Imported settings require exactly problem, mesh and validation")
    mesh = settings["mesh"]
    if not isinstance(mesh, dict) or set(mesh) != {"degree", "levels"} or type(mesh["degree"]) is not int or mesh["degree"] != 1:
        raise PDEInputError("Imported mesh transport requires scalar degree1 and levels")
    levels = mesh["levels"]
    if not isinstance(levels, list) or not 3 <= len(levels) <= 8:
        raise PDEInputError("Imported mesh sequence requires 3..8 complete levels")
    meshes, total = [], 0
    for row in levels:
        if (not isinstance(row, dict) or set(row) != {"format", "data", "sha256", "source"} or row["format"] != "gmsh_msh2_ascii" or
                not isinstance(row["source"], str) or not row["source"].strip() or len(row["source"]) > 256):
            raise PDEInputError("Imported mesh level requires immutable ASCII content/hash/display source")
        raw = _bytes(row["data"], row["sha256"])
        total += len(raw)
        if total > MAX_BYTES:
            raise PDEInputError("Total original inline MSH content exceeds 96KiB")
        meshes.append(parse_msh(row["data"], row["sha256"]))
    return meshes


def _format(mesh):
    groups = [(2, mesh["body"]["tag"], mesh["body"]["name"]), *[(1, row["tag"], name) for name, row in sorted(mesh["boundaries"].items())]]
    lines = ["$MeshFormat", "2.2 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(groups)), *[f'{dim} {tag} "{name}"' for dim, tag, name in groups], "$EndPhysicalNames", "$Nodes", str(len(mesh["nodes"]))]
    lines.extend(f"{row['id']} {row['coordinates'][0]:.17g} {row['coordinates'][1]:.17g} 0" for row in mesh["nodes"])
    lines.extend(["$EndNodes", "$Elements", str(len(mesh["cells"]) + sum(len(row["elements"]) for row in mesh["boundaries"].values()))])
    elements = [(row["id"], 2, row["physical_tag"], row["entity_tag"], row["node_ids"]) for row in mesh["cells"]]
    elements.extend((row["id"], 1, group["tag"], row["entity_tag"], row["node_ids"]) for group in mesh["boundaries"].values() for row in group["elements"])
    lines.extend(f"{identifier} {kind} 2 {physical} {entity} " + " ".join(map(str, node_ids)) for identifier, kind, physical, entity, node_ids in sorted(elements))
    return "\n".join([*lines, "$EndElements", ""])


def dense_import(mesh):
    """Create a distinct deterministic copy; never mutate source metadata."""
    derived = copy.deepcopy(mesh)
    original = [row["id"] for row in mesh["nodes"]]
    dense = list(range(1, len(original) + 1))
    table = dict(zip(original, dense))
    for row in derived["nodes"]:
        row["id"] = table[row["id"]]
    for row in derived["cells"]:
        row["node_ids"] = [table[node] for node in row["node_ids"]]
    for group in derived["boundaries"].values():
        for row in group["elements"]:
            row["node_ids"] = [table[node] for node in row["node_ids"]]
    data = _format(derived)
    sha = hashlib.sha256(data.encode("ascii")).hexdigest()
    derived["source_sha256"] = sha
    # Round-trip decimal serialization can expand the separately generated copy.
    # Its size follows the already bounded source rows; the public original cap
    # remains enforced by parse_msh/prepare rather than applied twice to a copy.
    if _parse_msh(data, sha, len(data)) != derived:
        raise PDEInputError("Derived dense input differs from exact source geometry/connectivity/groups")
    return data, {"dense_node_ids": dense, "original_node_ids": original, "original_sha256": mesh["source_sha256"], "dense_sha256": sha}


def manufactured_mesh(shape, n):
    """Labelled synthetic source grid: n intervals per unit, no native mesher."""
    if shape not in ("l_shape", "rectangle") or type(n) is not int or not 1 <= n <= 128:
        raise PDEInputError("Unsupported synthetic imported grid")
    squares = [(i, j) for j in range(2*n if shape == "l_shape" else n) for i in range(2*n) if shape != "l_shape" or i < n or j < n]
    points = sorted({(i+di, j+dj) for i, j in squares for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1))})
    identifiers = {point: 2*index+1 for index, point in enumerate(points)}
    mesh = {"body": {"name": "body", "tag": 1}, "nodes": [{"id": identifiers[p], "coordinates": [p[0]/n, p[1]/n]} for p in points], "cells": [], "boundaries": {}}
    edge_count = {}
    for i, j in squares:
        a, b, c, d = [identifiers[p] for p in ((i, j), (i+1, j), (i+1, j+1), (i, j+1))]
        for nodes in ([a, b, c], [a, c, d]):
            mesh["cells"].append({"id": 2*len(mesh["cells"])+1, "node_ids": nodes, "physical_tag": 1, "entity_tag": 1})
            for x, y in zip(nodes, nodes[1:]+nodes[:1]):
                edge = tuple(sorted((x, y)))
                edge_count[edge] = edge_count.get(edge, 0)+1
    names = ("west", "south", "east_lower", "notch_horizontal", "notch_vertical", "north") if shape == "l_shape" else ("west", "south", "east", "north")
    mesh["boundaries"] = {name: {"tag": tag, "elements": []} for tag, name in enumerate(names, 2)}
    coordinates = {row["id"]: row["coordinates"] for row in mesh["nodes"]}
    for edge, count in sorted(edge_count.items()):
        if count != 1:
            continue
        p, q = [coordinates[node] for node in edge]
        name = "west" if p[0] == q[0] == 0 else "south" if p[1] == q[1] == 0 else "north" if p[1] == q[1] == (2 if shape == "l_shape" else 1) else "east" if shape == "rectangle" else "east_lower" if p[0] == q[0] == 2 else "notch_horizontal" if p[1] == q[1] == 1 else "notch_vertical"
        row = {"id": 2*(len(mesh["cells"])+sum(len(group["elements"]) for group in mesh["boundaries"].values()))+1, "node_ids": list(edge), "entity_tag": mesh["boundaries"][name]["tag"]}
        mesh["boundaries"][name]["elements"].append(row)
    data = _format(mesh)
    return {"format": "gmsh_msh2_ascii", "data": data, "sha256": hashlib.sha256(data.encode("ascii")).hexdigest(), "source": f"SYNTHETIC {shape} source grid n={n}; intervals per unit"}
