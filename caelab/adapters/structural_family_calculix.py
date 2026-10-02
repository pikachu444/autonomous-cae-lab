"""Bounded linear structural families using native CalculiX 2.21 C3D20.

References, response selection and numerical limits belong to the domain. This
adapter checks the actual input/FRD topology and every native U/RF/S/COORD row.
RF is the internal nodal force, so a restrained reaction excludes the CLOAD
actually serialized on that component. Native point numbers are not cross-solver
identities: positions use checked input coordinates and the documented rule.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import struct
import subprocess
import sys

from plugins.structural_families import reference as _domain
from . import structural_family_mesh as _mesh
from .. import execution_control as _execution
from ..storage import save_json


_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_FILES = (Path(__file__).resolve(), Path(_domain.__file__).resolve(),
                 Path(_mesh.__file__).resolve(),
                 _ROOT / "benchmarks/specifications/structural-families-v1.json",
                 _ROOT / "caelab/storage.py", Path(_execution.__file__).resolve())
_SOURCE_BYTES = {path: path.read_bytes() for path in _SOURCE_FILES}
_SOURCE_HASHES = {path: hashlib.sha256(data).hexdigest() for path, data in _SOURCE_BYTES.items()}
_PENDING = ["static_strength", "material_qualification", "physical_validation",
            "fatigue_durability", "model_qualification", "original_midas_replication"]
_TIMEOUT = 240
_MAX_FILE_BYTES = 64 * 1024 ** 2
_FLOAT = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?\Z")
_INTEGER = re.compile(r"[1-9]\d*\Z")
# Official ccx_2.21.src.tar.bz2: gauss.f gauss3d3; printoutint.f uses it
# for both S and COORD. The native loop has x fastest, y middle, z outer.
_G = 0.774596669241483
CCX_GAUSS27 = tuple((x, y, z) for z in (-_G, 0.0, _G)
                   for y in (-_G, 0.0, _G) for x in (-_G, 0.0, _G))
# frd.c's ASCII 20-node brick output puts vertical midsides before top midsides.
FRD_FROM_C3D20 = (*range(12), *range(16, 20), *range(12, 16))
_RULES = {
    "source_url": "https://www.dhondt.de/ccx_2.21.src.tar.bz2",
    "source_archive_sha256": "52a20ef7216c6e2de75eae460539915640e3140ec4a2f631a9301e01eda605ad",
    "force_basis": "resultsmech.f internal fn; printoutnode.f RF exports fn; reaction = RF - serialized CLOAD on restrained DOFs only",
    "stress_order": ["xx", "yy", "zz", "xy", "xz", "yz"],
    "stress_basis": "printout.f / printoutint.f global S, all 27 gauss3d3 points of full C3D20",
    "point_coordinates": "Computed from checked native input mesh and documented gauss.f quadrature; independently corroborated by every native COORD row",
    "point_order": "x fastest, y middle, z outer; native POINT is not a cross-solver identifier",
    "frd_topology_basis": "frd.c HEX20 type4: canonical slots1..12,17..20,13..16",
    "serialization_relative_bound": 6e-14,
    "dat_format": "printoutnode.f / printoutint.f E13.6: seven significant digits",
    "frd_format": "frd.c / frdvector.c / frdselect.c E12.5: six significant digits with native float casts",
    "precision_policy": "Format-rounding and float-cast allowances verify native identity only; domain numerical limits are unchanged",
}
_FRD_ABI = {"format": "ELF64_SYSV_X86_64", "byte_order": "little",
            "id_bytes": 4, "real_bytes": 8, "real_format": "IEEE754_binary64"}
_DOUBLE_RULES = {**_RULES,
    "frd_format": "frd.c / frdvector.c / frdselect.c dbi: native C int32 IDs and IEEE754 binary64 mesh/U/RF/nodal S/optional ERROR, without float casts",
    "primary_displacement_basis": "Measured native DOUBLE-FRD DISP at the same catalogue nodes; DAT U corroborates seven-significant-digit rounding",
    "force_basis": "Measured native DOUBLE-FRD FORC internal fn; reaction = RF - serialized CLOAD on restrained DOFs only; DAT RF corroborates seven-significant-digit rounding",
    "binary_abi_basis": "Observed executable ELF64 little-endian EM_X86_64 and Linux host ABI; SysV AMD64 scalar C int32/double64. Unsupported ABIs are refused, not guessed",
}
_FRD_LABELS = {
    "DISP": ["D1 1 2 1 0", "D2 1 2 2 0", "D3 1 2 3 0", "ALL 1 2 0 0 1ALL"],
    "FORC": ["F1 1 2 1 0", "F2 1 2 2 0", "F3 1 2 3 0", "ALL 1 2 0 0 1ALL"],
    "STRESS": ["SXX 1 4 1 1", "SYY 1 4 2 2", "SZZ 1 4 3 3", "SXY 1 4 1 2", "SYZ 1 4 2 3", "SZX 1 4 3 1"],
    "ERROR": ["STR(%) 1 1 0 0"],
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 ** 2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture_sources(output: Path) -> dict:
    files = {}
    for source, data in _SOURCE_BYTES.items():
        if not source.is_file() or _sha(source) != _SOURCE_HASHES[source]:
            raise RuntimeError("Structural source changed since import; no native work is admitted")
        key = source.relative_to(_ROOT).as_posix()
        captured = output / "source_snapshot" / key
        captured.parent.mkdir(parents=True, exist_ok=True)
        captured.write_bytes(data)
        files[key] = {"sha256": _SOURCE_HASHES[source],
                      "artifact": "simulation/source_snapshot/" + key}
    _assert_sources(output)
    return files


def _assert_sources(output: Path) -> None:
    for source, expected in _SOURCE_HASHES.items():
        captured = output / "source_snapshot" / source.relative_to(_ROOT)
        if (not source.is_file() or not captured.is_file() or
                _sha(source) != expected or _sha(captured) != expected):
            raise RuntimeError("Structural source/snapshot drift; retained evidence cannot be mixed")


def _observed_frd_abi(executable: Path) -> dict:
    """Admit one observed native ABI; FRD does not carry an endian marker."""
    with executable.open("rb") as stream:
        header = stream.read(64)
    if (len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01" or header[7] not in (0, 3)
            or int.from_bytes(header[16:18], "little") not in (2, 3)
            or int.from_bytes(header[18:20], "little") != 62
            or int.from_bytes(header[20:24], "little") != 1
            or int.from_bytes(header[52:54], "little") != 64
            or sys.platform != "linux" or platform.machine().lower() != "x86_64"
            or sys.byteorder != "little" or struct.calcsize("@i") != 4 or struct.calcsize("@d") != 8
            or sys.float_info.mant_dig != 53 or sys.float_info.max_exp != 1024):
        raise RuntimeError("DOUBLE-FRD requires the observed Linux ELF64 little-endian x86-64 int32/double64 ABI")
    return deepcopy(_FRD_ABI)


def _runtime_identity() -> dict:
    command = shutil.which("ccx")
    if not command:
        raise RuntimeError("CalculiX runtime requires ccx on the configured PATH")
    executable = Path(command).resolve(strict=True)
    if not executable.is_file():
        raise RuntimeError("CalculiX command does not resolve to a regular executable")
    return {"executable": str(executable), "sha256": _sha(executable),
            "frd_abi": _observed_frd_abi(executable),
            "required_version": "2.21", "expected_binary_sha256": None,
            "binary_admission": "Actual PATH executable hash frozen for this run; no preconfigured expected binary SHA",
            "native_binary_build_source_identity": "UNKNOWN"}


def _process(command: list[str], output: Path, label: str, *, timeout: int = _TIMEOUT) -> str:
    """Retain partial logs and stop only this owned group on cancel/interruption."""
    if type(timeout) is not int or not 0 < timeout <= _TIMEOUT:
        raise ValueError("Native process exceeds the fixed timeout budget")
    save_json(output / f"{label}.command.json", {"argv": command,
              "cwd": str(output.resolve()), "timeout_seconds": timeout})
    with (output / f"{label}.stdout.log").open("wb") as stdout, \
            (output / f"{label}.stderr.log").open("wb") as stderr:
        try:
            _execution.check_cancelled()
        except _execution.ExecutionCancelled:
            save_json(output / f"{label}.exit.json", {"returncode": None, "timed_out": False,
                      "cancelled": True, "reason": "USER_REQUEST"})
            raise
        try:
            process = subprocess.Popen(command, cwd=output.resolve(), stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr,
                                       start_new_session=os.name == "posix")
        except OSError as exc:
            stderr.write(f"{type(exc).__name__}: {exc}\n".encode("utf-8"))
            save_json(output / f"{label}.exit.json", {"returncode": None, "timed_out": False,
                      "cancelled": False, "start_error": type(exc).__name__})
            raise RuntimeError("CalculiX process could not start; native logs retained") from exc

        def stop_owned(reason: str, *, timed_out: bool, exception_type: str | None = None) -> None:
            try:
                _execution.stop_owned_process(process, isolated_group=os.name == "posix")
            except _execution.ExecutionCleanupFailed:
                state = {"returncode": process.returncode, "timed_out": timed_out,
                         "cancelled": False, "cleanup_pending": True,
                         "reason": "GROUP_CLEANUP_UNCONFIRMED", "original_reason": reason,
                         "termination": "UNKNOWN"}
                if exception_type is not None:
                    state["exception_type"] = exception_type
                save_json(output / f"{label}.exit.json", state)
                raise

        try:
            _execution.wait_for_process(process, timeout=timeout)
        except _execution.ExecutionCancelled:
            stop_owned("USER_REQUEST", timed_out=False)
            save_json(output / f"{label}.exit.json", {"returncode": process.returncode,
                      "timed_out": False, "cancelled": True, "reason": "USER_REQUEST"})
            raise
        except subprocess.TimeoutExpired as exc:
            stop_owned("WALL_TIME_BUDGET", timed_out=True)
            save_json(output / f"{label}.exit.json", {"returncode": process.returncode,
                      "timed_out": True, "cancelled": False, "reason": "WALL_TIME_BUDGET"})
            raise RuntimeError("CalculiX process timed out; partial native evidence retained") from exc
        except BaseException as exc:
            stop_owned("INTERRUPTED", timed_out=False, exception_type=type(exc).__name__)
            save_json(output / f"{label}.exit.json", {"returncode": process.returncode,
                      "timed_out": False, "cancelled": False, "reason": "INTERRUPTED",
                      "exception_type": type(exc).__name__})
            raise
    save_json(output / f"{label}.exit.json", {"returncode": process.returncode, "timed_out": False,
              "cancelled": False})
    # The actual Ubuntu 2.21 executable returns201 for its metadata-only -v
    # query. Admit only that exact banner/query; solver jobs remain zero-only.
    version_query_exit = (process.returncode == 201 and label == "ccx_version"
                          and len(command) == 2 and command[1] == "-v"
                          and _read(output / f"{label}.stdout.log").strip() == "This is Version 2.21"
                          and not _read(output / f"{label}.stderr.log").strip())
    if process.returncode != 0 and not version_query_exit:
        raise RuntimeError(f"CalculiX {label} exited {process.returncode}; native logs retained")
    return "\n".join(_read(output / f"{label}.{stream}.log") for stream in ("stdout", "stderr"))


def _read(path: Path) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError("Native artifact is missing, linked, or exceeds the bounded parser size")
    return path.read_text(encoding="ascii", errors="strict")


def _number(token: str) -> float:
    if not _FLOAT.fullmatch(token):
        raise ValueError("Malformed native numeric field")
    value = float(token.replace("D", "E").replace("d", "e"))
    if not math.isfinite(value):
        raise ValueError("Nonfinite native numeric field")
    return value


def _identifier(token: str) -> int:
    if not _INTEGER.fullmatch(token):
        raise ValueError("Malformed native identifier")
    return int(token)


def _vector(value: object) -> list[float]:
    if (not isinstance(value, list) or len(value) != 3 or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in value)):
        raise ValueError("Catalogue requires three finite components")
    return [float(x) for x in value]


def _catalogue(mesh: dict) -> tuple[dict, dict, dict, dict]:
    if not isinstance(mesh, dict) or mesh.get("schema_version") != "1" or mesh.get("element_type") != "HEXA20":
        raise ValueError("Only the checked full HEXA20 catalogue is admitted")
    rows, cells = mesh.get("nodes"), mesh.get("elements")
    if (not isinstance(rows, list) or not 20 <= len(rows) <= 10000 or
            not isinstance(cells, list) or not 1 <= len(cells) <= 1024):
        raise ValueError("Incomplete or unbounded structural catalogue")
    nodes, elements = {}, {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("id")) is not int or not 1 <= row["id"] <= 10000 or row["id"] in nodes:
            raise ValueError("Duplicate, missing or unbounded catalogue node ID")
        nodes[row["id"]] = _vector(row.get("coordinates_mm"))
    if len({tuple(value) for value in nodes.values()}) != len(nodes):
        raise ValueError("Duplicate catalogue node coordinates")
    for row in cells:
        if not isinstance(row, dict) or type(row.get("id")) is not int or not 1 <= row["id"] <= 1024 or row["id"] in elements:
            raise ValueError("Duplicate, missing or unbounded catalogue element ID")
        ids = row.get("node_ids")
        if (not isinstance(ids, list) or len(ids) != 20 or
                any(type(node) is not int or node not in nodes for node in ids) or len(set(ids)) != 20):
            raise ValueError("Incomplete canonical C3D20 connectivity")
        elements[row["id"]] = list(ids)
    if {node for ids in elements.values() for node in ids} != nodes.keys():
        raise ValueError("Every catalogue node must belong to a volume element")
    groups = mesh.get("groups")
    if not isinstance(groups, dict) or set(groups.get("ALL_NODES", [])) != nodes.keys():
        raise ValueError("Catalogue requires an exact ALL_NODES group")
    for name, ids in groups.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", name) or name == "SOLID" or
                not isinstance(ids, list) or not ids or any(type(n) is not int or n not in nodes for n in ids) or
                len(set(ids)) != len(ids)):
            raise ValueError("Malformed, duplicate or unknown catalogue group node")
    supports = mesh.get("supports")
    if not isinstance(supports, list) or not supports:
        raise ValueError("Missing restrained-DOF catalogue")
    masks = {}
    for row in supports:
        if (not isinstance(row, dict) or type(row.get("node_id")) is not int or
                row["node_id"] not in nodes or row["node_id"] in masks):
            raise ValueError("Duplicate or unknown support node")
        axes = row.get("components")
        if (not isinstance(axes, list) or not axes or
                any(type(axis) is not int or axis not in (1, 2, 3) for axis in axes) or len(set(axes)) != len(axes)):
            raise ValueError("Duplicate or invalid restrained component")
        masks[row["node_id"]] = set(axes)
    loads = {}
    if not isinstance(mesh.get("nodal_loads_n"), list):
        raise ValueError("Missing complete nodal load catalogue")
    for row in mesh["nodal_loads_n"]:
        if (not isinstance(row, dict) or type(row.get("node_id")) is not int or
                row["node_id"] not in nodes or row["node_id"] in loads):
            raise ValueError("Duplicate or unknown load node")
        loads[row["node_id"]] = _vector(row.get("value"))
    if loads.keys() != nodes.keys():
        raise ValueError("Nodal loads must retain every node, including zero and negative weights")
    return nodes, elements, masks, loads


def parse_input_mesh(path: Path, mesh: dict) -> dict[int, list[float]]:
    """Check the actual native include, including continuations and all groups."""
    expected, expected_elements, _, _ = _catalogue(mesh)
    nodes, elements, groups = {}, {}, {}
    section, pending = None, []
    for line in _read(path).splitlines():
        line = line.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            if pending:
                raise ValueError("Incomplete native element continuation")
            parts = [item.strip().upper() for item in line.split(",")]
            if parts == ["*NODE"]:
                section = "nodes"
            elif set(parts) == {"*ELEMENT", "TYPE=C3D20", "ELSET=SOLID"} and len(parts) == 3:
                section = "elements"
            elif len(parts) == 2 and parts[0] == "*NSET" and parts[1].startswith("NSET="):
                section = parts[1][5:]
                if section in groups:
                    raise ValueError("Duplicate native node group")
                groups[section] = []
            else:
                raise ValueError("Unsupported native mesh keyword or reduced integration element")
            continue
        fields = [value.strip() for value in (line[:-1] if line.endswith(",") else line).split(",")]
        if len(fields) > 16:
            raise ValueError("Native mesh row exceeds the verified 16 input fields")
        if section == "nodes":
            if len(fields) != 4 or any(len(value) > 20 for value in fields[1:]):
                raise ValueError("Native node row exceeds the verified 20-character input fields")
            node = _identifier(fields[0])
            if node in nodes:
                raise ValueError("Duplicate native input node")
            nodes[node] = [_number(value) for value in fields[1:]]
        elif section == "elements":
            pending.extend(_identifier(value) for value in fields)
            if len(pending) > 21:
                raise ValueError("Extra native element connectivity")
            if len(pending) == 21:
                if pending[0] in elements:
                    raise ValueError("Duplicate native input element")
                elements[pending[0]] = pending[1:]
                pending = []
        elif section in groups:
            groups[section].extend(_identifier(value) for value in fields)
        else:
            raise ValueError("Native data occurs outside a declared mesh section")
    if pending or elements != expected_elements or nodes.keys() != expected.keys():
        raise ValueError("Native input topology does not match the source catalogue")
    if groups.keys() != mesh["groups"].keys() or any(
            len(ids) != len(set(ids)) or set(ids) != set(mesh["groups"][name]) for name, ids in groups.items()):
        raise ValueError("Native input groups do not match the source catalogue")
    if any(abs(x - y) > 6e-14 * abs(y) for node, xyz in nodes.items()
           for x, y in zip(xyz, expected[node])):
        raise ValueError("Native input coordinates exceed the declared serialization bound")
    return nodes


def _deck(mesh: dict, declaration: dict, path: Path) -> dict[int, list[float]]:
    _, _, masks, loads = _catalogue(mesh)
    material = declaration["model"]["materials"][0]
    young, poisson = material["youngs_modulus"], material["poisson_ratio"]
    if (young.get("unit") != "MPa" or poisson.get("unit") != "1" or
            type(young.get("value")) not in (int, float) or not math.isfinite(young["value"]) or young["value"] <= 0 or
            type(poisson.get("value")) not in (int, float) or not math.isfinite(poisson["value"]) or not 0 <= poisson["value"] < .49):
        raise ValueError("Domain declaration lacks trusted isotropic MPa material")
    lines = ["** Shared checked HEXA20 catalogue; full C3D20 integration.", "*INCLUDE,INPUT=mesh.inc",
             "*MATERIAL,NAME=DECLARED", "*ELASTIC", f"{young['value']:.13g},{poisson['value']:.13g}",
             "*SOLID SECTION,ELSET=SOLID,MATERIAL=DECLARED", "*STEP", "*STATIC", "*BOUNDARY"]
    lines += [f"{node},{axis},{axis},0" for node in sorted(masks) for axis in sorted(masks[node])]
    lines.append("*CLOAD")
    serialized = {}
    for node in sorted(loads):
        tokens = [f"{value:.13g}" for value in loads[node]]
        if any(len(token) > 20 for token in tokens):
            raise ValueError("CLOAD exceeds the verified 20-character numeric field")
        serialized[node] = [_number(token) for token in tokens]
        if any(abs(x - y) > 6e-13 * abs(y) for x, y in zip(serialized[node], loads[node])):
            raise ValueError("CLOAD serialization changed a declared component")
        lines += [f"{node},{axis},{token}" for axis, token in enumerate(tokens, 1) if serialized[node][axis - 1] != 0]
    lines += ["*NODE PRINT,NSET=ALL_NODES,GLOBAL=YES", "U,RF",
              "*EL PRINT,ELSET=SOLID,GLOBAL=YES", "S,COORD",
              "*NODE FILE,NSET=ALL_NODES,GLOBAL=YES,DOUBLE", "U,RF", "*EL FILE,GLOBAL=YES,DOUBLE",
              "S", "*END STEP"]
    with path.open("x", encoding="ascii", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    return serialized


_DAT_HEADERS = {
    "displacements (vx,vy,vz)": ("U", "ALL_NODES", 3, False),
    "forces (fx,fy,fz)": ("RF", "ALL_NODES", 3, False),
    "stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz)": ("S", "SOLID", 6, True),
    "global coordinates (elem, integ.pnt.,x,y,z)": ("COORD", "SOLID", 3, True),
}
_DAT_HEADER = re.compile(r"^\s*(.*?)\s+for set\s+(\S+)\s+and time\s+(\S+)\s*$")


def parse_dat(path: Path, mesh: dict) -> dict:
    nodes, elements, _, _ = _catalogue(mesh)
    tables, current = {}, None
    preamble = 0
    for line in _read(path).splitlines():
        if not line.strip():
            continue
        if re.fullmatch(r"\s*S\s+T\s+E\s+P\s+1\s*", line):
            if preamble or current is not None or tables:
                raise ValueError("Duplicate or misplaced native DAT step")
            preamble = 1
            continue
        if re.fullmatch(r"\s*INCREMENT\s+1\s*", line):
            if preamble != 1 or current is not None or tables:
                raise ValueError("Duplicate or misplaced native DAT increment")
            preamble = 2
            continue
        header = _DAT_HEADER.fullmatch(line)
        if header:
            if preamble == 1:
                raise ValueError("Incomplete native DAT step/increment metadata")
            descriptor, group, time = header.groups()
            if descriptor not in _DAT_HEADERS:
                raise ValueError("Unexpected native DAT table/component order")
            name, expected_group, size, integration = _DAT_HEADERS[descriptor]
            if name in tables or group != expected_group or _number(time) != 1.0:
                raise ValueError("Duplicate, foreign-set or wrong-time native DAT table")
            current = name, size, integration
            tables[name] = {}
            continue
        if current is None:
            raise ValueError("Unexpected native DAT content")
        name, size, integration = current
        fields = line.split()
        offset = 2 if integration else 1
        if len(fields) != size + offset:
            raise ValueError("Incomplete or extra native DAT row")
        identifier = _identifier(fields[0])
        key = (identifier, _identifier(fields[1])) if integration else identifier
        if key in tables[name]:
            raise ValueError("Duplicate native DAT row")
        tables[name][key] = [_number(token) for token in fields[offset:]]
    expected_points = {(element, point) for element in elements for point in range(1, 28)}
    if set(tables) != {"U", "RF", "S", "COORD"} or any(
            tables[name].keys() != (expected_points if name in ("S", "COORD") else nodes.keys())
            for name in tables):
        raise ValueError("Native DAT requires all nodes and exactly27 points per C3D20 element")
    return tables


def _printed_close(actual: float, expected: float, digits: int, *, float32: bool = False,
                   reference_digits: int | None = None) -> bool:
    """Half a printed decimal quantum, plus documented native float conversion."""
    scale = max(abs(actual), abs(expected))
    if scale == 0:
        return True
    quantum = 10.0 ** (math.floor(math.log10(scale)) - digits + 1)
    allowance = .51 * quantum + 32 * math.ulp(scale)
    if reference_digits is not None:
        allowance += .51 * 10.0 ** (math.floor(math.log10(scale)) - reference_digits + 1)
    if float32:
        allowance += 2 ** -23 * abs(expected)
    return abs(actual - expected) <= allowance


def _frd_row(line: str, components: int) -> tuple[int, list[float]]:
    if line[:3] != " -1" or len(line) < 13 + 12 * components or line[13 + 12 * components:].strip():
        raise ValueError("Malformed native ASCII FRD row")
    identifier = _identifier(line[3:13].strip())
    return identifier, [_number(line[13 + 12 * i:25 + 12 * i].strip()) for i in range(components)]


def _parse_ascii_frd(path: Path, mesh: dict, native_nodes: dict, dat: dict) -> dict:
    """Check ASCII FRD topology and complete nodal fields, preserving raw FRD."""
    nodes, elements, _, _ = _catalogue(mesh)
    lines = _read(path).splitlines()
    versions = [line for line in lines if re.match(r"\s*1UVERSION\b", line)]
    if len(versions) != 1 or not re.fullmatch(r"\s*1UVERSION\s+Version 2\.21\s*", versions[0]):
        raise ValueError("FRD must retain the exact native CalculiX2.21 version metadata")
    coordinates, topology, fields = {}, {}, {}
    step = header = None
    index, ended = 0, False
    while index < len(lines):
        line = lines[index]
        parts = line.split()
        index += 1
        if not parts:
            continue
        if parts[0] in ("2C", "3C"):
            if len(parts) != 3 or parts[2] != "1":
                raise ValueError("Only complete ASCII FRD mesh blocks are admitted")
            count = _identifier(parts[1])
            if parts[0] == "2C":
                if coordinates or topology or fields or count != len(nodes):
                    raise ValueError("Duplicate or mismatched FRD node block")
                while index < len(lines) and lines[index].strip() != "-3":
                    node, xyz = _frd_row(lines[index], 3)
                    if node in coordinates:
                        raise ValueError("Duplicate FRD mesh node")
                    coordinates[node] = xyz
                    index += 1
                if coordinates.keys() != nodes.keys():
                    raise ValueError("Incomplete FRD mesh coordinates")
            else:
                if not coordinates or topology or fields or count != len(elements):
                    raise ValueError("Duplicate or mismatched FRD element block")
                while index < len(lines) and lines[index].strip() != "-3":
                    row = lines[index]
                    if row[:3] != " -1" or len(row) < 28 or row[28:].strip():
                        raise ValueError("Malformed FRD element header")
                    element = _identifier(row[3:13].strip())
                    if row[13:18].strip() != "4" or row[18:23].strip() != "0" or row[23:28].strip() != "1" or element in topology:
                        raise ValueError("FRD requires unique native HEX20 type4 elements with declared material")
                    connectivity = []
                    for continuation in lines[index + 1:index + 3]:
                        if continuation[:3] != " -2" or len(continuation) < 103 or continuation[103:].strip():
                            raise ValueError("Incomplete FRD HEX20 connectivity continuation")
                        connectivity += [_identifier(continuation[3 + 10 * j:13 + 10 * j].strip()) for j in range(10)]
                    if len(connectivity) != 20:
                        raise ValueError("Incomplete FRD HEX20 element")
                    canonical = [None] * 20
                    for native, slot in zip(connectivity, FRD_FROM_C3D20):
                        canonical[slot] = native
                    topology[element] = canonical
                    index += 3
                if topology != elements:
                    raise ValueError("FRD native topology does not match the checked C3D20 source")
            if index == len(lines):
                raise ValueError("Unterminated FRD mesh block")
            index += 1
        elif parts[0] == "1PSTEP":
            if len(line) < 60 or not topology or step is not None:
                raise ValueError("Malformed FRD step metadata")
            counter, increment, number = (_identifier(line[a:b].strip()) for a, b in ((24, 36), (36, 48), (48, 60)))
            if counter != len(fields) + 1 or increment != 1 or number != 1:
                raise ValueError("FRD does not describe the declared single linear increment")
            step = counter
        elif parts[0] == "100CL":
            if step is None or header is not None or len(line) != 75:
                raise ValueError("Malformed FRD result metadata")
            if (_number(line[12:24].strip()) != 1.0 or _identifier(line[24:36].strip()) != len(nodes) or
                    line[7:12].strip() != "101" or line[58:63].strip() != "1" or line[74] != "1"):
                raise ValueError("FRD result time/coverage/increment/encoding differs from the input")
            header = True
        elif parts[0] == "-4":
            labels = _FRD_LABELS
            if (len(parts) != 4 or not header or parts[1] not in labels or parts[1] in fields or
                    parts[2] != str(len(labels[parts[1]])) or parts[3] != "1"):
                raise ValueError("Unexpected or duplicate FRD field")
            name = parts[1]
            for label in labels[name]:
                if index >= len(lines) or lines[index].split() != ["-5", *label.split()]:
                    raise ValueError("FRD component order differs from the documented native field")
                index += 1
            values = {}
            while index < len(lines) and lines[index].strip() != "-3":
                node, value = _frd_row(lines[index], 6 if name == "STRESS" else 1 if name == "ERROR" else 3)
                if node in values:
                    raise ValueError("Duplicate FRD field node")
                values[node] = value
                index += 1
            if index == len(lines) or values.keys() != nodes.keys():
                raise ValueError("Incomplete native FRD field")
            fields[name] = values
            index += 1
            step = header = None
        elif parts == ["9999"]:
            if index != len(lines) or step is not None:
                raise ValueError("Unexpected data after FRD end marker")
            ended = True
        elif coordinates or line[:3] in (" -1", " -2", " -3", " -5"):
            raise ValueError("Unexpected native FRD content")
        # Before 2C, official 1C/1U metadata is retained but not a field proof.
    if not ended or set(fields) not in ({"DISP", "FORC", "STRESS"}, {"DISP", "FORC", "STRESS", "ERROR"}):
        raise ValueError("Native FRD requires complete displacement/force/nodal-stress fields and end marker")
    if any(not _printed_close(value, expected, 6, float32=True) for node, xyz in coordinates.items()
           for value, expected in zip(xyz, native_nodes[node])):
        raise ValueError("FRD native coordinates differ from the actual input mesh")
    for name, native in (("DISP", "U"), ("FORC", "RF")):
        if any(not _printed_close(value, expected, 6, float32=True, reference_digits=7)
               for node, row in fields[name].items() for value, expected in zip(row, dat[native][node])):
            raise ValueError("FRD native field differs from the matching DAT observation")
    return {"coordinates_mm": coordinates, "elements_c3d20": topology,
            "nodal_averaged_stress_native_order": fields["STRESS"],
            "nodal_averaged_stress_components": ["xx", "yy", "zz", "xy", "yz", "zx"],
            "native_stress_error_estimate_percent": fields.get("ERROR"),
            "native_error_scope": "Optional native extrapolation estimator; not measured reference error or linear residual"}


class _BinaryFRDReader:
    """ASCII headers occur only at known boundaries, never within binary rows."""

    def __init__(self, data: bytes):
        self.data, self.offset = data, 0

    def line(self) -> str:
        end = self.data.find(b"\n", self.offset, self.offset + 257)
        if end < 0:
            raise ValueError("Missing, truncated or unbounded native FRD header")
        row = self.data[self.offset:end]
        if any(byte < 32 or byte > 126 for byte in row):
            raise ValueError("Non-ASCII native FRD header at a binary boundary")
        self.offset = end + 1
        return row.decode("ascii")

    def row(self, pattern: struct.Struct) -> tuple:
        if self.offset + pattern.size > len(self.data):
            raise ValueError("Truncated native DOUBLE-FRD payload")
        values = pattern.unpack_from(self.data, self.offset)
        self.offset += pattern.size
        return values


def _frd_bytes(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError("Native artifact is missing, linked, or exceeds the bounded parser size")
    with path.open("rb") as stream:
        data = stream.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        raise ValueError("Native artifact exceeds the bounded parser size")
    return data


def _binary_mesh_header(line: str, name: str, count: int, encoding: str) -> None:
    if (len(line) != 74 or line[:6] != "    " + name or line[6:24].strip()
            or _identifier(line[24:36].strip()) != count or line[36:].strip() != encoding):
        raise ValueError("Native DOUBLE-FRD mesh count/encoding differs from the checked catalogue")


def _binary_node_rows(reader: _BinaryFRDReader, nodes: dict, components: int) -> dict:
    pattern = struct.Struct("<i" + "d" * components)
    values = {}
    for _ in range(len(nodes)):
        node, *row = reader.row(pattern)
        if node not in nodes or node in values:
            raise ValueError("Duplicate or foreign native DOUBLE-FRD node ID")
        if not all(math.isfinite(value) for value in row):
            raise ValueError("Nonfinite native DOUBLE-FRD component")
        values[node] = row
    if values.keys() != nodes.keys():
        raise ValueError("Incomplete native DOUBLE-FRD field")
    return values


def _parse_double_frd(data: bytes, mesh: dict, native_nodes: dict, dat: dict, native_abi: dict | None) -> dict:
    if native_abi != _FRD_ABI:
        raise ValueError("Native DOUBLE-FRD requires the observed supported ABI; byte order is never guessed")
    nodes, elements, _, _ = _catalogue(mesh)
    if native_nodes.keys() != nodes.keys():
        raise ValueError("Native DOUBLE-FRD input node identities are incomplete")
    reader = _BinaryFRDReader(data)
    if reader.line().strip() != "1C":
        raise ValueError("Native DOUBLE-FRD requires the computational header")
    metadata = []
    # Exact 2.21 frd.c preamble for one declared material. These are retained
    # metadata, not a claim that the installed binary was built from that source.
    for tag in ("USER", "DATE", "TIME", "HOST", "PGM", "VERSION", "COMPILETIME", "DIR", "DBN", "MAT"):
        line = reader.line()
        prefix = "    1U" + tag
        if not line.startswith(prefix) or (len(line) > len(prefix) and line[len(prefix)] != " "):
            raise ValueError("Unexpected, duplicate or missing native DOUBLE-FRD metadata")
        value = line[len(prefix):].strip()
        if ((tag == "VERSION" and value != "Version 2.21")
                or (tag == "PGM" and value != "CalculiX")
                or (tag == "MAT" and not re.fullmatch(r"1\s*DECLARED", value))):
            raise ValueError("Native DOUBLE-FRD version/program/material metadata is foreign")
        metadata.append(line)
    _binary_mesh_header(reader.line(), "2C", len(nodes), "3")
    coordinates = _binary_node_rows(reader, nodes, 3)
    if any(not math.isfinite(expected) or abs(value - expected) > 32 * math.ulp(max(abs(value), abs(expected)))
           for node, xyz in coordinates.items() for value, expected in zip(xyz, native_nodes[node])):
        raise ValueError("Native DOUBLE-FRD coordinates differ from the actual input mesh")
    _binary_mesh_header(reader.line(), "3C", len(elements), "2")
    topology = {}
    pattern = struct.Struct("<24i")
    for _ in range(len(elements)):
        element, kind, group, material, *connectivity = reader.row(pattern)
        if element not in elements or element in topology or (kind, group, material) != (4, 0, 1):
            raise ValueError("Native DOUBLE-FRD requires unique checked HEX20 type4/material1 elements")
        canonical = [None] * 20
        for native, slot in zip(connectivity, FRD_FROM_C3D20):
            canonical[slot] = native
        topology[element] = canonical
    if topology != elements:
        raise ValueError("Native DOUBLE-FRD topology differs from the checked C3D20 catalogue")
    fields = {}
    while True:
        step = reader.line()
        if step.strip() == "9999":
            if reader.offset != len(data):
                raise ValueError("Extra bytes after native DOUBLE-FRD end marker")
            break
        if (len(step) != 70 or step[:10] != "    1PSTEP" or step[10:24].strip() or step[60:].strip()
                or [_identifier(step[a:b].strip()) for a, b in ((24, 36), (36, 48), (48, 60))]
                != [len(fields) + 1, 1, 1]):
            raise ValueError("Native DOUBLE-FRD step differs from the single linear increment")
        header = reader.line()
        if (len(header) != 75 or header[:7] != "  100CL" or header[7:12].strip() != "101"
                or _number(header[12:24].strip()) != 1.0 or _identifier(header[24:36].strip()) != len(nodes)
                or header[36:56].strip() or header[56:58].strip() != "0"
                or header[58:63].strip() != "1" or header[63:74].strip() or header[74] != "3"):
            raise ValueError("Native DOUBLE-FRD time/coverage/linear kind/encoding differs from the input")
        parts = reader.line().split()
        if (len(parts) != 4 or parts[0] != "-4" or parts[1] not in _FRD_LABELS or parts[1] in fields
                or parts[2] != str(len(_FRD_LABELS[parts[1]])) or parts[3] != "1"
                or len(fields) >= 4 or parts[1] != ("DISP", "STRESS", "FORC", "ERROR")[len(fields)]):
            raise ValueError("Unexpected, duplicate or reordered native DOUBLE-FRD field")
        name = parts[1]
        for label in _FRD_LABELS[name]:
            if reader.line().split() != ["-5", *label.split()]:
                raise ValueError("Native DOUBLE-FRD component order differs from the documented field")
        fields[name] = _binary_node_rows(reader, nodes, 6 if name == "STRESS" else 1 if name == "ERROR" else 3)
    if set(fields) not in ({"DISP", "STRESS", "FORC"}, {"DISP", "STRESS", "FORC", "ERROR"}):
        raise ValueError("Native DOUBLE-FRD requires complete U/RF/nodal stress fields")
    for name, native in (("DISP", "U"), ("FORC", "RF")):
        if any(not _printed_close(printed, actual, 7)
               for node, row in fields[name].items() for actual, printed in zip(row, dat[native][node])):
            raise ValueError("Native DOUBLE-FRD field exceeds matching DAT E13.6 rounding")
    return {"coordinates_mm": coordinates, "elements_c3d20": topology,
            "nodal_averaged_stress_native_order": fields["STRESS"],
            "nodal_averaged_stress_components": ["xx", "yy", "zz", "xy", "yz", "zx"],
            "native_stress_error_estimate_percent": fields.get("ERROR"),
            "native_error_scope": "Optional native extrapolation estimator; not measured reference error or linear residual",
            "native_displacements_mm": fields["DISP"], "native_internal_forces_n": fields["FORC"],
            "encoding": {"name": "CalculiX2.21_DOUBLE_FRD", "abi": deepcopy(native_abi),
                         "coordinate_code": 3, "topology_code": 2, "result_code": 3,
                         "nodal_precision": "binary64 without native float cast",
                         "DAT_corroboration": "Every U/RF component within E13.6 rounding; DAT is not the primary U/RF basis"},
            "computational_metadata": metadata}


def parse_frd(path: Path, mesh: dict, native_nodes: dict, dat: dict, *,
              native_abi: dict | None = None, require_double: bool = False) -> dict:
    """Retain strict historical ASCII replay; new decks explicitly require dbi."""
    data = _frd_bytes(path)
    prefix = _BinaryFRDReader(data)
    for _ in range(32):
        parts = prefix.line().split()
        if parts and parts[0] == "2C":
            if len(parts) == 3 and parts[2] == "3":
                return _parse_double_frd(data, mesh, native_nodes, dat, native_abi)
            if require_double or parts != ["2C", str(len(_catalogue(mesh)[0])), "1"]:
                raise ValueError("Fresh native output requires DOUBLE-FRD, not ASCII/float32 or foreign encoding")
            return _parse_ascii_frd(path, mesh, native_nodes, dat)
    raise ValueError("Native FRD lacks the bounded mesh preamble")


def _cross(x: list[float], force: list[float]) -> list[float]:
    return [x[1] * force[2] - x[2] * force[1], x[2] * force[0] - x[0] * force[2],
            x[0] * force[1] - x[1] * force[0]]


def _resultant(rows: list[list[float]]) -> list[float]:
    return [math.fsum(row[axis] for row in rows) for axis in range(3)]


def parse_fields(folder: Path, mesh: dict, serialized_loads: dict, native_nodes: dict, *,
                 native_abi: dict | None = None, require_double: bool = False) -> tuple[dict, dict]:
    nodes, elements, masks, declared_loads = _catalogue(mesh)
    if serialized_loads.keys() != nodes.keys() or native_nodes.keys() != nodes.keys():
        raise ValueError("Native input identities are incomplete")
    loads = {node: _vector(value) for node, value in serialized_loads.items()}
    native_nodes = {node: _vector(value) for node, value in native_nodes.items()}
    if any(abs(x - y) > 6e-14 * abs(y) for node, row in native_nodes.items() for x, y in zip(row, nodes[node])):
        raise ValueError("Native input coordinates differ from the checked catalogue")
    if any(abs(x - y) > 6e-13 * abs(y) for node, row in loads.items() for x, y in zip(row, declared_loads[node])):
        raise ValueError("Serialized CLOAD differs from the checked catalogue")
    dat = parse_dat(folder / "family.dat", mesh)
    if any(dat["U"][node][axis - 1] != 0 for node, axes in masks.items() for axis in axes):
        raise ValueError("Native displacement violates the declared zero restrained component")
    frd = parse_frd(folder / "family.frd", mesh, native_nodes, dat,
                    native_abi=native_abi, require_double=require_double)
    double = "encoding" in frd
    u = frd["native_displacements_mm"] if double else dat["U"]
    rf = frd["native_internal_forces_n"] if double else dat["RF"]
    if any(u[node][axis - 1] != 0 for node, axes in masks.items() for axis in axes):
        raise ValueError("Native displacement violates the declared zero restrained component")
    stresses = []
    for element in sorted(elements):
        coordinates = [native_nodes[node] for node in elements[element]]
        positions = []
        for point, local in enumerate(CCX_GAUSS27, 1):
            position = _vector(_mesh.hexa20_point_coordinates(coordinates, local))
            if any(not _printed_close(actual, expected, 7) for actual, expected in zip(dat["COORD"][(element, point)], position)):
                raise ValueError("Native COORD does not match the documented C3D20 quadrature/order")
            positions.append(tuple(position))
            stresses.append({"element_id": element, "point_id": point, "coordinates_mm": position,
                             "components_mpa": dat["S"][(element, point)]})
        if len(set(positions)) != 27:
            raise ValueError("Native integration-point coordinates are duplicated")
    reaction = {node: [rf[node][axis] - loads[node][axis] if axis + 1 in masks.get(node, set()) else 0.0
                       for axis in range(3)] for node in sorted(nodes)}
    applied_force = _resultant(list(loads.values()))
    applied_moment = _resultant([_cross(native_nodes[node], loads[node]) for node in nodes])
    reaction_force = _resultant(list(reaction.values()))
    reaction_moment = _resultant([_cross(native_nodes[node], reaction[node]) for node in nodes])
    order = sorted(nodes)
    record = {"cells": list(mesh["cells"]), "node_ids": order,
              "coordinates_mm": [nodes[node] for node in order], "displacements_mm": [u[node] for node in order],
              "reaction_n": reaction_force, "reaction_moment_n_mm": reaction_moment,
              "applied_force_n": applied_force, "applied_moment_n_mm": applied_moment,
              "stress_points": stresses, "element_count": len(elements),
              "field_completeness": {"displacement": True, "stress": True, "reaction": True, "native_mesh": True},
              "native_fields_artifact": "simulation/" + folder.name + "/family.frd"}
    metadata = {"rules": deepcopy(_DOUBLE_RULES if double else _RULES), "node_ids": order,
                "native_input_coordinates_mm": [native_nodes[node] for node in order],
                "raw_internal_forces_n": [rf[node] for node in order],
                "serialized_cload_n": [loads[node] for node in order],
                "restrained_component_masks": [[axis + 1 in masks.get(node, set()) for axis in range(3)] for node in order],
                "reaction_by_node_n": [reaction[node] for node in order],
                "native_mesh_and_nodal_stress": frd,
                "native_coordinated_stress_points": [{"element_id": eid, "point_id": point,
                    "coordinates_mm": dat["COORD"][(eid, point)]} for eid, point in sorted(dat["COORD"])]}
    if double:
        metadata["DAT_displacements_mm"] = [dat["U"][node] for node in order]
        metadata["DAT_internal_forces_n"] = [dat["RF"][node] for node in order]
        metadata["primary_field_encoding"] = deepcopy(frd["encoding"])
    return record, metadata


def _point_vtk(path: Path, coordinates: list, values: list, *, tensor: bool = False) -> None:
    """Retained vertex samples; these are not invented surface extrema/contours."""
    with path.open("x", encoding="ascii", newline="\n") as stream:
        stream.write("# vtk DataFile Version 3.0\nNative verified structural field samples\nASCII\nDATASET POLYDATA\n")
        stream.write(f"POINTS {len(coordinates)} double\n")
        for xyz in coordinates:
            stream.write(" ".join(f"{v:.17g}" for v in xyz) + "\n")
        stream.write(f"VERTICES {len(coordinates)} {2 * len(coordinates)}\n")
        for index in range(len(coordinates)):
            stream.write(f"1 {index}\n")
        stream.write(f"POINT_DATA {len(coordinates)}\n" + ("TENSORS gauss_stress_mpa double\n" if tensor else "VECTORS displacement_mm double\n"))
        for row in values:
            rows = ([row[0], row[3], row[4]], [row[3], row[1], row[5]], [row[4], row[5], row[2]]) if tensor else (row,)
            for vector in rows:
                stream.write(" ".join(f"{v:.17g}" for v in vector) + "\n")


class StructuralFamilyCalculiXAdapter:
    backend = "structural.families.calculix"
    domain = "structural_families"
    physics_domain = "structural"
    analysis_type = "linear_static"
    version = "1"
    default_metrics = ["primary_response"]
    input_source_files = _SOURCE_FILES

    def describe_model(self, settings: dict) -> dict:
        return _domain.model_declaration(settings)

    def input_runtime_identity(self) -> dict:
        if any(not path.is_file() or _sha(path) != expected for path, expected in _SOURCE_HASHES.items()):
            raise ValueError("Structural source changed before runtime identity")
        return _runtime_identity()

    def solve(self, output: Path, settings: dict) -> dict:
        output = Path(output)
        if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
            raise ValueError("Analysis output must be new or empty; original evidence cannot be overwritten")
        output.mkdir(parents=True, exist_ok=True)
        provenance = {"adapter": self.backend, "adapter_version": self.version,
                      "input_sources": _capture_sources(output), "native_rules": deepcopy(_DOUBLE_RULES)}
        save_json(output / "source_identity.json", provenance["input_sources"])

        def reject(code: str, error: ValueError) -> dict:
            result = {"status": "REJECTED", "solver_status": "NOT_RUN", "converged": None,
                      "checks": [{"code": code, "status": "FAIL", "observed": str(error)}],
                      "metrics": {}, "pending_validations": list(_PENDING), "provenance": provenance,
                      "raw_result": "simulation/analysis_raw.json"}
            _assert_sources(output)
            save_json(output / "analysis_raw.json", result)
            return result

        try:
            settings = _domain.validate_settings(settings)
        except ValueError as exc:
            return reject("structural_family_preflight", exc)
        save_json(output / "input.json", settings)
        declaration = self.describe_model(settings)
        save_json(output / "model_declaration.json", declaration)
        inputs = {output / name: _sha(output / name) for name in ("input.json", "model_declaration.json", "source_identity.json")}
        prepared = []
        for index, cells in enumerate(settings["mesh_cells"]):
            level = output / f"level_{index}"
            level.mkdir()
            try:
                mesh = _mesh.build_mesh(settings, cells)
                _catalogue(mesh)
                checks = _mesh.check_mesh(mesh, settings)
                save_json(level / "mesh.json", mesh)
                save_json(level / "mesh_checks.json", checks)
                _mesh.write_calculix_mesh(mesh, level / "mesh.inc")
                native_nodes = parse_input_mesh(level / "mesh.inc", mesh)
                serialized = _deck(mesh, declaration, level / "family.inp")
                save_json(level / "serialized_loads_n.json", [{"node_id": node, "value": value} for node, value in sorted(serialized.items())])
            except ValueError as exc:
                return reject("structural_mesh_preflight", exc)
            for name in ("mesh.json", "mesh_checks.json", "mesh.inc", "family.inp", "serialized_loads_n.json"):
                inputs[level / name] = _sha(level / name)
            prepared.append((level, mesh, native_nodes, serialized))
            _assert_sources(output)
        runtime = self.input_runtime_identity()
        provenance["runtime"] = runtime
        save_json(output / "runtime_identity.json", runtime)
        inputs[output / "runtime_identity.json"] = _sha(output / "runtime_identity.json")
        verified = {}

        def unchanged() -> None:
            _assert_sources(output)
            if self.input_runtime_identity() != runtime:
                raise RuntimeError("CalculiX executable/selection drifted; native evidence retained")
            if any(not path.is_file() or path.is_symlink() or _sha(path) != expected
                   for path, expected in {**inputs, **verified}.items()):
                raise RuntimeError("Structural native input/result changed; original evidence retained")

        unchanged()
        version = _process([runtime["executable"], "-v"], output, "ccx_version", timeout=10)
        unchanged()
        if re.findall(r"\bVersion\s+([\d.]+)\b", version, flags=re.IGNORECASE) != ["2.21"]:
            raise RuntimeError("Native CalculiX version must be exactly2.21; version output retained")
        provenance["versions"] = {"calculix": version.strip()}
        records = []
        for level, mesh, native_nodes, serialized in prepared:
            unchanged()
            text = _process([runtime["executable"], "-i", "family"], level, "solver")
            unchanged()
            if re.search(r"\*ERROR|\b(?:nan|infinity)\b", text, re.IGNORECASE) or "Job finished" not in text:
                raise RuntimeError("CalculiX did not report finite native linear termination; logs retained")
            result_hashes = {level / name: _sha(level / name) for name in ("family.dat", "family.frd")}
            record, metadata = parse_fields(level, mesh, serialized, native_nodes,
                                            native_abi=runtime.get("frd_abi"), require_double=True)
            if any(_sha(path) != expected for path, expected in result_hashes.items()):
                raise RuntimeError("Native results changed during extraction; evidence retained")
            save_json(level / "parsed_fields.json", record)
            save_json(level / "extraction_metadata.json", metadata)
            _point_vtk(level / "displacement_samples.vtk", record["coordinates_mm"], record["displacements_mm"])
            _point_vtk(level / "gauss_stress_samples.vtk", [row["coordinates_mm"] for row in record["stress_points"]],
                       [row["components_mpa"] for row in record["stress_points"]], tensor=True)
            verified.update(result_hashes)
            for name in ("parsed_fields.json", "extraction_metadata.json", "displacement_samples.vtk", "gauss_stress_samples.vtk"):
                verified[level / name] = _sha(level / name)
            records.append(record)
            save_json(output / "mesh_records.json", records)
            verified[output / "mesh_records.json"] = _sha(output / "mesh_records.json")
            provenance.setdefault("mesh_inputs", []).append({"cells": mesh["cells"], "mesh_sha256": inputs[level / "mesh.json"],
                "native_mesh_sha256": inputs[level / "mesh.inc"], "input_sha256": inputs[level / "family.inp"],
                "native_dat_sha256": result_hashes[level / "family.dat"], "native_frd_sha256": result_hashes[level / "family.frd"]})
            unchanged()
        assessment = _domain.assess(settings, records)
        unchanged()
        result = {**assessment, "status": "COMPLETED" if all(check["status"] == "PASS" for check in assessment["checks"]) else "REJECTED",
                  "solver_status": "COMPLETED", "converged": True, "provenance": provenance,
                  "raw_result": "simulation/analysis_raw.json"}
        save_json(output / "analysis_raw.json", result)
        return result
