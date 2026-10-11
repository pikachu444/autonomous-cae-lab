"""Real VTK numerical acceptance under a narrow ParaView proxy adapter.

These exercise vtkResampleWithDataSet and the exact server-side arithmetic script.
They do not establish an actual ParaView session, GUI, or PVSM acceptance.
"""
import importlib
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

vtk = pytest.importorskip("vtk")
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy


class Property:
    """ParaView-shaped typed property; it is not a source/subproxy."""
    def __init__(self, data):
        self.data = data
        self.SMProperty = self

    def GetData(self):
        return self.data

    def GetInformationOnly(self):
        return False

    def GetIsInternal(self):
        return False

    def GetXMLName(self):
        # vtkSMProperty has this method too, without proxy ListProperties.
        return "TestTypedProperty"


class Proxy:
    def __init__(self, native, kind, label, **properties):
        self.native, self.kind, self.label = native, kind, label
        self.data = properties.pop("data", None)
        self.props = dict(properties)
        self.TimestepValues = []
        native.sources[(label, len(native.sources))] = self
        native.active = self

    def __setattr__(self, key, value):
        if key in {"SliceType", "ClipType"} and value == "Plane":
            self.props[key] = Plane()
        elif key not in {"native", "kind", "label", "props", "data", "TimestepValues"} and "props" in self.__dict__:
            self.props[key] = value
        else:
            object.__setattr__(self, key, value)

    def __getattr__(self, key):
        if key not in self.props:
            raise AttributeError(key)
        return self.props[key]

    def GetXMLName(self):
        return self.kind

    def ListProperties(self):
        return list(self.props)

    def GetProperty(self, key):
        return Property(self.props[key])

    def UpdatePipelineInformation(self):
        pass

    def UpdatePipeline(self, time=None):
        if self.kind == "Reader":
            return
        if self.kind == "ForceTime":
            self.Input.UpdatePipeline(time=self.ForcedTime)
            self.data = self.Input.data
        elif self.kind == "PassArrays":
            self.Input.UpdatePipeline()
            self.data = vtk.vtkUnstructuredGrid()
            self.data.ShallowCopy(self.Input.data)
            self.data.GetPointData().Initialize()
            self.data.GetCellData().Initialize()
            self.data.GetFieldData().Initialize()
            for name in self.PointDataArrays:
                self.data.GetPointData().AddArray(self.Input.data.GetPointData().GetArray(name))
        elif self.kind == "ProgrammableFilter":
            inputs = self.Input if isinstance(self.Input, list) else [self.Input]
            for source in inputs:
                source.UpdatePipeline()
            self.data = vtk.vtkUnstructuredGrid()
            owner = SimpleNamespace(GetInputDataObject=lambda port, index: inputs[index].data,
                                    GetOutputDataObject=lambda port: self.data)
            exec(self.Script, {"self": owner})
        elif self.kind == "ResampleWithDataset":
            self.SourceDataArrays.UpdatePipeline()
            self.DestinationMesh.UpdatePipeline()
            probe = vtk.vtkResampleWithDataSet()
            probe.SetSourceData(self.SourceDataArrays.data)
            probe.SetInputData(self.DestinationMesh.data)
            for key in ("ComputeTolerance", "Tolerance", "SnapToCellWithClosestPoint", "MarkBlankPointsAndCells",
                        "PassPointArrays", "PassCellArrays", "PassFieldArrays", "CategoricalData"):
                getattr(probe, "Set" + key)(self.props[key])
            probe.Update()
            self.data = probe.GetOutput()
        elif self.kind in {"Slice", "Clip", "Contour", "WarpByVector", "PlotOverLine"}:
            self.Input.UpdatePipeline()
            source = self.Input.data
            if self.kind in {"Slice", "Clip"}:
                definition = self.SliceType if self.kind == "Slice" else self.ClipType
                plane = vtk.vtkPlane()
                plane.SetOrigin(definition.Origin)
                plane.SetNormal(definition.Normal)
                if self.kind == "Slice":
                    algorithm = vtk.vtkCutter()
                    algorithm.SetCutFunction(plane)
                    for i, value in enumerate(self.SliceOffsetValues):
                        algorithm.SetValue(i, value)
                else:
                    algorithm = vtk.vtkClipDataSet()
                    algorithm.SetClipFunction(plane)
                    algorithm.SetInsideOut(self.Invert)
            elif self.kind == "Contour":
                algorithm = vtk.vtkContourFilter()
                algorithm.SetInputArrayToProcess(0, 0, 0, 0, self.ContourBy[1])
                for i, value in enumerate(self.Isosurfaces):
                    algorithm.SetValue(i, value)
            elif self.kind == "WarpByVector":
                algorithm = vtk.vtkWarpVector()
                algorithm.SetInputArrayToProcess(0, 0, 0, 0, self.Vectors[1])
                algorithm.SetScaleFactor(self.ScaleFactor)
            else:
                line = vtk.vtkLineSource()
                line.SetPoint1(self.Point1)
                line.SetPoint2(self.Point2)
                line.SetResolution(self.Resolution)
                line.Update()
                algorithm = vtk.vtkResampleWithDataSet()
                algorithm.SetSourceData(source)
                algorithm.SetInputData(line.GetOutput())
                algorithm.SetComputeTolerance(self.ComputeTolerance)
                algorithm.SetTolerance(self.Tolerance)
            if self.kind != "PlotOverLine":
                algorithm.SetInputData(source)
            algorithm.Update()
            self.data = algorithm.GetOutput()
        else:
            raise AssertionError(self.kind)


class Plane:
    def __init__(self):
        self.Origin, self.Normal = [0,0,0], [1,0,0]
    def GetXMLName(self):
        return "Plane"
    def ListProperties(self):
        return ["Origin", "Normal"]
    def GetProperty(self, key):
        return Property(getattr(self, key))


class Native:
    def __init__(self):
        self.sources = {}
        self.active, self.view = None, object()
        self.scene = SimpleNamespace(AnimationTime=99)

    def GetActiveSource(self):
        return self.active

    def GetActiveView(self):
        return self.view

    def SetActiveSource(self, source):
        self.active = source

    def SetActiveView(self, view):
        self.view = view

    def GetSources(self):
        return self.sources

    def RenameSource(self, label, proxy):
        key = next(key for key, item in self.sources.items() if item is proxy)
        del self.sources[key]
        self.sources[(label, key[1])] = proxy
        proxy.label = label

    def Delete(self, proxy):
        keys = [key for key, item in self.sources.items() if item is proxy]
        for key in keys:
            del self.sources[key]

    def ProgrammableFilter(self, registrationName, Input):
        return Proxy(self, "ProgrammableFilter", registrationName, Input=Input, Script="")

    def PassArrays(self, registrationName, Input):
        return Proxy(self, "PassArrays", registrationName, Input=Input,
                     PointDataArrays=[], CellDataArrays=[], FieldDataArrays=[])

    def ForceTime(self, registrationName, Input):
        return Proxy(self, "ForceTime", registrationName, Input=Input, ForcedTime=0, IgnorePipelineTime=1)

    def ResampleWithDataset(self, registrationName, **kwargs):
        return Proxy(self, "ResampleWithDataset", registrationName, **kwargs,
                     ComputeTolerance=1, Tolerance=.001, SnapToCellWithClosestPoint=1,
                     MarkBlankPointsAndCells=1, PassPointArrays=1, PassCellArrays=1,
                     PassFieldArrays=1, CategoricalData=0)

    def Slice(self, registrationName, Input):
        return Proxy(self, "Slice", registrationName, Input=Input, SliceType=Plane(), SliceOffsetValues=[0],
                     Triangulatetheslice=1, Crinkleslice=0)

    def Clip(self, registrationName, Input):
        return Proxy(self, "Clip", registrationName, Input=Input, ClipType=Plane(), Invert=0, Crinkleclip=0,
                     Value=0., UseValueAsOffset=0)

    def Contour(self, registrationName, Input):
        return Proxy(self, "Contour", registrationName, Input=Input, ContourBy=[], Isosurfaces=[])

    def WarpByVector(self, registrationName, Input):
        return Proxy(self, "WarpByVector", registrationName, Input=Input, Vectors=[], ScaleFactor=1.)

    def PlotOverLine(self, registrationName, Input):
        return Proxy(self, "PlotOverLine", registrationName, Input=Input, Point1=[0,0,0], Point2=[1,0,0],
                     Resolution=10, SamplingPattern="Sample Uniformly", ComputeTolerance=1, Tolerance=.001)


def grid(points, cells, values, ids=None):
    result = vtk.vtkUnstructuredGrid()
    vtkpoints = vtk.vtkPoints()
    vtkpoints.SetData(numpy_to_vtk(np.asarray(points, dtype=float), deep=True))
    result.SetPoints(vtkpoints)
    for cell in cells:
        cellids = vtk.vtkIdList()
        for index in cell:
            cellids.InsertNextId(index)
        result.InsertNextCell(vtk.VTK_TETRA, cellids)
    array = numpy_to_vtk(np.asarray(values, dtype=float), deep=True)
    array.SetName("response")
    result.GetPointData().AddArray(array)
    array = numpy_to_vtk(np.asarray(ids if ids is not None else range(len(points)), dtype=np.int64), deep=True)
    array.SetName("NativeNodeId")
    result.GetPointData().AddArray(array)
    return result


@pytest.fixture
def analysis(monkeypatch):
    native = Native()
    manager = SimpleNamespace(Fetch=lambda source: source.data)
    monkeypatch.setitem(sys.modules, "paraview", SimpleNamespace(simple=native, servermanager=manager))
    # Narrow physical_input boundary: the real implementation is separately tested.
    def physical(source, arrays):
        assert arrays == [("POINTS", "response")]
        proxy = native.PassArrays(registrationName="physical", Input=source)
        proxy.PointDataArrays = ["response"]
        return proxy
    ext = SimpleNamespace(physical_input=physical)
    monkeypatch.setitem(sys.modules, "apps.desktop_post.external", ext)
    package = importlib.import_module("apps.desktop_post")
    monkeypatch.setattr(package, "external", ext, raising=False)
    monkeypatch.delitem(sys.modules, "apps.desktop_post.analysis", raising=False)
    module = importlib.import_module("apps.desktop_post.analysis")
    yield module, native
    sys.modules.pop("apps.desktop_post.analysis", None)


def recipe(method="linear_tetra_b_to_a"):
    side = {"source_ref": "stable-A", "array": "response", "association": "POINTS", "quantity": "temperature",
            "units": "K", "measure": "absolute", "frame": "scalar", "coordinate_units": "m",
            "coordinate_frame": "laboratory", "time": None, "time_units": None, "time_origin": None}
    return {"a": side, "b": {**side, "source_ref": "stable-B"}, "method": method, "tolerance": 1e-9}


def sources(native):
    bp = np.array([(0,0,0),(1,0,0),(0,1,0),(1,1,0),(0,0,1),(1,0,1),(0,1,1),(1,1,1)], dtype=float)
    bc = [(0,1,3,7),(0,3,2,7),(0,2,6,7),(0,6,4,7),(0,4,5,7),(0,5,1,7)]
    ap = np.array([(.2,.2,.2),(.8,.2,.2),(.2,.8,.2),(.2,.2,.8),(1.5,.2,.2)], dtype=float)
    affine = lambda xyz: 3 + 2*xyz[:,0] - 4*xyz[:,1] + 5*xyz[:,2]
    av = affine(ap) - 2
    av[0], av[2] = 0, np.nan
    a = Proxy(native, "Reader", "Original A", data=grid(ap, [(0,1,2,3),(1,2,3,4)], av,
                                                       ids=[2**60+i for i in range(len(ap))]))
    b = Proxy(native, "Reader", "Original B", data=grid(bp, bc, affine(bp), ids=range(900,908)))
    return a, b, affine


def test_actual_vtk_affine_cube_shifted_a_masks_ids_and_graph(analysis):
    module, native = analysis
    a, b, affine = sources(native)
    before = (native.active, native.view, native.scene.AnimationTime)
    bundle = module.build_comparison(a, b, recipe())
    assert (native.active, native.view, native.scene.AnimationTime) == before
    rows = module.sample_page(bundle)["rows"]
    assert rows[1]["b"] == pytest.approx(affine(np.array([rows[1]["coordinates"]]))[0], abs=1e-12)
    assert rows[1]["delta"] == pytest.approx(2, abs=1e-12)
    assert rows[0]["valid"] and rows[0]["percent"] is None and rows[0]["percent_reason"] == "zero_a"
    assert rows[2]["validity_reason"] == "nonfinite_a" and rows[2]["delta"] is None
    assert rows[4]["validity_reason"] == "outside_b_domain" and rows[4]["b"] is None
    assert rows[1]["original_a_ids"] == {"NativeNodeId": 2**60+1}
    assert all(900 not in row["original_a_ids"].values() for row in rows)
    probe = next(proxy for proxy in bundle["proxies"] if proxy.kind == "ResampleWithDataset")
    assert set(probe.SourceDataArrays.data.GetPointData().GetArrayName(i)
               for i in range(probe.SourceDataArrays.data.GetPointData().GetNumberOfArrays())) == {"__post_B_scalar"}
    assert probe.DestinationMesh is a
    assert not probe.ComputeTolerance and not probe.SnapToCellWithClosestPoint
    assert not any(probe.props[key] for key in ("PassPointArrays", "PassCellArrays", "PassFieldArrays"))
    summary = bundle["summary"]
    assert summary["validity_counts"] == {"valid": 3, "outside_b_domain": 1, "nonfinite_a": 1,
                                           "nonfinite_b": 0, "nonfinite_difference": 0}
    json.dumps(summary, allow_nan=False)
    graph = module.graph_signature(bundle)
    # Simulate session-local registration numeric IDs changing on PVSM restore.
    native.sources = {(label, i+10000): value for i, ((label, _), value) in enumerate(native.sources.items())}
    assert module.graph_signature(bundle) == graph
    probe.Tolerance = .005
    assert module.graph_signature(bundle)["sha256"] != graph["sha256"]
    module.cleanup(bundle)
    assert set(native.sources.values()) == {a, b}


def test_same_mesh_checks_exact_order_not_ids_and_nonfinite_b(analysis):
    module, native = analysis
    a, _, _ = sources(native)
    data = vtk.vtkUnstructuredGrid()
    data.DeepCopy(a.data)
    b = Proxy(native, "Reader", "Other B", data=data)
    vals = vtk_to_numpy(data.GetPointData().GetArray("response"))
    vals[:] = [1,2,3,np.inf,5]
    bundle = module.build_comparison(a, b, recipe("same_mesh"))
    assert module.sample_page(bundle, point_index=1)["rows"][0]["b"] == 2
    assert module.sample_page(bundle, point_index=3)["rows"][0]["validity_reason"] == "nonfinite_b"
    module.cleanup(bundle)
    coords = vtk_to_numpy(data.GetPoints().GetData())
    coords[[0,1]] = coords[[1,0]]
    before = dict(native.sources)
    with pytest.raises(ValueError, match="exact ordered"):
        module.build_comparison(a, b, recipe("same_mesh"))
    assert native.sources == before
    coords[[0,1]] = coords[[1,0]]
    cell = vtk.vtkIdList()
    for index in (1,0,2,3):
        cell.InsertNextId(index)
    data.ReplaceCell(0, 4, [1,0,2,3])
    with pytest.raises(ValueError, match="exact ordered"):
        module.build_comparison(a, b, recipe("same_mesh"))


@pytest.mark.parametrize("field,value", [("units", "C"), ("quantity", "displacement"), ("frame", "different"),
                                         ("measure", None), ("coordinate_units", "mm"), ("coordinate_frame", "local"),
                                         ("association", "CELLS"), ("time", .5)])
def test_incompatible_missing_metadata_no_mutation(analysis, field, value):
    module, native = analysis
    a, b, _ = sources(native)
    request = recipe()
    request["b"][field] = value
    before, active = dict(native.sources), native.active
    with pytest.raises(ValueError):
        module.build_comparison(a, b, request)
    assert native.sources == before and native.active is active and native.scene.AnimationTime == 99


def test_temporal_freeze_native_exact_time_and_cleanup_on_missing_property(analysis):
    module, native = analysis
    a, b, _ = sources(native)
    a.TimestepValues = b.TimestepValues = [0., 1.]
    request = recipe()
    for side in ("a", "b"):
        request[side].update(time=1., time_units="s", time_origin="experiment start")
    bundle = module.build_comparison(a, b, request)
    frozen = [proxy for proxy in bundle["proxies"] if proxy.kind == "ForceTime"]
    assert len(frozen) == 2 and all(proxy.ForcedTime == 1 and proxy.IgnorePipelineTime == 1 for proxy in frozen)
    assert native.scene.AnimationTime == 99
    module.cleanup(bundle)
    request["b"]["time"] = .5
    with pytest.raises(ValueError, match="exact common"):
        module.build_comparison(a, b, request)
    request["b"]["time"] = 1.
    old = native.ForceTime
    def broken(**kwargs):
        proxy = old(**kwargs)
        proxy.props.pop("IgnorePipelineTime")
        return proxy
    native.ForceTime = broken
    before = dict(native.sources)
    with pytest.raises(RuntimeError, match="lacks ForcedTime"):
        module.build_comparison(a, b, request)
    assert native.sources == before


def test_pages_bounded_actual_inspection_and_mesh_rejections(analysis):
    module, native = analysis
    a, b, _ = sources(native)
    bundle = module.build_comparison(a, b, recipe())
    page = module.sample_page(bundle, offset=1, limit=2)
    assert len(page["rows"]) == 2 and page["next_offset"] == 3
    for args in ({"limit":1001}, {"point_index":5}, {"point_index":True}, {"offset":-1}):
        with pytest.raises(ValueError):
            module.sample_page(bundle, **args)
    result = module.inspect_source(a, array="response")
    assert result["statistics"]["finite"] == 4 and result["mesh_hash"] == bundle["summary"]["mesh_hash_a"]
    vtk_to_numpy(a.data.GetPoints().GetData())[0,0] = np.inf
    with pytest.raises(ValueError, match="coordinates"):
        module.build_comparison(a, b, recipe())
    poly = Proxy(native, "Reader", "Poly", data=vtk.vtkPolyData())
    with pytest.raises(ValueError, match="vtkUnstructuredGrid"):
        module.build_comparison(poly, b, recipe())


@pytest.mark.parametrize("kind,settings", [
    ("Slice", {"origin":[.5,0,0], "normal":[1,0,0]}),
    ("Clip", {"origin":[.5,0,0], "normal":[1,0,0], "invert":True}),
    ("Contour", {"array":"response", "values":[3.]}),
    ("PlotOverLine", {"array":"response", "point1":[.1,.2,.3], "point2":[.9,.2,.3],
                      "resolution":8, "tolerance":1e-9}),
])
def test_filters_use_native_geometry_and_strip_interpolated_identity(analysis, kind, settings):
    module, native = analysis
    a, b, affine = sources(native)
    previous = (native.active, native.view)
    bundle = module.create_filter(b, kind, settings)
    assert (native.active, native.view) == previous
    result = bundle["source"].data
    assert result.GetNumberOfPoints() > 0
    assert result.GetPointData().GetArray("NativeNodeId") is None
    json.dumps(bundle["summary"], allow_nan=False)
    if kind == "Slice":
        assert all(result.GetPoint(i)[0] == pytest.approx(.5) for i in range(result.GetNumberOfPoints()))
    elif kind == "Clip":
        assert all(result.GetPoint(i)[0] <= .5+1e-12 for i in range(result.GetNumberOfPoints()))
    elif kind == "Contour":
        assert vtk_to_numpy(result.GetPointData().GetArray("response")) == pytest.approx(3.)
    else:
        page = module.sample_native_points(bundle["source"], "response", limit=3)
        assert page["points"] == 9 and page["next_offset"] == 3
        for row in page["rows"]:
            assert row["valid"] and row["value"] == pytest.approx(affine(np.array([row["coordinates"]]))[0])
    module.cleanup(bundle)
    assert set(native.sources.values()) == {a,b}


def test_warp_uses_native_vector_scale_and_filter_rejection_keeps_source(analysis):
    module, native = analysis
    a, b, _ = sources(native)
    vector = numpy_to_vtk(np.tile([.1,.2,.3], (b.data.GetNumberOfPoints(),1)), deep=True)
    vector.SetName("displacement")
    b.data.GetPointData().AddArray(vector)
    bundle = module.create_filter(b, "WarpByVector", {"array":"displacement", "scale_factor":2.})
    assert bundle["source"].data.GetPoint(0) == pytest.approx([.2,.4,.6])
    assert bundle["source"].data.GetPointData().GetArray("NativeNodeId") is not None
    module.cleanup(bundle)
    before, active = dict(native.sources), native.active
    for kind, settings in [("Slice", {"origin":[0,0,0],"normal":[0,0,0]}),
                           ("WarpByVector", {"array":"response","scale_factor":1}),
                           ("Contour", {"array":"response","values":[np.nan]}),
                           ("PlotOverLine", {"array":"NativeNodeId","point1":[0,0,0],"point2":[1,0,0],
                                             "resolution":10,"tolerance":0.}),
                           ("ProgrammableFilter", {})]:
        with pytest.raises(ValueError):
            module.create_filter(b, kind, settings)
        assert native.sources == before and native.active is active


def test_percent_change_uses_absolute_a_denominator(analysis):
    module, native = analysis
    a, _, _ = sources(native)
    bdata = vtk.vtkUnstructuredGrid()
    bdata.DeepCopy(a.data)
    b = Proxy(native, "Reader", "Negative reference B", data=bdata)
    vtk_to_numpy(a.data.GetPointData().GetArray("response"))[1] = -2.
    vtk_to_numpy(bdata.GetPointData().GetArray("response"))[1] = 1.
    bundle = module.build_comparison(a, b, recipe("same_mesh"))
    row = module.sample_page(bundle, point_index=1)["rows"][0]
    assert row["delta"] == 3. and row["percent"] == 150.
    assert bundle["summary"]["percent_definition"] == "100 * (B_at_A - A) / abs(A)"


def test_generic_native_samples_preserve_integer_ids_and_connectivity(analysis):
    module, native = analysis
    a, _, _ = sources(native)
    points = module.sample_data(a, offset=1, limit=2)
    assert points["rows"][0]["values"]["NativeNodeId"] == 2**60+1
    assert points["rows"][1]["values"]["response"] is None
    assert points["rows"][1]["validity"]["response"] == "nonfinite"
    cells = module.sample_data(a, association="CELLS")
    assert cells["rows"][0]["point_indices"] == [0,1,2,3]
    json.dumps(points, allow_nan=False)


def test_output_fingerprint_detects_upstream_values_and_original_identity_change(analysis):
    module, native = analysis
    a, _, _ = sources(native)
    bd = vtk.vtkUnstructuredGrid()
    bd.DeepCopy(a.data)
    b = Proxy(native, "Reader", "Fingerprint B", data=bd)
    bundle = module.build_comparison(a, b, recipe("same_mesh"))
    original = module.output_fingerprint(bundle)
    assert original["output_hash"] == bundle["summary"]["output_hash"]
    vtk_to_numpy(bd.GetPointData().GetArray("response"))[1] += 2
    changed = module.output_fingerprint(bundle)
    assert changed["output_hash"] != original["output_hash"] and changed["mesh_hash"] == original["mesh_hash"]
    vtk_to_numpy(a.data.GetPointData().GetArray("NativeNodeId"))[1] += 1
    assert module.output_fingerprint(bundle)["output_hash"] != changed["output_hash"]
