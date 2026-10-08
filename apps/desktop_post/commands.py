"""Product commands used by native ParaView's Macros menu and toolbar.

All computational objects are native ParaView sources/filters. No Qt binding or
canvas is replaced. State exports are appended and retain explicit source pins.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from paraview import simple as p, servermanager


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def project():
    path = Path(os.environ["CAE_POST_PROJECT"]).resolve(strict=True)
    return path, json.loads(path.read_text(encoding="utf-8"))


def verify_sources():
    path, doc = project()
    for source in doc["sources"].values():
        for pin in source["source_pins"]:
            source_path = Path(pin["path"])
            if source_path.stat().st_size != pin["bytes"] or sha(source_path) != pin["sha256"]:
                raise RuntimeError("Original retained data changed: " + str(source_path))
        if sha(source["result_path"]) != source["result_sha256"] or sha(source["proposal_path"]) != source["proposal_sha256"]:
            raise RuntimeError("Retained experiment/proposal changed")
        view = Path(source.get("view_path", path.parent / source["view_file"]))
        if sha(view) != source["view_sha256"]:
            raise RuntimeError("Derived native view changed: " + str(view))
    comp = doc["comparison"]
    if "view_file" in comp:
        view = Path(comp.get("view_path", path.parent / comp["view_file"]))
        if sha(view) != comp["view_sha256"]:
            raise RuntimeError("Derived comparison view changed")
    return path, doc


def verify_retained_readers(path, doc):
    """Bind retained labels/metadata to the live native readers' actual files."""
    expected = {
        "A | 150 N | native U [mm]": doc["sources"]["A"],
        "B | 200 N | native U [mm]": doc["sources"]["B"],
    }
    if "view_file" in doc["comparison"]:
        expected["Derived | B - A | exact matched IDs"] = doc["comparison"]
    registered = p.GetSources()
    for name, record in expected.items():
        readers = [source for (label, _), source in registered.items() if label == name]
        if len(readers) != 1 or readers[0].GetXMLName() != "XMLUnstructuredGridReader":
            raise RuntimeError("Retained reader missing, duplicated or replaced: " + name)
        wanted = Path(record.get("view_path", path.parent / record["view_file"])).resolve(strict=True)
        values = list(readers[0].FileName)
        try:
            actual = [Path(str(value)).resolve(strict=True) for value in values]
        except (OSError, RuntimeError) as error:
            raise RuntimeError("Retained reader path mismatch: " + name + ". Reopen the project before probing or saving.") from error
        if actual != [wanted]:
            raise RuntimeError("Retained reader path mismatch: " + name + ". Reopen the project before probing or saving.")


def reader_input_files(source):
    """Use ParaView's reader metadata, including FileNames and other native keys."""
    name = servermanager.vtkSMCoreUtilities.GetFileNameProperty(source.SMProxy)
    if not name:
        return []
    values = getattr(source, name)
    if isinstance(values, str):
        values = [values]
    return [Path(str(value)).resolve(strict=True) for value in values]


def candidate():
    result = p.FindSource("B | 200 N | native U [mm]")
    if result is None:
        raise RuntimeError("The retained B reader is not present in this workspace")
    return result


def active_field():
    source = p.GetActiveSource()
    if source is None:
        raise RuntimeError("Select a field source or filter in Pipeline Browser")
    source.UpdatePipeline()
    if "U_mm" not in source.PointData.keys():
        raise RuntimeError("The selected source has no recorded U_mm point vector")
    return source


def show_component(component="Magnitude"):
    source = active_field()
    view = p.GetActiveView()
    if view is None or view.GetXMLName() != "RenderView":
        raise RuntimeError("Click a 3D view before changing its component")
    display = p.Show(source, view)
    p.ColorBy(display, ("POINTS", "U_mm", component))
    display.RescaleTransferFunctionToDataRange(True, False)
    display.SetScalarBarVisibility(view, True)
    bar = p.GetScalarBar(display.LookupTable, view)
    bar.TitleColor = [0.12, 0.19, 0.28]
    bar.LabelColor = [0.12, 0.19, 0.28]
    bar.ComponentTitle = component
    p.HideUnusedScalarBars(view)
    p.Render(view)


def physical_input(source, name="Spatial sampling input | physical fields only"):
    """Only physical response arrays may be interpolated onto new locations.

    Native IDs and input classifications belong to original mesh entities.
    Passing them through Slice/PlotOverLine would create misleading values.
    """
    source.UpdatePipeline()
    known = {"U_mm", "UX_mm", "UY_mm", "UZ_mm", "U_magnitude_mm"}
    known.update("Delta_" + component + "_mm" for component in ("UX", "UY", "UZ"))
    known.update("Relative_" + component + "_percent" for component in ("UX", "UY", "UZ"))
    selected = p.PassArrays(registrationName=name, Input=source)
    selected.PointDataArrays = [name for name in source.PointData.keys() if name in known]
    selected.CellDataArrays = []
    selected.FieldDataArrays = []
    selected.UpdatePipeline()
    return selected


def new_slice():
    source = active_field()
    view = p.GetActiveView()
    if view is None or view.GetXMLName() != "RenderView":
        raise RuntimeError("Click a 3D view before creating a section")
    bounds = source.GetDataInformation().GetBounds()
    item = p.Slice(registrationName="Section | edit plane in Properties", Input=physical_input(source))
    item.SliceType = "Plane"
    item.SliceType.Origin = [(bounds[i] + bounds[i + 1]) / 2 for i in (0, 2, 4)]
    item.SliceType.Normal = [1, 0, 0]
    item.UpdatePipeline()
    p.Hide(source, view)
    display = p.Show(item, view)
    p.ColorBy(display, ("POINTS", "U_magnitude_mm"))
    display.SetScalarBarVisibility(view, True)
    p.SetActiveSource(item)
    p.Render(view)


def show_candidate():
    source = candidate()
    view = p.GetActiveView()
    if view is None or view.GetXMLName() != "RenderView":
        view = next(v for v in p.GetViews() if v.GetXMLName() == "RenderView")
        p.SetActiveView(view)
    p.Show(source, view)
    p.SetActiveSource(source)
    show_component()
    p.Render(view)
    p.ResetCamera(view)
    p.Render(view)


def exact_peak_probe():
    path, doc = verify_sources()
    verify_retained_readers(path, doc)
    source = candidate()
    node = doc["exact_probe"]
    p.SetActiveSource(source)
    from paraview.selection import CreateSelection
    selection = CreateSelection("SelectionQuerySource", "CAE fixed native node " + str(node["node_id"]),
                                ElementType=0, QueryString="NativeNodeId == " + str(node["node_id"]), InsideOut=0)
    extraction = p.ExtractSelection(registrationName="Saved probe | B | native node " + str(node["node_id"]), Input=source, Selection=selection)
    extraction.UpdatePipeline()
    layout = p.CreateLayout(name="Probe | native node " + str(node["node_id"]))
    view = p.CreateView("SpreadSheetView")
    p.AssignViewToLayout(view=view, layout=layout, hint=0)
    p.Show(extraction, view, "SpreadSheetRepresentation")
    p.SetActiveSource(extraction)
    p.SetActiveView(view)
    print("EXACT NATIVE PROBE " + json.dumps(node))


def save_project():
    path, doc = verify_sources()
    verify_retained_readers(path, doc)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    root = Path(doc.get("project_root", path.parent))
    output = root / "saved" / stamp
    output.mkdir(parents=True, exist_ok=False)
    state = output / "analysis.pvsm"
    # Source paths inside PVSM remain actual native reader paths, not copies of
    # the meshes. The manifest records those references and their current hash.
    input_files = {}
    for source in p.GetSources().values():
        for current in reader_input_files(source):
            input_files[str(current)] = sha(current)
    p.SaveState(str(state))
    for source in doc["sources"].values():
        source["view_path"] = str(Path(source.get("view_path", path.parent / source["view_file"])))
    if "view_file" in doc["comparison"]:
        comp = doc["comparison"]
        comp["view_path"] = str(Path(comp.get("view_path", path.parent / comp["view_file"])))
    doc.update(project_root=str(root), workspace_file="analysis.pvsm", workspace_sha256=sha(state),
               saved_utc=datetime.now(timezone.utc).isoformat(), parent_project=str(path),
               native_reader_files=input_files)
    (output / "project.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.environ["CAE_POST_PROJECT"] = str(output / "project.json")
    print("PROJECT SAVED " + str(output / "project.json"))
    return output / "project.json"


def restore_workspace():
    path, doc = verify_sources()
    if "workspace_sha256" in doc and sha(path.parent / doc["workspace_file"]) != doc["workspace_sha256"]:
        raise RuntimeError("Saved analysis state hash mismatch")
    for file, expected in doc.get("native_reader_files", {}).items():
        if sha(file) != expected:
            raise RuntimeError("Saved analysis reader input changed: " + file)
    p.LoadState(str(path.parent / doc["workspace_file"]))
    verify_retained_readers(path, doc)
    p.SetActiveSource(candidate())
    view = next(v for v in p.GetViews() if v.GetXMLName() == "RenderView")
    p.SetActiveView(view)
    print("CAE Post loaded. Macros: CAE Save project / Section / Probe / U components. Ctrl+S remains native data export in this prototype.")
