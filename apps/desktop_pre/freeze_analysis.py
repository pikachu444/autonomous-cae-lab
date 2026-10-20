"""Export an existing FreeCAD FEM Analysis; retain legacy snapshot compatibility."""
import hashlib
import json
import math
from pathlib import Path
import uuid

# FreeCAD 1.1.4 FemMesh.cpp writeABAQUS, Tetra10: raw getElementNodes
# SMESH slots -> CalculiX slots. Node membership alone does not prove identity.
# https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Fem/App/FemMesh.cpp
CCX_FROM_NATIVE_TET10 = (1, 0, 2, 3, 4, 6, 5, 8, 7, 9)


def require_ready_model(doc, *, owner=None):
    """Admit managed pose candidates without repairing or refreshing their CAD."""
    from . import metadata
    reader = getattr(owner, 'read_metadata', None)
    stored = reader() if reader else metadata.read(doc) if hasattr(doc, 'getObject') else {}
    if 'assembly_pose_candidate' not in stored:
        return
    from .assembly_pose_candidate import require_valid
    if owner is None:
        from types import SimpleNamespace
        owner = SimpleNamespace(doc=doc, read_metadata=lambda: metadata.read(doc))
    report = require_valid(owner, exact=False)
    if report['state'] != 'READY':
        raise ValueError('선택 자세 모델의 준비가 끝나지 않았습니다. 보존한 원 조립에서 다시 만들거나 준비된 사본을 여세요.')
    return report


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def _hash(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def _number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Nonfinite native input")
    return value


def _serialized_coordinate_close(native, written):
    # FemMesh.cpp sets ostream precision(13). Permit only decimal serialization
    # and a few binary rounding ULPs, not a geometric percentage tolerance.
    expected = float(format(_number(native), ".13g"))
    written = _number(written)
    if expected == 0:
        return written == 0
    # math.ulp was introduced in Python 3.9; FreeCAD-side code stays portable.
    mantissa, exponent = math.frexp(abs(expected))
    ulp = 2.0 ** (exponent - 53)
    return abs(written - expected) <= 8 * ulp


def _plain(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "Name") and hasattr(value, "Document"):
        return {"object": value.Name, "document": value.Document.Name}
    return str(value)  # Native quantities retain their explicit unit text.


def _identity(obj, femutils):
    return {"name": obj.Name, "type": obj.TypeId, "native_type": femutils.type_of_obj(obj)}


def _references(obj, doc, shape):
    result = []
    for target, names in obj.References:
        if target.Document is not doc or target is not shape:
            raise ValueError("References must belong to the selected single solid")
        names = [names] if isinstance(names, str) else list(names)
        if any(not name.startswith("Face") or not name[4:].isdigit()
               or not 1 <= int(name[4:]) <= len(shape.Shape.Faces) for name in names):
            raise ValueError("Only exact FaceN references are supported")
        result.append({"object": target.Name, "subelements": names})
    return result


def _deck(path):
    """Read the native writer's narrow mesh/Fixed/Force syntax, without editing it."""
    nodes, elements, sets, boundaries, loads = {}, {}, {}, [], []
    section, options, flags, pending = "", {}, set(), []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            if pending:
                raise ValueError("Incomplete native element connectivity")
            parts = [part.strip().upper() for part in line.split(",")]
            section = parts[0]
            options = dict(part.split("=", 1) for part in parts[1:] if "=" in part)
            flags = {part for part in parts[1:] if "=" not in part}
            if section == "*INCLUDE":
                raise ValueError("Split/include decks are unsupported")
            if section == "*ELEMENT" and options.get("TYPE") != "C3D10":
                raise ValueError("Only C3D10 elements are supported")
            continue
        row = [part.strip() for part in line.split(",") if part.strip()]
        if section == "*NODE":
            identifier = int(row[0])
            if identifier in nodes or len(row) != 4:
                raise ValueError("Duplicate or invalid native node")
            if identifier <= 0:
                raise ValueError("Native node ID must be positive")
            nodes[identifier] = [_number(part.replace("D", "E")) for part in row[1:]]
            if "NSET" in options:
                sets.setdefault(options["NSET"], []).append(identifier)
        elif section == "*ELEMENT":
            pending.extend(int(part) for part in row)
            if len(pending) == 11:
                identifier, *connectivity = pending
                if identifier in elements or len(set(connectivity)) != 10:
                    raise ValueError("Duplicate or invalid native element")
                elements[identifier] = connectivity
                pending = []
            elif len(pending) > 11:
                raise ValueError("Invalid native element connectivity")
        elif section == "*NSET":
            name = options["NSET"]
            identifiers = list(map(int, row))
            if "GENERATE" in flags:
                if len(identifiers) not in (2, 3) or identifiers[1] < identifiers[0] or (len(identifiers) == 3 and identifiers[2] <= 0):
                    raise ValueError("Invalid generated native node set")
                identifiers = range(identifiers[0], identifiers[1] + 1, identifiers[2] if len(identifiers) == 3 else 1)
            sets.setdefault(name, []).extend(identifiers)
        elif section == "*BOUNDARY":
            if len(row) not in (2, 3, 4):
                raise ValueError("Malformed native Fixed row")
            boundaries.append(row)
        elif section == "*CLOAD":
            if "AMPLITUDE" in options:
                raise ValueError("Load amplitudes are unsupported")
            if len(row) != 3:
                raise ValueError("Malformed native Force row")
            loads.append((int(row[0]), int(row[1]), _number(row[2])))
    if pending:
        raise ValueError("Incomplete native element connectivity")
    fixed = set()
    for row in boundaries:
        selected = sets.get(row[0].upper())
        if selected is None:
            selected = [int(row[0])]
        first = int(row[1])
        last = int(row[2]) if len(row) > 2 else first
        if len(row) > 3 and _number(row[3]) != 0:
            raise ValueError("Only Fixed zero displacement is supported")
        if not 1 <= first <= last <= 3:
            raise ValueError("Only XYZ Fixed DOFs are supported")
        fixed.update((node, component) for node in selected for component in range(first, last + 1))
    if not nodes or not elements:
        raise ValueError("Native writer produced no solid mesh")
    return nodes, elements, fixed, loads


def _deck_scope(path, manifest):
    """Admit the native static writer's cards and bind their effective meaning.

    FreeCAD 1.1.4 write_step_output emits OUTPUT as well as NODE/EL FILE.
    Inert thermal expansion metadata is preserved, but temperature loads,
    transforms, alternate constitutive laws and keyword options are not admitted.
    This reader is also used in the headless adapter; it imports no native module.
    """
    allowed = {
        "*HEADING": set(), "*NODE": {"NSET"}, "*ELEMENT": {"TYPE", "ELSET"},
        "*NSET": {"NSET", "GENERATE"}, "*ELSET": {"ELSET", "GENERATE"},
        "*MATERIAL": {"NAME"}, "*ELASTIC": set(), "*EXPANSION": {"ZERO"},
        "*PHYSICAL CONSTANTS": {"ABSOLUTE ZERO", "STEFAN BOLTZMANN"},
        "*SOLID SECTION": {"ELSET", "MATERIAL"}, "*STEP": {"INC"},
        "*STATIC": {"DIRECT", "SOLVER"}, "*CONTROLS": {"PARAMETERS"},
        "*BOUNDARY": set(), "*CLOAD": set(), "*NODE FILE": set(),
        "*EL FILE": set(), "*NODE PRINT": {"NSET", "TOTALS"},
        "*OUTPUT": {"FREQUENCY"}, "*END STEP": set(),
    }
    sections = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            parts = [p.strip().upper() for p in line.split(",")]
            card, options = parts[0], {}
            if card not in allowed:
                raise ValueError("Unsupported frozen native card: " + card)
            for part in parts[1:]:
                key, sep, value = part.partition("=")
                if (key not in allowed[card] or key in options or
                        (not sep and key not in {"GENERATE", "DIRECT"})
                        or (sep and (not value or key in {"GENERATE", "DIRECT"}))):
                    raise ValueError("Unsupported or duplicate native option: " + part)
                options[key] = value if sep else None
            sections.append((card, options, []))
        elif not sections:
            raise ValueError("Native deck content precedes a keyword")
        else:
            sections[-1][2].append(line)
    by = {}
    for section in sections:
        by.setdefault(section[0], []).append(section)
    for key in ("*NODE", "*MATERIAL", "*ELASTIC", "*SOLID SECTION", "*STEP", "*STATIC", "*END STEP", "*NODE FILE"):
        if len(by.get(key, [])) != 1:
            raise ValueError("Frozen input requires exactly one " + key)
    if not by.get("*ELEMENT") or sections[-1][0] != "*END STEP" or by["*END STEP"][0][2]:
        raise ValueError("Frozen input requires one complete final static step")
    step_index = next(i for i, row in enumerate(sections) if row[0] == "*STEP")
    in_step = {"*STATIC", "*CONTROLS", "*BOUNDARY", "*CLOAD", "*NODE FILE", "*EL FILE", "*NODE PRINT", "*OUTPUT", "*END STEP"}
    for i, (card, options, rows) in enumerate(sections):
        if (card in in_step) != (i > step_index) and card != "*STEP":
            raise ValueError("Native card is outside its admitted model/step location")
    def numeric(row):
        tokens = [p.strip() for p in row.split(",")]
        if not tokens or any(not p for p in tokens):
            raise ValueError("Malformed native numeric row")
        return [_number(p.replace("D", "E").replace("d", "e")) for p in tokens]
    def positive_int(value):
        if not str(value).isdigit() or int(value) <= 0:
            raise ValueError("Native option requires a positive integer")
    step_options = by["*STEP"][0][1]
    if by["*STEP"][0][2]:
        raise ValueError("Unexpected STEP data")
    if "INC" in step_options:
        positive_int(step_options["INC"])
    static = by["*STATIC"][0]
    if static[1].get("SOLVER", "SPOOLES") not in {"PASTIX", "PARDISO", "SPOOLES", "ITERATIVE SCALING", "ITERATIVE CHOLESKY"}:
        raise ValueError("Unsupported native matrix solver")
    if len(static[2]) != 1:
        raise ValueError("Explicit native static time controls are required")
    times = numeric(static[2][0])
    if len(times) != 4 or any(v <= 0 for v in times) or not times[2] <= times[0] <= min(times[1], times[3]):
        raise ValueError("Invalid native static time controls")
    elastic = by["*ELASTIC"][0]
    material = manifest["material"]
    expected = [float(f"{material['young_modulus_MPa']:.13G}"), float(f"{material['poisson_ratio']:.13G}")]
    if len(elastic[2]) != 1 or numeric(elastic[2][0]) != expected:
        raise ValueError("Native deck elasticity differs from retained material")
    material_section = by["*MATERIAL"][0]
    if set(material_section[1]) != {"NAME"} or material_section[2]:
        raise ValueError("Invalid native material declaration")
    material_index = sections.index(material_section)
    if sections.index(elastic) != material_index + 1:
        raise ValueError("Elasticity is not attached to the retained material")
    expansions = by.get("*EXPANSION", [])
    if len(expansions) > 1:
        raise ValueError("Multiple thermal expansion laws are unsupported")
    for card, options, rows in expansions:
        if set(options) != {"ZERO"} or len(rows) != 1 or len(numeric(rows[0])) != 1:
            raise ValueError("Only native isotropic expansion metadata is admitted")
        _number(options["ZERO"])
        if sections.index((card, options, rows)) != material_index + 2:
            raise ValueError("Expansion is not attached to the retained material")
    for card, options, rows in by.get("*PHYSICAL CONSTANTS", []):
        if (set(options) != {"ABSOLUTE ZERO", "STEFAN BOLTZMANN"} or rows
                or _number(options["ABSOLUTE ZERO"]) != 0 or _number(options["STEFAN BOLTZMANN"]) <= 0):
            raise ValueError("Only native inert physical constants are admitted")
    nodes, elements, _, _ = _deck(path)
    elsets = {}
    for card, options, rows in sections:
        if card == "*ELEMENT":
            if options.get("TYPE") != "C3D10":
                raise ValueError("Only native C3D10 elements are admitted")
            # Each native writer section has one complete element per row,
            # with an optional connectivity continuation after a trailing comma.
            pending, ids = [], []
            for row in rows:
                pending.extend(int(p) for p in row.split(",") if p.strip())
                if len(pending) == 11:
                    ids.append(pending[0]); pending = []
            if "ELSET" in options:
                elsets.setdefault(options["ELSET"], []).extend(ids)
        elif card == "*ELSET":
            if "ELSET" not in options:
                raise ValueError("Missing native element set name")
            values = [p.strip().upper() for row in rows for p in row.split(",") if p.strip()]
            if "GENERATE" in options:
                if len(values) not in (2, 3):
                    raise ValueError("Invalid generated native element set")
                start, end = map(int, values[:2]); stride = int(values[2]) if len(values) == 3 else 1
                if start <= 0 or end < start or stride <= 0:
                    raise ValueError("Invalid generated native element set")
                values = list(range(start, end + 1, stride))
            elsets.setdefault(options["ELSET"], []).extend(values)
    def resolved(name, active=()):
        if name in active or name not in elsets:
            raise ValueError("Invalid/cyclic native element set")
        result = set()
        for value in elsets[name]:
            if str(value).isdigit(): result.add(int(value))
            else: result.update(resolved(value, active + (name,)))
        if not result <= set(elements):
            raise ValueError("Foreign native element set member")
        return result
    section = by["*SOLID SECTION"][0]
    if (set(section[1]) != {"ELSET", "MATERIAL"} or section[2]
            or section[1]["MATERIAL"] != material_section[1]["NAME"]
            or resolved(section[1]["ELSET"]) != set(elements)):
        raise ValueError("Native material assignment does not cover the complete existing mesh")
    if by["*NODE FILE"][0][2] != ["U"]:
        raise ValueError("Complete native displacement U output is required")
    for card, options, rows in by.get("*EL FILE", []):
        if rows != ["S, E"]:
            raise ValueError("Only native stress/total-strain ancillary output is admitted")
    for card, options, rows in by.get("*NODE PRINT", []):
        if set(options) != {"NSET", "TOTALS"} or options["TOTALS"] != "ONLY" or rows != ["RF"]:
            raise ValueError("Only native Fixed reaction totals are supported in DAT")
    for card, options, rows in by.get("*OUTPUT", []):
        if set(options) != {"FREQUENCY"} or rows:
            raise ValueError("Only native output frequency is admitted")
        positive_int(options["FREQUENCY"])
    for card, options, rows in by.get("*CONTROLS", []):
        if options != {"PARAMETERS": "TIME INCREMENTATION"} or len(rows) != 2:
            raise ValueError("Only native time incrementation controls are admitted")
        for row in rows:
            for token in row.split(","):
                if token.strip(): _number(token.strip())
    return times[1]


def _freeze_legacy_analysis(analysis, solver, output_root, *, binding_validator=None):
    """Return a new complete snapshot manifest, using the installed native writer.

    Must be called on FreeCAD's GUI/main thread after native editing/recompute.
    An incomplete export may remain for diagnosis; only snapshot.json publishes it.
    """
    import threading
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("Export requires the native main thread")
    doc = analysis.Document
    require_ready_model(doc)
    import FreeCAD as App
    from femtools import femutils, membertools, checksanalysis
    from femmesh import meshtools
    from femmesh.meshsetsgetter import MeshSetsGetter
    from femsolver.calculix.writer import FemInputWriterCcx
    if App.GuiUp:
        import FreeCADGui as Gui
        if Gui.Control.activeDialog() or (Gui.activeDocument() and Gui.activeDocument().getInEdit()):
            raise ValueError("Finish the native task edit before exporting")
    if femutils.type_of_obj(analysis) != "Fem::FemAnalysis" or solver.Document is not doc or solver not in analysis.Group:
        raise ValueError("Select an exact Analysis and its solver")
    if any(getattr(obj, "CAELabLawNative", "") for obj in analysis.Group):
        raise ValueError("LAW_NATIVE_INTERFACE_REQUIRED: CalculiX cannot export the old elastic card")
    if femutils.type_of_obj(solver) != "Fem::SolverCcxTools":
        raise ValueError("Only the native CalculiX CcxTools solver is supported")
    if doc.isTouched() or any(set(obj.State) & {"Touched", "Invalid", "Error", "Recompute"} for obj in doc.Objects):
        raise ValueError("Document must be valid and recomputed before exporting")
    expected = {"AnalysisType": "static", "ModelSpace": "3D", "GeometricalNonlinearity": "linear",
                "MaterialNonlinearity": "linear", "SplitInputWriter": False}
    if any(getattr(solver, key) != value for key, value in expected.items()):
        raise ValueError("Only unsplit 3D static linear analysis is supported")
    mesh, error = membertools.get_mesh_to_solve(analysis)
    if mesh is None:
        raise ValueError(error)
    binding = (binding_validator(mesh) if binding_validator is not None else
               {"status": "NOT_OBSERVED", "qualification": "UNKNOWN"})
    shape = getattr(mesh, "Shape", None)
    if (shape is None or shape.Document is not doc or not shape.Shape.isValid()
            or len(shape.Shape.Solids) != 1):
        raise ValueError("The existing mesh must reference one valid solid in this document")
    member = membertools.AnalysisMember(analysis)
    allowed = [solver, mesh] + [row["Object"] for group in (member.mats_linear, member.cons_fixed, member.cons_force) for row in group]
    if any(obj not in allowed or getattr(obj, "Suppressed", False) for obj in analysis.Group):
        raise ValueError("Unsupported or suppressed Analysis member; no input is silently omitted")
    if len(member.mats_linear) != 1 or not member.cons_fixed or not member.cons_force:
        raise ValueError("One isotropic material, Fixed supports and Force loads are required")
    material = member.mats_linear[0]["Object"]
    if femutils.type_of_obj(material) != "Fem::MaterialCommon" or material.Category != "Solid":
        raise ValueError("Only one isotropic solid material is supported")
    material_refs = _references(material, doc, shape)
    if material_refs:
        raise ValueError("Use one whole-solid material; native writer ignores single-material references")
    modulus = _number(App.Units.Quantity(material.Material["YoungsModulus"]).getValueAs("MPa").Value)
    ratio = _number(material.Material["PoissonRatio"])
    if modulus <= 0 or not -1 < ratio < .5:
        raise ValueError("Isotropic elasticity requires E > 0 and -1 < nu < 0.5")
    conditions = []
    for row in member.cons_fixed + member.cons_force:
        obj = row["Object"]
        kind = "Fem::ConstraintForce" if row in member.cons_force else "Fem::ConstraintFixed"
        if femutils.type_of_obj(obj) != kind:
            raise ValueError("Only native Fixed and Force constraints are supported")
        refs = _references(obj, doc, shape)
        if not refs or any(not ref["subelements"] for ref in refs):
            raise ValueError("Fixed/Force needs explicit solid faces")
        item = dict(_identity(obj, femutils), references=refs)
        if row in member.cons_force:
            if obj.EnableAmplitude:
                raise ValueError("Force amplitudes are unsupported")
            item.update(force_N=_number(obj.Force.getValueAs("N").Value),
                        direction=[_number(v) for v in (obj.DirectionVector.x, obj.DirectionVector.y, obj.DirectionVector.z)])
        conditions.append(item)
    native_nodes = {int(key): [_number(v) for v in (point.x, point.y, point.z)] for key, point in mesh.FemMesh.Nodes.items()}
    native_elements = {int(key): list(map(int, nodes)) for key, nodes in meshtools.get_femelement_volumes_table(mesh.FemMesh).items()}
    if (not native_nodes or not native_elements or any(key <= 0 for key in [*native_nodes, *native_elements])
            or any(len(nodes) != 10 or len(set(nodes)) != 10 for nodes in native_elements.values())
            or set(native_nodes) != {node for nodes in native_elements.values() for node in nodes}):
        raise ValueError("A complete existing C3D10 solid mesh is required")
    errors = checksanalysis.check_member_for_solver_calculix(analysis, solver, mesh, member)
    if errors:
        raise ValueError(errors)
    settings = {name: _plain(getattr(solver, name)) for name in solver.PropertiesList if name != "Proxy"}
    native_material = _plain(material.Material)
    def native_state():
        require_ready_model(doc)
        # Read live source again after the native writer, so its output cannot
        # be published against changed supports, force references or mesh data.
        shape_value = shape.Shape
        shape_signature = (shape_value.exportBrepToString()
                           if hasattr(shape_value, "exportBrepToString") else None)
        constraint_values = []
        for row in member.cons_fixed + member.cons_force:
            obj = row["Object"]
            value = {"name": obj.Name, "references": _references(obj, doc, shape)}
            if row in member.cons_force:
                value.update(force_N=_number(obj.Force.getValueAs("N").Value),
                             direction=[_number(v) for v in (obj.DirectionVector.x, obj.DirectionVector.y, obj.DirectionVector.z)],
                             amplitude=bool(obj.EnableAmplitude))
            constraint_values.append(value)
        return {"group": [(id(obj), obj.Name, bool(getattr(obj, "Suppressed", False))) for obj in analysis.Group],
                "mesh_shape": id(mesh.Shape), "shape": shape_signature,
                "shape_valid": shape_value.isValid(), "solid_count": len(shape_value.Solids),
                "material": _plain(material.Material), "material_references": _references(material, doc, shape),
                "conditions": constraint_values,
                "settings": {name: _plain(getattr(solver, name)) for name in solver.PropertiesList if name != "Proxy"},
                "nodes": {int(key): [_number(v) for v in (point.x, point.y, point.z)] for key, point in mesh.FemMesh.Nodes.items()},
                "elements": {int(key): list(map(int, ids)) for key, ids in meshtools.get_femelement_volumes_table(mesh.FemMesh).items()}}
    before = native_state()
    filename = doc.FileName
    original = Path(filename) if filename else None
    original_hash = _hash(original) if original and original.is_file() else None
    root = Path(output_root).resolve() / ("F" + uuid.uuid4().hex)
    root.mkdir(parents=True, exist_ok=False)
    doc.saveCopy(str(root / "editable.FCStd"))
    if doc.FileName != filename or not (root / "editable.FCStd").is_file():
        raise ValueError("Native document copy failed or changed the live filename")
    getter = MeshSetsGetter(analysis, solver, mesh, member)
    getter.get_mesh_sets()
    writer = FemInputWriterCcx(analysis, solver, mesh, getter.member, str(root), getter.mat_geo_sets)
    written = writer.write_solver_input()
    if not written or Path(written).resolve().parent != root:
        raise ValueError("Native writer did not produce the requested snapshot input")
    inp = Path(written).resolve()
    nodes, elements, fixed, loads = _deck(inp)
    if set(nodes) != set(native_nodes) or set(elements) != set(native_elements):
        raise ValueError("Written mesh IDs differ from the existing FemMesh")
    if any(not all(_serialized_coordinate_close(b, a) for a, b in zip(nodes[key], point)) for key, point in native_nodes.items()):
        raise ValueError("Written coordinates differ from the existing FemMesh")
    if any(nodes != [native_elements[key][slot] for slot in CCX_FROM_NATIVE_TET10]
           for key, nodes in elements.items()):
        raise ValueError("Written ordered connectivity differs from the existing FemMesh")
    expected_fixed = {(int(node), component) for row in getter.member.cons_fixed for node in row["Nodes"] for component in (1, 2, 3)}
    expected_loads = []
    for row in getter.member.cons_force:
        direction = row["Object"].DirectionVector
        for _, table in row["NodeLoadTable"]:
            for node in sorted(table):
                for component, factor in enumerate((direction.x, direction.y, direction.z), 1):
                    if abs(factor) > 1e-15:
                        expected_loads.append((int(node), component, float(f"{_number((factor * table[node]).Value):.13G}")))
    if fixed != expected_fixed or sorted(loads) != sorted(expected_loads):
        raise ValueError("Written boundary/load data differ from native resolved mesh sets")
    if (not fixed or any(node not in nodes or component not in (1, 2, 3) for node, component in fixed)
            or not any(force != 0 for _, _, force in loads)
            or any(node not in nodes or component not in (1, 2, 3) for node, component, _ in loads)):
        raise ValueError("Missing or invalid resolved Fixed/Force data")
    if len({(node, component) for node, component, _ in loads}) != len(loads) or any((node, component) in fixed and force != 0 for node, component, force in loads):
        raise ValueError("Overlapping load DOFs or force on a Fixed DOF is unsupported")
    _deck_scope(inp, {"material": {"young_modulus_MPa": modulus, "poisson_ratio": ratio}})
    _json(root / "mesh.json", {"schema_version": "1", "kind": "freecad-fem-mesh",
          "units": {"position": "mm", "displacement": "mm", "force": "N", "stress": "MPa"},
          "nodes": [{"node_id": key, "position_mm": nodes[key], "native_position_mm": native_nodes[key]} for key in sorted(nodes)],
          "elements": [{"element_id": key, "type": "C3D10", "node_ids": elements[key],
                        "native_node_ids": native_elements[key]} for key in sorted(elements)],
          "native_to_deck_slots": list(CCX_FROM_NATIVE_TET10),
          "fixed_dofs": [{"node_id": node, "component": component, "value_mm": 0.} for node, component in sorted(fixed)],
          "loads": [{"node_id": node, "component": component, "force_N": force} for node, component, force in loads],
          "coordinate_comparison": {"significant_digits": 13, "rounding_ulps": 8, "purpose": "native serialization identity only"}})
    if (before != native_state() or doc.FileName != filename or doc.isTouched()
            or (binding_validator is not None and binding_validator(mesh) != binding)
            or any(set(obj.State) & {"Touched", "Invalid", "Error", "Recompute"} for obj in doc.Objects)
            or (original_hash and _hash(original) != original_hash)
            or native_material != _plain(material.Material)
            or settings != {name: _plain(getattr(solver, name)) for name in solver.PropertiesList if name != "Proxy"}):
        raise ValueError("Live document or original file changed during export")
    files = [{"relative": path.name, "bytes": path.stat().st_size, "sha256": _hash(path)}
             for path in sorted(root.iterdir()) if path.is_file()]
    if {row["relative"] for row in files} != {"editable.FCStd", "mesh.json", inp.name}:
        raise ValueError("Unexpected native writer dependencies")
    manifest = root / "snapshot.json"
    _json(manifest, {"schema_version": "1", "kind": "freecad-fem-frozen", "id": root.name,
          "native_version": list(App.Version()), "document": {"name": doc.Name, "original_sha256": original_hash},
          "analysis": _identity(analysis, femutils), "solver": dict(_identity(solver, femutils), settings=settings),
          "mesh": _identity(mesh, femutils), "shape": dict(_identity(shape, femutils), solid_count=1),
          "mesh_source_binding": binding,
          "material": dict(_identity(material, femutils), law="isotropic_linear_elastic", references=material_refs,
                           native_values=native_material, young_modulus_MPa=modulus, poisson_ratio=ratio),
          "conditions": conditions, "input_file": inp.name, "files": files,
          "solver_execution": "NOT_PERFORMED", "qualification": "NOT_ASSESSED",
          "limits": ["3D single-solid C3D10 static linear elasticity; Fixed/Force only",
                     "No remesh, solver execution, contact, amplitudes or split includes",
                     "Export admission is not rigid-mode, Jacobian or physical validation",
                     "Native output: displacement/stress/total-strain FRD; reaction totals DAT; no per-node U/RF DAT"]})
    return manifest


def freeze_analysis(analysis, solver, output_root, *, binding_validator=None):
    """Export the selected native Analysis using FreeCAD's CalculiX writer."""
    from .native_calculix import export_analysis
    return export_analysis(analysis, solver, output_root, binding_validator=binding_validator)
