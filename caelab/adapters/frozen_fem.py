"""Execute a retained FreeCAD FEM deck without importing FreeCAD or remeshing.

Admission is deliberately limited to one single-solid static linear C3D10
analysis with isotropic elasticity, Fixed supports and resolved nodal Force.
FRD provides displacement only; DAT totals are retained, never called nodal RF.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess

import numpy as np

from apps.desktop_pre.freeze_analysis import _deck, _deck_scope, _serialized_coordinate_close, CCX_FROM_NATIVE_TET10
from apps.desktop_post.prepare import write_vtu
from .fixture_field import _frd_record, _identifier, _number, _printed_close, _LABELS
from ..execution_control import run_owned_command, check_cancelled, ExecutionCancelled, ExecutionCleanupFailed
from ..storage import check_id, save_json

MAX_BYTES = 256 * 1024 ** 2
_FRD_LABELS = {**_LABELS, "PE": ("PE 1 1 0 0",), "TOSTRAIN": (
    "EXX 1 4 1 1", "EYY 1 4 2 2", "EZZ 1 4 3 3",
    "EXY 1 4 1 2", "EYZ 1 4 2 3", "EZX 1 4 3 1"),
    "FORC": ("F1 1 2 1 0", "F2 1 2 2 0", "F3 1 2 3 0", "ALL 1 2 0 0 1ALL")}


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _read(path, limit=MAX_BYTES):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError("Frozen input must be a regular local file")
    if path.stat().st_size > limit:
        raise ValueError("Frozen source exceeds admission size limit")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Frozen source changed or exceeds size limit")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Frozen source association changed during read")
    return data


def _relative(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or Path(value).anchor or PureWindowsPath(value).anchor
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise ValueError("Invalid frozen source relative path")
    return value


def _finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Frozen mesh needs finite numeric values")
    return float(value)


def _id(value):
    if type(value) is not int or value <= 0:
        raise ValueError("Frozen mesh needs positive native integer IDs")
    return value


def _mesh(mesh):
    if mesh.get("kind") != "freecad-fem-mesh" or str(mesh.get("schema_version")) != "1":
        raise ValueError("Unsupported frozen mesh contract")
    if mesh.get("units") != {"position": "mm", "displacement": "mm", "force": "N", "stress": "MPa"}:
        raise ValueError("Frozen native units differ from the admitted writer")
    nodes, elements, fixed, loads = {}, {}, set(), []
    for row in mesh["nodes"]:
        node = _id(row["node_id"])
        if node in nodes or len(row["position_mm"]) != 3:
            raise ValueError("Duplicate or invalid frozen node")
        nodes[node] = tuple(_finite(v) for v in row["position_mm"])
        native = row["native_position_mm"]
        if len(native) != 3 or any(not _serialized_coordinate_close(_finite(v), deck)
                                   for v, deck in zip(native, nodes[node])):
            raise ValueError("Frozen coordinates differ from the existing native mesh")
    if mesh.get("native_to_deck_slots") != list(CCX_FROM_NATIVE_TET10):
        raise ValueError("Frozen mesh must record the native C3D10 ordering rule")
    for row in mesh["elements"]:
        element = _id(row["element_id"])
        ids = tuple(_id(v) for v in row["node_ids"])
        native = tuple(_id(v) for v in row["native_node_ids"])
        if (element in elements or row["type"] != "C3D10" or len(ids) != 10 or len(set(ids)) != 10
                or len(native) != 10 or ids != tuple(native[s] for s in CCX_FROM_NATIVE_TET10)):
            raise ValueError("Invalid frozen ordered C3D10 element")
        elements[element] = ids
    if not nodes or not elements or set(nodes) != {n for ids in elements.values() for n in ids}:
        raise ValueError("Frozen mesh has foreign or unused nodes")
    for row in mesh["fixed_dofs"]:
        key = (_id(row["node_id"]), _id(row["component"]))
        if key in fixed or key[0] not in nodes or key[1] not in (1, 2, 3) or _finite(row["value_mm"]) != 0:
            raise ValueError("Invalid frozen Fixed DOF")
        fixed.add(key)
    if not fixed or any({d for n, d in fixed if n == node} != {1, 2, 3} for node, _ in fixed):
        raise ValueError("Only full XYZ Fixed nodes are supported")
    for row in mesh["loads"]:
        item = (_id(row["node_id"]), _id(row["component"]), _finite(row["force_N"]))
        if item[0] not in nodes or item[1] not in (1, 2, 3) or (item[:2] in fixed and item[2] != 0):
            raise ValueError("Invalid or constrained frozen load")
        loads.append(item)
    if not any(f != 0 for _, _, f in loads) or len({r[:2] for r in loads}) != len(loads):
        raise ValueError("Missing or duplicate frozen loads")
    return nodes, elements, fixed, loads


def _jacobian_gates(nodes, elements):
    # Same C3D10 Gauss-point derivative rule as run_structural_screen, without
    # importing its optional CadQuery meshing dependency into a frozen-deck run.
    coords = np.asarray([[nodes[n] for n in ids] for ids in elements.values()])
    dL = np.asarray([[-1, -1, -1], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
    shifted = coords - coords[:, :1, :]
    scales = np.ptp(coords, axis=1).max(axis=1)
    if not np.all(np.isfinite(scales)) or np.any(scales <= 0):
        raise ValueError("Degenerate native element coordinate scale")
    normalized = shifted / scales[:, None, None]
    minimum, minimum_scaled = math.inf, math.inf
    for corner in range(4):
        L = np.full(4, .1381966011250105)
        L[corner] = .5854101966249685
        deriv = np.empty((10, 3))
        for a in range(4):
            deriv[a] = (4 * L[a] - 1) * dL[a]
        for k, (a, b) in enumerate(((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)), 4):
            deriv[k] = 4 * (L[a] * dL[b] + L[b] * dL[a])
        determinants = np.linalg.det(np.einsum("nic,ir->ncr", normalized, deriv))
        minimum_scaled = min(minimum_scaled, float(determinants.min()))
        minimum = min(minimum, float((determinants * scales ** 3).min()))
    # Preserve the original/pinned upstream admission floor in native mm units.
    # Normalization adds a numerical guard; it does not replace that floor.
    if not math.isfinite(minimum) or minimum <= 1e-10:
        raise ValueError("Sampled C3D10 Jacobian is nonfinite or at/below 1e-10 mm^3")
    if minimum_scaled <= 256 * np.finfo(float).eps:
        raise ValueError("Nonpositive or numerically singular sampled C3D10 Jacobian")
    return {"minimum_sampled_jacobian_mm3": minimum, "minimum_scaled_sampled_jacobian": minimum_scaled}


def _gates(nodes, elements, fixed):
    quality = _jacobian_gates(nodes, elements)
    # Reuse native_structural_deck's six rigid-mode rows; gate each connected
    # mesh component so a detached unrestrained island cannot pass global rank.
    parent = {n: n for n in nodes}
    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    for ids in elements.values():
        for n in ids[1:]:
            parent[find(n)] = find(ids[0])
    components = {}
    for n in nodes:
        components.setdefault(find(n), []).append(n)
    if len(components) != 1:
        raise ValueError("Single-solid frozen scope requires one connected mesh")
    xyz = np.asarray(list(nodes.values()))
    origin, length = xyz.mean(axis=0), float(np.ptp(xyz, axis=0).max())
    rows = []
    for n, component in fixed:
        x, y, z = (np.asarray(nodes[n]) - origin) / length
        rows.append(([1, 0, 0, 0, z, -y], [0, 1, 0, -z, 0, x], [0, 0, 1, y, -x, 0])[component - 1])
    if np.linalg.matrix_rank(np.asarray(rows)) != 6:
        raise ValueError("Frozen Fixed DOFs leave unrestrained rigid-body modes")
    return {**quality, "rigid_body_constraint_rank": 6,
            "limitation": "Four C3D10 Gauss-point samples are not a proof over the entire element"}


def validate_snapshot(path):
    """Return manifest, mesh, exact pins and pre-run gates; never run a process."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("snapshot_path must be an absolute manifest path")
    raw = _read(path, 8 * 1024 ** 2)
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Frozen manifest must be an object")
    if manifest.get("kind") != "freecad-fem-frozen" or str(manifest.get("schema_version")) != "1":
        raise ValueError("Unsupported frozen Analysis manifest")
    check_id(manifest["id"])
    if manifest["shape"]["solid_count"] != 1 or manifest["material"]["law"] != "isotropic_linear_elastic":
        raise ValueError("Only single-solid isotropic elasticity is admitted")
    E, nu = _finite(manifest["material"]["young_modulus_MPa"]), _finite(manifest["material"]["poisson_ratio"])
    if E <= 0 or not -1 < nu < .5:
        raise ValueError("Invalid frozen isotropic elasticity")
    settings = manifest["solver"]["settings"]
    expected = {"AnalysisType": "static", "ModelSpace": "3D", "GeometricalNonlinearity": "linear",
                "MaterialNonlinearity": "linear", "SplitInputWriter": False}
    if any(settings.get(k) != v for k, v in expected.items()):
        raise ValueError("Only unsplit static linear native settings are admitted")
    kinds = [c["native_type"] for c in manifest["conditions"]]
    if not {"Fem::ConstraintFixed", "Fem::ConstraintForce"} <= set(kinds) or any(c not in {"Fem::ConstraintFixed", "Fem::ConstraintForce"} for c in kinds):
        raise ValueError("Unsupported frozen Analysis condition")
    if manifest["solver"].get("native_type") != "Fem::SolverCcxTools":
        raise ValueError("Frozen snapshot must retain its native CalculiX solver")
    entry = _relative(manifest["input_file"])
    if Path(entry).suffix.lower() != ".inp" or Path(entry).name != entry:
        raise ValueError("Native deck must have .inp extension")
    pins = {"snapshot.json": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}
    for row in manifest["files"]:
        relative = _relative(row["relative"])
        if relative in pins or type(row["bytes"]) is not int or row["bytes"] <= 0 or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"]):
            raise ValueError("Invalid or duplicate frozen file pin")
        data = _read(path.parent / relative)
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("Frozen input hash/size mismatch: " + relative)
        pins[relative] = {"bytes": row["bytes"], "sha256": row["sha256"]}
    expected = {"snapshot.json", "editable.FCStd", "mesh.json", entry}
    if manifest.get('editable_project') == 'editable.caepre':
        expected.add('editable.caepre')
    elif manifest.get('editable_project') is not None:
        raise ValueError('Unsupported retained editable project member')
    if set(pins) != expected or path.name != "snapshot.json":
        raise ValueError("Frozen snapshot requires exactly manifest, editable copy, mesh and unsplit deck")
    mesh = json.loads(_read(path.parent / "mesh.json").decode("utf-8"))
    nodes, elements, fixed, loads = _mesh(mesh)
    _deck_scope(path.parent / entry, manifest)
    dnodes, delements, dfixed, dloads = _deck(path.parent / entry)
    if (dnodes != {k: list(v) for k, v in nodes.items()} or delements != {k: list(v) for k, v in elements.items()}
            or dfixed != fixed or sorted(dloads) != sorted(loads)):
        raise ValueError("Frozen native deck differs from ordered mesh/Fixed/Force record")
    return manifest, mesh, pins, _gates(nodes, elements, fixed)


class FrdTruncatedEOF(ValueError):
    """A syntactically valid field prefix ended at physical EOF, not corruption.

    prefix_lines excludes the WHOLE incomplete increment, not just its last
    field, or only an EOF-truncated file terminator after complete fields.
    Only retained_prefix uses this signal to create a derived copy.
    Strict callers still receive a ValueError and never receive partial fields.
    """
    def __init__(self, message, prefix_lines, *, reason="incomplete_increment_at_eof"):
        super().__init__(message)
        self.prefix_lines = prefix_lines
        self.reason = reason


def read_frd(path, nodes, elements, *, contact_materials=None, contact_profile=None, require_contact=True,
             data=None, allow_missing_end=False):
    """Read native ASCII geometry and the last complete static displacement.

    Fixed-column records and component labels follow CalculiX 2.21 frd.c and
    frdheader.c. The loadcase counter counts fields, not increments; all fields
    of a given output increment share KODE and time. Known ancillary fields
    are checked and retained as source information, never qualified responses.
    data is a bounded in-memory reading copy. allow_missing_end admits ONLY an
    absent file terminator after complete fields; malformed fields remain errors.
    A torn file terminator signals its own strict derived-copy cutoff.
    """
    try:
        raw = _read(path) if data is None else data
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
            raise ValueError("FRD reading copy exceeds the bounded reader size")
        text = raw.decode("ascii").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise ValueError("Only ASCII CalculiX FRD is supported") from exc
    if "\r" in text or "\x00" in text:
        raise ValueError("Malformed ASCII FRD line encoding")
    lines, xyz, topology, fields = text.splitlines(), {}, {}, {}
    labels_by_name = dict(_FRD_LABELS)
    if contact_materials is not None:
        labels_by_name["CONTACT"] = tuple(name + " 1 1 0 0" for name in
            ("COPEN", "CSLIP1", "CSLIP2", "CPRESS", "CSHEAR1", "CSHEAR2"))
    frames, material_names, contact_tokens = [], {}, {}
    field_coverage = None
    if contact_profile is not None:
        if contact_materials is None or contact_profile.get('version') != 1 or not contact_profile.get('steps'):
            raise ValueError('Step-aware FRD requires the explicit retained contact profile')
    increment_start = None
    def eof(message):
        raise FrdTruncatedEOF(message, increment_start)

    def last_fragment(index):
        return index == len(lines) - 1 and not text.endswith("\n")

    def numeric_tail(row, width, records):
        # Only a SHORT, unterminated final record with valid completed tokens is
        # eligible. A short newline-terminated row, a bad number, foreign node,
        # duplicate or damage followed by another record is still corruption.
        if row in (" -", " -1"):
            return True
        if row[:3] != " -1" or len(row) >= 13 + 12 * width:
            return False
        if not re.fullmatch(r" *[0-9]*", row[3:13]):
            return False
        if len(row) < 13:
            return True
        node = _identifier(row[3:13].strip())
        if node not in nodes or node in records:
            raise ValueError("Foreign or duplicate FRD field node")
        for start in range(13, len(row), 12):
            token = row[start:start+12].strip()
            if start+12 <= len(row):
                _number(token)
            elif token and not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]*)(?:[EeDd][+-]?[0-9]*)?|[+-]", token):
                return False
        return True

    def retain_frame(*, at_eof=False):
        if contact_materials is not None:
            if "DISP" not in fields or require_contact and "CONTACT" not in fields:
                if at_eof:
                    eof("EOF before the complete final displacement/contact increment")
                raise ValueError("Incomplete contact frame: displacement and CONTACT are both required")
            frames.append({"static": {"step": active_step, "increment": increment, "load_parameter": parameter},
                           "load_parameter_token": parameter_token, "fields": fields,
                           "contact_tokens": contact_tokens})
    i, pending, header, ended = 0, None, None, False
    counter, increment, kode, parameter, parameter_token = 0, None, None, None, None
    active_step = None
    versions = [line.strip() for line in lines if line.strip().startswith("1UVERSION")]
    if len(versions) != 1 or not re.fullmatch(r"1UVERSION\s+Version 2\.\d+", versions[0]):
        raise ValueError("Missing or unsupported native CalculiX version metadata")
    if contact_materials is not None and versions[0].split("Version ")[1] != "2.22":
        raise ValueError("The contact reader profile requires CalculiX 2.22; raw output is retained")
    field_count = 0
    while i < len(lines):
        line = lines[i].rstrip()
        parts = line.split()
        i += 1
        if not parts:
            continue
        if ended:
            raise ValueError("Trailing FRD content after end marker")
        if line[4:9] == "1UMAT" and contact_materials is not None:
            material_index = _identifier(line[9:14].strip())
            material_name = line[14:72].strip()
            if (xyz or material_index in material_names or not material_name or
                    material_name not in contact_materials["names"]):
                raise ValueError("Invalid/duplicate native material identity")
            material_names[material_index] = material_name
        elif parts[0] in ("2C", "3C"):
            if len(parts) != 3 or parts[2] != "1":
                raise ValueError("Only native ASCII FRD geometry is supported")
            count = _identifier(parts[1])
            if parts[0] == "2C":
                if xyz or topology or field_count or count != len(nodes):
                    raise ValueError("Duplicate/incomplete FRD nodes")
                while i < len(lines) and lines[i].strip() != "-3":
                    n, vector, tokens = _frd_record(lines[i].rstrip(), 3)
                    if n in xyz or n not in nodes or any(not _printed_close(t, v) for t, v in zip(tokens, nodes[n])):
                        raise ValueError("FRD node identity/coordinates differ from native deck")
                    xyz[n] = vector
                    i += 1
                if set(xyz) != set(nodes):
                    raise ValueError("Incomplete FRD geometry")
            else:
                if not xyz or topology or field_count or count != len(elements):
                    raise ValueError("Duplicate/incomplete FRD elements")
                while i < len(lines) and lines[i].strip() != "-3":
                    row = lines[i].rstrip()
                    if (row[:3] != " -1" or len(row) != 28 or
                            [row[a:b].strip() for a, b in ((13,18),(18,23))] != ["6","0"] or
                            (contact_materials is None and row[23:28].strip() != "1")):
                        raise ValueError("Only native FRD TET10 material1 is supported")
                    e = _identifier(row[3:13].strip())
                    if contact_materials is not None:
                        material_index = _identifier(row[23:28].strip())
                        if (set(material_names.values()) != set(contact_materials["names"]) or
                                material_names.get(material_index) != contact_materials["elements"].get(e)):
                            raise ValueError("FRD element material differs from retained body section")
                    if e in topology or e not in elements or i + 1 >= len(lines):
                        raise ValueError("Foreign/duplicate/truncated FRD element")
                    row = lines[i + 1].rstrip()
                    if row[:3] != " -2" or len(row) != 103:
                        raise ValueError("Malformed FRD connectivity")
                    ids = tuple(_identifier(row[3+10*j:13+10*j].strip()) for j in range(10))
                    if ids != tuple(elements[e]):
                        raise ValueError("FRD ordered connectivity differs from native deck")
                    topology[e] = ids
                    i += 2
                if set(topology) != set(elements):
                    raise ValueError("Incomplete FRD elements")
            if i == len(lines):
                raise ValueError("Unterminated FRD geometry")
            i += 1
        elif parts[0] == "1PSTEP":
            if last_fragment(i-1) and len(line) < 60 and re.fullmatch(r"\s*1PSTEP[ 0-9]*", line):
                # An incomplete step header cannot certify a new increment; keep
                # only the previously closed increment prefix conservatively.
                eof("EOF within a native FRD step header")
            row = line.ljust(70)
            if not topology or pending is not None or header is not None or len(line) > 70 or row[10:24].strip() or row[60:].strip():
                raise ValueError("Malformed FRD step")
            count, inc, step = (_identifier(row[a:b].strip()) for a,b in ((24,36),(36,48),(48,60)))
            if (count != counter + 1 or
                    (contact_profile is None and step != 1) or
                    (contact_profile is not None and not 1 <= step <= len(contact_profile['steps'])) or
                    (active_step is not None and (step, inc) < (active_step, increment))):
                raise ValueError("FRD requires ordered fields in the retained steps")
            if (step, inc) != (active_step, increment):
                increment_start = i - 1
            pending = (count, inc, step)
        elif parts[0] == "100CL":
            if (pending is not None and header is None and last_fragment(i-1) and len(line) < 75
                    and re.fullmatch(r"\s*100CL[ 0-9EeDd+.\-]*", line)):
                eof("EOF within a native FRD field header")
            if pending is None or header is not None or len(line) != 75:
                raise ValueError("Malformed FRD static field header")
            output_inc = _identifier(line[58:63].strip())
            count_token = line[24:36].strip()
            if contact_materials is not None:
                if not re.fullmatch(r"0|[1-9][0-9]*", count_token):
                    raise ValueError("Invalid declared native field coverage")
                field_coverage = int(count_token)
            else:
                field_coverage = _identifier(count_token)
            mode = '1' if contact_profile is not None and contact_profile['steps'][pending[2]-1]['procedure']=='dynamic' else '0'
            if (line[7:12].strip() != str(100 + output_inc)
                    or not 0 <= field_coverage <= len(nodes)
                    or (contact_materials is None and field_coverage != len(nodes)) or line[36:58].strip() != mode
                    or line[63:74].strip() or line[74] != "1"):
                raise ValueError("FRD static mode/coverage/encoding differs")
            token = line[12:24].strip()
            value = _number(token)
            if value < 0 or value == 0 and mode != '1':
                raise ValueError("Invalid static FRD load parameter")
            inc, native_step = pending[1], pending[2]
            if increment is not None:
                if (native_step, inc) == (active_step, increment):
                    if output_inc != kode or value != parameter:
                        raise ValueError("FRD fields describe different load parameters within an increment")
                elif output_inc <= kode or value <= parameter or "DISP" not in fields:
                    raise ValueError("Incomplete or unordered static FRD output increments")
            if (native_step, inc) != (active_step, increment):
                if increment is not None:
                    retain_frame()
                fields = {}
                contact_tokens = {}
            active_step, increment, kode, parameter, parameter_token = native_step, inc, output_inc, value, token
            header = True
        elif parts[0] == "-4":
            if header is not None and last_fragment(i-1):
                fragment = " ".join(parts)
                candidates = [f"-4 {name} {len(labels)} 1" for name, labels in labels_by_name.items()
                              if name not in fields]
                if any(candidate != fragment and candidate.startswith(fragment) for candidate in candidates):
                    eof("EOF within a native FRD field definition")
            if header is None or len(parts) != 4 or parts[1] not in labels_by_name or parts[1] in fields:
                raise ValueError("Unexpected or duplicate FRD field")
            name, labels = parts[1], labels_by_name[parts[1]]
            if parts[2:] != [str(len(labels)), "1"]:
                raise ValueError("Malformed FRD field definition")
            for label in labels:
                if i >= len(lines):
                    eof("EOF within native FRD component labels")
                if lines[i].split() != ["-5", *label.split()]:
                    if last_fragment(i) and ("-5 " + label).startswith(" ".join(lines[i].split())):
                        eof("EOF within a native FRD component label")
                    raise ValueError("FRD component meaning/order differs")
                i += 1
            records = {}
            width = {"DISP":3, "FORC":3, "STRESS":6, "TOSTRAIN":6, "PE":1, "ERROR":1, "CONTACT":6}[name]
            while i < len(lines) and lines[i].strip() != "-3":
                raw_record = lines[i].rstrip()
                if last_fragment(i) and numeric_tail(raw_record, width, records):
                    if len(records) >= field_coverage and raw_record != " -":
                        raise ValueError("FRD records exceed declared coverage before EOF")
                    eof("EOF within a native FRD field record")
                if name == "CONTACT":
                    if raw_record[:3] != " -1" or len(raw_record) != 13 + 12*width:
                        raise ValueError("Malformed native CONTACT record")
                    n = _identifier(raw_record[3:13].strip())
                    tokens = [raw_record[13+12*j:25+12*j].strip() for j in range(width)]
                    values = []
                    for token in tokens:
                        try:
                            values.append(_number(token))
                        except ValueError:
                            if not re.fullmatch(r"[-+]?([Nn][Aa][Nn]|[Ii][Nn][Ff](inity)?)|\*+", token):
                                raise ValueError("Malformed CONTACT value")
                            values.append(None)  # Raw token retained; never a synthetic zero.
                    contact_tokens[n] = tokens
                else:
                    n, values, tokens = _frd_record(raw_record, width)
                if n in records or n not in nodes:
                    raise ValueError("Foreign or duplicate FRD field node")
                records[n] = values
                i += 1
            if i == len(lines):
                if len(records) > field_coverage:
                    raise ValueError("FRD records exceed declared coverage before EOF")
                eof("EOF before native FRD field terminator")
            if (len(records) != field_coverage or
                    (name != "CONTACT" and set(records) != set(nodes))):
                raise ValueError("Incomplete FRD field relative to declared coverage")
            fields[name] = records
            i += 1
            counter, field_count = pending[0], field_count + 1
            pending, header = None, None
        elif parts == ["9999"]:
            if pending is not None or header is not None:
                raise ValueError("Incomplete FRD end marker")
            ended = True
        elif last_fragment(i-1) and line.strip() in ("9", "99", "999"):
            if pending is not None or header is not None:
                raise ValueError("Incomplete FRD end marker")
            # Derive a strict copy ending BEFORE the torn terminator, preserving
            # all complete fields for the usual required-field/STA checks.
            raise FrdTruncatedEOF("EOF within a native FRD file terminator", i-1,
                                  reason="partial_end_marker_at_eof")
        elif xyz or not re.match(r"\s*1[CU]", line):
            if (last_fragment(i-1) and topology and any(marker.startswith(line.strip())
                    for marker in ("1PSTEP", "100CL", "-4", "9999"))):
                eof("EOF within a native FRD record marker")
            raise ValueError("Unexpected native FRD content")
    if pending is not None or header is not None:
        eof("EOF before a complete native FRD field")
    if (not ended and not allow_missing_end) or "DISP" not in fields:
        raise ValueError("Missing complete final FRD displacement/end marker")
    retain_frame(at_eof=not ended and allow_missing_end)
    return {**({"frames": frames} if contact_materials is not None else {}), "displacements": fields["DISP"], "frd_coordinates_mm": xyz,
            "elements": topology, "static": {"step":active_step, "increment":increment, "load_parameter":parameter},
            "load_parameter_token":parameter_token, "final_fields":sorted(fields), "field_count":field_count,
            "native_version": versions[0].split("Version ")[1]}


class FrozenFemCalculixAdapter:
    backend = "structure.calculix.frozen"
    version = "1"

    def run(self, settings, *, output, runtime=None):
        if not isinstance(settings, dict) or set(settings) - {"snapshot_path", "data_id"} or "snapshot_path" not in settings:
            raise ValueError("Frozen FEM settings require only snapshot_path and optional data_id")
        if runtime:
            raise ValueError("Frozen CalculiX uses ccx on configured PATH; runtime overrides unsupported")
        if not isinstance(settings["snapshot_path"], str):
            raise ValueError("snapshot_path must be an absolute path string")
        if "data_id" in settings:
            check_id(settings["data_id"])
        output = Path(output).absolute()
        if any(p.is_symlink() for p in (output, *output.parents)):
            raise ValueError("Output must be a new regular directory")
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise ValueError("Frozen run refuses an existing nonempty output directory")
        result = {"execution_status":"REJECTED", "responses":{}, "checks":[],
                  "qualification":"UNKNOWN", "decision":"NOT_RELEASED", "engineering_valid":False,
                  "diagnostics":{}, "artifacts":[]}
        try:
            source = Path(settings["snapshot_path"])
            manifest, mesh, pins, gates = validate_snapshot(source)
            retained = output / "frozen_input"
            retained.mkdir()
            for relative, pin in pins.items():
                target = retained / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source.parent / relative, target)
                if target.stat().st_size != pin["bytes"] or _sha(target) != pin["sha256"]:
                    raise ValueError("Frozen input changed during capture")
            validate_snapshot(retained / "snapshot.json")
            result.update(snapshot_id=manifest["id"], data_id=settings.get("data_id"), input_pins=pins,
                          checks=[{"name":"frozen_mesh_admission", "status":"PASS", **gates}])
            result["execution_status"] = "FAILED"
            check_cancelled()
            command = shutil.which("ccx")
            if not command:
                raise RuntimeError("CalculiX requires ccx on configured PATH")
            executable = Path(command).resolve(strict=True)
            binary_hash = _sha(executable)
            result["runtime"] = {"executable":str(executable), "sha256":binary_hash,
                                 "configuration":"configured PATH", "build_identity":"UNKNOWN"}
            native = output / "solver"
            native.mkdir()
            deck = native / manifest["input_file"]
            shutil.copyfile(retained / manifest["input_file"], deck)
            result["execution_status"] = "FAILED"
            check_cancelled()
            solved = run_owned_command([str(executable), "-i", deck.stem], native, "ccx_frozen")
            if solved.returncode:
                raise RuntimeError("CalculiX failed; owned logs and raw outputs retained")
            check_cancelled()
            for relative, pin in pins.items():
                if (_sha(source.parent / relative) != pin["sha256"] or _sha(retained / relative) != pin["sha256"]):
                    raise ValueError("Frozen input changed during execution")
            if _sha(deck) != pins[manifest["input_file"]]["sha256"] or _sha(executable) != binary_hash:
                raise ValueError("Native deck/executable changed during execution")
            nodes, elements, fixed, loads = _mesh(mesh)
            observed = read_frd(deck.with_suffix(".frd"), nodes, elements)
            if not _printed_close(observed["load_parameter_token"], _deck_scope(deck, manifest)):
                raise ValueError("FRD is not the retained final static load parameter")
            raw = {"kind":"frozen_fem_nodal_displacement", "schema_version":"1", "snapshot_id":manifest["id"],
                   "coordinate_frame":"FREECAD_DOCUMENT_GLOBAL", "position_unit":"mm", "displacement_unit":"mm",
                   "coverage":"ALL_MESH_NODES", "qualification":"UNKNOWN", "engineering_valid":False,
                   "static":observed["static"], "source":{"relative":"solver/" + deck.with_suffix(".frd").name,
                   "sha256":_sha(deck.with_suffix(".frd"))}, "input_pins":pins,
                   "nodes":[{"node_id":n,"position_mm":list(nodes[n]),"frd_position_mm":observed["frd_coordinates_mm"][n],
                             "displacement_mm":observed["displacements"][n]} for n in sorted(nodes)],
                   "elements":mesh["elements"], "fixed_node_ids":sorted({n for n,d in fixed}), "loads":mesh["loads"]}
            post = output / "post"
            post.mkdir()
            save_json(post / "displacement.json", raw)
            write_vtu(post / "displacement.vtu", raw)
            vectors = [row["displacement_mm"] for row in raw["nodes"]]
            metadata = {"node_ids":sorted(nodes), "coordinates_mm":[list(nodes[n]) for n in sorted(nodes)],
                        "coordinate_frame":raw["coordinate_frame"], "position_unit":"mm", "association":"POINTS",
                        "snapshot_id":manifest["id"], "static":observed["static"], "source":"solver/" + deck.with_suffix(".frd").name,
                        "coverage":"ALL_MESH_NODES", "interpolated":False}
            result["responses"] = {"displacement":{"kind":"field","unit":"mm","value":vectors,
                                    "component":"VECTOR","location":"native_nodes","reduction":"none","metadata":metadata}}
            for axis, name in enumerate(("UX", "UY", "UZ")):
                result["responses"][name] = {"kind":"field","unit":"mm","value":[v[axis] for v in vectors],
                    "component":name,"location":"native_nodes","reduction":"none","metadata":metadata}
            result["responses"]["max_displacement"] = {"kind":"scalar","unit":"mm", "value":max(math.hypot(*v) for v in vectors),
                "component":"VECTOR_MAGNITUDE","location":"all_native_nodes","reduction":"max", "metadata":metadata}
            # The native reader receives the writer's explicit declarations with
            # its registered bytes, never units inferred from array-name suffixes.
            arrays = [{"name":"U_mm", "association":"POINTS", "components":3,
                       "component_names":["UX","UY","UZ"], "units":"mm",
                       "frame":raw["coordinate_frame"], "measure":"displacement"}]
            arrays += [{"name":name, "association":"POINTS", "components":1, "units":"mm",
                        "frame":raw["coordinate_frame"], "measure":"displacement"}
                       for name in ("UX_mm", "UY_mm", "UZ_mm", "U_magnitude_mm")]
            arrays += [{"name":name, "association":association, "components":1, "units":"1",
                        "frame":"not_applicable", "measure":measure}
                       for name, association, measure in (("NativeNodeId","POINTS","identity"),
                           ("NativeElementId","CELLS","identity"), ("FixedXYZ_input","POINTS","input_classification"),
                           ("LoadedNode_input","POINTS","input_classification"))]
            native_metadata = {"coordinate_units":"mm", "coordinate_frame":raw["coordinate_frame"],
                               "static":observed["static"], "arrays":arrays}
            result.update(execution_status="SUCCEEDED", native_version=observed["native_version"],
                          final_native_fields=observed["final_fields"],
                          post_artifact={"relative":"post/displacement.vtu","bytes":(post / "displacement.vtu").stat().st_size,
                                         "sha256":_sha(post / "displacement.vtu"), "native_metadata":native_metadata})
        except ExecutionCleanupFailed:
            raise
        except ExecutionCancelled as exc:
            result.update(execution_status="CANCELLED", responses={}, diagnostics={"reason":str(exc)})
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            result["responses"] = {}
            result["diagnostics"] = {"type":type(exc).__name__, "reason":str(exc)}
        result["limitations"] = ["Final complete step1 ASCII FRD displacement only",
            "Stress, strain and reaction totals are raw output, not qualified responses",
            "No physical acceptance, remesh, FreeCAD execution or nonlinear analysis"]
        result["artifacts"] = [{"relative":p.relative_to(output).as_posix(), "bytes":p.stat().st_size,"sha256":_sha(p)}
                               for p in sorted(output.rglob("*")) if p.is_file() and not p.is_symlink()]
        save_json(output / "frozen_execution.json", result)
        return result


# Public generic name; keep the backend-specific name for existing registry use.
FrozenFemAdapter = FrozenFemCalculixAdapter
