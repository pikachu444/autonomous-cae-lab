"""Independent closed mathematical and source controls, not native solver data."""

from copy import deepcopy
import importlib.util
import math
from pathlib import Path

import pytest

from caelab.adapters.fenicsx_gmsh import prepare
from caelab import Lab
from caelab.adapters import fenicsx_gmsh as syntax
from caelab.adapters.fenicsx_imported import level_files
from caelab.storage import save_json
from plugins.pde_imported import reference as domain
from plugins.pde_imported.reference import validate_settings
from scripts import verify_imported_pde as runner


def interpolant(n=2, harmonic=False):
    points = [(i/n,j/n)for j in range(2*n+1)for i in range(2*n+1)if i<=n or j<=n]
    point_id = {point:index for index,point in enumerate(points)}
    cells = []
    for j in range(2*n):
        for i in range(2*n):
            if i>=n and j>=n: continue
            a,b,c,d = [point_id[p]for p in ((i/n,j/n),((i+1)/n,j/n),((i+1)/n,(j+1)/n),(i/n,(j+1)/n))]
            cells.extend([[a,b,c],[a,c,d]])
    sign=-1 if harmonic else 1
    return {"source_only_fixture":True,"node_ids":list(range(len(points))),"coordinates":[list(p)for p in points],
            "values":[x*x+sign*y*y+x+2*y+1 for x,y in points],"cell_node_ids":cells}


@pytest.mark.parametrize("n",[1,2,4])
@pytest.mark.parametrize("harmonic",[False,True])
def test_full_original_triangle_integrals_match_closed_l_shape_interpolant(n,harmonic):
    field=interpolant(n,harmonic)
    settings={"problem":{"weak_form":{"diffusion":1.,"reaction":0.}}}
    name="E-imported-harmonic"if harmonic else"E-imported-mixed"
    before=deepcopy(field);observed=runner._integrate_field(name,settings,field)
    assert observed["l2"]**2 == pytest.approx((1 if harmonic else 11)/(30*n**4),rel=1e-12)
    assert observed["h1"]**2 == pytest.approx(2/n**2,rel=1e-12)
    assert field==before


def test_closed_integral_is_independent_of_node_ids_row_order_and_orientation():
    original=interpolant()
    settings={"problem":{"weak_form":{"diffusion":1.,"reaction":0.}}}
    expected=runner._integrate_field("E-imported-mixed",settings,original)
    ids={index:101+7*index for index in original["node_ids"]};order=original["node_ids"][::-1]
    changed={"node_ids":[ids[index]for index in order],"coordinates":[original["coordinates"][index]for index in order],
             "values":[original["values"][index]for index in order],"cell_node_ids":[[ids[node]for node in cell[::-1]]for cell in original["cell_node_ids"]]}
    assert runner._integrate_field("E-imported-mixed",settings,changed)==pytest.approx(expected,rel=1e-12)
    changed["cell_node_ids"][0]=[changed["node_ids"][0]]*3
    with pytest.raises(AssertionError,match="triangle"):runner._integrate_field("E-imported-mixed",settings,changed)


def test_frozen_controls_and_criteria_precede_any_native_output():
    accepted,rejected,refused=runner.cases()
    assert (len(accepted),len(rejected),len(refused))==(5,2,10)
    assert len(set(accepted)|set(rejected)|set(refused))==17
    assert sum(len(settings["mesh"]["levels"])for settings in [*accepted.values(),*rejected.values()])==21
    for settings in [*accepted.values(),*rejected.values()]:
        assert validate_settings(settings,prepare(settings))==settings
        assert settings["validation"]=={"max_l2_error":.02,"min_l2_rate":1.8,"max_h1_seminorm_error":.3,"min_h1_rate":.9,"max_residual_relative":1e-10}
    assert accepted["E-imported-harmonic"]["problem"]["weak_form"]["rhs"]=="0.0"
    assert all(row["type"]=="dirichlet"for row in accepted["E-imported-all-dirichlet"]["problem"]["boundaries"].values())
    assert all(row["type"]=="dirichlet"for row in accepted["E-imported-rectangle"]["problem"]["boundaries"].values())
    assert rejected["E-imported-reference-reject"]["problem"]["reference"]["solution"]=="0.0"


@pytest.mark.parametrize("name",["expression","hash","missing-name","duplicate-name","entity-tags",
                                 "missing-line","duplicate-cell","corner","pure-neumann","polygon"])
def test_each_preflight_control_refuses_without_native_work(name):
    settings=runner.cases()[2]["E-imported-invalid-"+name]
    with pytest.raises(ValueError):validate_settings(settings,prepare(settings))


def test_direct_operator_and_neumann_closed_totals():
    settings={"problem":{"weak_form":{"diffusion":3.,"reaction":2.}}}
    data=runner._math("E-imported-reaction",settings,.5,.25)
    assert data["gradient"]==[2.,2.5]
    assert data["rhs"]==pytest.approx(-12+2*data["solution"])
    # Outward quadratic Neumann integrals on the four L-shape named sides.
    settings["problem"]["weak_form"]={"diffusion":1.,"reaction":0.}
    edges=[((2.,0.),(2.,1.),(1.,0.),5.),((2.,1.),(1.,1.),(0.,1.),4.),
           ((1.,1.),(1.,2.),(1.,0.),3.),((1.,2.),(0.,2.),(0.,1.),6.)]
    for a,b,normal,total in edges:
        actual=0.
        for t,weight in runner._QUADRATURE:
            point=[a[axis]+t*(b[axis]-a[axis])for axis in range(2)]
            gradient=runner._math("E-imported-mixed",settings,*point)["gradient"]
            actual+=math.dist(a,b)*weight*sum(gradient[axis]*normal[axis]for axis in range(2))
        assert actual==pytest.approx(total,rel=1e-12)


def test_fresh_store_and_source_guards_block_before_core_native_or_creation(tmp_path,monkeypatch):
    old=tmp_path/"old";old.mkdir();(old/"original").write_bytes(b"retain")
    monkeypatch.setattr(runner,"_source_pin",lambda:pytest.fail("Old store must refuse before source setup"))
    with pytest.raises(AssertionError,match="must be new"):runner.run(old)
    assert (old/"original").read_bytes()==b"retain"
    monkeypatch.setattr(runner,"_source_pin",lambda:{"core":{"core_dirty":True,"core_commit":"candidate"},"files":{}})
    monkeypatch.setattr(runner,"Lab",lambda *a,**k:pytest.fail("Dirty source must block before Core/native"))
    with pytest.raises(AssertionError,match="committed clean"):runner.run(tmp_path/"new")
    assert not (tmp_path/"new").exists()


def test_source_closure_covers_every_native_dependency_and_independent_reader():
    assert len(runner.SOURCE_PATHS)==10 and len(set(runner.SOURCE_FILES))==12
    assert "scripts/verify_vector_pde.py"in runner.SOURCE_FILES
    assert {row[0]for row in runner.SOURCE_PATHS.values()}<=set(runner.SOURCE_FILES)


def source_fixture_module():
    # Reuse the writer's explicitly UNSOLVED transport fixture, never its verdict
    # or error integrator. Root integrates the original polynomial separately.
    path = Path(__file__).with_name("test_pde_imported_reference.py")
    spec = importlib.util.spec_from_file_location("unsolved_imported_source_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceOnlyImportedAdapter:
    backend = "test.source_only_imported"
    version = "1"
    pde_model_declaration = True
    domain = "mathematics"
    physics_domain = "mathematics"
    analysis_type = "UNSOLVED_source_fixture"
    default_metrics = ["l2_error", "h1_seminorm_error"]

    def describe_model(self, settings):
        return domain.model_declaration(settings, prepare(settings))

    def solve(self, output, settings):
        output.mkdir()
        meshes, studies, fields, bindings, mappings = source_fixture_module().synthetic_imported(settings)
        for index, (mesh, study, field, binding, mapping) in enumerate(zip(meshes, studies, fields, bindings, mappings)):
            files = level_files(index)
            (output / files["original"]).parent.mkdir()
            (output / files["original"]).write_bytes(settings["mesh"]["levels"][index]["data"].encode("ascii"))
            (output / files["dense"]).write_bytes(syntax.dense_import(mesh)[0].encode("ascii"))
            for key, value in (("mapping", mapping), ("dofs", field), ("binding", binding)):
                save_json(output / files[key], value)
            for key in ("field", "field_data", "form_source"):
                (output / files[key]).write_bytes(b"UNSOLVED SOURCE TRANSPORT PLACEHOLDER; NOT NATIVE DATA\n")
            study["files"] = files
            study["artifact_sha256"] = {key: runner._sha(output / relative) for key, relative in files.items()}
            save_json(output / f"level_{index}/observation.json", study)
        assessment = domain.assess(settings, meshes, studies, fields, bindings, mappings)
        outcome = {"status": "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                   "checks": assessment["checks"], "metrics": assessment["metrics"],
                   "pending_validations": assessment["pending_validations"],
                   "mesh_studies": assessment["mesh_studies"], "raw_result": "pde/result.json",
                   "provenance": {"source_only_fixture": True, "native_calls": 0, "fixture_kind": "UNSOLVED interpolant"}}
        save_json(output / "worker_result.json", {"source_only_fixture": True, "mesh_studies": studies})
        save_json(output / "progress.json", {"schema_version": "1", "status": "COMPLETED",
                  "completed": [{"level": index} for index in range(len(meshes))]})
        save_json(output / "result.json", outcome)
        return outcome


@pytest.mark.parametrize("experiment,case,shape", [
    ("E-imported-mixed", "mixed", "l_shape"),
    ("E-imported-harmonic", "harmonic", "l_shape"),
    ("E-imported-rectangle", "all_dirichlet", "rectangle"),
])
def test_complete_retained_fields_use_actual_core_envelope_without_native_work(tmp_path, experiment, case, shape):
    settings = source_fixture_module().small_settings(case, shape)
    adapter = SourceOnlyImportedAdapter()
    lab = Lab(tmp_path, adapters={}, analysis_adapters={}, doe_adapters={},
              optimization_adapters={}, model_analysis_adapters={}, pde_adapters={adapter.backend: adapter})
    lab.create_study("S-source", "Imported reader regression", "Can the retained artifacts be read?",
                     "Core owns metadata; adapter owns observations", "UNSOLVED transport fixtures only")
    result = lab.run_pde(study_id="S-source", experiment_id=experiment, backend=adapter.backend, settings=settings)
    assert result["decision"] == "NOT_RELEASED"
    assert "mesh_studies" not in result["extensions"]["pde"]
    assert lab.inspect_experiment(experiment) == result
    folder = tmp_path / "experiments" / experiment
    before = {str(path.relative_to(folder)): runner._sha(path) for path in folder.rglob("*") if path.is_file()}
    closure = runner._fields(experiment, settings, result, folder)
    assert [row["level"] for row in closure] == [0, 1, 2]
    assert closure[-1]["l2"] == pytest.approx(result["metrics"]["l2_error"]["value"], rel=1e-12)
    assert closure[-1]["h1"] == pytest.approx(result["metrics"]["h1_seminorm_error"]["value"], rel=1e-12)
    assert before == {str(path.relative_to(folder)): runner._sha(path) for path in folder.rglob("*") if path.is_file()}


@pytest.mark.parametrize("kind", ["geometry_source", "vertex_dof", "finalized_boolean", "missing_flux_value"])
def test_independent_import_mapping_and_boundary_reader_refuses_corruption(kind):
    settings = source_fixture_module().small_settings(counts=(1, 2, 4))
    meshes, studies, fields, _, mappings = source_fixture_module().synthetic_imported(settings)
    field, mesh, mapping = fields[1], meshes[1], mappings[1]
    if kind == "missing_flux_value":
        field["boundaries"]["north"]["prescribed_values"].pop()
        geometry = runner._geometry(field, mesh)
        with pytest.raises(AssertionError, match="DOFs/inputs incomplete"):
            runner._boundaries("E-imported-mixed", settings, field, mesh, *geometry[:3])
    else:
        if kind == "geometry_source": mapping["geometry_source_node_ids"][0] = mapping["geometry_source_node_ids"][1]
        elif kind == "vertex_dof": mapping["vertex_dof_ids"].reverse()
        else: mapping["gmsh_initialization"]["finalized"] = 1
        with pytest.raises(AssertionError):
            runner._mapping(field, mapping, mesh, studies[1]["source_sha256"], studies[1]["dense_sha256"])
