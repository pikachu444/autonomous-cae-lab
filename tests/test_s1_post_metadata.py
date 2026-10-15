"""Captured S1 metadata through real retained inputs and ParaView 6.2 readers.

Controlled field values only: no FE solve, GUI, SDK or provider execution.
Run with the existing pvpython/pytest driver; no proxy or validator doubles.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

paraview = pytest.importorskip("paraview.simple")
from paraview import servermanager
import vtk

from apps.desktop_post.external import validate_declared_metadata
from caelab.native_inputs import register_native_input
from caelab.physical_fields import write_field
from caelab.workbench import Workbench
from plugins.thermoelastic.reference import seal_field
from test_s1_p1_temperature import analytic_field, settings


OPTIONAL = ("basis", "mesh_sha256", "snapshot_kind")


def captured_field(basis="P1", snapshot_kind="steady"):
    field = analytic_field(settings(instant=2., origin="captured_physical_clock"))
    if basis == "DG0":
        coordinates = deepcopy(field["coordinates"])
        lookup = dict(zip(field["node_ids"], coordinates))
        cells = field["cell_node_ids"]
        field.update(association="CELLS", basis="DG0", mesh_coordinates=coordinates,
            coordinates=[[sum(lookup[node][axis] for node in cell) / 3 for axis in range(2)] for cell in cells],
            cell_ids=list(range(101, 101 + len(cells))),
            value=[[1.e6 + index, 2.e6 + index, 3.e5 + index] for index in range(len(cells))],
            component="tensor_components", components=["xx", "yy", "xy"],
            unit="Pa", quantity="stress", measure="infinitesimal_Cauchy",
            location="cell", reduction="cell_average", valid_mask=[True] * len(cells))
    field["snapshot_kind"] = snapshot_kind
    return seal_field(field)


def registered_input(workbench, exported, metadata):
    entry = Path(exported["path"])
    receipt = register_native_input(workbench.root, entry.parent, entry, "D" + uuid.uuid4().hex,
        root_id="captured-s1", relative=entry.name, limit=1024 * 1024, native_metadata=metadata)
    native = workbench.native_input(receipt["id"])
    assert native["native_metadata"] == metadata
    assert Path(native["path"]).is_relative_to(workbench.root / "inputs")
    assert {Path(pin["path"]).suffix for pin in native["source_pins"]} == {".pvd", ".vtu"}
    return native


@contextmanager
def retained_field(folder, field):
    name = "stress" if field.get("association") == "CELLS" else "temperature"
    exported = write_field(name, field, folder / "captured-field")
    wb = Workbench(folder / "workspace")
    reader = None
    try:
        native = registered_input(wb, exported, exported["native_metadata"])
        reader = paraview.PVDReader(FileName=str(native["path"]))
        reader.UpdatePipelineInformation()
        reader.UpdatePipeline(time=field["time"])
        yield SimpleNamespace(field=field, name=name, exported=exported, native=native, reader=reader, workbench=wb)
    finally:
        if reader is not None:
            paraview.Delete(reader)
        wb.shutdown()


@pytest.fixture(scope="module")
def p1_retained(tmp_path_factory):
    with retained_field(tmp_path_factory.mktemp("s1-metadata-native"), captured_field()) as result:
        yield result


@pytest.mark.parametrize("basis,snapshot_kind", [("P1", "steady"), ("DG0", "physical_snapshot")])
def test_captured_metadata_survives_publisher_registration_and_native_readers(tmp_path, basis, snapshot_kind):
    field = captured_field(basis, snapshot_kind)
    original = deepcopy(field)
    with retained_field(tmp_path, field) as result:
        metadata = validate_declared_metadata(result.reader, result.native["native_metadata"])
        assert metadata == result.exported["native_metadata"]
        assert {key: metadata[key] for key in OPTIONAL} == {key: field[key] for key in OPTIONAL}
        assert metadata["time"] == {"unit": "s", "semantics": "captured_physical_clock", "values": [2.]}
        assert list(result.reader.TimestepValues) == [2.]
        assert metadata["static"] is None and metadata["coordinate_units"] == "m"
        quantity = [row for row in metadata["arrays"] if row.get("quantity")]
        assert quantity and all(row["association"] == field["association"] for row in quantity)
        assert all((row["units"], row["frame"], row["measure"]) ==
            (field["unit"], field["frame"], field["measure"]) for row in quantity)
        # Read the actual copied VTU separately from the actual PVD proxy.
        path = next(Path(pin["path"]) for pin in result.native["source_pins"] if Path(pin["path"]).suffix == ".vtu")
        reader = vtk.vtkXMLUnstructuredGridReader()
        reader.SetFileName(str(path))
        reader.Update()
        grid = reader.GetOutput()
        assert grid.GetNumberOfPoints() == len(field["node_ids"])
        assert grid.GetNumberOfCells() == len(field["cell_node_ids"])
        data = grid.GetPointData() if basis == "P1" else grid.GetCellData()
        names = [result.name] if basis == "P1" else [result.name + "_" + name for name in field["components"]]
        for component, name in enumerate(names):
            expected = field["value"] if basis == "P1" else [row[component] for row in field["value"]]
            array = data.GetArray(name)
            assert [array.GetTuple1(index) for index in range(array.GetNumberOfTuples())] == expected
        fetched = servermanager.Fetch(result.reader)
        assert fetched.GetNumberOfPoints() == len(field["node_ids"])
        assert fetched.GetNumberOfCells() == len(field["cell_node_ids"])
        assert field == original
        assert not result.workbench.manager.list()


@pytest.mark.parametrize("key,bad", [
    ("basis", "P2"), ("basis", []), ("basis", {}), ("basis", None),
    ("mesh_sha256", "A" * 64), ("mesh_sha256", []), ("mesh_sha256", {}), ("mesh_sha256", None),
    ("snapshot_kind", "transient"), ("snapshot_kind", []), ("snapshot_kind", {}), ("snapshot_kind", None),
])
def test_invalid_optional_declarations_are_rejected_by_publisher_and_real_native_validator(p1_retained, tmp_path, key, bad):
    result = p1_retained
    field = deepcopy(result.field)
    field[key] = bad
    with pytest.raises(ValueError):
        write_field("temperature", seal_field(field), tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()
    metadata = deepcopy(result.native["native_metadata"])
    metadata[key] = bad
    native = registered_input(result.workbench, result.exported, metadata)
    reader = paraview.PVDReader(FileName=native["path"])
    try:
        reader.UpdatePipeline(time=2.)
        with pytest.raises(ValueError):
            validate_declared_metadata(reader, native["native_metadata"])
    finally:
        paraview.Delete(reader)


def test_basis_association_and_actual_pvd_clock_remain_strict(p1_retained, tmp_path):
    result = p1_retained
    field = deepcopy(result.field)
    field["basis"] = "DG0"
    with pytest.raises(ValueError):
        write_field("temperature", seal_field(field), tmp_path / "wrong-association")
    metadata = deepcopy(result.native["native_metadata"])
    metadata["basis"] = "DG0"
    with pytest.raises(ValueError):
        validate_declared_metadata(result.reader, metadata)
    metadata = deepcopy(result.native["native_metadata"])
    metadata["time"]["values"] = [2.5]
    with pytest.raises(ValueError, match="exact native PVD timesteps"):
        validate_declared_metadata(result.reader, metadata)
    metadata = deepcopy(result.native["native_metadata"])
    next(row for row in metadata["arrays"] if row.get("quantity"))["units"] = ""
    with pytest.raises(ValueError):
        validate_declared_metadata(result.reader, metadata)


def test_legacy_without_optional_metadata_is_not_relabelled(tmp_path):
    field = captured_field()
    for key in OPTIONAL:
        field.pop(key)
    with retained_field(tmp_path, seal_field(field)) as result:
        metadata = validate_declared_metadata(result.reader, result.native["native_metadata"])
        assert metadata == result.exported["native_metadata"]
        assert all(key not in metadata for key in OPTIONAL)
        assert metadata["time"]["values"] == [2.] and metadata["time"]["unit"] == "s"
        assert next(row for row in metadata["arrays"] if row.get("quantity"))["units"] == "K"


@pytest.mark.parametrize("unit,instant", [("s", 2.), ("ms", 1000.), ("min", 2.), ("h", .5)])
def test_physical_clock_units_keep_original_native_values(tmp_path, unit, instant):
    field = captured_field()
    field.update(time=instant, time_units=unit)
    with retained_field(tmp_path, seal_field(field)) as result:
        metadata = validate_declared_metadata(result.reader, result.native["native_metadata"])
        assert metadata["time"] == {"unit": unit, "semantics": "captured_physical_clock", "values": [instant]}
        assert [float(value) for value in result.reader.TimestepValues] == [instant]
        assert result.field["time"] == instant and result.field["time_units"] == unit
        assert result.native["native_metadata"]["snapshot_kind"] == "steady"
