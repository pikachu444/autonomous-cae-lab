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
    from . import naming
except ImportError:
    from commands import sha, reader_input_files
    import naming


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


def beam_api():
    import sys
    repository = str(Path(__file__).resolve().parents[2])
    sys.path.insert(0, repository)
    try:
        from caelab import beam_inspection
        return beam_inspection
    finally:
        sys.path.remove(repository)


def dynamic_api():
    import sys
    repository = str(Path(__file__).resolve().parents[2])
    sys.path.insert(0, repository)
    try:
        from caelab import dynamic_locations
        return dynamic_locations
    finally:
        sys.path.remove(repository)


def source_files(entry, native_metadata=None):
    """Validate and enumerate a bounded, local PVD+VTU dependency set."""
    entry = Path(entry).resolve(strict=True)
    if not entry.is_file() or entry.suffix.lower() not in READERS:
        raise ValueError("Supported result inputs are VTU and PVD with relative VTU frames")
    from caelab.native_post_dependencies import inspect_dataset
    files = [Path(row['path']) for row in inspect_dataset(entry, baseline_pins=None,
        approved_roots=[entry.parent], limits={})['files']]
    if dynamic_api().required(entry, native_metadata):
        bundle = dynamic_api().load(entry, native_metadata)
        files = list(dict.fromkeys([*files, *bundle['paths']]))
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
    if (any(key in (native_metadata or {}) for key in ('beam', 'beam_inspection')) or
            entry.name == 'beam.pvd' and (entry.parent/'beam_inspection.json').exists()):
        bundle = beam_api().validate_metadata(entry, native_metadata)
        files = list(dict.fromkeys([*files, *bundle['paths']]))
    return files


def pins(files):
    return [{"path": str(file), "bytes": file.stat().st_size, "sha256": sha(file)} for file in files]


def verify_sources(path, doc, *, full=False):
    for record in doc["sources"].values():
        for pin in record.get('conversion', {}).get('source_pins', []):
            file = Path(pin['path'])
            if file.stat().st_size != pin['bytes'] or sha(file) != pin['sha256']:
                raise RuntimeError('Retained FRD source changed: ' + str(file))
        recorded = record["source_pins"]
        if (record.get('native_metadata') or {}).get('dynamic_locations') is not None:
            dynamic_api().verify_saved_source(record['entry_path'], record['native_metadata'],
                record.get('registration_origin'), recorded, full=full)
            continue
        for pin in recorded:
            file = Path(pin["path"])
            if file.stat().st_size != pin["bytes"] or sha(file) != pin["sha256"]:
                raise RuntimeError("Original retained data changed: " + str(file))
        if set(map(str, source_files(record["entry_path"], record.get("native_metadata")))) != {pin["path"] for pin in recorded}:
            raise RuntimeError("Result dependency set does not match its recorded source pins")
        if (record.get('native_metadata') or {}).get('dynamic_locations') is not None:
            dynamic_api().verify_registration(record['entry_path'], record['native_metadata'], record.get('registration_origin'))
    return path, doc


def verify_readers(doc):
    registered = p.GetSources()
    names = [name for name, _ in registered]
    if len(names) != len(set(names)):
        raise RuntimeError('Duplicate native source registrations cannot be restored safely')
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
    beam = isinstance(metadata, dict) and any(key in metadata for key in ('beam', 'beam_inspection'))
    beam_keys = set()
    raw_beam = False
    if beam:
        inputs = reader_input_files(source)
        if len(inputs) != 1 or source.GetXMLName() != 'PVDReader':
            raise ValueError('Beam declaration requires its exact retained PVD reader')
        bundle = beam_api().validate_metadata(inputs[0], metadata)
        # The owner has re-read exact raw dependencies and regenerated these
        # declarations. Do not extend the vocabulary for arbitrary sources.
        raw_beam = metadata['beam'].get('output') == '3D_RAW_STRESS'
        beam_keys = set(bundle['manifest']['native_metadata']) | {'beam_inspection'}
    dynamic = isinstance(metadata, dict) and 'dynamic_locations' in metadata
    if dynamic:
        inputs = reader_input_files(source)
        if len(inputs) != 1 or source.GetXMLName() != 'PVDReader':
            raise ValueError('Dynamic declaration requires its exact retained PVD reader')
        dynamic_api().load(inputs[0], metadata)
    spatial_keys = {'basis', 'mesh_sha256', 'snapshot_kind'}
    if not isinstance(metadata, dict) or not required_keys <= set(metadata) or set(metadata) - required_keys - {"time", "contact_inspection", "field_availability", "field_meanings", "dynamic_locations"} - spatial_keys - shell_keys - beam_keys:
        raise ValueError("Native metadata requires coordinate units/frame, explicit state/clock and declared arrays")
    if 'basis' in metadata and metadata['basis'] not in ('P1', 'DG0'):
        raise ValueError('Declared field basis must be P1 or DG0')
    if 'mesh_sha256' in metadata and (not isinstance(metadata['mesh_sha256'], str)
            or len(metadata['mesh_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in metadata['mesh_sha256'])):
        raise ValueError('Declared mesh identity requires a SHA256 digest')
    if 'snapshot_kind' in metadata and metadata['snapshot_kind'] not in ('steady', 'physical_snapshot'):
        raise ValueError('Declared field requires its exact snapshot kind')
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
                or not ((clock["unit"] == "1" and clock["semantics"] in {"DIMENSIONLESS_MODEL_TIME", "STATIC_LOAD_PARAMETER", "MIXED_NATIVE_COORDINATE_NOT_PHYSICAL_TIME"})
                        or (clock["unit"] in ("s", "ms", "min", "h") and isinstance(clock["semantics"], str) and clock["semantics"].strip()))
                or not isinstance(clock["values"], list) or not clock["values"]
                or any(type(t) not in (int, float) or not math.isfinite(t) for t in clock["values"])
                or any(b <= a for a, b in zip(clock["values"], clock["values"][1:]))
                or source.GetXMLName() != "PVDReader" or times(source) != clock["values"]):
            raise ValueError("Declared dimensionless/physical clock differs from the exact native PVD timesteps")
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
        raw_keys = {'source_field', 'interpolated_by_lab', 'source_array',
                    'basis_is_native_IP_material_basis', 'source_blocks'} if raw_beam else set()
        if not isinstance(declaration, dict) or not required <= set(declaration) or set(declaration) - required - {"component_names", "quantity", "recovery", "shear_convention", "strain_role", "reference_configuration", "strain_precision"} - ({'location'} if shell or beam else set()) - raw_keys:
            raise ValueError("Each declared array requires exact association/name/components and units/frame/measure")
        for key in ("name", "units", "frame", "measure"):
            if not isinstance(declaration[key], str) or not declaration[key].strip():
                raise ValueError("Declared array meaning must be nonempty explicit text")
        if 'quantity' in declaration and (not isinstance(declaration['quantity'], str) or not declaration['quantity'].strip()):
            raise ValueError('Declared quantity must be explicit nonempty text')
        for key in ('strain_role', 'reference_configuration'):
            if key in declaration and (not isinstance(declaration[key], str) or not declaration[key].strip()):
                raise ValueError('변형률 종류와 기준 배치는 명시한 원 선언이어야 합니다.')
        if 'strain_precision' in declaration:
            from caelab.post_strain_measures import precision
            precision(declaration, required=True)
        shell_recovery = {'native_nodal_dof', 'magnitude_of_native_vector',
                          'native_extrapolated_nodal_averaged',
                          'basis_change_of_native_nodal_recovery'} if shell else set()
        beam_recovery = {'native_nodal_dof', 'native_original_beam_nodal_rf', 'native_section_force_output'} if beam else set()
        if raw_beam:
            beam_recovery |= {'native_expanded_nodal_dof', 'native_expanded_RF',
                              'native_extrapolated_nodal_averaged',
                              'basis_change_of_native_nodal_recovery', 'none_native_DAT'}
        if 'recovery' in declaration and (not isinstance(declaration['recovery'], str) or declaration['recovery'] not in {
                'native nodal force; reactions only at restrained DOFs',
                'native integration-point extrapolation and nodal averaging'} | shell_recovery | beam_recovery):
            raise ValueError('Unsupported native field recovery declaration')
        allowed_shear = {'tensor_shear_not_engineering_shear'}
        if raw_beam:
            allowed_shear.add('tensor_off_diagonal_not_engineering_gamma')
        if 'shear_convention' in declaration and declaration['shear_convention'] not in allowed_shear:
            raise ValueError('Unsupported native tensor shear convention')
        association = declaration["association"]
        if 'basis' in metadata and 'quantity' in declaration and association != {'P1': 'POINTS', 'DG0': 'CELLS'}[metadata['basis']]:
            raise ValueError('Declared field basis differs from its native array association')
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


def selected_context(source=None):
    """Read the exact displayed pipeline target; no export or native mutation."""
    source = p.GetActiveSource() if source is None else source
    if source is None:
        raise ValueError('토론할 ParaView 결과를 선택하세요.')
    files = reader_input_files(source)
    project = os.environ.get('CAE_POST_PROJECT')
    if not files and not project:
        raise ValueError('선택한 결과의 원 파일을 확인할 수 없습니다. 결과 프로젝트를 여세요.')
    view = p.GetActiveView()
    display = p.GetDisplayProperties(source, view=view) if view is not None and hasattr(p, 'GetDisplayProperties') else None
    color = list(getattr(display, 'ColorArrayName', [])) if display is not None else []
    scope = {'kind': 'post-selection', 'pipeline': next((name for (name, _), value in p.GetSources().items()
             if _same_proxy(value, source)), None), 'time': float(p.GetAnimationScene().AnimationTime)}
    if len(color) == 2 and color[1]:
        scope.update(association=color[0], array=color[1])
        transfer = getattr(display, 'LookupTable', None)
        if transfer is not None:
            scope['component'] = (getattr(transfer, 'VectorComponent', None)
                                  if getattr(transfer, 'VectorMode', None) == 'Component' else 'Magnitude')
    metadata = inspect_result(source)
    scope['static'] = deepcopy(metadata.get('static'))
    # Native selection is retained as its own descriptor, never promoted to all mesh points.
    if hasattr(source, 'GetSelectionInput'):
        selected = source.GetSelectionInput(0)
        if selected is not None:
            scope['native_selection'] = {'type': selected.GetXMLName(),
                **{key: list(getattr(selected, key)) for key in ('IDs', 'Blocks', 'QueryString')
                   if hasattr(selected, key) and key != 'QueryString'},
                **({'query': str(selected.QueryString)} if hasattr(selected, 'QueryString') else {})}
    return {'path': str(files[0]) if files else str(project), 'scope': scope,
            'result_metadata': metadata}


def _inspect_result(source, time=None, native_metadata=None):
    exact_dynamic = None
    if (native_metadata or {}).get('dynamic_locations') is not None:
        available = native_metadata['time']['values']
        current = float(p.GetAnimationScene().AnimationTime)
        chosen = time if time is not None else current if current in available else available[0]
        exact_dynamic = dynamic_api().select(reader_input_files(source)[0],native_metadata,time=chosen)
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
                           **({"location": declared[(association, name)]["location"]}
                              if "location" in declared.get((association, name), {}) else {}),
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
            "arrays": arrays, "qualification": "UNKNOWN",
            **({'dynamic': exact_dynamic}
               if declaration and 'dynamic_locations' in declaration else {}),
            **({"beam": {**deepcopy(declaration["beam"]),
                 "selected_static": next((deepcopy(row) for row in declaration["beam"]["frames"]
                                           if row["load_parameter"] == selected), None)}}
               if declaration and 'beam_inspection' in declaration else {})}


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
    p.HideUnusedScalarBars(view)
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
    if native_metadata and 'beam_inspection' in native_metadata:
        # Titles name one physical quantity/unit; SECTION FORCES is never stress.
        transfer = p.GetColorTransferFunction(array)
        p.UpdateScalarBarsComponentTitle(transfer, display)
        bar = p.GetScalarBar(transfer, view)
        unit = selected_metadata['units']
        bar.Title = selected_metadata['quantity'] + (' [' + unit + ']' if unit != '1' else '')
        bar.TitleFontSize = 12
        bar.LabelFontSize = 11
        # VTK's bundled Arial does not contain Korean glyphs. Use the installed
        # Windows font without copying/redistributing its font file.
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'malgun.ttf'
        if os.name == 'nt' and font.is_file():
            bar.TitleFontFamily = 'File'
            bar.TitleFontFile = str(font)
    return {"association": association, "array": array, "component": component,
            "time": metadata["time"], "time_units": metadata["time_units"], "time_semantics": metadata["time_semantics"],
            **{key: selected_metadata[key] for key in ("units", "frame", "measure", "metadata_status", "recovery", "shear_convention")},
            **({"location": selected_metadata["location"]} if "location" in selected_metadata else {}),
            **{key: deepcopy(metadata[key]) for key in ("coordinate_units", "coordinate_frame", "static")},
            **({'beam': deepcopy(metadata['beam'])} if 'beam' in metadata else {}),
            **({'dynamic': deepcopy(metadata['dynamic'])} if 'dynamic' in metadata else {})}


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


def save_project(path, doc, *, prepare=None, _history_owner=None):
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
    if issues:
        doc['partial_workspace'] = True
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
            # Preserve declarations/raw companions for the exact registered
            # reader while collecting saved dependencies; no filter inheritance.
            declaration = next((record.get("native_metadata") for record in doc["sources"].values()
                if record["reader_name"] == label and
                   Path(record["entry_path"]).resolve(strict=True) == entry), None)
            if entry.suffix.lower() in READERS:
                files = source_files(entry, declaration)
            else:
                from caelab.native_post_dependencies import inspect_dataset
                files = [Path(row['path']) for row in inspect_dataset(entry, baseline_pins=None,
                    approved_roots=[entry.parent], limits={})['files']]
            for file in files:
                native_files[str(file)] = sha(file)
    state = output / "analysis.pvsm"
    p.SaveState(str(state))
    from caelab.native_post_dependencies import inspect_pvsm
    try:
        admitted = inspect_pvsm(state, saved_readers=native_readers, source_records=healthy['sources'], limits={})
        doc['native_dependency_issues'] = admitted['issues']
    except ValueError as error:
        # Saving a repairable native draft remains possible. Registration must
        # independently verify the state and cannot promote this to complete.
        doc['native_dependency_issues'] = [{'code': 'SAVED_READER_BINDING_INVALID', 'message': str(error)}]
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
    from apps.desktop_post.portable_project import finalize_saved_history
    finalize_saved_history(project, saved, owner=_history_owner)
    attempt = getattr(_history_owner, '_native_save_attempt', None)
    if attempt is not None and attempt.get('phase') == 'INVOKED':
        # This completed native manifest+basis boundary precedes notification.
        # A later exception is not a confirmed failed native Save.
        attempt.update(phase='PUBLISHED', saved_file=str(project))
    os.environ["CAE_POST_PROJECT"] = str(project)
    print("PROJECT SAVED " + str(project))
    return project


def restore_workspace(path, doc, *, allow_repair=False, _native_load=None):
    global _recovery, _recovery_state
    load_state = p.LoadState if _native_load is None else _native_load
    _recovery = []
    _recovery_state = None
    state = path.parent / doc["workspace_file"]
    if sha(state) != doc["workspace_sha256"]:
        raise RuntimeError("Saved analysis state hash mismatch")
    try:
        from .source_repair import source_issues, verify_analysis_files, partial_state
    except ImportError:
        from source_repair import source_issues, verify_analysis_files, partial_state
    history_issues = verify_analysis_files(doc, allow_missing=allow_repair, project_path=path)
    issues = source_issues(doc)
    if any(row.get('code') == 'CONTENT_CHANGED' for row in issues):
        raise ValueError('CONTENT_CHANGED: saved source bytes differ; add a new result or restore the exact original bytes')
    issues.extend(history_issues)
    missing_refs = {row['source_ref'] for row in issues if row.get('source_ref')}
    _verify_metadata_records({**doc, 'sources': {ref: row for ref, row in doc.get('sources', {}).items() if ref not in missing_refs}})
    if issues:
        if not allow_repair:
            verify_sources(path, doc)
        _recovery = issues
        partial = Path(doc['project_root']) / 'repairs' / ('P' + uuid.uuid4().hex) / 'available.pvsm'
        selection = partial_state(state, doc, issues, partial, retain_applied=True)
        load_state(str(partial))
        missing = {row['source_ref'] for row in issues if row.get('source_ref')}
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
    dynamic_pins = {}
    for record in doc.get('sources', {}).values():
        if (record.get('native_metadata') or {}).get('dynamic_locations') is not None:
            checked = dynamic_api().verify_saved_source(record['entry_path'],record['native_metadata'],
                record.get('registration_origin'),record['source_pins'])
            dynamic_pins.update({row['path']: row['sha256'] for row in checked['pins']})
    for file, expected in doc.get("native_reader_files", {}).items():
        if file in dynamic_pins:
            if dynamic_pins[file] != expected:
                raise RuntimeError("Saved dynamic reader pin differs: " + file)
        elif sha(file) != expected:
            raise RuntimeError("Saved analysis reader input changed: " + file)
    if any(record.get('summary', {}).get('comparison_version') == 2 and record.get('result_files')
           for obj in doc.get('analysis', {}).get('objects', {}).values() for record in obj.get('history', [])):
        # Read pinned applied fields, not the original executable comparison
        # graph. The immutable PVSM is retained for provenance/explicit editing.
        restored = Path(doc['project_root']) / 'repairs' / ('P' + uuid.uuid4().hex) / 'retained.pvsm'
        partial_state(state, doc, [], restored, retain_applied=True)
        load_state(str(restored))
    else:
        load_state(str(state))
    for record in doc.get('sources', {}).values():
        declaration=record.get('native_metadata') or {}
        if 'dynamic_locations' in declaration:
            available=declaration['time']['values']
            current=float(p.GetAnimationScene().AnimationTime)
            if current not in available:
                raise ValueError('SELECTION_TIME_UNAVAILABLE: saved time is outside the declared source range')
            dynamic_api().select(record['entry_path'],declaration,
                time=current,
                registration_origin=record.get('registration_origin'))
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


def admit_result(input_path, input_id=None, source_pins=None, native_metadata=None, registration_origin=None, *, display_name=None, conversion_directory=None):
    """Admit one immutable reader without creating a document, view or layout."""
    if input_id is not None and source_pins is None:
        raise ValueError("A registered input ID requires its complete verified source pins")
    if native_metadata is not None and (not input_id or source_pins is None):
        raise ValueError("Declared native metadata requires a verified registered input receipt")
    conversion = None
    if Path(input_path).suffix.lower() == '.frd':
        if input_id is not None or source_pins is not None or native_metadata is not None:
            raise ValueError('Registered FRD inputs must be converted before registration')
        from caelab.adapters.native_calculix_results import convert_independent
        if conversion_directory is None:
            current = os.environ.get('CAE_POST_PROJECT')
            root = Path(current).parent if current and Path(current).is_file() else Path.home() / '.caelab' / 'post'
            conversion_directory = root / 'sources' / ('F' + uuid.uuid4().hex)
        conversion = convert_independent(input_path, conversion_directory)
        conversion['source_pins'] = pins([Path(conversion['retained_path'])])
        display_name = display_name or Path(input_path).name
        input_path = conversion['entry_path']
    files = source_files(input_path, native_metadata)
    entry = files[0]
    if (native_metadata or {}).get('dynamic_locations') is not None:
        checked = dynamic_api().verify_saved_source(entry, native_metadata, registration_origin, source_pins)
        pinned = checked['pins']
        initial_times = native_metadata['time']['values']
        current = float(p.GetAnimationScene().AnimationTime)
        dynamic_api().select(entry, native_metadata, time=current if current in initial_times else initial_times[0],
                             registration_origin=registration_origin)
    else:
        pinned = pins(files)
    if source_pins is not None and (native_metadata or {}).get('dynamic_locations') is not None:
        pinned = deepcopy(source_pins)
    if source_pins is not None and pinned != source_pins:
        raise RuntimeError("Registered source pins do not match the actual result dependency set")
    name = naming.unique_name(display_name or entry.name, p.GetSources())
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
    if conversion is not None:
        record['conversion'] = conversion
    if declaration is not None:
        record.update(native_metadata=declaration, native_metadata_sha256=_metadata_hash(declaration))
    return source, record


def open_result(input_path, project_directory, input_id=None, source_pins=None, native_metadata=None, registration_origin=None):
    # Admission is also used by Add result in an already open analysis.
    if Path(input_path).suffix.lower() == '.frd' and Path(project_directory).exists():
        raise FileExistsError('새 결과 프로젝트 폴더를 선택하세요: ' + str(project_directory))
    conversion = ({'conversion_directory': Path(project_directory).resolve() / 'sources' / ('F' + uuid.uuid4().hex)}
                  if Path(input_path).suffix.lower() == '.frd' else {})
    source, record = admit_result(input_path, input_id, source_pins, native_metadata, registration_origin, **conversion)
    record['label'] = Path(input_path).name
    folder = Path(project_directory).resolve()
    folder.mkdir(parents=True, exist_ok=bool(conversion))
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
    doc = {"kind": KIND, "version": 1, "document_id": "D" + uuid.uuid4().hex, "title": Path(input_path).name,
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
    # Portable pvpython starts this script outside the repository working directory.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    main()
