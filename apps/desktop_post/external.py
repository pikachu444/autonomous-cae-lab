"""Independent VTU/PVD analysis using native ParaView readers and PVSM state.

Run in the native ParaView Python environment. Input paths are exact local files;
managed callers supply the entry path of their registered dependency snapshot.
"""
from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import uuid
import xml.etree.ElementTree as ET

from paraview import simple as p, servermanager

try:
    from .commands import sha, reader_input_files
except ImportError:
    from commands import sha, reader_input_files


KIND = "external-result"
READERS = {".vtu": "XMLUnstructuredGridReader", ".pvd": "PVDReader", ".vtt": "XMLTableReader"}
_recovery = []
_recovery_state = None


def recovery_records():
    return deepcopy(_recovery)


def contact_api():
    # Native portable Python loads this file without installing the repository.
    import sys
    repository = str(Path(__file__).resolve().parents[2])
    sys.path.insert(0, repository)
    try:
        from caelab import contact_inspection
        return contact_inspection
    finally:
        sys.path.remove(repository)


def shell_api():
    import sys
    repository = str(Path(__file__).resolve().parents[2])
    sys.path.insert(0, repository)
    try:
        from caelab import shell_inspection
        return shell_inspection
    finally:
        sys.path.remove(repository)


def source_files(entry, native_metadata=None):
    """Validate and enumerate a bounded, local PVD+VTU dependency set."""
    entry = Path(entry).resolve(strict=True)
    if not entry.is_file() or entry.suffix.lower() not in READERS:
        raise ValueError("Supported result inputs are VTU and PVD with relative VTU frames")
    files = [entry]
    if entry.suffix.lower() == ".pvd":
        maximum = 8 * 1024 * 1024
        if entry.stat().st_size > maximum:
            raise ValueError("PVD collection metadata exceeds 8 MiB")
        with entry.open("rb") as stream:
            payload = stream.read(maximum + 1)
        if len(payload) > maximum:
            raise ValueError("PVD collection metadata exceeds 8 MiB")
        text = payload.decode("utf-8-sig")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("PVD declarations and entities are not supported")
        try:
            root = ET.fromstring(text)
        except ET.ParseError as error:
            raise ValueError("Invalid PVD collection XML: " + str(error)) from error
        if root.tag != "VTKFile" or root.get("type") != "Collection":
            raise ValueError("PVD must contain a VTK Collection")
        datasets = root.findall("./Collection/DataSet")
        if not datasets:
            raise ValueError("PVD contains no frame datasets")
        if len(datasets) > 1024:
            raise ValueError("PVD supports at most 1024 datasets")
        references = []
        for dataset in datasets:
            reference = dataset.get("file", "")
            relative = Path(reference)
            if (not reference or "\\" in reference or ":" in reference or "\x00" in reference
                    or relative.anchor or PureWindowsPath(reference).anchor or ".." in relative.parts):
                raise ValueError("PVD frames must be relative local VTU paths inside the input set")
            if relative.suffix.lower() != ".vtu":
                raise ValueError("PVD supports only contained VTU frame files")
            try:
                time = float(dataset.attrib["timestep"])
            except (KeyError, ValueError) as error:
                raise ValueError("Each PVD frame needs a finite numeric timestep") from error
            if not math.isfinite(time):
                raise ValueError("Each PVD frame needs a finite numeric timestep")
            references.append(relative)
        for relative in references:
            frame = (entry.parent / relative).resolve(strict=True)
            if not frame.is_relative_to(entry.parent) or not frame.is_file():
                raise ValueError("PVD supports only contained VTU frame files")
            if frame not in files:
                files.append(frame)
    if entry.suffix.lower() == ".vtt" and native_metadata is not None:
        from caelab.post_curves import load_curve
        _, sidecar = load_curve(entry, native_metadata)
        files.append(sidecar)
    declaration = (native_metadata or {}).get("contact_inspection")
    if declaration is not None:
        bundle = contact_api().load(entry, declaration)
        if bundle['manifest']['native_metadata'] != {k: v for k, v in native_metadata.items() if k != 'contact_inspection'}:
            raise ValueError('Contact field declarations differ from the pinned bundle')
        files = list(dict.fromkeys([*files, *bundle["paths"]]))
    declaration = (native_metadata or {}).get("shell_inspection")
    if declaration is not None:
        bundle = shell_api().load(entry, declaration)
        if bundle['manifest']['native_metadata'] != {k: v for k, v in native_metadata.items() if k != 'shell_inspection'}:
            raise ValueError('Shell field declarations differ from the retained bundle')
        files = list(dict.fromkeys([*files, *bundle['paths']]))
    return files


def pins(files):
    return [{"path": str(file), "bytes": file.stat().st_size, "sha256": sha(file)} for file in files]


def verify_sources(path, doc):
    for record in doc["sources"].values():
        recorded = record["source_pins"]
        for pin in recorded:
            file = Path(pin["path"])
            if file.stat().st_size != pin["bytes"] or sha(file) != pin["sha256"]:
                raise RuntimeError("Original retained data changed: " + str(file))
        if set(map(str, source_files(record["entry_path"], record.get("native_metadata")))) != {pin["path"] for pin in recorded}:
            raise RuntimeError("Result dependency set does not match its recorded source pins")
    return path, doc


def verify_readers(doc):
    registered = p.GetSources()
    for record in list(doc["sources"].values()) + doc.get("native_readers", []):
        readers = [source for (label, _), source in registered.items() if label == record["reader_name"]]
        if len(readers) != 1 or readers[0].GetXMLName() != record["reader_type"]:
            raise RuntimeError("External result reader missing, duplicated or replaced: " + record["reader_name"])
        expected = record.get("input_paths", [record.get("entry_path")])
        if reader_input_files(readers[0]) != [Path(file).resolve(strict=True) for file in expected]:
            raise RuntimeError("External result reader path mismatch: " + record["reader_name"])


def times(source):
    return [float(value) for value in getattr(source, "TimestepValues", [])]


def set_time(source, time=None):
    available = times(source)
    if time is not None:
        if isinstance(time, bool) or not math.isfinite(float(time)) or float(time) not in available:
            raise ValueError("Choose an exact native timestep from " + str(available))
        selected = float(time)
    elif available:
        current = float(p.GetAnimationScene().AnimationTime)
        selected = current if current in available else available[0]
    else:
        source.UpdatePipeline()
        return None
    p.GetAnimationScene().AnimationTime = selected
    source.UpdatePipeline(time=selected)
    view = p.GetActiveView()
    if view is not None and view.GetXMLName() == "RenderView":
        view.ViewTime = selected
    return selected


def _metadata_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate_declared_metadata(source, metadata):
    """Validate an explicit source-owner declaration against exact native arrays."""
    if isinstance(metadata, dict) and 'curve' in metadata:
        if set(metadata) != {'curve'} or source.GetXMLName() != 'XMLTableReader':
            raise ValueError('Curve metadata belongs to its exact registered table reader')
        from caelab.post_curves import load_curve
        curve, _ = load_curve(reader_input_files(source)[0], metadata)
        data = servermanager.Fetch(source)
        if not data.IsA('vtkTable') or data.GetNumberOfRows() != len(curve['rows']):
            raise ValueError('Native table differs from its pinned source rows')
        for name, field in (('axis', 'x'), ('value', 'y')):
            array = data.GetColumnByName(name)
            if array is None or array.GetNumberOfComponents() != 1:
                raise ValueError('Native curve column is missing')
            for i, row in enumerate(curve['rows']):
                actual, expected = array.GetTuple1(i), row[field]
                if not (math.isnan(actual) if expected is None else actual == expected):
                    raise ValueError('Native curve values differ from the exact Data snapshot')
        return deepcopy(metadata)
    required_keys = {"coordinate_units", "coordinate_frame", "static", "arrays"}
    shell = isinstance(metadata, dict) and 'shell_inspection' in metadata
    shell_keys = set()
    if shell:
        inputs = reader_input_files(source)
        if len(inputs) != 1:
            raise ValueError('Shell declaration requires its exact retained surface reader')
        bundle = shell_api().load(inputs[0], metadata['shell_inspection'])
        if bundle['manifest']['native_metadata'] != {k: v for k, v in metadata.items() if k != 'shell_inspection'}:
            raise ValueError('Shell field declarations differ from the retained bundle')
        shell_keys = set(bundle['manifest']['native_metadata']) | {'shell_inspection'}
    if not isinstance(metadata, dict) or not required_keys <= set(metadata) or set(metadata) - required_keys - {"time", "contact_inspection", "field_availability", "field_meanings"} - shell_keys:
        raise ValueError("Native metadata requires coordinate units/frame, explicit state/clock and declared arrays")
    if "contact_inspection" in metadata:
        contact_api().descriptor(metadata["contact_inspection"])
    for key in ("coordinate_units", "coordinate_frame"):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise ValueError("Native coordinate units and frame must be explicitly declared")
    static = metadata["static"]
    clock = metadata.get("time")
    if static is not None:
        if not isinstance(static, dict) or set(static) != {"step", "increment", "load_parameter"} or clock is not None:
            raise ValueError("Static metadata requires step, increment and load_parameter; it is not time in seconds")
        if any(type(static[key]) is not int or static[key] < 1 for key in ("step", "increment")):
            raise ValueError("Static step and increment must be positive integers")
        if type(static["load_parameter"]) not in (int, float) or not math.isfinite(static["load_parameter"]):
            raise ValueError("Static load parameter must be finite")
    elif "time" not in metadata:
        raise ValueError("A declared field must explicitly distinguish no clock from an omitted clock")
    if clock is None:
        if source.GetXMLName() != "XMLUnstructuredGridReader" or times(source):
            raise ValueError("Declared non-temporal metadata requires its exact VTU reader")
    else:
        if (not isinstance(clock, dict) or set(clock) != {"unit", "semantics", "values"}
                or not ((clock["unit"] == "1" and clock["semantics"] in {"DIMENSIONLESS_MODEL_TIME", "STATIC_LOAD_PARAMETER"})
                        or (clock["unit"] == "s" and isinstance(clock["semantics"], str) and clock["semantics"].strip()))
                or not isinstance(clock["values"], list) or not clock["values"]
                or any(type(t) not in (int, float) or not math.isfinite(t) for t in clock["values"])
                or any(b <= a for a, b in zip(clock["values"], clock["values"][1:]))
                or source.GetXMLName() != "PVDReader" or times(source) != clock["values"]):
            raise ValueError("Declared dimensionless/seconds clock differs from the exact native PVD timesteps")
    arrays = metadata["arrays"]
    if "field_meanings" in metadata:
        from caelab.calculix_material import result_meanings
        if metadata["field_meanings"] not in [result_meanings(value) for value in (None, False, True)]:
            raise ValueError("Native field meanings differ from the supported CalculiX declarations")
    if "field_availability" in metadata:
        availability = metadata["field_availability"]
        if not isinstance(availability, dict) or set(availability) != {"FORC", "STRESS", "TOSTRAIN", "PE"}:
            raise ValueError("Native field availability requires the declared CalculiX fields")
        for record in availability.values():
            if (not isinstance(record, dict) or set(record) != {"present_frames", "total_frames", "missing_policy"}
                    or type(record["present_frames"]) is not int or type(record["total_frames"]) is not int
                    or record["total_frames"] != (len(clock["values"]) if clock else 1)
                    or not 0 <= record["present_frames"] <= record["total_frames"]
                    or record["missing_policy"] != "unavailable; no zero fill"):
                raise ValueError("Native field availability differs from the retained frame collection")
    if not isinstance(arrays, list) or not arrays or len(arrays) > 128:
        raise ValueError("Declare a bounded nonempty array list")
    seen = set()
    for declaration in arrays:
        required = {"association", "name", "components", "units", "frame", "measure"}
        if not isinstance(declaration, dict) or not required <= set(declaration) or set(declaration) - required - {"component_names", "quantity", "recovery", "shear_convention"} - ({'location'} if shell else set()):
            raise ValueError("Each declared array requires exact association/name/components and units/frame/measure")
        for key in ("name", "units", "frame", "measure"):
            if not isinstance(declaration[key], str) or not declaration[key].strip():
                raise ValueError("Declared array meaning must be nonempty explicit text")
        if 'quantity' in declaration and (not isinstance(declaration['quantity'], str) or not declaration['quantity'].strip()):
            raise ValueError('Declared quantity must be explicit nonempty text')
        shell_recovery = {'native_nodal_dof', 'magnitude_of_native_vector',
                          'native_extrapolated_nodal_averaged',
                          'basis_change_of_native_nodal_recovery'} if shell else set()
        if 'recovery' in declaration and (not isinstance(declaration['recovery'], str) or declaration['recovery'] not in {
                'native nodal force; reactions only at restrained DOFs',
                'native integration-point extrapolation and nodal averaging'} | shell_recovery):
            raise ValueError('Unsupported native field recovery declaration')
        if 'shear_convention' in declaration and declaration['shear_convention'] != 'tensor_shear_not_engineering_shear':
            raise ValueError('Unsupported native tensor shear convention')
        association = declaration["association"]
        if association not in ("POINTS", "CELLS", "FIELD"):
            raise ValueError("Declared array association must match POINTS, CELLS or FIELD")
        identity = association, declaration["name"]
        if identity in seen:
            raise ValueError("Declared array identities must be distinct")
        seen.add(identity)
        data = {"POINTS": source.PointData, "CELLS": source.CellData, "FIELD": source.FieldData}[association]
        if declaration["name"] not in data.keys():
            raise ValueError("Declared array is absent from its exact native association: " + str(identity))
        array = data[declaration["name"]]
        count = declaration["components"]
        if type(count) is not int or count < 1 or count != array.GetNumberOfComponents():
            raise ValueError("Declared array component count differs from the native source")
        if "component_names" in declaration and declaration["component_names"] != [array.GetComponentName(i) for i in range(count)]:
            raise ValueError("Declared component names differ from the native source")
    return deepcopy(metadata)


def _same_proxy(a, b):
    a, b = getattr(a, "SMProxy", a), getattr(b, "SMProxy", b)
    if hasattr(a, "GetGlobalIDAsString") and hasattr(b, "GetGlobalIDAsString"):
        return a.GetGlobalIDAsString() == b.GetGlobalIDAsString()
    return a is b


def _source_metadata(source):
    """Only the exact pinned original reader may use a retained declaration."""
    location = os.environ.get("CAE_POST_PROJECT")
    if not location or not Path(location).is_file():
        return None
    path = Path(location)
    try:
        from . import commands
    except ImportError:
        import commands
    path, doc = commands.project()
    if doc.get("kind") != KIND:
        return None
    for record in doc.get("sources", {}).values():
        if record.get("native_metadata") is None:
            continue
        readers = [candidate for (label, _), candidate in p.GetSources().items()
                   if label == record["reader_name"]]
        if len(readers) != 1 or not _same_proxy(readers[0], source):
            continue  # No derived/filter mapping is implied by its input lineage.
        if source.GetXMLName() != record["reader_type"]:
            raise RuntimeError("Declared source reader type changed")
        if reader_input_files(source) != [Path(record["entry_path"]).resolve(strict=True)]:
            raise RuntimeError("Declared source reader path changed")
        if not record.get("input_id") or _metadata_hash(record["native_metadata"]) != record.get("native_metadata_sha256"):
            raise RuntimeError("Retained native metadata identity changed or lacks a registered input")
        verify_sources(path, {**doc, 'sources': {'selected': record}})
        return validate_declared_metadata(source, record["native_metadata"])
    return None


def inspect_result(source, time=None):
    return _inspect_result(source, time, _source_metadata(source))


def _inspect_result(source, time=None, native_metadata=None):
    selected = set_time(source, time)
    declaration = validate_declared_metadata(source, native_metadata) if native_metadata is not None else None
    if declaration and 'curve' in declaration:
        from caelab.post_curves import load_curve
        curve, _ = load_curve(reader_input_files(source)[0], declaration)
        return {'reader': source.GetXMLName(), 'points': 0, 'cells': 0, 'rows': len(curve['rows']),
                'timesteps': [], 'arrays': [], 'curve': {'title': curve['title'],
                'declaration': curve['declaration'], 'axis': curve['axis']}, 'qualification': 'UNKNOWN'}
    declared = {(row["association"], row["name"]): row for row in declaration["arrays"]} if declaration else {}
    info = source.GetDataInformation()
    arrays = []
    for association, data in (("POINTS", source.PointData), ("CELLS", source.CellData), ("FIELD", source.FieldData)):
        for name in data.keys():
            array = data[name]
            components = array.GetNumberOfComponents()
            arrays.append({"name": name, "association": association, "components": components,
                           "component_names": [array.GetComponentName(i) for i in range(components)],
                           "range": [value if math.isfinite(value) else None for value in array.GetRange()],
                           **{key: declared.get((association, name), {}).get(key) for key in ("units", "frame", "measure", "quantity", "recovery", "shear_convention")},
                           "metadata_status": "DECLARED" if (association, name) in declared else "UNKNOWN"})
    return {"reader": source.GetXMLName(), "points": info.GetNumberOfPoints(),
            "cells": info.GetNumberOfCells(), "bounds": list(info.GetBounds()),
            "timesteps": times(source), "time": selected,
            "time_units": (declaration.get("time") or {}).get("unit") if declaration else None,
            "time_semantics": (declaration.get("time") or {}).get("semantics") if declaration else None,
            "coordinate_units": declaration["coordinate_units"] if declaration else None,
            "coordinate_frame": declaration["coordinate_frame"] if declaration else None,
            "static": deepcopy(declaration["static"]) if declaration else None,
            "field_availability": deepcopy(declaration.get("field_availability")) if declaration else None,
            "metadata_status": "DECLARED" if declaration else "UNKNOWN",
            "arrays": arrays, "qualification": "UNKNOWN"}


def select_array(source, association, array, component=None, time=None, view=None):
    view = p.GetActiveView() if view is None else view
    if view is None or view.GetXMLName() != "RenderView":
        raise RuntimeError("Select a native Render view")
    available = times(source)
    if time is not None:
        if isinstance(time, bool) or not math.isfinite(float(time)) or float(time) not in available:
            raise ValueError("Choose an exact native timestep from " + str(available))
    elif available and float(p.GetAnimationScene().AnimationTime) not in available:
        raise ValueError("Choose an exact native timestep from " + str(available))
    if association not in ("POINTS", "CELLS"):
        raise ValueError("Select an existing POINTS or CELLS array; association conversion is explicit")
    data = source.PointData if association == "POINTS" else source.CellData
    if array not in data.keys():
        raise ValueError("Select an existing POINTS or CELLS array; association conversion is explicit")
    component_names = [data[array].GetComponentName(i) for i in range(data[array].GetNumberOfComponents())]
    if component is not None and component != "Magnitude" and component not in component_names:
        raise ValueError("Unknown native array component: " + str(component))
    # Validate source declarations before changing native time or active view.
    native_metadata = _source_metadata(source)
    p.SetActiveView(view)
    metadata = _inspect_result(source, time, native_metadata)
    display = p.Show(source, view)
    selection = (association, array) if component is None else (association, array, component)
    p.ColorBy(display, selection)
    display.RescaleTransferFunctionToDataRange(True, False)
    display.SetScalarBarVisibility(view, True)
    p.SetActiveSource(source)
    selected_metadata = next(row for row in metadata["arrays"] if row["association"] == association and row["name"] == array)
    if native_metadata and 'shell_inspection' in native_metadata:
        titles = {'U_mm': 'Displacement', 'U_magnitude_mm': 'Displacement magnitude',
                  'S_surface_recovered': 'Surface stress (recovered)',
                  'E_surface_recovered': 'Surface strain (recovered)',
                  'S_surface_local': 'Local surface stress (recovered)',
                  'E_surface_local': 'Local surface strain (recovered)',
                  'ShellSide': 'Shell side', 'NativeElementId': 'Element number',
                  'NativeNodeId': 'Expanded node number', 'ShellNodeId': 'Shell node number',
                  'Normal_native': 'Surface normal'}
        if array in titles:
            transfer = p.GetColorTransferFunction(array)
            p.UpdateScalarBarsComponentTitle(transfer, display)
            bar = p.GetScalarBar(transfer, view)
            unit = selected_metadata['units']
            bar.Title = titles[array] + (' [' + unit + ']' if unit != '1' else '')
    return {"association": association, "array": array, "component": component,
            "time": metadata["time"], "time_units": metadata["time_units"], "time_semantics": metadata["time_semantics"],
            **{key: selected_metadata[key] for key in ("units", "frame", "measure", "metadata_status", "recovery", "shear_convention")},
            **{key: deepcopy(metadata[key]) for key in ("coordinate_units", "coordinate_frame", "static")}}


def physical_input(source, arrays):
    """Allow only explicitly selected response arrays into spatial interpolation."""
    source.UpdatePipeline()
    identity = {"nativenodeid", "nativeelementid", "globalnodeid", "globalelementid", "vtkoriginalpointids", "vtkoriginalcellids", "globalids", "pedigreeids"}
    grouped = {"POINTS": [], "CELLS": []}
    for association, name in arrays:
        if association not in grouped or name.lower().endswith(("_input","_applicable")) or name.lower() in {"erosion_status","vtkghosttype"} or re.search(r"(?:^|_)ids?$|Ids?$|IDs?$", name) or name.lower() in identity:
            raise ValueError("Identity/classification arrays cannot be spatially interpolated: " + name)
        data = source.PointData if association == "POINTS" else source.CellData
        if name not in data.keys():
            raise ValueError("Selected response array does not exist: " + name)
        grouped[association].append(name)
    selected = p.PassArrays(registrationName="Spatial sampling | selected response arrays only", Input=source)
    selected.PointDataArrays = grouped["POINTS"]
    selected.CellDataArrays = grouped["CELLS"]
    selected.FieldDataArrays = []
    selected.UpdatePipeline()
    return selected


def _verify_metadata_records(doc, *, live=False):
    for record in doc.get("sources", {}).values():
        metadata = record.get("native_metadata")
        if metadata is None:
            continue
        if not record.get("input_id") or _metadata_hash(metadata) != record.get("native_metadata_sha256"):
            raise RuntimeError("Retained native metadata identity changed or lacks a registered input")
        if live:
            validate_declared_metadata(p.FindSource(record["reader_name"]), metadata)


def save_project(path, doc, *, prepare=None):
    try:
        from .source_repair import source_issues
    except ImportError:
        from source_repair import source_issues
    issues = source_issues(doc)
    missing = {row['source_ref'] for row in issues}
    healthy = {**doc, 'sources': {ref: record for ref, record in doc['sources'].items() if ref not in missing}}
    missing_readers = {row['reader_name'] for row in issues}
    # A partial native load intentionally removed these exact saved branches.
    # Keep their original source/pin records repairable. A present/replaced reader
    # still undergoes normal name/type/path checks; absence alone grants nothing.
    removed = set(doc.get('_partial_removed_source_names', [])) if doc.get('partial_workspace') else set()
    # Owner construction rereads the immutable manifest after native LoadState.
    # Carry the exact removed set across that read without changing the file or
    # exempting names in another project/earlier state.
    if doc.get('partial_workspace') and _recovery_state is not None:
        saved_state = str((Path(path).parent / doc['workspace_file']).resolve())
        if (saved_state, doc.get('workspace_sha256')) == _recovery_state['state']:
            removed.update(_recovery_state['removed_source_names'])
    live_names = {name for name, _ in p.GetSources()}
    absent_removed = removed - live_names
    healthy['native_readers'] = [row for row in doc.get('native_readers', [])
        if row['reader_name'] not in missing_readers and row['reader_name'] not in absent_removed]
    verify_sources(path, healthy)
    verify_readers(healthy)
    _verify_metadata_records(healthy, live=True)
    output = Path(doc["project_root"]) / "saved" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    output.mkdir(parents=True, exist_ok=False)
    # The native owner adds only its analysis records/files in this unpublished
    # revision. A failed filter/export/state write never replaces the last save.
    doc = deepcopy(doc)
    # The new PVSM/native_readers below describe only the live graph. This
    # partial-load bookkeeping is not a new persisted reader exemption.
    doc.pop('_partial_removed_source_names', None)
    doc['repair'] = issues
    if prepare is not None:
        doc = prepare(doc, output)
    active=p.GetActiveSource() if hasattr(p,'GetActiveSource') else None
    view=p.GetActiveView() if hasattr(p,'GetActiveView') else None
    doc['active_selection']={'source_name':next((name for (name,_),item in p.GetSources().items() if _same_proxy(item,active)),None),
        'view_name':next((name for (name,_),item in servermanager.ProxyManager().GetProxiesInGroup('views').items() if _same_proxy(item,view)),None)}
    native_files = {}
    native_readers = []
    for (label, _), source in p.GetSources().items():
        inputs = reader_input_files(source)
        if inputs:
            native_readers.append({"reader_name": label, "reader_type": source.GetXMLName(), "input_paths": list(map(str, inputs))})
        for entry in inputs:
            files = source_files(entry) if entry.suffix.lower() in READERS else [entry]
            for file in files:
                native_files[str(file)] = sha(file)
    state = output / "analysis.pvsm"
    p.SaveState(str(state))
    verify_sources(path, healthy)
    for file, expected in native_files.items():
        if sha(file) != expected:
            raise RuntimeError("Reader input changed while saving: " + file)
    saved = dict(doc, workspace_file=state.name, workspace_sha256=sha(state), native_reader_files=native_files, native_readers=native_readers,
                 saved_utc=datetime.now(timezone.utc).isoformat(), parent_project=str(path))
    if os.environ.get("CAE_POST_PROJECT") and Path(os.environ["CAE_POST_PROJECT"]).resolve() == Path(path).resolve():
        # Runtime reconnection belongs to this newly saved revision. Merely
        # opening a past project never rewrites its stored connection fields.
        for variable, field in (("CAELAB_ORIGIN_JOB_ID", "origin_job_id"), ("CAELAB_DESKTOP_PYTHON", "desktop_python"),
                                ("CAELAB_REPO_ROOT", "repo_root"), ("CAE_POST_SERVICE_URL", "service_url")):
            if os.environ.get(variable):
                saved[field] = os.environ[variable]
    project = output / "project.json"
    project.write_text(json.dumps(saved, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.environ["CAE_POST_PROJECT"] = str(project)
    print("PROJECT SAVED " + str(project))
    return project


def restore_workspace(path, doc, *, allow_repair=False):
    global _recovery, _recovery_state
    _recovery = []
    _recovery_state = None
    _verify_metadata_records(doc)
    state = path.parent / doc["workspace_file"]
    if sha(state) != doc["workspace_sha256"]:
        raise RuntimeError("Saved analysis state hash mismatch")
    try:
        from .source_repair import source_issues, verify_analysis_files, partial_state
    except ImportError:
        from source_repair import source_issues, verify_analysis_files, partial_state
    verify_analysis_files(doc)
    issues = source_issues(doc)
    if issues:
        if not allow_repair:
            verify_sources(path, doc)
        _recovery = issues
        partial = Path(doc['project_root']) / 'repairs' / ('P' + uuid.uuid4().hex) / 'available.pvsm'
        selection = partial_state(state, doc, issues, partial)
        p.LoadState(str(partial))
        missing = {row['source_ref'] for row in issues}
        healthy = {**doc, 'sources': {ref: row for ref, row in doc['sources'].items() if ref not in missing}}
        available_names = set(selection['healthy_source_names'])
        healthy['native_readers'] = [row for row in doc.get('native_readers', [])
            if row['reader_name'] in available_names]
        verify_readers(healthy)
        _verify_metadata_records(healthy, live=True)
        restore_selection(healthy)
        doc['partial_workspace'] = True
        doc['_partial_removed_source_names'] = selection['removed_source_names']
        _recovery_state = {'state': (str(state.resolve()), doc['workspace_sha256']),
                           'removed_source_names': list(selection['removed_source_names'])}
        print('PARTIAL RESTORE: healthy sources and retained analysis remain available; missing-input branches require explicit repair.')
        return {'state': 'PARTIAL_RESTORE', 'issues': issues, **selection}
    for file, expected in doc.get("native_reader_files", {}).items():
        if sha(file) != expected:
            raise RuntimeError("Saved analysis reader input changed: " + file)
    p.LoadState(str(state))
    verify_readers(doc)
    _verify_metadata_records(doc, live=True)
    restore_selection(doc)
    print("CAE Post external result restored; source declarations apply only to the exact registered original reader.")


def restore_selection(doc):
    selection=doc.get('active_selection')
    if selection:
        source=p.FindSource(selection.get('source_name')) if selection.get('source_name') else None
        views=servermanager.ProxyManager().GetProxiesInGroup('views')
        view=next((item for (name,_),item in views.items() if name==selection.get('view_name')),None)
        p.SetActiveSource(source)
        if view is not None: p.SetActiveView(view)
    else:
        # Legacy files had no selection identity. Their original result remains
        # the explicit fallback; newer files restore the user's selected analysis.
        original = doc.get('sources', {}).get('result') or next(iter(doc.get('sources', {}).values()), None)
        p.SetActiveSource(p.FindSource(original['reader_name']) if original else None)
        view=next((item for item in p.GetViews() if item.GetXMLName()=='RenderView'),None)
        if view is not None: p.SetActiveView(view)


def admit_result(input_path, input_id=None, source_pins=None, native_metadata=None, registration_origin=None):
    """Admit one immutable reader without creating a document, view or layout."""
    if input_id is not None and source_pins is None:
        raise ValueError("A registered input ID requires its complete verified source pins")
    if native_metadata is not None and (not input_id or source_pins is None):
        raise ValueError("Declared native metadata requires a verified registered input receipt")
    files = source_files(input_path, native_metadata)
    entry = files[0]
    pinned = pins(files)
    if source_pins is not None and pinned != source_pins:
        raise RuntimeError("Registered source pins do not match the actual result dependency set")
    name = "Result | " + entry.name + " | " + uuid.uuid4().hex[:8]
    reader_type = READERS[entry.suffix.lower()]
    previous_source = p.GetActiveSource() if hasattr(p, "GetActiveSource") else None
    previous_view = p.GetActiveView()
    previous_view_time = getattr(previous_view, "ViewTime", None)
    constructor = getattr(p, reader_type)
    source = constructor(registrationName=name, FileName=[str(entry)] if entry.suffix.lower() in (".vtu", ".vtt") else str(entry))
    scene = p.GetAnimationScene()
    previous_time = float(scene.AnimationTime)
    try:
        source.UpdatePipeline()
        declaration = validate_declared_metadata(source, native_metadata) if native_metadata is not None else None
        metadata = _inspect_result(source, native_metadata=declaration)
        if not metadata["points"] and not metadata["cells"] and not metadata.get("rows"):
            raise RuntimeError("Native reader returned no mesh data; inspect the reader error before retrying")
    except BaseException:
        if hasattr(p, "Delete"):
            p.Delete(source)
        raise
    finally:
        scene.AnimationTime = previous_time
        p.SetActiveSource(previous_source)
        p.SetActiveView(previous_view)
        if previous_view_time is not None:
            previous_view.ViewTime = previous_view_time
    record = {"entry_path": str(entry), "input_id": input_id, "reader_name": name,
              "reader_type": reader_type, "source_pins": pinned, "metadata": metadata,
              "source_revision": _metadata_hash({"format": entry.suffix.lower(),
                  "files": sorted([{"relative": Path(pin["path"]).relative_to(entry.parent).as_posix(),
                             "sha256": pin["sha256"], "bytes": pin["bytes"]} for pin in pinned], key=lambda row: row['relative'])})}
    if registration_origin is not None:
        record['registration_origin'] = deepcopy(registration_origin)
    if declaration is not None:
        record.update(native_metadata=declaration, native_metadata_sha256=_metadata_hash(declaration))
    return source, record


def open_result(input_path, project_directory, input_id=None, source_pins=None, native_metadata=None, registration_origin=None):
    # Admission is also used by Add result in an already open analysis.
    source, record = admit_result(input_path, input_id, source_pins, native_metadata, registration_origin)
    record['label'] = Path(input_path).name
    folder = Path(project_directory).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    scene = p.GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()
    set_time(source)
    layout = p.CreateLayout(name="Result inspection")
    view = p.CreateView("XYChartView" if record.get("metadata", {}).get("curve") else "RenderView")
    p.AssignViewToLayout(view=view, layout=layout, hint=0)
    p.SetActiveView(view)
    display = p.Show(source, view)
    p.SetActiveSource(source)
    if view.GetXMLName() == 'XYChartView':
        display.AttributeType = 'Row Data'
        display.UseIndexForXAxis = 0
        display.XArrayName = 'axis'
        display.SeriesVisibility = ['value']
    else:
        p.ResetCamera(view)
    doc = {"kind": KIND, "version": 1, "document_id": "D" + uuid.uuid4().hex,
           "project_root": str(folder), "sources": {"result": record}}
    # Publish the first manifest only after the native state and dependency checks succeed.
    saved = save_project(folder / "project.json", doc)
    initial = json.loads(saved.read_text(encoding="utf-8"))
    initial["workspace_file"] = str((saved.parent / initial["workspace_file"]).relative_to(folder))
    initial.pop("parent_project", None)
    project = folder / "project.json"
    project.write_text(json.dumps(initial, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.environ["CAE_POST_PROJECT"] = str(project)
    print("PROJECT CREATED " + str(project))
    return project


def open_registered(input_id, project_directory, service_url):
    """Resolve ID, entry and complete pins together through the existing service."""
    import sys
    # The portable native interpreter has no installed repository package.
    repository = str(Path(__file__).resolve().parents[2])
    sys.path.insert(0, repository)
    try:
        from caelab.workbench_client import Client
    finally:
        sys.path.remove(repository)
    receipt = Client(service_url).native_input(input_id)
    if receipt.get("id") != input_id:
        raise RuntimeError("Registered input receipt ID does not match the requested input")
    entry = Path(receipt["path"])
    if not entry.is_absolute() or receipt.get("format") not in ("vtu", "pvd") or entry.suffix.lower() != "." + receipt["format"]:
        raise ValueError("Registered native receipt needs an absolute matching VTU/PVD entry")
    if not isinstance(receipt.get("source_pins"), list) or not receipt["source_pins"]:
        raise ValueError("Registered native receipt needs its complete source pins")
    return open_result(entry, project_directory, input_id=receipt["id"], source_pins=receipt["source_pins"],
                       native_metadata=receipt.get("native_metadata"), registration_origin=receipt.get("registration_origin"))


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Create an independent native VTU/PVD analysis")
    parser.add_argument("paths", nargs="+", help="INPUT_PATH OUTPUT_DIRECTORY, or OUTPUT_DIRECTORY in registered mode")
    parser.add_argument("--registered-input")
    parser.add_argument("--service-url")
    args = parser.parse_args(argv)
    if args.registered_input is not None:
        if len(args.paths) != 1 or not args.service_url:
            parser.error("Registered mode requires OUTPUT_DIRECTORY --registered-input ID --service-url URL")
        return open_registered(args.registered_input, args.paths[0], args.service_url)
    if len(args.paths) != 2 or args.service_url is not None:
        parser.error("Direct mode requires INPUT_PATH OUTPUT_DIRECTORY without service options")
    return open_result(*args.paths)


if __name__ == "__main__":
    main()
