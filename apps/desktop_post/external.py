"""Independent VTU/PVD analysis using native ParaView readers and PVSM state.

Run in the native ParaView Python environment. Input paths are exact local files;
managed callers supply the entry path of their registered dependency snapshot.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import uuid
import xml.etree.ElementTree as ET

from paraview import simple as p

try:
    from .commands import sha, reader_input_files
except ImportError:
    from commands import sha, reader_input_files


KIND = "external-result"
READERS = {".vtu": "XMLUnstructuredGridReader", ".pvd": "PVDReader"}


def source_files(entry):
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
        if set(map(str, source_files(record["entry_path"]))) != {pin["path"] for pin in recorded}:
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


def inspect_result(source, time=None):
    selected = set_time(source, time)
    info = source.GetDataInformation()
    arrays = []
    for association, data in (("POINTS", source.PointData), ("CELLS", source.CellData), ("FIELD", source.FieldData)):
        for name in data.keys():
            array = data[name]
            components = array.GetNumberOfComponents()
            arrays.append({"name": name, "association": association, "components": components,
                           "component_names": [array.GetComponentName(i) for i in range(components)],
                           "range": [value if math.isfinite(value) else None for value in array.GetRange()], "units": None})
    return {"reader": source.GetXMLName(), "points": info.GetNumberOfPoints(),
            "cells": info.GetNumberOfCells(), "bounds": list(info.GetBounds()),
            "timesteps": times(source), "time": selected, "time_units": None,
            "coordinate_units": None, "arrays": arrays, "qualification": "UNKNOWN"}


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
    # Validate the complete selection before changing the native time or active view.
    p.SetActiveView(view)
    metadata = inspect_result(source, time)
    display = p.Show(source, view)
    selection = (association, array) if component is None else (association, array, component)
    p.ColorBy(display, selection)
    display.RescaleTransferFunctionToDataRange(True, False)
    display.SetScalarBarVisibility(view, True)
    p.SetActiveSource(source)
    return {"association": association, "array": array, "component": component, "time": metadata["time"], "units": None}


def physical_input(source, arrays):
    """Allow only explicitly selected response arrays into spatial interpolation."""
    source.UpdatePipeline()
    identity = {"nativenodeid", "nativeelementid", "globalnodeid", "globalelementid", "vtkoriginalpointids", "vtkoriginalcellids", "globalids", "pedigreeids"}
    grouped = {"POINTS": [], "CELLS": []}
    for association, name in arrays:
        if association not in grouped or name.lower().endswith("_input") or re.search(r"(?:^|_)ids?$|Ids?$|IDs?$", name) or name.lower() in identity:
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


def save_project(path, doc):
    verify_sources(path, doc)
    verify_readers(doc)
    output = Path(doc["project_root"]) / "saved" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    output.mkdir(parents=True, exist_ok=False)
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
    verify_sources(path, doc)
    for file, expected in native_files.items():
        if sha(file) != expected:
            raise RuntimeError("Reader input changed while saving: " + file)
    saved = dict(doc, workspace_file=state.name, workspace_sha256=sha(state), native_reader_files=native_files, native_readers=native_readers,
                 saved_utc=datetime.now(timezone.utc).isoformat(), parent_project=str(path))
    project = output / "project.json"
    project.write_text(json.dumps(saved, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.environ["CAE_POST_PROJECT"] = str(project)
    print("PROJECT SAVED " + str(project))
    return project


def restore_workspace(path, doc):
    verify_sources(path, doc)
    state = path.parent / doc["workspace_file"]
    if sha(state) != doc["workspace_sha256"]:
        raise RuntimeError("Saved analysis state hash mismatch")
    for file, expected in doc.get("native_reader_files", {}).items():
        if sha(file) != expected:
            raise RuntimeError("Saved analysis reader input changed: " + file)
    p.LoadState(str(state))
    verify_readers(doc)
    p.SetActiveSource(p.FindSource(doc["sources"]["result"]["reader_name"]))
    p.SetActiveView(next(view for view in p.GetViews() if view.GetXMLName() == "RenderView"))
    print("CAE Post external result restored; units remain undeclared unless supplied by the source owner.")


def open_result(input_path, project_directory, input_id=None, source_pins=None):
    if input_id is not None and source_pins is None:
        raise ValueError("A registered input ID requires its complete verified source pins")
    files = source_files(input_path)
    entry = files[0]
    pinned = pins(files)
    if source_pins is not None and pinned != source_pins:
        raise RuntimeError("Registered source pins do not match the actual result dependency set")
    folder = Path(project_directory).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    name = "Result | " + entry.name + " | " + uuid.uuid4().hex[:8]
    reader_type = READERS[entry.suffix.lower()]
    constructor = getattr(p, reader_type)
    source = constructor(registrationName=name, FileName=[str(entry)] if entry.suffix.lower() == ".vtu" else str(entry))
    scene = p.GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()
    metadata = inspect_result(source)
    if not metadata["points"] and not metadata["cells"]:
        raise RuntimeError("Native reader returned no mesh data; inspect the reader error before retrying")
    layout = p.CreateLayout(name="Result inspection")
    view = p.CreateView("RenderView")
    p.AssignViewToLayout(view=view, layout=layout, hint=0)
    p.SetActiveView(view)
    p.Show(source, view)
    p.SetActiveSource(source)
    p.ResetCamera(view)
    record = {"entry_path": str(entry), "input_id": input_id, "reader_name": name,
              "reader_type": reader_type, "source_pins": pinned, "metadata": metadata}
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
    return open_result(entry, project_directory, input_id=receipt["id"], source_pins=receipt["source_pins"])


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
