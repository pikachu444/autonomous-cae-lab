"""Prepare an append-only native ParaView project from retained CalculiX fields.

Run with the repository Python, not pvpython. No solver or source file is changed.
The existing adapter validates the field contract; this module only writes a
lossless VTK view of its recorded displacement and quadratic-tetra connectivity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from caelab.adapters.structural_response_fields import select_field_response
from caelab.schema import validate
from caelab.storage import canonical_hash

DEFAULT_STORE = ROOT / "runs/cae-conditions-20261006-01/experiments"
DEFAULT_A = DEFAULT_STORE / "fea_width38_150N_mesh4_condition_reuse_20261006_r01"
DEFAULT_B = DEFAULT_STORE / "E-explicit-200N-20261006-r01"
FIELD_PATH = "simulation/support_0/fea_field.json"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_source(folder):
    folder = Path(folder).resolve(strict=True)
    result_path, proposal_path = folder / "result.json", folder / "proposal.json"
    initial = {str(p): sha(p) for p in (result_path, proposal_path)}
    result = json.loads(result_path.read_text(encoding="utf-8"))
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    validate("result", result)
    validate("experiment", proposal)
    if canonical_hash(proposal) != result["provenance"]["proposal_sha256"]:
        raise ValueError("Proposal hash does not match retained result")
    entries = {entry["path"]: entry for entry in result["artifacts"]}
    field_entry = entries[FIELD_PATH]
    field_path = folder / FIELD_PATH
    raw = json.loads(field_path.read_text(encoding="utf-8"))
    required = [FIELD_PATH] + ["simulation/support_0/" + row["path"] for row in raw["sources"].values()]
    pins = []
    for relative in required:
        path = (folder / relative).resolve(strict=True)
        if not path.is_relative_to(folder):
            raise ValueError("Retained source escapes experiment")
        entry = entries[relative]
        if path.stat().st_size != entry["size_bytes"] or sha(path) != entry["sha256"]:
            raise ValueError(f"Retained source hash/size mismatch: {relative}")
        initial[str(path)] = entry["sha256"]
        pins.append({"path": str(path), "sha256": entry["sha256"], "bytes": entry["size_bytes"]})
    select_field_response(result, proposal, raw, field_entry, {
        "artifact": FIELD_PATH, "sha256": field_entry["sha256"],
        "cad_revision": result["cad_revision"], "node_id": raw["nodes"][0]["node_id"], "component": "UZ"})
    for path, expected in initial.items():
        if sha(path) != expected:
            raise ValueError("Retained source changed during preparation")
    record = {
        "experiment_id": result["experiment_id"], "experiment_path": str(folder),
        "result_path": str(result_path), "result_sha256": initial[str(result_path)],
        "proposal_path": str(proposal_path), "proposal_sha256": initial[str(proposal_path)],
        "field_path": str(field_path), "field_sha256": field_entry["sha256"], "source_pins": pins,
        "cad_revision": result["cad_revision"], "backend": result["provenance"]["adapter"],
        "versions": result["provenance"]["adapter_details"]["versions"],
        "force_N": result["provenance"]["adapter_details"]["force_per_support_N"],
        "node_count": raw["node_count"], "element_count": raw["element_count"],
        "coordinate_frame": raw["coordinate_frame"], "position_unit": "mm", "displacement_unit": "mm",
        "static": raw["static"], "qualification": "UNKNOWN", "decision": result["decision"],
        "engineering_valid": False, "solver_status": result["solver_status"],
        "limitations": ["Recorded static load step; not a physical time history", "Assumed material and load; NOT_RELEASED", "Stress is not exposed: retained stress validity is not established", "No reaction-force field is present in this displacement artifact"]}
    return raw, record


def data_array(parent, name, values, components=1, integer=False):
    attrs = {"type": "Int64" if integer else "Float64", "Name": name, "format": "ascii"}
    if components != 1:
        attrs["NumberOfComponents"] = str(components)
    child = ET.SubElement(parent, "DataArray", attrs)
    child.text = " ".join(str(v) if integer else format(float(v), ".17g") for v in values)
    return child


def write_vtu(path, raw, extra=None):
    nodes = raw["nodes"]
    index = {row["node_id"]: i for i, row in enumerate(nodes)}
    vtk = ET.Element("VTKFile", type="UnstructuredGrid", version="0.1", byte_order="LittleEndian")
    grid = ET.SubElement(vtk, "UnstructuredGrid")
    piece = ET.SubElement(grid, "Piece", NumberOfPoints=str(len(nodes)), NumberOfCells=str(len(raw["elements"])))
    points = ET.SubElement(piece, "Points")
    data_array(points, "Position_mm", (v for row in nodes for v in row["position_mm"]), 3)
    cells = ET.SubElement(piece, "Cells")
    # CalculiX C3D10 and VTK_QUADRATIC_TETRA use the same six midside-edge order.
    data_array(cells, "connectivity", (index[n] for row in raw["elements"] for n in row["node_ids"]), integer=True)
    data_array(cells, "offsets", (10 * (i + 1) for i in range(len(raw["elements"]))), integer=True)
    data_array(cells, "types", (24 for _ in raw["elements"]), integer=True)
    point_data = ET.SubElement(piece, "PointData", Scalars="U_magnitude_mm", Vectors="U_mm")
    data_array(point_data, "NativeNodeId", (row["node_id"] for row in nodes), integer=True)
    vector = data_array(point_data, "U_mm", (v for row in nodes for v in row["displacement_mm"]), 3)
    for i, name in enumerate(("UX", "UY", "UZ")):
        vector.set(f"ComponentName{i}", name)
        data_array(point_data, name + "_mm", (row["displacement_mm"][i] for row in nodes))
    data_array(point_data, "U_magnitude_mm", (math.hypot(*row["displacement_mm"]) for row in nodes))
    fixed = set(raw["fixed_node_ids"])
    loaded = {row["node_id"] for row in raw["loads"]}
    data_array(point_data, "FixedXYZ_input", (int(row["node_id"] in fixed) for row in nodes), integer=True)
    data_array(point_data, "LoadedNode_input", (int(row["node_id"] in loaded) for row in nodes), integer=True)
    for name, values in (extra or {}).items():
        data_array(point_data, name, values)
    cell_data = ET.SubElement(piece, "CellData")
    data_array(cell_data, "NativeElementId", (row["element_id"] for row in raw["elements"]), integer=True)
    ET.ElementTree(vtk).write(path, encoding="utf-8", xml_declaration=True)


def comparison(a, b, ra, rb):
    checks = {
        "cad_revision": ra["cad_revision"] == rb["cad_revision"],
        "coordinate_frame": ra["coordinate_frame"] == rb["coordinate_frame"],
        "units": (ra["position_unit"], ra["displacement_unit"]) == (rb["position_unit"], rb["displacement_unit"]),
        "static_step": ra["static"] == rb["static"],
        "native_node_ids_and_coordinates": [(n["node_id"], n["position_mm"]) for n in a["nodes"]] == [(n["node_id"], n["position_mm"]) for n in b["nodes"]],
        "native_element_ids_and_connectivity": a["elements"] == b["elements"],
    }
    return {"status": "EXACT_RECORDED_MESH_MATCH" if all(checks.values()) else "BLOCKED", "checks": checks,
            "method": "Exact CAD revision, node-ID/coordinate and element-ID/connectivity equality; no interpolation",
            "difference": "B - A", "relative_change": "100 * (B - A) / abs(A)",
            "zero_denominator": "NaN plus valid mask = 0; no epsilon replacement", "engineering_alignment": "UNKNOWN"}


def validate_fixture_pair(a, b):
    # ponytail: the native workspace labels describe this retained fixture pair.
    # Derive every label/reader identity from metadata before admitting other pairs.
    for key, record, force in (("A", a, 150), ("B", b, 200)):
        if (record["force_N"] != force or record["backend"] != "fixture.calculix"
                or record["versions"].get("ccx") != "This is Version 2.21"
                or record["static"] != {"step": 1, "increment": 1, "load_parameter": 1.0}
                or record["decision"] != "NOT_RELEASED"):
            raise ValueError(f"Source {key} does not match the prototype's {force} N / CalculiX 2.21 static-step-1 labels")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-a", type=Path, default=DEFAULT_A)
    parser.add_argument("--source-b", type=Path, default=DEFAULT_B)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    a, ra = read_source(args.source_a)
    b, rb = read_source(args.source_b)
    validate_fixture_pair(ra, rb)
    write_vtu(out / "A_150N_U.vtu", a)
    write_vtu(out / "B_200N_U.vtu", b)
    ra["view_file"], rb["view_file"] = "A_150N_U.vtu", "B_200N_U.vtu"
    for record in (ra, rb):
        record["view_sha256"] = sha(out / record["view_file"])
    comp = comparison(a, b, ra, rb)
    if comp["status"] != "BLOCKED":
        arrays = {}
        for i, label in enumerate(("UX", "UY", "UZ")):
            base = [row["displacement_mm"][i] for row in a["nodes"]]
            delta = [nb["displacement_mm"][i] - na["displacement_mm"][i] for na, nb in zip(a["nodes"], b["nodes"])]
            arrays["Delta_" + label + "_mm"] = delta
            arrays["Relative_" + label + "_percent"] = [100 * d / abs(x) if x != 0 else math.nan for x, d in zip(base, delta)]
            arrays["Relative_" + label + "_valid"] = [int(x != 0) for x in base]
        write_vtu(out / "Derived_B_minus_A.vtu", b, arrays)
        comp["view_file"] = "Derived_B_minus_A.vtu"
        comp["view_sha256"] = sha(out / comp["view_file"])
    with (out / "B_exact_nodes.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["NativeNodeId", "X_mm", "Y_mm", "Z_mm", "UX_mm", "UY_mm", "UZ_mm", "U_magnitude_mm"])
        writer.writerows([n["node_id"], *n["position_mm"], *n["displacement_mm"], math.hypot(*n["displacement_mm"])] for n in b["nodes"])
    max_node = max(b["nodes"], key=lambda n: math.hypot(*n["displacement_mm"]))
    project = {"schema_version": "desktop_post_prototype.1", "title": "CAE Post | retained fixture response", "sources": {"A": ra, "B": rb},
               "comparison": comp, "exact_probe": max_node, "workspace_file": "workspace.pvsm",
               "prototype": True, "gui_verified": False, "source_policy": "Read-only retained sources; append-only saved analysis revisions"}
    write_json(out / "project.json", project)
    print(json.dumps({"project": str(out / "project.json"), "comparison": comp["status"], "nodes": rb["node_count"], "elements": rb["element_count"]}))


if __name__ == "__main__":
    main()
