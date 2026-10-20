"""Native reader/state boundaries without requiring ParaView in ordinary Python."""
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


class Array:
    def __init__(self, components=1):
        self.components = components

    def GetNumberOfComponents(self):
        return self.components

    def GetComponentName(self, index):
        return ["X", "Y", "Z"][index] if self.components > 1 else ""

    def GetRange(self):
        return (1.0, 7.0)


class Source:
    def __init__(self, kind, filename, temporal=False):
        self.kind = kind
        self.FileName = [filename] if isinstance(filename, str) else filename
        self.SMProxy = self
        self.TimestepValues = [0.0, 1.0] if temporal else []
        self.PointData = {"response": Array(), "velocity": Array(3), "NativeNodeId": Array()}
        self.CellData = {"response": Array()}
        self.FieldData = {}
        self.time = None

    def GetXMLName(self):
        return self.kind

    def UpdatePipeline(self, time=None):
        self.time = time

    def GetDataInformation(self):
        return SimpleNamespace(GetNumberOfPoints=lambda: 4, GetNumberOfCells=lambda: 1,
                               GetBounds=lambda: [0, 1, 0, 1, 0, 1])


class Native:
    def __init__(self):
        self.sources = {}
        self.views = []
        self.active = None
        self.view = None
        self.scene = SimpleNamespace(AnimationTime=0.0, UpdateAnimationUsingDataTimeSteps=lambda: None)
        self.loaded = False

    def reader(self, kind, registrationName, FileName):
        source = Source(kind, FileName, temporal=kind == "PVDReader")
        self.sources[(registrationName, len(self.sources))] = source
        return source

    def XMLUnstructuredGridReader(self, **args):
        return self.reader("XMLUnstructuredGridReader", **args)

    def PVDReader(self, **args):
        return self.reader("PVDReader", **args)

    def GetSources(self):
        return self.sources

    def FindSource(self, name):
        return next((source for (label, _), source in self.sources.items() if label == name), None)

    def CreateLayout(self, **args):
        return object()

    def CreateView(self, kind):
        view = SimpleNamespace(GetXMLName=lambda: kind, ViewTime=0.0)
        self.views.append(view)
        return view

    def AssignViewToLayout(self, **args):
        pass

    def GetViews(self):
        return self.views

    def GetActiveView(self):
        return self.view

    def SetActiveView(self, view):
        self.view = view

    def SetActiveSource(self, source):
        self.active = source

    def GetActiveSource(self):
        return self.active

    def GetAnimationScene(self):
        return self.scene

    def Show(self, source, view):
        return SimpleNamespace(RescaleTransferFunctionToDataRange=lambda *args: None,
                               SetScalarBarVisibility=lambda *args: None)

    def ResetCamera(self, view):
        pass

    def ColorBy(self, display, selection):
        self.selection = selection

    def HideUnusedScalarBars(self, view):
        assert view in self.views

    def PassArrays(self, registrationName, Input):
        return Source("PassArrays", [])

    def SaveState(self, path):
        Path(path).write_text(json.dumps({"readers": [{"label": label, "kind": source.kind, "files": source.FileName}
                                                     for (label, _), source in self.sources.items()],
                                         "time": self.scene.AnimationTime}), encoding="utf-8")

    def LoadState(self, path):
        self.loaded = True
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        self.sources.clear()
        for record in state["readers"]:
            self.reader(record["kind"], record["label"], record["files"])
        self.scene.AnimationTime = state["time"]
        self.views.clear()
        self.CreateView("RenderView")


@pytest.fixture
def native(monkeypatch):
    monkeypatch.setenv("CAE_POST_PROJECT", "test-not-opened")
    fake = Native()
    manager = SimpleNamespace(
        vtkSMCoreUtilities=SimpleNamespace(GetFileNameProperty=lambda source: "FileName"),
        ProxyManager=lambda: SimpleNamespace(GetProxiesInGroup=lambda group:
            {(f"View{i}", i): view for i, view in enumerate(fake.views)} if group == "views" else fake.sources),
    )
    monkeypatch.setitem(sys.modules, "paraview", SimpleNamespace(simple=fake, servermanager=manager))
    for name in ("apps.desktop_post.commands", "apps.desktop_post.external"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    commands = importlib.import_module("apps.desktop_post.commands")
    external = importlib.import_module("apps.desktop_post.external")
    yield fake, commands, external
    sys.modules.pop("apps.desktop_post.external", None)
    sys.modules.pop("apps.desktop_post.commands", None)


def pvd_files(tmp_path):
    folder = tmp_path / "한글 결과"
    folder.mkdir()
    frames = folder / "frames"
    frames.mkdir()
    (frames / "zero.vtu").write_text("native frame zero", encoding="utf-8")
    (frames / "one.vtu").write_text("native frame one", encoding="utf-8")
    entry = folder / "시계열.pvd"
    entry.write_text('<VTKFile type="Collection"><Collection><DataSet timestep="0" file="frames/zero.vtu"/>'
                     '<DataSet timestep="1" file="frames/one.vtu"/></Collection></VTKFile>', encoding="utf-8")
    return entry


def test_new_document_title_uses_input_filename(native, tmp_path):
    _, _, external = native
    entry = pvd_files(tmp_path)
    project = external.open_result(entry, tmp_path / 'analysis')
    assert json.loads(project.read_text(encoding='utf-8'))['title'] == entry.name


def test_independent_frd_open_uses_converter_and_retains_original_without_declared_units(native, tmp_path, monkeypatch):
    _, _, external = native
    frd = tmp_path / 'calculation.frd'; frd.write_bytes(b'actual native source')
    converted = pvd_files(tmp_path)
    def convert(source, output):
        assert Path(source) == frd
        output.mkdir(parents=True)
        retained = output / 'calculation.frd'; retained.write_bytes(frd.read_bytes())
        return {'entry_path': str(converted), 'original_path': str(frd), 'retained_path': str(retained),
                'summary': {'time_units': None}, 'execution_status': None}
    monkeypatch.setattr('caelab.adapters.native_calculix_results.convert_independent', convert)
    project = external.open_result(frd, tmp_path / 'analysis')
    doc = json.loads(project.read_text(encoding='utf-8'))
    record = doc['sources']['result']
    assert doc['title'] == frd.name and record['label'] == frd.name
    assert record['conversion']['execution_status'] is None
    assert record['metadata']['coordinate_units'] is None and 'native_metadata' not in record
    frd.write_bytes(b'next run same name')
    external.verify_sources(project, doc)
    with pytest.raises(FileExistsError):
        external.open_result(frd, tmp_path / 'analysis')
    Path(record['conversion']['retained_path']).write_bytes(b'changed retained source')
    with pytest.raises(RuntimeError, match='Retained FRD'):
        external.verify_sources(project, doc)
    from apps.desktop_post import source_repair
    monkeypatch.setattr(source_repair, 'external', external)
    assert source_repair.source_issues(doc)[0]['code'] == 'CONTENT_CHANGED'
    Path(record['conversion']['retained_path']).unlink()
    assert source_repair.source_issues(doc)[0]['code'] == 'MISSING_DEPENDENCY'


def test_selected_context_retains_displayed_array_component_and_native_time(native, tmp_path):
    fake, _, external = native
    entry = pvd_files(tmp_path)
    external.open_result(entry, tmp_path / 'analysis')
    fake.GetDisplayProperties = lambda source, view: SimpleNamespace(
        ColorArrayName=['POINTS', 'velocity'], LookupTable=SimpleNamespace(VectorMode='Component', VectorComponent=2))
    fake.scene.AnimationTime = 1.
    context = external.selected_context()
    assert context['path'] == str(entry)
    assert context['scope']['array'] == 'velocity' and context['scope']['component'] == 2
    assert context['scope']['time'] == 1. and context['scope']['static'] is None
    assert 'native_selection' not in context['scope']


def test_post_discussion_navigation_uses_primary_runtime_and_original_discussion(tmp_path, monkeypatch):
    from apps.desktop_post.navigation import discuss_selection
    import sys
    calls = []
    monkeypatch.setattr('apps.desktop_post.navigation.subprocess.Popen',
        lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(pid=42))
    selection = {'path': str(tmp_path / 'native.pvd'), 'scope': {'array': 'STRESS', 'component': 3, 'time': .2}}
    environment = {'CAE_POST_SERVICE_URL': 'http://127.0.0.1:8766', 'CAELAB_DESKTOP_PYTHON': sys.executable,
        'CAELAB_REPO_ROOT': str(tmp_path), 'PYTHONPATH': 'foreign-runtime', 'CAELAB_DISCUSSION_ID': 'Eoriginal'}
    result = discuss_selection({}, selection, environment=environment)
    command, settings = calls[0]
    assert command[:3] == [sys.executable, '-m', 'apps.research.selection_discussion']
    assert json.loads(command[command.index('--selection') + 1]) == selection
    assert command[-3:] == ['--discussion', 'Eoriginal', selection['path']]
    assert 'PYTHONPATH' not in settings['env'] and result['pid'] == 42


def test_temporal_open_selection_save_restore_and_dependency_guards(native, tmp_path, monkeypatch):
    fake, commands, external = native
    entry = pvd_files(tmp_path)
    before = external.pins(external.source_files(entry))
    project = external.open_result(entry, tmp_path / "analysis", input_id="Iregistered", source_pins=before)
    assert len(fake.views) == 1
    source = fake.active
    metadata = external.inspect_result(source, time=1)
    assert metadata["time"] == 1 and metadata["timesteps"] == [0, 1]
    assert all(array["units"] is None for array in metadata["arrays"])
    assert {array["association"] for array in metadata["arrays"]} == {"POINTS", "CELLS"}
    external.select_array(source, "CELLS", "response", time=1)
    assert fake.selection == ("CELLS", "response")
    with pytest.raises(ValueError, match="exact native timestep"):
        external.inspect_result(source, time=0.5)
    with pytest.raises(ValueError, match="association conversion"):
        external.select_array(source, "FIELD", "response")
    saved = commands.save_project()
    fake.sources.clear()
    commands.restore_workspace()
    assert fake.loaded and fake.scene.AnimationTime == 1
    assert json.loads(saved.read_text(encoding="utf-8"))["sources"]["result"]["input_id"] == "Iregistered"
    assert before == external.pins(external.source_files(entry))
    frame = entry.parent / "frames/one.vtu"
    frame.write_text("changed frame", encoding="utf-8")
    fake.loaded = False
    with pytest.raises(ValueError, match="CONTENT_CHANGED"):
        commands.restore_workspace()
    assert not fake.loaded


def test_live_reader_retarget_and_rehashed_state_mismatch_rejected(native, tmp_path):
    fake, commands, external = native
    entry = tmp_path / "source.vtu"
    other = tmp_path / "other.vtu"
    entry.write_text("source")
    other.write_text("other")
    project = external.open_result(entry, tmp_path / "analysis")
    fake.active.FileName = [str(other)]
    with pytest.raises(RuntimeError, match="reader path mismatch"):
        commands.save_project()
    doc = json.loads(project.read_text())
    state = project.parent / doc["workspace_file"]
    fake.SaveState(str(state))
    doc["workspace_sha256"] = commands.sha(state)
    project.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="reader path mismatch"):
        commands.restore_workspace()


def test_dependencies_unsupported_and_registered_pins(native, tmp_path):
    _, _, external = native
    entry = pvd_files(tmp_path)
    with pytest.raises(RuntimeError, match="Registered source pins"):
        external.open_result(entry, tmp_path / "bad-pins", source_pins=[])
    assert not (tmp_path / "bad-pins").exists()
    unsupported = tmp_path / "mesh.vtk"
    unsupported.write_text("legacy")
    with pytest.raises(ValueError, match="Supported result inputs"):
        external.source_files(unsupported)
    entry.write_text('<VTKFile type="Collection"><Collection><DataSet timestep="0" file="../outside.vtu"/></Collection></VTKFile>')
    with pytest.raises(ValueError, match="contained relative local paths"):
        external.source_files(entry)


def test_missing_frames_and_nonfinite_times(native, tmp_path):
    _, _, external = native
    entry = pvd_files(tmp_path)
    entry.write_text('<VTKFile type="Collection"><Collection><DataSet timestep="nan" file="frames/zero.vtu"/></Collection></VTKFile>')
    with pytest.raises(ValueError, match="finite numeric timestep"):
        external.source_files(entry)
    entry.write_text('<VTKFile type="Collection"><Collection><DataSet timestep="0" file="frames/missing.vtu"/></Collection></VTKFile>')
    with pytest.raises(FileNotFoundError):
        external.source_files(entry)


def test_spatial_sampling_requires_response_selection_and_strips_identity(native):
    fake, _, external = native
    source = Source("XMLUnstructuredGridReader", [])
    with pytest.raises(ValueError, match="Identity/classification"):
        external.physical_input(source, [("POINTS", "NativeNodeId")])
    sampled = external.physical_input(source, [("POINTS", "response")])
    assert sampled.PointDataArrays == ["response"]
    assert sampled.CellDataArrays == [] and sampled.FieldDataArrays == []


@pytest.mark.parametrize("reference", ["", "/outside.vtu", "C:/outside.vtu", "frames\\outside.vtu", "remote:outside.vtu", "../outside.vtu"])
def test_unsafe_pvd_references_rejected_before_frame_access(native, tmp_path, reference):
    _, _, external = native
    entry = tmp_path / "unsafe.pvd"
    # Even the first legal reference is missing: all paths must be admitted before access.
    entry.write_text('<VTKFile type="Collection"><Collection><DataSet timestep="0" file="missing.vtu"/>'
                     f'<DataSet timestep="1" file="{reference}"/></Collection></VTKFile>', encoding="utf-8")
    with pytest.raises(ValueError, match="contained relative local paths"):
        external.source_files(entry)


@pytest.mark.parametrize("payload, message", [
    (b'<!DOCTYPE VTKFile><VTKFile type="Collection"/>', "declarations/entities"),
    (b'<!ENTITY injected "value"><VTKFile type="Collection"/>', "declarations/entities"),
    (b'<VTKFile type="Collection"><Collection>', "Invalid native XML metadata"),
    (b'<VTKFile type="Collection">\xff</VTKFile>', "Invalid native XML metadata"),
])
def test_pvd_xml_admission(native, tmp_path, payload, message):
    _, _, external = native
    entry = tmp_path / "invalid.pvd"
    entry.write_bytes(payload)
    with pytest.raises(ValueError, match=message):
        external.source_files(entry)


def test_pvd_metadata_and_dataset_limits(native, tmp_path):
    _, _, external = native
    entry = tmp_path / "oversized.pvd"
    with entry.open("wb") as stream:
        stream.truncate(8 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="exceeds its size limit"):
        external.source_files(entry)
    entry.write_text('<VTKFile type="Collection"><Collection>'
                     + '<DataSet timestep="0" file="missing.vtu"/>' * 1025
                     + '</Collection></VTKFile>', encoding="utf-8")
    with pytest.raises(ValueError, match="1..1024 frame datasets"):
        external.source_files(entry)


def test_registered_open_derives_path_id_and_complete_pins_from_service(native, tmp_path, monkeypatch):
    _, _, external = native
    from caelab.workbench_client import Client
    entry = pvd_files(tmp_path)
    receipt = {"id": "Iregistered", "path": str(entry), "format": "pvd",
               "source_pins": external.pins(external.source_files(entry))}
    requested = []

    def native_input(client, identifier):
        requested.append((client.url, identifier))
        return receipt

    monkeypatch.setattr(Client, "native_input", native_input, raising=False)
    project = external.open_registered("Iregistered", tmp_path / "managed", "http://127.0.0.1:8000")
    record = json.loads(project.read_text(encoding="utf-8"))["sources"]["result"]
    assert requested == [("http://127.0.0.1:8000", "Iregistered")]
    assert record["input_id"] == receipt["id"] and record["entry_path"] == receipt["path"]
    assert record["source_pins"] == receipt["source_pins"]


@pytest.mark.parametrize("damage", ["wrong_id", "wrong_path", "hash", "missing_frame"])
def test_registered_receipt_mismatch_is_rejected_before_native_mutation(native, tmp_path, monkeypatch, damage):
    fake, _, external = native
    from caelab.workbench_client import Client
    entry = pvd_files(tmp_path)
    receipt = {"id": "Iregistered", "path": str(entry), "format": "pvd",
               "source_pins": external.pins(external.source_files(entry))}
    if damage == "wrong_id":
        receipt["id"] = "Iother"
    elif damage == "wrong_path":
        receipt["path"] = str(entry.parent / "frames/zero.vtu")
        receipt["format"] = "vtu"
    elif damage == "hash":
        receipt["source_pins"][1]["sha256"] = "0" * 64
    else:
        receipt["source_pins"].pop()
    monkeypatch.setattr(Client, "native_input", lambda client, identifier: receipt, raising=False)
    with pytest.raises(RuntimeError, match="receipt ID|source pins"):
        external.open_registered("Iregistered", tmp_path / "rejected", "http://127.0.0.1:8000")
    assert fake.sources == {} and not (tmp_path / "rejected").exists()


def test_unverified_input_id_and_remote_service_are_rejected(native, tmp_path):
    _, _, external = native
    entry = pvd_files(tmp_path)
    with pytest.raises(ValueError, match="complete verified source pins"):
        external.open_result(entry, tmp_path / "unverified", input_id="Iarbitrary")
    with pytest.raises(ValueError, match="explicit local workbench"):
        external.open_registered("Iregistered", tmp_path / "remote", "https://example.com")
    assert not (tmp_path / "unverified").exists() and not (tmp_path / "remote").exists()


def test_cli_has_exclusive_direct_and_registered_modes(native, monkeypatch):
    _, _, external = native
    opened = []
    monkeypatch.setattr(external, "open_result", lambda *args: opened.append(("direct", args)))
    monkeypatch.setattr(external, "open_registered", lambda *args: opened.append(("registered", args)))
    external.main(["input.vtu", "output"])
    external.main(["output", "--registered-input", "Iregistered", "--service-url", "http://127.0.0.1:8000"])
    assert opened == [("direct", ("input.vtu", "output")),
                      ("registered", ("Iregistered", "output", "http://127.0.0.1:8000"))]
    for args in (["input.vtu", "output", "--input-id", "Iarbitrary"],
                 ["input.vtu", "output", "--registered-input", "Iregistered", "--service-url", "http://127.0.0.1:8000"],
                 ["output", "--registered-input", "Iregistered"]):
        with pytest.raises(SystemExit):
            external.main(args)


@pytest.mark.parametrize("selection", [
    {"association": "POINTS", "array": "missing", "time": 0},
    {"association": "FIELD", "array": "response", "time": 0},
    {"association": "POINTS", "array": "velocity", "component": "missing", "time": 0},
    {"association": "POINTS", "array": "response", "time": .5},
])
def test_rejected_selection_does_not_change_time_view_or_active_source(native, selection):
    fake, _, external = native
    source = fake.PVDReader(registrationName="source", FileName="not-read.pvd")
    original = fake.CreateView("RenderView")
    requested = fake.CreateView("RenderView")
    fake.SetActiveView(original)
    fake.SetActiveSource(source)
    fake.scene.AnimationTime = original.ViewTime = 1
    with pytest.raises(ValueError):
        external.select_array(source, view=requested, **selection)
    assert fake.scene.AnimationTime == original.ViewTime == 1
    assert fake.view is original and fake.active is source
    assert requested.ViewTime == 0


def test_selection_applies_time_to_exact_requested_view(native):
    fake, _, external = native
    source = fake.PVDReader(registrationName="source", FileName="not-read.pvd")
    original = fake.CreateView("RenderView")
    requested = fake.CreateView("RenderView")
    fake.SetActiveView(original)
    external.select_array(source, "POINTS", "response", time=1, view=requested)
    assert fake.view is requested and requested.ViewTime == 1 and original.ViewTime == 0
