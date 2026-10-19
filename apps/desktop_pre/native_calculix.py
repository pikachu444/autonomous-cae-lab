"""FreeCAD CalculiX writer integration; no case-specific model or mesh builder."""
from pathlib import Path
import threading
import uuid

from .freeze_analysis import _hash, _identity, _json, _number, _plain, _serialized_coordinate_close

PROFILE = "freecad-calculix-writer"
UNITS = {"position": "mm", "displacement": "mm", "force": "N", "stress": "MPa"}

# FreeCAD 1.1.4 FemMesh.cpp::writeABAQUS, not a benchmark admission list.
_ORDERS = {}
for _names, _order in (
    ("C3D4", (1, 0, 2, 3)),
    ("C3D10 C3D10T", (1, 0, 2, 3, 4, 6, 5, 8, 7, 9)),
    ("C3D6", (4, 5, 3, 1, 2, 0)),
    ("C3D15", (4, 5, 3, 1, 2, 0, 10, 11, 9, 7, 8, 6, 13, 14, 12)),
    ("C3D8 C3D8R C3D8I", (5, 6, 7, 4, 1, 2, 3, 0)),
    ("C3D20 C3D20R", (5, 6, 7, 4, 1, 2, 3, 0, 13, 14, 15, 12, 9, 10, 11, 8, 17, 18, 19, 16)),
    ("S3 M3D3 CPS3 CPE3 CAX3", (0, 1, 2)),
    ("S6 M3D6 CPS6 CPE6 CAX6", tuple(range(6))),
    ("S4 S4R M3D4 M3D4R CPS4 CPS4R CPE4 CPE4R CAX4 CAX4R", tuple(range(4))),
    ("S8 S8R M3D8 M3D8R CPS8 CPS8R CPE8 CPE8R CAX8 CAX8R", tuple(range(8))),
    ("B31 B31R T3D2", (0, 1)),
    ("B32 B32R T3D3", (0, 2, 1)),
):
    for _name in _names.split():
        _ORDERS[_name] = _order


def read_deck(path):
    """Read mesh identity and static clock from the writer, retaining all cards.

    Material/contact/load syntax remains owned by the installed native writer
    and solver. Includes must remain inside the snapshot that owns the run.
    """
    path = Path(path).resolve()
    root, sections, files = path.parent, [], []

    def visit(source, active=()):
        if any(p.is_symlink() for p in (source, *source.parents)):
            raise ValueError("CalculiX input includes must be regular local files")
        source = source.resolve()
        if (not source.is_relative_to(root) or source in active or source.is_symlink()
                or not source.is_file() or source.stat().st_size > 256 * 1024 ** 2):
            raise ValueError("CalculiX input includes a missing, cyclic or external file: " + source.name)
        if source not in files:
            files.append(source)
        section = None
        for raw in source.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("**"):
                continue
            if line.startswith("*"):
                parts = [value.strip() for value in line.split(",")]
                options = {}
                for part in parts[1:]:
                    key, _, value = part.partition("=")
                    options[key.upper()] = value
                if parts[0].upper() == "*INCLUDE":
                    name = options.get("INPUT", "").strip('"\'')
                    if not name or "\\" in name or ":" in name or any(p in {"", ".", ".."} for p in name.split("/")):
                        raise ValueError("CalculiX include must use a local relative filename")
                    visit(source.parent / name, active + (source,))
                    section = None
                else:
                    section = (parts[0].upper(), options, [])
                    sections.append(section)
            elif section is not None:
                section[2].append(line)
            else:
                raise ValueError("CalculiX input data has no keyword")

    visit(path)
    nodes, elements, steps, current = {}, {}, [], None
    for card, options, rows in sections:
        if card == "*NODE":
            for row in rows:
                values = [value.strip() for value in row.split(",")]
                node = int(values[0])
                if node <= 0 or node in nodes or len(values) != 4:
                    raise ValueError("Invalid or duplicate CalculiX mesh node")
                nodes[node] = [_number(v.replace("D", "E").replace("d", "e")) for v in values[1:]]
        elif card == "*ELEMENT":
            kind = options.get("TYPE", "").upper()
            if kind not in _ORDERS:
                raise ValueError("The installed mesh writer element is not supported by this connection: " + kind)
            width, pending = len(_ORDERS[kind]), []
            for row in rows:
                pending.extend(int(v.strip()) for v in row.split(",") if v.strip())
                if len(pending) == width + 1:
                    identifier, *ids = pending
                    if identifier <= 0 or identifier in elements or len(set(ids)) != width:
                        raise ValueError("Invalid or duplicate CalculiX element connectivity")
                    elements[identifier] = {"element_id": identifier, "type": kind, "node_ids": ids}
                    pending = []
                elif len(pending) > width + 1:
                    raise ValueError("Invalid CalculiX element connectivity length")
            if pending:
                raise ValueError("Incomplete CalculiX element connectivity")
        elif card == "*STEP":
            if current is not None:
                raise ValueError("Nested CalculiX analysis step")
            current = {"options": options, "period": None}
        elif card == "*STATIC":
            if current is None:
                raise ValueError("CalculiX static procedure is outside a step")
            values = rows[0].split(",") if rows else []
            period = _number(values[1]) if len(values) > 1 and values[1].strip() else 1.0
            if period <= 0:
                raise ValueError("CalculiX static step period must be positive")
            current["period"] = period
        elif card == "*END STEP":
            if current is None or current["period"] is None:
                raise ValueError("This connection requires a complete static analysis step")
            steps.append(current)
            current = None
    if current is not None or not steps or not nodes or not elements:
        raise ValueError("CalculiX input is missing a mesh or a complete static step")
    if any(node not in nodes for row in elements.values() for node in row["node_ids"]):
        raise ValueError("CalculiX element references a missing mesh node")
    if not any(card == "*MATERIAL" for card, _, _ in sections):
        raise ValueError("CalculiX input has no material assignment")
    return {"nodes": nodes, "elements": elements, "steps": steps,
            "cards": list(dict.fromkeys(row[0] for row in sections)),
            "files": [p.relative_to(root).as_posix() for p in files]}


def _properties(obj):
    names = getattr(obj, "PropertiesList", None)
    if names is None:
        names = [name for name in vars(obj) if name not in {"Document", "Shape", "FemMesh"}]
    return {name: _plain(getattr(obj, name)) for name in names
            if name not in {"Proxy", "Shape", "FemMesh", "ExpressionEngine"} and not callable(getattr(obj, name))}


def _mesh_quality(native, elements):
    """Observe bounded actual mesh samples without adding an admission rule.

    FreeCAD 1.1.4 FemMeshPyImp.cpp exposes Nodes/getElementNodes, but no
    general quality API. FemMesh.Volume only covers Tet10 and is unsuitable
    here. Reuse the editor's existing tetra calculation, not a new criterion.
    """
    from .fem_edit import _element_quality

    count, limit = len(elements), 256
    indices = range(count) if count <= limit else (i * (count - 1) // (limit - 1) for i in range(limit))
    sample = [elements[i] for i in indices]
    summary = {
        "status": "NOT_MEASURED", "source": "FreeCAD FemMesh.Nodes/getElementNodes",
        "native_quality_api": "NOT_AVAILABLE_IN_FREECAD_1_1_4",
        "scope": "Tetra Jacobian samples only; other element families and quality measures are unmeasured.",
        "element_count": count, "sample_limit": limit,
        "sampled_element_ids": [row["element_id"] for row in sample],
        "sampling": "Equally spaced exported element order, including endpoints; no statistical guarantee.",
        "unmeasured_element_types": sorted({row["type"] for row in elements if row["type"] not in {"C3D4", "C3D10", "C3D10T"}}),
        "jacobian": {
            "status": "NOT_MEASURED", "unit": "mm^3", "measured_element_count": 0,
            "unmeasured_element_count": count, "minimum": None, "maximum": None,
            "negative_element_count": 0, "zero_element_count": 0,
            "degenerate_coordinate_scale_count": 0, "read_error_count": 0,
            "method": "Existing FEM editor: constant Tet4 or four Tet10 interior samples; minimum per element.",
            "limitations": "These are sampled Jacobian minima, not extrema over the mesh or the full element. No acceptance threshold is applied.",
        },
    }
    metric = summary["jacobian"]
    try:
        nodes = native.Nodes
        if not callable(getattr(native, "getElementNodes", None)):
            raise AttributeError("Native ordered connectivity is unavailable")
    except (AttributeError, TypeError, ValueError, RuntimeError) as error:
        summary["reason"] = "Native node coordinates or ordered connectivity are unavailable: " + str(error)
        return summary
    measured = []
    for element in sample:
        if element["type"] not in {"C3D4", "C3D10", "C3D10T"}:
            continue
        try:
            row = _element_quality(native, element["element_id"], node_table=nodes)
            metric["degenerate_coordinate_scale_count"] += "DEGENERATE_COORDINATE_SCALE" in row["errors"]
            value = row.get("minimum_sampled_jacobian_mm3")
            if value is not None:
                measured.append((value, element["element_id"]))
                metric["negative_element_count"] += value < 0
                metric["zero_element_count"] += value == 0
        except (AttributeError, IndexError, KeyError, TypeError, ValueError, OverflowError, RuntimeError):
            metric["read_error_count"] += 1
    metric["measured_element_count"] = len(measured)
    metric["unmeasured_element_count"] = count - len(measured)
    if measured:
        metric["minimum"], metric["minimum_element_id"] = min(measured)
        metric["maximum"], metric["maximum_element_id"] = max(measured)
        metric["status"] = summary["status"] = "MEASURED" if len(measured) == count else "PARTIALLY_MEASURED"
    return summary


def validate_analysis(analysis, solver):
    """Apply the installed writer's input checks to the selected native objects."""
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("Finish the FreeCAD edit before exporting on its main thread")
    doc = analysis.Document
    from .freeze_analysis import require_ready_model
    require_ready_model(doc)
    import FreeCAD as App
    from femtools import femutils, membertools, checksanalysis

    if App.GuiUp:
        import FreeCADGui as Gui
        if Gui.Control.activeDialog() or (Gui.activeDocument() and Gui.activeDocument().getInEdit()):
            raise ValueError("Finish the open FreeCAD task before running the analysis")
    if (femutils.type_of_obj(analysis) != "Fem::FemAnalysis" or solver.Document is not doc
            or solver not in analysis.Group or femutils.type_of_obj(solver) != "Fem::SolverCcxTools"):
        raise ValueError("Select a FEM Analysis and its CalculiX solver")
    if solver.AnalysisType != "static":
        raise ValueError(getattr(solver, "Label", solver.Name) + ": select static analysis; other procedures are not connected yet")
    invalid = [obj.Name for obj in doc.Objects if set(obj.State) & {"Touched", "Invalid", "Error", "Recompute"}]
    if doc.isTouched() or invalid:
        raise ValueError("Recompute the FreeCAD model before running: " + ", ".join(invalid))
    mesh, error = membertools.get_mesh_to_solve(analysis)
    if mesh is None:
        raise ValueError(error)
    member = membertools.AnalysisMember(analysis)
    errors = checksanalysis.check_member_for_solver_calculix(analysis, solver, mesh, member)
    if errors:
        raise ValueError(errors)
    members = []
    for name, rows in vars(member).items():
        if name.startswith(("mats_", "cons_", "geos_")) and isinstance(rows, list):
            for row in rows:
                obj = row["Object"]
                if not any(obj is known for known in members):
                    members.append(obj)
    for obj in analysis.Group:
        kind = femutils.type_of_obj(obj)
        if getattr(obj, "Suppressed", False) or "Result" in kind or "Post" in kind:
            continue
        if obj is not mesh and obj is not solver and not any(obj is known for known in members):
            raise ValueError(obj.Name + ": this object is not supported by the CalculiX writer")
        if getattr(obj, "CAELabLawNative", ""):
            raise ValueError(obj.Name + ": this custom material law needs its native material interface")
    for row in getattr(member, "mats_linear", []):
        obj = row["Object"]
        values = obj.Material
        if (getattr(obj, "Category", "Solid") == "Solid"
                and "YoungsModulus" in values and "PoissonRatio" in values):
            e = _number(App.Units.Quantity(values["YoungsModulus"]).getValueAs("MPa").Value)
            nu = _number(values["PoissonRatio"])
            if e <= 0 or not -1 < nu < .5:
                raise ValueError(obj.Name + ": elasticity requires E > 0 and -1 < nu < 0.5")
    return mesh, member


def export_analysis(analysis, solver, output_root, *, binding_validator=None):
    """Freeze an editable Analysis and the exact files its official writer emits."""
    mesh, member = validate_analysis(analysis, solver)
    import FreeCAD as App
    from femtools import femutils
    from femmesh.meshsetsgetter import MeshSetsGetter
    from femsolver.calculix.writer import FemInputWriterCcx
    doc = analysis.Document
    members = []
    for name, rows in vars(member).items():
        if name.startswith(("mats_", "cons_", "geos_")) and isinstance(rows, list):
            for row in rows:
                if not any(row["Object"] is obj for obj in members):
                    members.append(row["Object"])

    def native_state():
        from .freeze_analysis import require_ready_model
        require_ready_model(doc)
        return {"members": [(obj.Name, _properties(obj)) for obj in analysis.Group],
                "nodes": {int(n): [_number(v) for v in (p.x, p.y, p.z)] for n, p in mesh.FemMesh.Nodes.items()},
                "elements": {family: [(int(n), list(mesh.FemMesh.getElementNodes(n)))
                                      for n in sorted(getattr(mesh.FemMesh, family, []))]
                             for family in ("Edges", "Faces", "Volumes")}}

    before = native_state()
    from .mesh_binding import PROPERTY_NAME
    bound = binding_validator is not None and PROPERTY_NAME in getattr(mesh, "PropertiesList", [])
    binding = binding_validator(mesh) if bound else {"status": "NOT_OBSERVED"}
    filename = doc.FileName
    original = Path(filename) if filename else None
    original_hash = _hash(original) if original and original.is_file() else None
    root = Path(output_root).resolve() / ("F" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    doc.saveCopy(str(root / "editable.FCStd"))
    if doc.FileName != filename or not (root / "editable.FCStd").is_file():
        raise ValueError("FreeCAD could not save an editable copy of the current model")
    getter = MeshSetsGetter(analysis, solver, mesh, member)
    getter.get_mesh_sets()
    writer = FemInputWriterCcx(analysis, solver, mesh, getter.member, str(root), getter.mat_geo_sets)
    written = writer.write_solver_input()
    if not written or Path(written).resolve().parent != root:
        raise ValueError("The CalculiX writer could not export this Analysis; see the FreeCAD report")
    inp = Path(written).resolve()
    deck = read_deck(inp)
    if not set(before["nodes"]) <= set(deck["nodes"]) or any(
            not all(_serialized_coordinate_close(a, b) for a, b in zip(xyz, deck["nodes"][n]))
            for n, xyz in before["nodes"].items()):
        raise ValueError("The written mesh coordinates differ from the selected FreeCAD mesh")
    elements = list(deck["elements"].values())
    if hasattr(mesh.FemMesh, "getElementNodes"):
        for element in elements:
            native = list(mesh.FemMesh.getElementNodes(element["element_id"]))
            if [native[i] for i in _ORDERS[element["type"]]] != element["node_ids"]:
                raise ValueError(mesh.Name + ": native element connectivity changed during export")
            element["native_node_ids"] = native
    _json(root / "mesh.json", {"schema_version": "1", "kind": "freecad-fem-mesh",
          "export_profile": PROFILE, "units": UNITS,
          "nodes": [{"node_id": n, "position_mm": xyz, "native_position_mm": before["nodes"].get(n),
                     "source": "mesh" if n in before["nodes"] else "native_writer"}
                    for n, xyz in sorted(deck["nodes"].items())], "elements": elements})
    quality = _mesh_quality(mesh.FemMesh, elements)
    if (native_state() != before or doc.FileName != filename or doc.isTouched()
            or (original_hash and _hash(original) != original_hash)
            or (bound and binding_validator(mesh) != binding)):
        raise ValueError("The source model changed while the CalculiX input was being written")
    objects = [dict(_identity(obj, femutils), label=getattr(obj, "Label", obj.Name),
                    properties=_properties(obj)) for obj in members]
    files = [{"relative": p.relative_to(root).as_posix(), "bytes": p.stat().st_size, "sha256": _hash(p)}
             for p in sorted(root.rglob("*")) if p.is_file()]
    manifest = root / "snapshot.json"
    _json(manifest, {"schema_version": "1", "kind": "freecad-fem-frozen", "export_profile": PROFILE,
          "id": root.name, "native_version": list(App.Version()),
          "document": {"name": doc.Name, "original_sha256": original_hash},
          "analysis": _identity(analysis, femutils),
          "solver": dict(_identity(solver, femutils), settings=_properties(solver)),
          "mesh": dict(_identity(mesh, femutils), node_count=len(deck["nodes"]),
                       element_count=len(elements), element_types=sorted({e["type"] for e in elements})),
          "mesh_source_binding": binding,
          "mesh_quality": quality,
          "materials": [o for o in objects if "Material" in o["native_type"]],
          "sections": [o for o in objects if "Element" in o["native_type"]],
          "conditions": [o for o in objects if "Constraint" in o["native_type"]],
          "input_file": inp.name, "input_dependencies": deck["files"], "files": files,
          "steps": deck["steps"], "native_cards": deck["cards"], "units": UNITS,
          "solver_execution": "NOT_PERFORMED", "qualification": "NOT_ASSESSED",
          "verification_case": "없음"})
    return manifest
