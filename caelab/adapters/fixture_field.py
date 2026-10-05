"""Complete observed displacement for the pinned fixture's ASCII CalculiX run.

This is an adapter artifact, not a common metric or an engineering verdict.
Deck coordinates and forces are authoritative; native printed precision is the
only allowance used to corroborate FRD and loaded-node DAT observations.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from typing import Mapping

from ..storage import check_id


MAX_SOURCE_BYTES = 64 * 1024 * 1024
_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?\Z")
_FRD_NUMBER = re.compile(r"[-+]?\d\.\d{5}E[-+]\d{2,3}\Z")
_DAT_NUMBER = re.compile(r"[-+]?\d\.\d{6}E[-+]\d{2,3}\Z")
_ID = re.compile(r"[1-9]\d*\Z")
_LABELS = {
    "DISP": ("D1 1 2 1 0", "D2 1 2 2 0", "D3 1 2 3 0", "ALL 1 2 0 0 1ALL"),
    "STRESS": ("SXX 1 4 1 1", "SYY 1 4 2 2", "SZZ 1 4 3 3",
               "SXY 1 4 1 2", "SYZ 1 4 2 3", "SZX 1 4 3 1"),
    "ERROR": ("STR(%) 1 1 0 0",),
}
_FACES = ((0, 1, 2, 4, 5, 6), (0, 3, 1, 7, 8, 4),
          (1, 3, 2, 8, 9, 5), (2, 3, 0, 9, 7, 6))


def _identifier(token: str) -> int:
    if not _ID.fullmatch(token):
        raise ValueError("Invalid native positive identifier")
    return int(token)


def _number(token: str) -> float:
    if not _NUMBER.fullmatch(token):
        raise ValueError("Malformed or nonfinite native number")
    value = float(token.replace("D", "E").replace("d", "e"))
    if not math.isfinite(value):
        raise ValueError("Nonfinite native number")
    return value


def _ascii(data: bytes) -> str:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Fixture field requires ASCII native sources") from exc
    if "\x00" in text or "\r" in text:
        raise ValueError("Fixture field requires normalized ASCII source lines")
    return text


def _read_bytes(path: Path) -> bytes:
    # Refuse symlink/reparse associations before and after a bounded read.
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise ValueError("Fixture field source must be a regular local file")
    with path.open("rb") as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Fixture field source exceeds 64 MiB")
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Fixture field source association changed")
    return data


def _paths(folder: Path, mesh_index: int, *, inputs_only: bool = False) -> dict[str, Path]:
    if type(mesh_index) is not int or not 0 <= mesh_index < 8:
        raise ValueError("Invalid fixture field mesh index")
    raw = str(folder)
    if ".." in raw.replace("\\", "/").split("/"):
        raise ValueError("Fixture field folder must have a normalized local association")
    root = Path(folder)
    if (not root.is_dir() or root.name != f"support_{mesh_index}" or
            any(part.is_symlink() for part in (root, *root.parents))):
        raise ValueError("Fixture field folder does not match the mesh index")
    root = root.resolve(strict=True)
    job = f"support_{mesh_index}"
    names = {"mesh": "gmsh.inp", "deck": f"{job}.inp", "saddle": "saddle_load.json"}
    if not inputs_only:
        names.update(frd=f"{job}.frd", dat=f"{job}.dat")
    return {key: root / name for key, name in names.items()}


def _source(path: Path, data: bytes) -> dict:
    return {"path": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def capture_fixture_field_inputs(folder: Path, mesh_index: int) -> dict:
    """Bind the three actual inputs before native execution (no process calls)."""
    return {key: _source(path, _read_bytes(path))
            for key, path in _paths(folder, mesh_index, inputs_only=True).items()}


def _sections(text: str) -> list[tuple[str, dict[str, str], list[str]]]:
    sections = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            fields = [part.strip().upper() for part in line.split(",")]
            options = {}
            for field in fields[1:]:
                if field.count("=") != 1:
                    raise ValueError("Unexpected native INP keyword option")
                key, value = field.split("=")
                if not key or not value or key in options:
                    raise ValueError("Duplicate or malformed native INP keyword option")
                options[key.strip()] = value.strip()
            sections.append((fields[0], options, []))
        elif not sections:
            raise ValueError("Native INP content precedes a keyword")
        else:
            sections[-1][2].append(line)
    return sections


def _csv(line: str, count: int) -> list[str]:
    fields = [part.strip() for part in line.split(",")]
    if len(fields) != count or any(not part for part in fields):
        raise ValueError("Malformed native INP record")
    return fields


def _geometry(sections: list, *, mesh: bool) -> tuple[dict, dict, list]:
    nodes, elements, boundary = {}, {}, []
    element_ids = set()
    node_sections = 0
    for keyword, options, rows in sections:
        if keyword == "*NODE":
            node_sections += 1
            if options or node_sections != 1:
                raise ValueError("Duplicate or foreign native node section")
            for row in rows:
                fields = _csv(row, 4)
                node = _identifier(fields[0])
                if node in nodes:
                    raise ValueError("Duplicate native mesh node")
                nodes[node] = tuple(_number(token) for token in fields[1:])
        elif keyword == "*ELEMENT":
            kind, group = options.get("TYPE"), options.get("ELSET")
            if (set(options) != {"TYPE", "ELSET"} or not group or
                    not re.fullmatch(r"[A-Z][A-Z0-9_]*", group) or
                    kind not in (("T3D3", "CPS6", "C3D10") if mesh else ("C3D10",))):
                raise ValueError("Unexpected native mesh element definition")
            width = {"T3D3": 3, "CPS6": 6, "C3D10": 10}[kind]
            for row in rows:
                fields = _csv(row, width + 1)
                element, *ids = [_identifier(token) for token in fields]
                if element in element_ids or len(set(ids)) != width or any(node not in nodes for node in ids):
                    raise ValueError("Duplicate or foreign native element connectivity")
                element_ids.add(element)
                if kind == "C3D10":
                    elements[element] = tuple(ids)
                elif kind == "CPS6":
                    boundary.append({"element_id": element, "group": group,
                                     "type": kind, "node_ids": ids})
    if not nodes or not elements or set(nodes) != {node for ids in elements.values() for node in ids}:
        raise ValueError("Native geometry requires every mesh node in C3D10 connectivity")
    return nodes, elements, sorted(boundary, key=lambda row: row["element_id"])


def _face_key(ids: tuple | list) -> tuple:
    # A six-node membership alone misses swapped midside nodes. Bind each edge.
    edges = tuple(sorted((min(ids[a], ids[b]), max(ids[a], ids[b]), ids[mid])
                         for a, b, mid in ((0, 1, 3), (1, 2, 4), (2, 0, 5))))
    return tuple(sorted(ids[:3])), edges


def _exterior(elements: dict, boundary: list) -> set[int]:
    faces = {}
    for ids in elements.values():
        for slots in _FACES:
            face = tuple(ids[slot] for slot in slots)
            corners, edges = _face_key(face)
            if corners in faces and faces[corners][0] != edges:
                raise ValueError("C3D10 faces disagree on midside topology")
            old = faces.get(corners, (edges, 0))
            faces[corners] = edges, old[1] + 1
            if faces[corners][1] > 2:
                raise ValueError("Nonmanifold C3D10 exterior")
    expected = {(corners, edges) for corners, (edges, count) in faces.items() if count == 1}
    observed = [_face_key(row["node_ids"]) for row in boundary]
    if not observed or len(set(observed)) != len(observed) or set(observed) != expected:
        raise ValueError("CPS6 boundary does not match the complete C3D10 exterior")
    return {node for row in boundary for node in row["node_ids"]}


def request_complete_displacement(deck: Path, nodes: Mapping) -> None:
    """Change only one output request and insert one explicit output-only set."""
    if (not isinstance(nodes, Mapping) or not nodes or
            any(type(node) is not int or node <= 0 or not isinstance(xyz, (tuple, list)) or
                len(xyz) != 3 or any(type(v) not in (float, int) or not math.isfinite(v) for v in xyz)
                for node, xyz in nodes.items())):
        raise ValueError("Complete output requires verified mesh identifiers and coordinates")
    deck = Path(deck)
    original = _read_bytes(deck)
    text = _ascii(original)
    actual, _, _ = _geometry(_sections(text), mesh=False)
    if (actual.keys() != nodes.keys() or any(actual[node] != tuple(float(f"{v:.10g}") for v in xyz)
                                            for node, xyz in nodes.items())):
        raise ValueError("Output request deck differs from the verified serialized mesh")
    marker = "*NODE FILE, NSET=ROLLER_NODES\nU\n"
    material = "*MATERIAL, NAME=PRINT_INPUT\n"
    if (text.count(marker) != 1 or text.count(material) != 1 or
            sum(key == "*NODE FILE" for key, _, _ in _sections(text)) != 1 or
            "FIELD_ALL_NODES" in text):
        raise ValueError("Unexpected fixture output request structure")
    ids = sorted(nodes)
    nset = "*NSET, NSET=FIELD_ALL_NODES\n" + "".join(
        ", ".join(map(str, ids[index:index + 12])) + "\n" for index in range(0, len(ids), 12))
    modified = text.replace(material, nset + material, 1).replace(
        marker, "*NODE FILE, NSET=FIELD_ALL_NODES\nU\n", 1).encode("ascii")
    if _read_bytes(deck) != original:
        raise ValueError("Fixture deck changed during output request transformation")
    deck.write_bytes(modified)


def _deck(text: str, mesh_nodes: dict, mesh_elements: dict, boundary_nodes: set[int]) -> tuple[dict, list[int], list[dict]]:
    sections = _sections(text)
    nodes, elements, _ = _geometry(sections, mesh=False)
    if (elements != mesh_elements or nodes.keys() != mesh_nodes.keys() or
            any(nodes[node] != tuple(float(f"{v:.10g}") for v in xyz) for node, xyz in mesh_nodes.items())):
        raise ValueError("Serialized solver deck differs from the actual Gmsh geometry")
    sets, loads = {}, {}
    counts = Counter(keyword for keyword, _, _ in sections)
    required = {"*HEADING": 1, "*NODE": 1, "*ELEMENT": 1, "*NSET": 3, "*MATERIAL": 1,
                "*ELASTIC": 1, "*SOLID SECTION": 1, "*STEP": 1, "*STATIC": 1, "*BOUNDARY": 1,
                "*CLOAD": 1, "*NODE PRINT": 2, "*NODE FILE": 1, "*EL FILE": 1, "*END STEP": 1}
    if counts != required or sections[-1] != ("*END STEP", {}, []):
        raise ValueError("Fixture deck must retain one declared static step and output structure")
    material_index = next(index for index, (key, _, _) in enumerate(sections) if key == "*MATERIAL")
    step_index = next(index for index, (key, _, _) in enumerate(sections) if key == "*STEP")
    if any(index >= material_index for index, (key, _, _) in enumerate(sections) if key == "*NSET"):
        raise ValueError("Fixture node sets must precede the material")
    for index, (keyword, options, rows) in enumerate(sections):
        if keyword == "*NSET":
            name = options.get("NSET")
            if set(options) != {"NSET"} or name not in {"BASE_FIXED", "ROLLER_NODES", "FIELD_ALL_NODES"} or name in sets:
                raise ValueError("Unexpected fixture node set")
            ids = [_identifier(token.strip()) for row in rows for token in row.split(",")]
            if not ids or len(set(ids)) != len(ids) or not set(ids) <= nodes.keys():
                raise ValueError("Duplicate, missing or foreign fixture node-set member")
            sets[name] = set(ids)
        elif keyword == "*BOUNDARY":
            if options or rows != ["BASE_FIXED, 1, 3"] or index <= step_index:
                raise ValueError("Fixture field requires the actual fixed XYZ boundary")
        elif keyword == "*CLOAD":
            if options or index <= step_index:
                raise ValueError("Unexpected fixture concentrated load section")
            for row in rows:
                node, dof, token = _csv(row, 3)
                node = _identifier(node)
                force = _number(token)
                if dof != "3" or force >= 0 or node in loads or node not in nodes:
                    raise ValueError("Duplicate, foreign or changed fixture force vector")
                loads[node] = {"node_id": node, "force_N": [0.0, 0.0, force], "dof": 3, "force_token": token}
        elif keyword in ("*STEP", "*STATIC", "*END STEP"):
            if options or rows:
                raise ValueError("Fixture field requires the declared default single static increment")
        elif keyword in ("*NODE PRINT", "*NODE FILE", "*EL FILE"):
            expected = {"*NODE FILE": ({"NSET": "FIELD_ALL_NODES"}, ["U"]),
                        "*EL FILE": ({}, ["S"])}
            if keyword == "*NODE PRINT":
                if (options, rows) not in (({"NSET": "ROLLER_NODES"}, ["U"]), ({"NSET": "BASE_FIXED"}, ["RF"])):
                    raise ValueError("Fixture DAT requests must retain loaded U and fixed RF")
            elif (options, rows) != expected[keyword]:
                raise ValueError("Fixture native field output request changed")
    prints = [(options, rows) for key, options, rows in sections if key == "*NODE PRINT"]
    if prints != [({"NSET": "ROLLER_NODES"}, ["U"]), ({"NSET": "BASE_FIXED"}, ["RF"])]:
        raise ValueError("Fixture DAT output order changed")
    if (sets.keys() != {"BASE_FIXED", "ROLLER_NODES", "FIELD_ALL_NODES"} or
            sets["FIELD_ALL_NODES"] != nodes.keys() or set(loads) != sets["ROLLER_NODES"] or
            sets["BASE_FIXED"] & sets["ROLLER_NODES"] or
            not (sets["BASE_FIXED"] | sets["ROLLER_NODES"]) <= boundary_nodes):
        raise ValueError("Fixture complete-output, fixed or loaded set association is invalid")
    # The generator selects the bottom from mesh XYZ with exactly this tolerance.
    minimum = min(xyz[2] for xyz in mesh_nodes.values())
    if sets["BASE_FIXED"] != {node for node, xyz in mesh_nodes.items() if abs(xyz[2] - minimum) < 1e-4}:
        raise ValueError("Fixture fixed set differs from the actual mesh bottom")
    return nodes, sorted(sets["BASE_FIXED"]), [loads[node] for node in sorted(loads)]


def _saddle(text: str, loads: list[dict], boundary: list) -> None:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate saddle JSON association")
            result[key] = value
        return result
    try:
        data = json.loads(text, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite saddle JSON")))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Malformed saddle source JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("nodal_loads"), dict):
        raise ValueError("Saddle source must retain the actual nodal forces")
    native = {_identifier(key): value for key, value in data["nodal_loads"].items()}
    ids = [row["node_id"] for row in loads]
    faces = [row for row in boundary if row["group"] == data.get("surface_group")]
    surface_nodes = {node for row in faces for node in row["node_ids"]}
    source_ids = data.get("loaded_node_ids")
    if (not isinstance(source_ids, list) or any(type(node) is not int for node in source_ids) or
            set(native) != set(ids) or source_ids != ids or
            type(data.get("loaded_node_count")) is not int or data["loaded_node_count"] != len(ids) or
            type(data.get("face_count")) is not int or data["face_count"] != len(faces) or
            not faces or not set(ids) <= surface_nodes):
        raise ValueError("Saddle source node/group/face association differs from the deck")
    for row in loads:
        force = native[row["node_id"]]
        if type(force) not in (float, int) or not math.isfinite(force) or force >= 0 or float(f"{force:.12g}") != row["force_N"][2]:
            raise ValueError("Serialized CLOAD differs from the source saddle force")
    total = data.get("total_applied_force_N")
    expected = -math.fsum(native.values())
    if type(total) not in (float, int) or not math.isfinite(total) or abs(total - expected) > 64 * math.ulp(expected):
        raise ValueError("Saddle source total differs from its nodal forces")


def _frd_record(line: str, components: int) -> tuple[int, list[float], list[str]]:
    width = 13 + 12 * components
    if line[:3] != " -1" or len(line) != width:
        raise ValueError("Malformed native ASCII FRD vector record")
    node = _identifier(line[3:13].strip())
    tokens = [line[13 + 12 * axis:25 + 12 * axis].strip() for axis in range(components)]
    if any(not _FRD_NUMBER.fullmatch(token) for token in tokens):
        raise ValueError("Malformed native ASCII FRD component")
    return node, [_number(token) for token in tokens], tokens


def _printed_close(token: str, expected: float, *, reference_token: str | None = None) -> bool:
    value = _number(token)
    # Decimal exponent is the printed last-place exponent, not a percent gate.
    # E+00 on a printed zero does not grant a 1e-5 absolute allowance to a
    # small nonzero observation. Only actual float32 underflow can explain it.
    allowance = .51 * 10.0 ** Decimal(token).as_tuple().exponent if value else 0.0
    try:
        allowance += abs(struct.unpack("f", struct.pack("f", expected))[0] - expected)
    except (OverflowError, struct.error):
        return False
    if reference_token is not None:
        if _number(reference_token):
            allowance += .51 * 10.0 ** Decimal(reference_token.replace("D", "E")).as_tuple().exponent
    allowance += 32 * math.ulp(max(abs(value), abs(expected)))
    return abs(value - expected) <= allowance


def _frd(text: str, nodes: dict, elements: dict) -> dict:
    lines = text.splitlines()
    versions = [line for line in lines if re.match(r"\s*1UVERSION\b", line)]
    if len(versions) != 1 or not re.fullmatch(r"\s*1UVERSION\s+Version 2\.21\s*", versions[0]):
        raise ValueError("Fixture field requires native CalculiX 2.21 metadata")
    coordinates, topology, fields = {}, {}, {}
    index, step, header, ended = 0, None, None, False
    while index < len(lines):
        line = lines[index]
        parts = line.split()
        index += 1
        if not parts:
            if ended:
                raise ValueError("Content follows native FRD end marker")
            continue
        if parts[0] in ("2C", "3C"):
            if len(parts) != 3 or parts[2] != "1":
                raise ValueError("Fixture field requires current ASCII FRD geometry")
            count = _identifier(parts[1])
            if parts[0] == "2C":
                if coordinates or topology or fields or count != len(nodes):
                    raise ValueError("Duplicate or incomplete FRD mesh nodes")
                while index < len(lines) and lines[index].strip() != "-3":
                    node, xyz, tokens = _frd_record(lines[index], 3)
                    if node in coordinates or node not in nodes:
                        raise ValueError("Duplicate or foreign FRD mesh node")
                    if any(not _printed_close(token, expected) for token, expected in zip(tokens, nodes[node])):
                        raise ValueError("FRD coordinates differ from the actual serialized deck")
                    coordinates[node] = xyz
                    index += 1
                if coordinates.keys() != nodes.keys():
                    raise ValueError("Incomplete FRD mesh coordinates")
            else:
                if not coordinates or topology or fields or count != len(elements):
                    raise ValueError("Duplicate or incomplete FRD mesh elements")
                while index < len(lines) and lines[index].strip() != "-3":
                    row = lines[index]
                    if row[:3] != " -1" or len(row) != 28 or [row[a:b].strip() for a, b in ((13, 18), (18, 23), (23, 28))] != ["6", "0", "1"]:
                        raise ValueError("Fixture FRD requires native TET10 type6 material1")
                    element = _identifier(row[3:13].strip())
                    if element in topology or element not in elements or index + 1 >= len(lines):
                        raise ValueError("Duplicate, foreign or truncated FRD element")
                    continuation = lines[index + 1]
                    if continuation[:3] != " -2" or len(continuation) != 103:
                        raise ValueError("Incomplete native FRD TET10 connectivity")
                    ids = tuple(_identifier(continuation[3 + 10 * slot:13 + 10 * slot].strip()) for slot in range(10))
                    if ids != elements[element]:
                        raise ValueError("FRD C3D10 node order differs from the actual deck")
                    topology[element] = ids
                    index += 2
                if topology != elements:
                    raise ValueError("Incomplete FRD C3D10 topology")
            if index == len(lines):
                raise ValueError("Unterminated FRD geometry")
            index += 1
        elif parts[0] == "1PSTEP":
            if len(line) != 70 or not topology or step is not None or line[10:24].strip() or line[60:].strip():
                raise ValueError("Malformed FRD static step metadata")
            counter, increment, number = (_identifier(line[a:b].strip()) for a, b in ((24, 36), (36, 48), (48, 60)))
            if counter != len(fields) + 1 or increment != 1 or number != 1:
                raise ValueError("Fixture FRD must describe step1 increment1")
            step = counter
        elif parts[0] == "100CL":
            if (step is None or header is not None or len(line) != 75 or line[7:12].strip() != "101" or
                    _number(line[12:24].strip()) != 1.0 or _identifier(line[24:36].strip()) != len(nodes) or
                    line[36:58].strip() != "0" or line[58:63].strip() != "1" or
                    line[63:74].strip() or line[74] != "1"):
                raise ValueError("Fixture FRD static load parameter/coverage/encoding changed")
            header = True
        elif parts[0] == "-4":
            if (not header or len(parts) != 4 or parts[1] not in _LABELS or parts[1] in fields or
                    parts[2:] != [str(len(_LABELS[parts[1]])), "1"]):
                raise ValueError("Unexpected or duplicate native FRD field")
            name = parts[1]
            if name != ("DISP", "STRESS", "ERROR")[len(fields)]:
                raise ValueError("Native FRD field order changed")
            for label in _LABELS[name]:
                if index >= len(lines) or lines[index].split() != ["-5", *label.split()]:
                    raise ValueError("Native FRD component order or definition changed")
                index += 1
            records = {}
            while index < len(lines) and lines[index].strip() != "-3":
                node, vector, tokens = _frd_record(lines[index], {"DISP": 3, "STRESS": 6, "ERROR": 1}[name])
                if node in records or node not in nodes:
                    raise ValueError("Duplicate or foreign native FRD field node")
                records[node] = vector, tokens
                index += 1
            if index == len(lines) or records.keys() != nodes.keys():
                raise ValueError("Incomplete all-mesh-node native FRD field")
            fields[name] = records
            index += 1
            step = header = None
        elif parts == ["9999"]:
            if index != len(lines) or step is not None or header is not None:
                raise ValueError("Incomplete or trailing native FRD end marker")
            ended = True
        elif coordinates or line[:3] in (" -1", " -2", " -3", " -5"):
            raise ValueError("Unexpected native FRD content")
        elif not re.match(r"\s*1[CU]", line):
            raise ValueError("Unexpected native FRD preamble")
    if not ended or set(fields) != {"DISP", "STRESS", "ERROR"}:
        raise ValueError("Incomplete native fixture FRD fields/end marker")
    return fields["DISP"]


def _dat(text: str, loads: list[dict], fixed: list[int], displacements: dict) -> None:
    tables, current = {}, None
    step = increment = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if re.fullmatch(r"\s*S T E P\s+1\s*", line):
            step += 1
            continue
        if re.fullmatch(r"\s*INCREMENT\s+1\s*", line):
            increment += 1
            continue
        header = re.fullmatch(r"\s*(displacements \(vx,vy,vz\)|forces \(fx,fy,fz\)) for set (\w+) and time\s+(\S+)\s*", line)
        if header:
            name = "U" if header[1].startswith("displacements") else "RF"
            if name in tables or header[2] != {"U": "ROLLER_NODES", "RF": "BASE_FIXED"}[name] or _number(header[3]) != 1.0:
                raise ValueError("Duplicate, foreign-set or wrong-parameter fixture DAT table")
            tables[name] = {}
            current = name
            continue
        if current is None:
            raise ValueError("Unexpected fixture DAT content or step/increment")
        fields = line.split()
        if len(fields) != 4 or any(not _DAT_NUMBER.fullmatch(token) for token in fields[1:]):
            raise ValueError("Malformed fixture DAT vector")
        node = _identifier(fields[0])
        if node in tables[current]:
            raise ValueError("Duplicate fixture DAT observation")
        tables[current][node] = [_number(token) for token in fields[1:]], fields[1:]
    if (step != 1 or increment != 1 or list(tables) != ["U", "RF"] or
            tables["U"].keys() != {row["node_id"] for row in loads} or tables["RF"].keys() != set(fixed)):
        raise ValueError("Incomplete or misassociated fixture DAT observations")
    for node, (vector, tokens) in tables["U"].items():
        frd_vector, frd_tokens = displacements[node]
        if any(not _printed_close(frd_token, expected, reference_token=dat_token)
               for frd_token, expected, dat_token in zip(frd_tokens, vector, tokens)):
            raise ValueError("Native FRD loaded vector differs from the matching DAT observation")


def extract_fixture_field(folder: Path, *, mesh_index: int, mesh_size_max_mm: float,
                          parent_experiment_id: str, cad_revision: str, expected_inputs: dict) -> dict:
    """Read an immutable complete field; never infer U for an omitted native row."""
    check_id(parent_experiment_id)
    if (type(mesh_size_max_mm) not in (float, int) or not math.isfinite(mesh_size_max_mm) or mesh_size_max_mm <= 0 or
            not isinstance(cad_revision, str) or not re.fullmatch(r"[0-9a-f]{64}", cad_revision)):
        raise ValueError("Invalid fixture field experiment/mesh identity")
    paths = _paths(folder, mesh_index)
    data = {key: _read_bytes(path) for key, path in paths.items()}
    sources = {key: _source(paths[key], value) for key, value in data.items()}
    if (not isinstance(expected_inputs, dict) or expected_inputs.keys() != {"mesh", "deck", "saddle"} or
            any(sources[key] != expected_inputs[key] for key in expected_inputs)):
        raise ValueError("Fixture native inputs changed since the pre-execution binding")
    mesh_sections = _sections(_ascii(data["mesh"]))
    if any(key not in {"*HEADING", "*NODE", "*ELEMENT"} for key, _, _ in mesh_sections):
        raise ValueError("Unexpected Gmsh source definition")
    mesh_nodes, elements, boundary = _geometry(mesh_sections, mesh=True)
    boundary_nodes = _exterior(elements, boundary)
    nodes, fixed, loads = _deck(_ascii(data["deck"]), mesh_nodes, elements, boundary_nodes)
    _saddle(_ascii(data["saddle"]), loads, boundary)
    displacements = _frd(_ascii(data["frd"]), nodes, elements)
    _dat(_ascii(data["dat"]), loads, fixed, displacements)
    for key, path in paths.items():
        if _read_bytes(path) != data[key]:
            raise ValueError(f"Fixture source changed during field extraction: {key}")
    return {"schema_version": "1.0", "kind": "fixture_calculix_nodal_displacement",
            "backend": "fixture.calculix", "adapter_version": "5",
            "parent_experiment_id": parent_experiment_id, "cad_revision": cad_revision,
            "mesh_index": mesh_index, "mesh_size_max_mm": mesh_size_max_mm,
            "coordinate_frame": "SOLVER_GLOBAL_CARTESIAN", "position_unit": "mm",
            "displacement_unit": "mm", "force_unit": "N",
            "static": {"step": 1, "increment": 1, "load_parameter": 1.0},
            "coverage": "ALL_MESH_NODES", "qualification": "UNKNOWN", "engineering_valid": False,
            "nodes": [{"node_id": node, "position_mm": list(nodes[node]),
                       "displacement_mm": displacements[node][0], "displacement_tokens": displacements[node][1]}
                      for node in sorted(nodes)],
            "elements": [{"element_id": element, "type": "C3D10", "node_ids": list(elements[element])}
                         for element in sorted(elements)],
            "boundary_faces": boundary, "fixed_node_ids": fixed, "fixed_dofs": [1, 2, 3],
            "loads": loads, "node_count": len(nodes), "element_count": len(elements),
            "boundary_face_count": len(boundary), "sources": sources}
