"""Fresh synthetic native read/save and independent-process cold-reopen check.

pvpython --force-offscreen-rendering verify_external.py create NEW_DIRECTORY
pvpython --force-offscreen-rendering verify_external.py reopen NEW_DIRECTORY
No original experiment or user data is modified; this is not GUI acceptance.
"""
import json
import os
from pathlib import Path
import sys

from paraview import simple as p, servermanager

import commands
import external


def check_values(source, time):
    external.inspect_result(source, time=time)
    mesh = servermanager.Fetch(source)
    assert mesh.GetNumberOfPoints() == 4 and mesh.GetNumberOfCells() == 1
    values = mesh.GetPointData().GetArray("response")
    ids = mesh.GetPointData().GetArray("NativeNodeId")
    for index in range(4):
        x, y, z = mesh.GetPoint(index)
        assert abs(values.GetTuple1(index) - (1 + x + 2 * y + 3 * z + time * .25)) < 1e-12
        assert ids.GetTuple1(index) == 11 + index


def check_line(line, time):
    line.UpdatePipeline(time=time)
    data = servermanager.Fetch(line)
    assert data.GetNumberOfPoints() == 5
    assert data.GetPointData().GetArray("NativeNodeId") is None
    assert data.GetCellData().GetArray("NativeElementId") is None
    mask = data.GetPointData().GetArray("vtkValidPointMask")
    values = data.GetPointData().GetArray("response")
    for index in range(data.GetNumberOfPoints()):
        x, y, z = data.GetPoint(index)
        assert mask.GetTuple1(index) == 1
        assert abs(values.GetTuple1(index) - (1 + x + 2 * y + 3 * z + time * .25)) < 1e-10


def create(folder):
    folder.mkdir(parents=True, exist_ok=False)
    inputs = folder / "synthetic inputs"
    frames = inputs / "frames"
    frames.mkdir(parents=True)
    for time in (0, 1):
        values = " ".join(str(1 + x + 2*y + 3*z + .25*time) for x, y, z in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)))
        content = f'''<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian"><UnstructuredGrid><Piece NumberOfPoints="4" NumberOfCells="1">
<PointData><DataArray type="Float64" Name="response" format="ascii">{values}</DataArray><DataArray type="Int64" Name="NativeNodeId" format="ascii">11 12 13 14</DataArray></PointData>
<CellData><DataArray type="Float64" Name="response" format="ascii">{3 + .25*time}</DataArray><DataArray type="Int64" Name="NativeElementId" format="ascii">42</DataArray></CellData>
<Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">0 0 0 1 0 0 0 1 0 0 0 1</DataArray></Points>
<Cells><DataArray type="Int64" Name="connectivity" format="ascii">0 1 2 3</DataArray><DataArray type="Int64" Name="offsets" format="ascii">4</DataArray><DataArray type="UInt8" Name="types" format="ascii">10</DataArray></Cells>
</Piece></UnstructuredGrid></VTKFile>'''
        (frames / f"frame-{time}.vtu").write_text(content, encoding="utf-8")
    entry = inputs / "series.pvd"
    entry.write_text('<VTKFile type="Collection" version="0.1" byte_order="LittleEndian"><Collection>'
                     '<DataSet timestep="0" group="" part="0" file="frames/frame-0.vtu"/>'
                     '<DataSet timestep="1" group="" part="0" file="frames/frame-1.vtu"/></Collection></VTKFile>', encoding="utf-8")
    original = external.pins(external.source_files(entry))
    # Exercise an independent standalone VTU as well as the temporal collection.
    standalone = external.open_result(frames / "frame-0.vtu", folder / "standalone")
    static_metadata = external.inspect_result(p.GetActiveSource())
    assert static_metadata["timesteps"] == [] and static_metadata["time"] is None
    p.ResetSession()
    project = external.open_result(entry, folder / "analysis")
    source = p.GetActiveSource()
    assert len(p.GetViews()) == 1
    metadata = external.inspect_result(source)
    assert metadata["timesteps"] == [0., 1.]
    assert all(array["units"] is None for array in metadata["arrays"])
    for time in (0, 1):
        check_values(source, time)
    external.select_array(source, "CELLS", "response", time=1)
    external.select_array(source, "POINTS", "response", time=1)
    physical = external.physical_input(source, [("POINTS", "response")])
    line = p.PlotOverLine(registrationName="Affine interpolated line", Input=physical)
    line.Point1, line.Point2, line.Resolution = [.1, .1, .1], [.2, .2, .2], 4
    check_line(line, 1)
    saved = commands.save_project()
    assert original == external.pins(external.source_files(entry))
    report = {"create_pid": os.getpid(), "saved_project": str(saved), "standalone_project": str(standalone),
              "initial_project": str(project), "original_files": original, "native_version": str(p.GetParaViewVersion()),
              "two_actual_frames_verified": True, "point_and_cell_selection": True,
              "affine_line_verified": True, "interpolated_identity_absent": True, "gui_verified": False}
    (folder / "created.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


def reopen(folder):
    report = json.loads((folder / "created.json").read_text(encoding="utf-8"))
    assert os.getpid() != report["create_pid"]
    os.environ["CAE_POST_PROJECT"] = report["saved_project"]
    commands.restore_workspace()
    source = p.GetActiveSource()
    assert float(p.GetAnimationScene().AnimationTime) == 1
    display = p.GetDisplayProperties(source, p.GetActiveView())
    assert list(display.ColorArrayName) == ["POINTS", "response"]
    check_values(source, 1)
    check_line(p.FindSource("Affine interpolated line"), 1)
    assert report["original_files"] == external.pins([Path(pin["path"]) for pin in report["original_files"]])
    report.update(status="PASS", cold_reopen_pid=os.getpid(), cold_reopen_actual_values_verified=True,
                  saved_time_and_array_selection_restored=True, original_files_unchanged=True)
    (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(folder / "report.json"), **report}))


if __name__ == "__main__":
    operation, directory = sys.argv[1:]
    {"create": create, "reopen": reopen}[operation](Path(directory).resolve())
