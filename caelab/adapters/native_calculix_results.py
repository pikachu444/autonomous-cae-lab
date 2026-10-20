"""Publish FreeCAD's native FRD conversion as a ParaView time collection."""
import math
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from ..execution_control import run_owned_command
from ..storage import load_json, save_json
from .vtu import data_array


def inspect_frd(path, *, require_displacement=True):
    """Observe record coverage so the native converter cannot fill missing data with zero.

    FreeCAD FemVTKTools.cpp initializes arrays with zero. This reader retains
    original node coverage; the official converter still owns mesh/field values.
    """
    nodes, frames, current, field = [], {}, None, None
    section, count, digits, ended = None, 0, 10, False
    with Path(path).open(encoding="ascii") as stream:
        for raw in stream:
            line = raw.rstrip()
            parts = line.split()
            if not parts:
                continue
            if ended:
                raise ValueError("Unexpected data after the CalculiX result terminator")
            if parts[0] in {"2C", "3C"}:
                if len(parts) != 3 or parts[2] not in {"0", "1"}:
                    raise ValueError("This FreeCAD result connection requires ASCII FRD output")
                section, count = parts[0], int(parts[1])
                digits = 10 if parts[2] == "1" else 5
            elif line.startswith("  100C"):
                value = float(line[12:24])
                count = int(line[24:36])
                analysis_type = line[56:58].strip()
                increment = int(line[58:63])
                if not math.isfinite(value) or count < 0:
                    raise ValueError("Invalid CalculiX result frame")
                current = frames.setdefault((increment, analysis_type), {
                    "value": value, "step": increment, "analysis_type": analysis_type, "fields": {}})
                if current["value"] != value:
                    raise ValueError("CalculiX fields disagree on their output increment")
                digits = 10 if line[74:75] == "1" else 5
            elif parts[0] == "-4":
                if current is None or field is not None:
                    raise ValueError("Incomplete CalculiX field header")
                name = parts[1]
                if name in current["fields"]:
                    raise ValueError("Duplicate CalculiX field in one output increment")
                field = {"name": name, "ids": set(), "arrays": set(), "components": {}, "expected": count}
                current["fields"][name] = field
            elif parts[0] == "-5" and field is not None:
                # Native entity columns: name, menu, type, row, column, existence.
                if len(parts) < 6:
                    raise ValueError("Incomplete CalculiX component declaration")
                if len(parts) > 6 and parts[6].startswith("1"):
                    continue  # Predefined magnitude has no stored values.
                array_name = parts[1] if parts[3] == "1" or int(parts[4]) < 1 else field["name"]
                field['arrays'].add(array_name)
                field['components'].setdefault(array_name, []).append(parts[1])
            elif parts[0] == "-1":
                identifier = int(line[3:3 + digits])
                if section == "2C":
                    nodes.append(identifier)
                elif field is not None:
                    if identifier in field["ids"]:
                        raise ValueError("Duplicate CalculiX nodal result")
                    field["ids"].add(identifier)
            elif parts[0] == "-3":
                if section == "2C" and (len(nodes) != count or len(set(nodes)) != len(nodes)):
                    raise ValueError("Incomplete or duplicate CalculiX geometry nodes")
                section = None
                if field is not None:
                    if len(field["ids"]) != field["expected"]:
                        raise ValueError("CalculiX result field is truncated")
                    field = None
            elif parts == ["9999"]:
                if section is not None or field is not None:
                    raise ValueError("CalculiX result is incomplete")
                ended = True
    if not ended or not nodes or not frames:
        raise ValueError("CalculiX did not write a complete result file; inspect its original logs")
    for frame in frames.values() if require_displacement else ():
        displacement = frame["fields"].get("DISP")
        if displacement is None or not set(nodes) <= displacement["ids"]:
            raise ValueError("CalculiX displacement output is missing mesh nodes")
    return nodes, list(frames.values())


def _freecad_command(configured=None):
    command = os.environ.get("FREECAD_CMD") or shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
    if command:
        return str(Path(command).resolve(strict=True))
    from ..native_tools import discover, saved_executable
    found = discover("freecad_executable", context={"freecad_executable": configured} if configured else None,
                     saved=saved_executable("freecad_executable"))
    if found["status"] == "FOUND":
        gui = Path(found["path"])
        for folder in (gui.parent, gui.parent / "bin"):
            for name in ("FreeCADCmd.exe", "freecadcmd", "FreeCADCmd"):
                candidate = folder / name
                if candidate.is_file():
                    return str(candidate)
    raise RuntimeError("FreeCADCmd was not found. Set the installed FreeCAD path to convert the solver result.")


def convert(frd, output, manifest, *, freecad_executable=None):
    frd, output = Path(frd), Path(output)
    node_ids, frames = inspect_frd(frd)
    expected_end = sum(step["period"] for step in manifest["steps"])
    # FRD's time is E12.5; only printed rounding, not a convergence tolerance.
    if not math.isclose(frames[-1]["value"], expected_end, rel_tol=5e-6, abs_tol=1e-12):
        raise ValueError("The solver stopped before the requested final static increment; original output is retained")
    post = output / "post"
    _convert_native(frd, post, freecad_executable=freecad_executable)
    return publish_conversion(post, manifest, node_ids, frames)


def _convert_native(frd, post, *, freecad_executable=None):
    post.mkdir(parents=True)
    request = post / "conversion.json"
    save_json(request, {"source": str(frd.resolve()), "output": str(post.resolve())})
    worker = Path(__file__).with_name("freecad_frd_worker.py")
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(key, None)
    env["CAELAB_FRD_CONVERSION"] = str(request.resolve())
    converted = run_owned_command([_freecad_command(freecad_executable), str(worker)], post, "freecad_result",
                                  env=env, owned_tree=True, timeout=120)
    if converted.returncode:
        raise RuntimeError("FreeCAD could not convert the CalculiX result; see the retained conversion log")
    receipt = load_json(post / "converted.json")
    if receipt.get("error"):
        raise ValueError(receipt["error"])


def convert_independent(frd, output, *, freecad_executable=None):
    """Convert observed output without assigning a model's units or run status."""
    frd, output = Path(frd).resolve(strict=True), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    retained = output / frd.name
    shutil.copyfile(frd, retained)
    node_ids, frames = inspect_frd(retained, require_displacement=False)
    post = output / 'post'
    _convert_native(retained, post, freecad_executable=freecad_executable)
    result = publish_conversion(post, {}, node_ids, frames, managed=False)
    return {'entry_path': str(post / 'results.pvd'), 'original_path': str(frd),
            'retained_path': str(retained), 'summary': result['native_field_summary'],
            'output_increment_count': len(frames), 'execution_status': None,
            'units': None, 'time_semantics': None}


def publish_conversion(post, manifest, node_ids, frames, *, managed=True):
    """Index native VTU blocks without rebuilding or approximating their topology."""
    files = []
    for path in sorted(Path(post).rglob("*.vtu")):
        tree = ET.parse(path)
        time = tree.find(".//FieldData/DataArray[@Name='TimeValue']")
        if time is None or not time.text:
            raise ValueError("FreeCAD result has no native output increment value")
        files.append((float(time.text.strip()), path, tree))
    files.sort(key=lambda row: row[0])
    ordered_frames = sorted(frames, key=lambda frame: frame['value'])
    if len(files) != len(frames):
        raise ValueError("FreeCAD conversion omitted or duplicated a solver output increment")
    collection = ET.Element("VTKFile", type="Collection", version="0.1", byte_order="LittleEndian")
    datasets = ET.SubElement(collection, "Collection")
    final_arrays, vectors, coordinates, field_summary, frame_summaries = [], [], [], [], []
    if not managed and any(b['value'] <= a['value'] for a, b in zip(ordered_frames, ordered_frames[1:])):
        raise ValueError('Repeated FRD output coordinates cannot be represented unambiguously by this PVD reader; open the native VTM result in ParaView')
    for (value, path, tree), frame in zip(files, ordered_frames if not managed else frames):
        vectors = []
        if not math.isclose(value, frame["value"], rel_tol=1e-6, abs_tol=1e-12):
            raise ValueError("FreeCAD output increment differs from the native result")
        piece = tree.find(".//Piece")
        if piece is None or int(piece.get("NumberOfPoints", "0")) != len(node_ids):
            raise ValueError("FreeCAD result changed the native result mesh node count")
        point_data = piece.find("PointData")
        if point_data is None:
            raise ValueError("FreeCAD result has no nodal fields")
        arrays = []
        field_summary = []
        for array in point_data.findall("DataArray"):
            name = array.get("Name", "")
            width = int(array.get("NumberOfComponents", "1"))
            if array.get("format") != "ascii":
                raise ValueError("The result converter did not produce requested ASCII arrays")
            field = next((f for f in frame["fields"].values() if name in f["arrays"]), None)
            if field is None:
                raise ValueError("A converted array has no original solver field: " + name)
            values = [float(v) for v in (array.text or "").split()]
            if len(values) != width * len(node_ids):
                raise ValueError("Incomplete converted nodal array: " + name)
            missing = [i for i, node in enumerate(node_ids) if node not in field["ids"]]
            if missing:
                for i in missing:
                    values[i * width:(i + 1) * width] = [math.nan] * width
                point_data.remove(array)
                array = data_array(point_data, name, values, width)
            component_names = field.get('components', {}).get(name, [])
            if len(component_names) == width:
                for i, component_name in enumerate(component_names):
                    array.set('ComponentName' + str(i), component_name)
            unit, measure = _field_meaning(field["name"], name)
            arrays.append({"name": name, "association": "POINTS", "components": width,
                           "units": unit if managed else None,
                           "frame": ("FREECAD_DOCUMENT_GLOBAL" if field["name"] != "CONTACT" else "CONTACT_LOCAL") if managed else None,
                           "measure": measure})
            if len(component_names) == width:
                arrays[-1]['component_names'] = component_names
            ranges = []
            for component in range(width):
                column = values[component::width]
                finite = [v for v in column if math.isfinite(v)]
                ranges.append({"minimum": min(finite) if finite else None,
                               "maximum": max(finite) if finite else None,
                               "finite_count": len(finite), "missing_count": len(column) - len(finite)})
            field_summary.append({**arrays[-1], "ranges": ranges})
            if name == "DISP":
                if managed and (width != 3 or not all(math.isfinite(v) for v in values)):
                    raise ValueError("Native displacement contains failed or missing values")
                vectors = [values[i:i + 3] for i in range(0, len(values), 3)]
        data_array(point_data, "NativeNodeId", node_ids, integer=True)
        arrays.append({"name": "NativeNodeId", "association": "POINTS", "components": 1,
                       "units": "1", "frame": "not_applicable", "measure": "identity"})
        tree.write(path, encoding="utf-8", xml_declaration=True)
        ET.SubElement(datasets, "DataSet", timestep=format(frame["value"], ".17g"), group="", part="0",
                      file=path.relative_to(post).as_posix())
        position = piece.find("Points/DataArray")
        xyz = [float(v) for v in position.text.split()]
        coordinates = [xyz[i:i + 3] for i in range(0, len(xyz), 3)]
        final_arrays = arrays
        frame_summaries.append({**{key: frame.get(key) for key in ('value', 'step', 'analysis_type')},
                                'fields': field_summary})
    if managed and not vectors:
        raise ValueError("No readable native displacement field was returned")
    path = Path(post) / "results.pvd"
    ET.ElementTree(collection).write(path, encoding="utf-8", xml_declaration=True)
    if not managed:
        return {'native_field_summary': {'output_value': frame_summaries[-1]['value'],
            'output_values': [frame['value'] for frame in frame_summaries],
            'native_output_order': [{key: frame.get(key) for key in ('value', 'step', 'analysis_type')} for frame in frames],
            'time_units': None,
            'frames': frame_summaries,
            'time_semantics': None, 'association': 'POINTS', 'fields': field_summary,
            'limitations': 'Units, coordinate basis, clock meaning and solver completion are not established by this FRD file.'}}
    metadata = {"coordinate_units": "mm", "coordinate_frame": "FREECAD_DOCUMENT_GLOBAL", "static": None,
                "time": {"unit": "1", "semantics": "STATIC_LOAD_PARAMETER", "values": [frame["value"] for frame in frames]},
                "arrays": final_arrays}
    field_metadata = {"node_ids": node_ids, "coordinates_mm": coordinates, "position_unit": "mm",
                      "coordinate_frame": "FREECAD_DOCUMENT_GLOBAL", "association": "POINTS",
                      "source": "native CalculiX FRD via FreeCAD Fem.frdToVTK", "interpolated": False,
                      "load_parameter": frames[-1]["value"]}
    responses = {"displacement": {"kind": "field", "unit": "mm", "value": vectors,
                  "component": "VECTOR", "location": "native_result_nodes", "reduction": "none", "metadata": field_metadata},
                 "max_displacement": {"kind": "scalar", "unit": "mm", "value": max(math.hypot(*v) for v in vectors),
                  "component": "VECTOR_MAGNITUDE", "location": "native_result_nodes", "reduction": "max", "metadata": field_metadata}}
    return {"responses": responses, "post_artifact": {"relative": "post/results.pvd", "native_metadata": metadata},
            "result_readability": "READABLE", "verification_case": manifest.get("verification_case", "없음"),
            "final_native_fields": list(frames[-1]["fields"]), "output_increment_count": len(frames),
            "native_field_summary": {"load_parameter": frames[-1]["value"], "association": "POINTS",
                "fields": field_summary, "limitations": "Nodal values from the solver, including extrapolation; these ranges are not integration-point material validation."},
            "limitations": ["Solver output is readable; numerical validity and engineering qualification have not been assessed.",
                            "Beam and shell fields use the solver's actual output geometry and reported field basis."]}


def _field_meaning(field, name):
    if field == "CONTACT":
        return ("MPa", "contact_stress") if name in {"CPRESS", "CSHEAR1", "CSHEAR2"} else ("mm", "contact_displacement")
    return {"DISP": ("mm", "displacement"), "STRESS": ("MPa", "stress"),
            "TOSTRAIN": ("1", "total_strain"), "PE": ("1", "equivalent_plastic_strain"),
            "FORC": ("N", "force"), "ERROR": ("%", "solver_error_estimate")}.get(field, (None, "native_solver_field"))
