"""Build real ParaView readers, filters, charts and state with bundled pvpython."""
from pathlib import Path
import json
import math
import sys

from paraview import simple as p
from paraview import servermanager
from commands import physical_input


def text(view, name, content, location="Upper Left Corner"):
    source = p.Text(registrationName=name)
    source.Text = content
    display = p.Show(source, view, "TextSourceRepresentation")
    display.WindowLocation = location
    display.FontSize = 12
    display.Color = [0.12, 0.19, 0.28]
    return source


def render_view():
    view = p.CreateView("RenderView")
    view.UseColorPaletteForBackground = 0
    view.Background = [0.95, 0.965, 0.98]
    view.OrientationAxesVisibility = 1
    view.CameraParallelProjection = 1
    return view


def fit_view(view, source, direction=(1.2, -1.6, 1.1)):
    """Fit known data bounds before the GUI has rendered its representations.

    Native ResetCamera before the first representation update can see no visible
    bounds. Store a conservative explicit camera, then let native Fit refine it.
    """
    bounds = source.GetDataInformation().GetBounds()
    center = [(bounds[i] + bounds[i + 1]) / 2 for i in (0, 2, 4)]
    diameter = math.sqrt(sum((bounds[i + 1] - bounds[i]) ** 2 for i in (0, 2, 4)))
    length = math.sqrt(sum(value * value for value in direction))
    view.CameraFocalPoint = center
    view.CameraPosition = [center[i] + 3 * diameter * direction[i] / length for i in range(3)]
    view.CameraViewUp = [0, 0, 1]
    view.CameraParallelScale = max(diameter * 0.78, 1.0)


def field_display(source, view, array="U_magnitude_mm"):
    display = p.Show(source, view, "UnstructuredGridRepresentation")
    display.Representation = "Surface With Edges"
    display.EdgeColor = [0.28, 0.32, 0.38]
    p.ColorBy(display, ("POINTS", array))
    display.SetScalarBarVisibility(view, True)
    lut = p.GetColorTransferFunction(array)
    lut.ApplyPreset("Cool to Warm (Extended)", True)
    lut.RescaleTransferFunction(*source.PointData[array].GetRange())
    bar = p.GetScalarBar(lut, view)
    bar.Title = array.replace("_", " ")
    bar.ComponentTitle = ""
    bar.TitleColor = [0.12, 0.19, 0.28]
    bar.LabelColor = [0.12, 0.19, 0.28]
    bar.WindowLocation = "Lower Right Corner"
    bar.TitleFontSize = 12
    bar.LabelFontSize = 11
    fit_view(view, source)
    return display


def build(project_path):
    project_path = Path(project_path).resolve()
    folder = project_path.parent
    project = json.loads(project_path.read_text(encoding="utf-8"))
    p._DisableFirstRenderCameraReset()
    a = p.XMLUnstructuredGridReader(registrationName="A | 150 N | native U [mm]", FileName=[str(folder / project["sources"]["A"]["view_file"])])
    b = p.XMLUnstructuredGridReader(registrationName="B | 200 N | native U [mm]", FileName=[str(folder / project["sources"]["B"]["view_file"])])
    a.UpdatePipeline()
    b.UpdatePipeline()
    bounds = b.GetDataInformation().GetBounds()
    main = p.CreateLayout(name="01  Result inspection")
    main.SplitHorizontal(0, 0.66)
    main.SplitVertical(2, 0.53)
    view = render_view()
    section_view = render_view()
    chart = p.CreateView("XYChartView")
    p.AssignViewToLayout(view=view, layout=main, hint=1)
    p.AssignViewToLayout(view=section_view, layout=main, hint=5)
    p.AssignViewToLayout(view=chart, layout=main, hint=6)
    field_display(b, view)
    text(view, "CAE Post | source and qualification", "CAE POST   /   FIELD INSPECTION\n200 N  |  CalculiX 2.21  |  U [mm]\nStatic step 1  /  qualification UNKNOWN  /  NOT RELEASED")
    sampling_input = physical_input(b, "B | spatial sampling | physical fields only")
    section = p.Slice(registrationName="Section | B | plane X = 0 mm", Input=sampling_input)
    section.SliceType = "Plane"
    section.SliceType.Origin = [0, 0, (bounds[4] + bounds[5]) / 2]
    section.SliceType.Normal = [1, 0, 0]
    section.UpdatePipeline()
    field_display(section, section_view)
    fit_view(section_view, section, direction=(1, 0, 0))
    text(section_view, "Section label", "SECTION  /  X = 0 mm")
    line = p.PlotOverLine(registrationName="Line probe | B | spatial interpolation", Input=sampling_input)
    # A vertical material line near the left edge; gaps remain VTK valid-mask data.
    x, y = bounds[0] + 0.2 * (bounds[1] - bounds[0]), 0.0
    line.Point1 = [x, y, bounds[4]]
    line.Point2 = [x, y, bounds[5]]
    line.Resolution = 160
    line.UpdatePipeline()
    plot = p.Show(line, chart, "XYChartRepresentation")
    plot.UseIndexForXAxis = 0
    plot.XArrayName = "arc_length"
    plot.SeriesVisibility = ["UZ_mm"]
    chart.ChartTitle = "Line probe B  |  interpolated UZ"
    chart.BottomAxisTitle = "Distance along line [mm]"
    chart.LeftAxisTitle = "UZ [mm]"
    chart.ChartTitleFontSize = 13
    chart.ShowLegend = 0
    compare = p.CreateLayout(name="02  Compare A and B")
    compare.SplitHorizontal(0, 0.5)
    av, bv = render_view(), render_view()
    p.AssignViewToLayout(view=av, layout=compare, hint=1)
    p.AssignViewToLayout(view=bv, layout=compare, hint=2)
    field_display(a, av)
    field_display(b, bv)
    common_max = max(a.PointData["U_magnitude_mm"].GetRange()[1], b.PointData["U_magnitude_mm"].GetRange()[1])
    p.GetColorTransferFunction("U_magnitude_mm").RescaleTransferFunction(0, common_max)
    text(av, "A comparison label", "A   /   150 N\nU magnitude [mm]  /  common range\nUNKNOWN  /  NOT RELEASED")
    text(bv, "B comparison label", "B   /   200 N\nU magnitude [mm]  /  common range\nUNKNOWN  /  NOT RELEASED")
    if project["comparison"]["status"] != "BLOCKED":
        delta = p.XMLUnstructuredGridReader(registrationName="Derived | B - A | exact matched IDs", FileName=[str(folder / project["comparison"]["view_file"])])
        delta.UpdatePipeline()
        layout = p.CreateLayout(name="03  Difference and relative change")
        dv = render_view()
        p.AssignViewToLayout(view=dv, layout=layout, hint=0)
        field_display(delta, dv, "Delta_UZ_mm")
        text(dv, "Difference policy", "DERIVED   /   B - A  /  UZ [mm]\nExact native IDs, coordinates and topology\nRelative_*_percent: 100 (B - A) / abs(A)\nZero baseline = undefined; *_valid mask retained")
    exact_layout = p.CreateLayout(name="04  Exact native values")
    sheet = p.CreateView("SpreadSheetView")
    p.AssignViewToLayout(view=sheet, layout=exact_layout, hint=0)
    p.Show(b, sheet, "SpreadSheetRepresentation")
    p.SetActiveView(view)
    p.SetActiveSource(b)
    main.SetSize(1440, 880)
    p.SaveState(str(folder / project["workspace_file"]))
    # A real native-reader verification: every coordinate, ID, component and cell.
    import vtkmodules.util.numpy_support as ns
    checks = []
    for key, source in (("A", a), ("B", b)):
        data = servermanager.Fetch(source)
        raw = json.loads(Path(project["sources"][key]["field_path"]).read_text(encoding="utf-8"))
        ids = ns.vtk_to_numpy(data.GetPointData().GetArray("NativeNodeId"))
        u = ns.vtk_to_numpy(data.GetPointData().GetArray("U_mm"))
        xyz = ns.vtk_to_numpy(data.GetPoints().GetData())
        eids = ns.vtk_to_numpy(data.GetCellData().GetArray("NativeElementId"))
        assert len(ids) == len(raw["nodes"]) and len(eids) == len(raw["elements"])
        assert ids.tolist() == [n["node_id"] for n in raw["nodes"]]
        assert u.tolist() == [n["displacement_mm"] for n in raw["nodes"]]
        assert xyz.tolist() == [n["position_mm"] for n in raw["nodes"]]
        for index, element in enumerate(raw["elements"]):
            cell = data.GetCell(index)
            assert cell.GetCellType() == 24 and int(eids[index]) == element["element_id"]
            assert [int(ids[cell.GetPointId(j)]) for j in range(10)] == element["node_ids"]
        checks.append({"source": key, "nodes": len(ids), "elements": len(eids), "max_component_error_mm": 0.0, "all_node_ids_coordinates_and_connectivity_equal": True})
    forbidden = {"NativeNodeId", "NativeElementId", "FixedXYZ_input", "LoadedNode_input"}
    for sampled in (section, line):
        sampled.UpdatePipeline()
        assert not forbidden.intersection(sampled.PointData.keys())
        assert not forbidden.intersection(sampled.CellData.keys())
        assert "U_mm" in sampled.PointData.keys()
    (folder / "native_reader_verification.json").write_text(json.dumps({"paraview": str(p.GetParaViewVersion()), "checks": checks, "slice_cells": section.GetDataInformation().GetNumberOfCells(), "line_points": line.GetDataInformation().GetNumberOfPoints(), "interpolated_outputs_have_no_native_identity_or_input_classification": True, "gui_verified": False}, indent=2), encoding="utf-8")
    print("READY " + str(folder / project["workspace_file"]))
    return project


if __name__ == "__main__":
    build(sys.argv[1])
