"""Cold contracts using explicitly synthetic SDK/process observations.

These portable fixtures never import/initialize Gmsh, generate CAD or mesh, or
claim native/physics qualification. Distinct sparse IDs and signatures expose
array-order, byte, field-coverage and lifecycle failures instead of count alone.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


BASE = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


h = load(BASE / "caelab/adapters/fixture_assembly_mesh.py", "caelab.adapters._assembly_mesh_candidate")
w = load(BASE / "caelab/adapters/fixture_assembly_mesh_worker.py", "_assembly_mesh_worker_candidate")
d = h.domain()

REFERENCE_NODES = [[0.,0.,0.], [1.,0.,0.], [0.,1.,0.], [0.,0.,1.],
                   [.5,0.,0.], [.5,.5,0.], [0.,.5,0.], [0.,0.,.5], [.5,0.,.5], [0.,.5,.5]]
NCOUNTS = {"printed_base": 22, "printed_support_left": 20, "printed_support_right": 20,
           "metal_roller_left": 3, "metal_roller_right": 3, "metal_loading_nose": 3, "specimen": 6}


def create_parent(root):
    """A complete synthetic parent envelope, not an upstream CAD substitute."""
    root.mkdir()
    cadroot = root / "cad"
    cadroot.mkdir()
    files, components = {}, []
    def add(name, data):
        file = cadroot / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        files[name] = h.file_entry(file)
        return files[name]["sha256"]
    for i, name in enumerate(d.ACTIVE + d.INACTIVE):
        body_path = "native_bodies/"+name+".brep"
        body_hash = add(body_path, ("SYNTHETIC_BODY:"+name).encode())
        box = {"min_mm": [10.*i,0.,0.], "max_mm": [10.*i+1.,1.,1.]}
        center = [10.*i+.25,.25,.25]
        faces = []
        for j in range(NCOUNTS.get(name, 5)):
            face_path = f"native_faces/{name}/face-{j+1:03d}.brep"
            fh = add(face_path, f"SYNTHETIC_FACE:{name}:{j}".encode())
            fc = [10.*i + .001*j, .01*j, .02*j]
            faces.append({"id": f"{name}:face:{j+1}:{fh}", "component_id": name,
                "geom_type": "PLANE", "area_mm2": 1., "center_of_mass_mm": fc,
                "bounds": {"min_mm": [fc[0],fc[1],fc[2]], "max_mm": [fc[0]+1.,fc[1]+1.,fc[2]]},
                "surface": {"normal": [0.,0.,1.], "origin_mm": fc},
                "native_brep_path": face_path, "native_geometry_sha256": fh})
        components.append({"id": name, "role": "specimen" if name == "specimen" else "printed" if name.startswith("printed") else "metal",
            "volume_mm3": 1/6, "area_mm2": float(len(faces)), "center_of_mass_mm": center, "bounds": box,
            "faces": faces, "native_brep_path": body_path, "native_geometry_sha256": body_hash,
            "frame": "global_assembly_cartesian_mm", "xde_product_name": name, "solid_count": 1, "valid": True})
    step_hash = add("assembly.step", b"SYNTHETIC_STEP_NOT_CAD")
    source_sha = h.digest({"synthetic_source": "declared_control_fixture"})
    input_sha = add("input.json", b'{"synthetic_input":true}\n')
    catalog = {"component_count": 15, "face_count": 117, "components": components,
               "interfaces": [{"id": f"synthetic-interface-{i}"} for i in range(15)],
               "source_sha256": source_sha, "input_sha256": input_sha, "assembly_step_sha256": step_hash}
    h.save(cadroot / "assembly_catalog.json", catalog)
    catalog_sha = h.file_entry(cadroot / "assembly_catalog.json")["sha256"]
    raw = {"cad_generated": True, "decision": "REVIEW_REQUIRED", "source_sha256": source_sha,
           "input_sha256": input_sha, "catalog_sha256": catalog_sha, "native_files": deepcopy(files),
           "source_fingerprint_before": {"synthetic": "explicitly_injected_trusted_source_context"}}
    raw["native_revision"] = h.digest({"synthetic_native_identity": files, "input": input_sha, "catalog": catalog_sha})
    h.save(cadroot / "result.json", raw)
    proposal = {"model": {"geometry": {"backend": "fixture.assembly", "source": "bending_assembly"}},
                "physics": {"analysis_type": "cad_preflight"}, "parameters": {"P-width": 10.}, "registry_revision": 1}
    registry = {"revision": 1, "entries": [], "synthetic_utf8_label": "시편 폭"}
    # Independent Core encoding/identity reference, including non-ASCII text.
    core_hash = lambda v: __import__("hashlib").sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    pr = core_hash({"model": "bending_assembly", "values": proposal["parameters"], "registry": registry})
    revision = core_hash({"source": raw["native_revision"], "proposal": pr})
    for name, value in (("proposal.json", proposal), ("registry_snapshot.json", registry)):
        h.save(root / name, value)
    artifacts = [{"path": "cad/" + p.relative_to(cadroot).as_posix(), **h.file_entry(p), "revision": revision}
                 for p in sorted(cadroot.rglob("*")) if p.is_file()]
    result = {"experiment_id": "SYNTHETIC-COLD-PARENT", "status": "COMPLETED_REVIEW_REQUIRED",
        "decision": "NOT_RELEASED", "solver_status": "NOT_RUN", "converged": None,
        "cad_revision": revision, "proposal_revision": pr, "registry_revision": 1,
        "input_parameters": deepcopy(proposal["parameters"]), "artifacts": artifacts, "validations": [{"status": "PASS"}],
        "provenance": {"adapter": "fixture.assembly", "proposal_sha256": core_hash(proposal),
            "registry_sha256": core_hash(registry), "cad_source_sha256": source_sha,
            "core_commit": "SYNTHETIC_NOT_A_GIT_COMMIT", "source_commit": "UNKNOWN"}}
    h.save(root / "result.json", result)
    return result, catalog, raw


@pytest.fixture
def context(tmp_path, monkeypatch):
    parent = tmp_path / "existing_parent"
    result, catalog, raw = create_parent(parent)
    sdk = tmp_path / "synthetic-sdk.py"
    sdk.write_bytes(b"# Synthetic cold source, not the Gmsh SDK\n")
    lib = tmp_path / "synthetic-library.so"
    lib.write_bytes(b"SYNTHETIC_LIBRARY_NOT_LOADABLE")
    calls = []
    class CapturedCADVerifier:
        @staticmethod
        def verify_result(cadroot, actual, expected):
            calls.append(str(cadroot))
            assert actual == raw and expected == raw["source_fingerprint_before"]
            h.check_files(cadroot, raw["native_files"])
        @staticmethod
        def source_files():
            return {"synthetic-fixture-source": sdk}
    # Explicit controlled source injection; production contains no admission bypass.
    monkeypatch.setattr(h, "_cad_adapter", lambda: CapturedCADVerifier)
    monkeypatch.setattr(h, "SDK_FILE", sdk)
    monkeypatch.setattr(h, "SDK_SHA256", h.file_entry(sdk)["sha256"])
    monkeypatch.setattr(h, "SDK_LIBRARY", lib)
    monkeypatch.setattr(h, "SDK_LIBRARY_SHA256", h.file_entry(lib)["sha256"])
    output = tmp_path / "new_mesh"
    request = h.prepare_request(result, parent, output, 3.)
    return SimpleNamespace(parent=parent, result=result, catalog=catalog, raw=raw, output=output,
                           request=request, calls=calls, monkeypatch=monkeypatch)


class ControlledSDK:
    """No SDK binary is loaded; all calls below return independent synthetic data."""
    def __init__(self, catalog):
        self.catalog = catalog
        self.imported = set()
        self.volumes, self.faces = {}, {}
        self.parts = {c["id"]: c for c in catalog["components"]}
        self.tags = {name: 901-i*19 for i, name in enumerate(d.ACTIVE)}
        self.face_tags = {}
        self.physical = {}
        self.options = {}
        self.generated = 0
        self.nodes = {}
        self.blocks = {}
        self.geometry_error = None
        for i, name in enumerate(d.ACTIVE):
            tag = self.tags[name]
            c = self.parts[name]
            self.volumes[tag] = c
            node_ids = [101 + i*1000 + j*7 for j in range(10)]
            for nid, xyz in zip(node_ids, REFERENCE_NODES):
                row = [xyz[0] + 10*i, xyz[1], xyz[2]]
                if i == 0 and nid == node_ids[0]:
                    row[1] = -0.0
                self.nodes[nid] = row
            self.blocks[(3,tag)] = (11, [5001+i*103], node_ids)
            for j, f in enumerate(c["faces"]):
                ft = 100003-i*1000-j*3
                self.faces[ft] = f
                self.face_tags[(name,j)] = ft
                self.blocks[(2,ft)] = (9, [70001+i*1000+j*11], [node_ids[k] for k in (0,1,2,4,5,6)])
        self.model = SimpleNamespace(
            add=lambda name: None, occ=SimpleNamespace(importShapes=self.import_shapes,
                synchronize=lambda: None, getBoundingBox=self.bounding_box,
                getCenterOfMass=lambda dim, tag: deepcopy(self.record(dim,tag)["center_of_mass_mm"]),
                getMass=lambda dim,tag: self.record(dim,tag)["volume_mm3" if dim == 3 else "area_mm2"]),
            getBoundary=self.boundary, getEntities=self.entities, getType=lambda dim,tag: "Plane",
            getParametrizationBounds=lambda dim,tag: ([0.,0.], [1.,1.]),
            getPrincipalCurvatures=lambda tag,uv: ([0.], [0.], [1.,0.,0.], [0.,1.,0.]),
            getValue=lambda dim,tag,uv: deepcopy(self.faces[tag]["surface"]["origin_mm"]),
            getNormal=lambda tag,uv: [0.,0.,1.], addPhysicalGroup=self.add_physical,
            getPhysicalGroupsForEntity=lambda dim,tag: [k for (dd,k), gg in self.physical.items() if dd == dim and gg["entity"] == tag],
            getPhysicalName=lambda dim,tag: self.physical[(dim,tag)]["name"],
            getEntitiesForPhysicalGroup=lambda dim,tag: [self.physical[(dim,tag)]["entity"]],
            mesh=SimpleNamespace(generate=self.generate, getNodes=self.get_nodes,
                getNodesForPhysicalGroup=self.group_nodes, getElements=self.get_elements,
                getElementProperties=self.properties, getJacobians=self.jacobians))
        self.option = SimpleNamespace(setNumber=lambda name,v: self.options.__setitem__(name,v),
                                      getNumber=lambda name: self.options[name])
    def record(self, dim, tag):
        return (self.volumes if dim == 3 else self.faces)[tag]
    def import_shapes(self, file, highestDimOnly, format):
        assert highestDimOnly is True and format == "brep"
        name = Path(file).stem
        assert name not in self.imported
        self.imported.add(name)
        return [(3,self.tags[name])]
    def bounding_box(self, dim, tag):
        box = self.record(dim,tag)["bounds"]
        row = box["min_mm"]+box["max_mm"]
        if self.geometry_error == "bounds":
            row = [v+3e-7 for v in row]
        return row
    def boundary(self, entities, combined, oriented, recursive):
        assert not combined and not oriented and not recursive
        tag = entities[0][1]
        name = next(n for n,t in self.tags.items() if t == tag)
        faces = [(2,t) for (n,j),t in self.face_tags.items() if n == name]
        return list(reversed(faces))  # Deliberately not catalog order.
    def entities(self, dim):
        if dim == 3:
            return [(3,t) for n,t in self.tags.items() if n in self.imported]
        if dim == 2:
            return [(2,t) for (n,j),t in self.face_tags.items() if n in self.imported]
        return []
    def add_physical(self, dim, tags, name):
        assert len(tags) == 1
        tag = 20001+len(self.physical)*13
        self.physical[(dim,tag)] = {"name": name, "entity": tags[0]}
        return tag
    def generate(self, dim):
        assert dim == 3
        self.generated += 1  # A synthetic callback, not a real meshing job.
    def get_nodes(self):
        ids = list(reversed(list(self.nodes)))
        return np.asarray(ids,dtype="uint64"), np.asarray([v for n in ids for v in self.nodes[n]],dtype="float64"), []
    def group_nodes(self, dim, tag):
        entity = self.physical[(dim,tag)]["entity"]
        ids = list(reversed(list(dict.fromkeys(self.blocks[(dim,entity)][2]))))
        return ids, [v for n in ids for v in self.nodes[n]]
    def get_elements(self, dim=-1, tag=-1):
        selected = [b for (dd,tt),b in self.blocks.items() if dim == -1 or (dd,tt) == (dim,tag)]
        if dim != -1:
            return ([b[0] for b in selected], [b[1] for b in selected], [b[2] for b in selected])
        output = []
        for kind in (9,11):
            blocks = list(reversed([b for b in selected if b[0] == kind]))
            output.append((kind, [v for b in blocks for v in b[1]], [v for b in blocks for v in b[2]]))
        return [b[0] for b in output], [b[1] for b in output], [b[2] for b in output]
    def properties(self, kind):
        if kind == 11:
            return "Synthetic Tetrahedron10",3,2,10,[v for row in REFERENCE_NODES for v in row],4
        assert kind == 9
        return "Synthetic Triangle6",2,2,6,[0.,0.,1.,0.,0.,1.,.5,0.,.5,.5,0.,.5],3
    def jacobians(self, kind, points, tag):
        assert kind == 11 and points == [v for p in d.POINTS for v in p]
        name = next(n for n,t in self.tags.items() if t == tag)
        i = list(d.ACTIVE).index(name)
        return [1.,0.,0.,0.,1.,0.,0.,0.,1.]*5, [1.]*5, [v for p in d.POINTS for v in (p[0]+10*i,p[1],p[2])]


@pytest.fixture
def produced(context):
    g = ControlledSDK(context.catalog)
    values = w.produce(g,h,context.output,context.request,context.catalog)
    assert g.generated == 1
    return context, g, values


def positive_result(ctx, values):
    runtime = {"python": "3.12.3", "gmsh_version": "4.12.1", "sdk_sha256": h.SDK_SHA256,
        "library_sha256": h.SDK_LIBRARY_SHA256, "cpu_limit_seconds": 86400,
        "observation": "SYNTHETIC_COLD_RUNTIME_NOT_OBSERVED_NATIVE"}
    h.save(ctx.output / "lifecycle.json", {"initialize_succeeded": True, "finalize_succeeded": True,
        "initialize_attempts": 1, "read_config_files": False, "logger_started": True, "solver_calls": 0, "provider_calls": 0})
    (ctx.output / "mesher.log").write_text("SYNTHETIC_COLD_LOG\n", encoding="utf-8")
    result = {"schema_version": 1, "status": "VALID_PREPROCESSING", "decision": "NOT_RELEASED",
        "parent": ctx.request["parent"], "request_sha256": h.file_entry(ctx.output / "request.json")["sha256"],
        "source_files": ctx.request["source_files"], "profile": ctx.request["profile"], "policy": deepcopy(h.POLICY),
        "runtime_before": deepcopy(runtime), "runtime_after": deepcopy(runtime), **values,
        "output_files": {name: h.file_entry(ctx.output / name) for name in
            ("mesh.msh", "mapping.json", "jacobians.npz", "jacobian_metadata.json", "mesher.log", "imported_geometry.json", "quality.json", "lifecycle.json")}}
    result["mesh_revision"] = h.digest(h.revision_material(result))
    return result


@pytest.mark.parametrize("size", [3.,1.5])
def test_controlled_complete_recipe_sparse_ids_shuffled_geometry(context, size):
    request = deepcopy(context.request)
    request["profile"] = d.profile(size)
    # API production step only; source capsule admission remains independently tested.
    g = ControlledSDK(context.catalog)
    values = w.produce(g,h,context.output,request,context.catalog)
    mapping = h.read_json(context.output / "mapping.json")
    joins = h.check_mapping(mapping,context.catalog)
    h.verify_msh(context.output / "mesh.msh",mapping)
    assert len(joins["nodes"]) == 70 and len(joins["elements"]) == 84
    assert [c["component_id"] for c in values["quality"]["bodies"]] == list(d.ACTIVE)
    assert all(b["status"] == "PASS" and b["sample_count"] == 5 for b in values["quality"]["bodies"])
    assert mapping["nodes"][0]["id"] != 1 and mapping["mesh_size_mm"] == size
    assert mapping["options"]["requested"]["Mesh.HighOrderOptimize"] == 2
    assert mapping["options"]["observed"]["Mesh.HighOrderOptimize"] == 2
    assert len(mapping["geometry_join"]["entities"]) == 84
    assert d.intent(context.catalog["components"])["inactive"] == context.request["intent"]["inactive"]
    assert len(d.intent(context.catalog["components"])["inactive"]) == 8
    assert not (context.output / "result.json").exists()  # No native qualification claimed.


def test_complete_bound_positive_output_is_preprocessing_only(produced):
    ctx,g,values = produced
    result = positive_result(ctx,values)
    h.verify_output(ctx.output,result,ctx.request)
    assert result["decision"] == "NOT_RELEASED" and result["status"] == "VALID_PREPROCESSING"
    assert result["parent"]["cad_provenance"]["source_commit"] == "UNKNOWN"
    assert ctx.calls and h.read_json(ctx.output / "parent/result.json") == ctx.result


@pytest.mark.parametrize("size", [True, float("nan"), 2.0])
def test_unsupported_profiles_block_before_any_new_output(context,size,tmp_path):
    target = tmp_path / "invalid_request"
    with pytest.raises(ValueError,match="3.0/1.5"):
        h.prepare_request(context.result,context.parent,target,size)
    assert not target.exists()


@pytest.mark.parametrize("change", ["backend","revision","artifact","duplicate_artifact","input","proposal","catalog_count","brep_hash"])
def test_foreign_or_changed_parent_refused(context,change):
    result = deepcopy(context.result)
    if change == "backend":
        result["provenance"]["adapter"] = "fixture.cadquery"
    elif change == "revision":
        result["cad_revision"] = "f"*64
    elif change == "artifact":
        result["artifacts"][-1]["sha256"] = "f"*64
    elif change == "duplicate_artifact":
        result["artifacts"].append(deepcopy(result["artifacts"][0]))
    elif change == "input":
        result["input_parameters"]["P-width"] = 12.
    elif change == "proposal":
        (context.parent / "proposal.json").write_text("{}",encoding="utf-8")
    elif change in ("catalog_count","brep_hash"):
        catalog = deepcopy(context.catalog)
        if change == "catalog_count":
            catalog["face_count"] = 116
        else:
            catalog["components"][0]["native_geometry_sha256"] = "f"*64
        (context.parent / "cad/assembly_catalog.json").write_bytes(h.canonical(catalog))
    if result != context.result:
        (context.parent / "result.json").write_bytes(h.canonical(result))
    with pytest.raises((ValueError,AssertionError)):
        h.validate_parent(result,context.parent)


@pytest.mark.parametrize("name", ["../result.json","cad/../result.json","cad\\result.json","/result.json"])
def test_path_escape_refusal(context,name):
    with pytest.raises(ValueError,match="Unsafe|escaping"):
        h.safe(context.parent,name)


def test_fresh_symlink_source_and_captured_drift_refuse(context,tmp_path):
    with pytest.raises(ValueError,match="Fresh"):
        h.fresh(context.output)
    link = tmp_path / "link"
    link.symlink_to(context.parent,target_is_directory=True)
    with pytest.raises(ValueError,match="Symlink"):
        h.safe(link,"result.json")
    (context.output / "capsule/assembly_mesh.py").write_bytes(b"changed")
    with pytest.raises(ValueError,match="drift"):
        h.check_request(context.output,context.request)


@pytest.mark.parametrize("change", ["bounds","missing","ambiguous","surface","extra"])
def test_geometry_signature_failures_prevent_mesh_export(context,change):
    g = ControlledSDK(context.catalog)
    if change == "bounds":
        g.geometry_error = "bounds"
    elif change == "missing":
        key = next(iter(g.face_tags))
        del g.face_tags[key]
    elif change == "ambiguous":
        tags = list(g.faces)
        g.faces[tags[1]] = deepcopy(g.faces[tags[0]])
    elif change == "surface":
        g.model.getNormal = lambda tag,uv: [1.,0.,0.]
    else:
        original = g.entities
        g.model.getEntities = lambda dim: original(dim)+([(2,999999)] if dim == 2 else [])
    with pytest.raises(ValueError,match="geometry|entity"):
        w.produce(g,h,context.output,context.request,context.catalog)
    assert g.generated == 0 and not (context.output / "mesh.msh").exists()


@pytest.mark.parametrize("change", ["node_foreign","node_duplicate","body_shared","physical","entity","face","partial_global","group_coords","order","options"])
def test_complete_native_join_controls(produced,change):
    ctx,g,values = produced
    mapping = h.read_json(ctx.output / "mapping.json")
    if change == "node_foreign":
        mapping["elements"][-1]["node_ids"][-1] = 99999999
    elif change == "node_duplicate":
        mapping["nodes"].append(deepcopy(mapping["nodes"][0]))
    elif change == "body_shared":
        e = next(e for e in mapping["elements"] if e["component_id"] == d.ACTIVE[1] and e["type"] == 11)
        e["node_ids"][0] = next(e for e in mapping["elements"] if e["type"] == 11)["node_ids"][0]
    elif change == "physical":
        mapping["elements"][-1]["physical_tag"] = 999999
    elif change == "entity":
        mapping["elements"][-1]["entity_tag"] = 999999
    elif change == "face":
        mapping["elements"][-1]["catalog_face_id"] = "foreign"
    elif change == "partial_global":
        block = mapping["api_global_elements"][0]
        block["element_ids"].pop(); del block["node_ids"][-block["node_count"]:]
    elif change == "group_coords":
        mapping["physical_groups"][-1]["node_coordinates_mm"][-1][0] += .1
    elif change == "order":
        mapping["element_properties"]["11"]["order"] = 1
    else:
        mapping["options"]["observed"]["Mesh.ElementOrder"] = 1
    with pytest.raises(ValueError):
        h.check_mapping(mapping,ctx.catalog)


@pytest.mark.parametrize("change", ["negative_zero","rounding","connectivity","physical","missing_node","trailing"])
def test_independent_msh_parser_refuses_real_byte_corruption(produced,change):
    ctx,g,values = produced
    file = ctx.output / "mesh.msh"
    mapping = h.read_json(ctx.output / "mapping.json")
    lines = file.read_text(encoding="ascii").splitlines()
    start = lines.index("$Nodes")+2
    if change == "negative_zero":
        idx = next(i for i in range(start,start+70) if " -0 " in lines[i])
        lines[idx] = lines[idx].replace(" -0 "," 0 ")
    elif change == "rounding":
        row = lines[start].split(); row[1] = str(float(row[1]) + .00001); lines[start] = " ".join(row)
    elif change in ("connectivity","physical"):
        idx = lines.index("$Elements")+2
        row = lines[idx].split(); row[-1 if change == "connectivity" else 3] = "9999999"; lines[idx] = " ".join(row)
    elif change == "missing_node":
        del lines[start]
    else:
        lines.append("FOREIGN")
    file.write_text("\n".join(lines)+"\n",encoding="ascii")
    with pytest.raises(ValueError):
        h.verify_msh(file,mapping)


@pytest.mark.parametrize("change", ["last_negative","partial","wrong_id","wrong_entity","wrong_matrix","nonfinite","float32"])
def test_all_five_actual_jacobians_and_identity_required(produced,change):
    ctx,g,values = produced
    file = ctx.output / "jacobians.npz"
    with np.load(file,allow_pickle=False) as raw:
        arrays = {k: raw[k].copy() for k in raw.files}
    metadata = deepcopy(values["jacobian_metadata"])
    if change == "last_negative":
        arrays["determinants"][-1,-1] = -1.
        arrays["jacobians"][-1,-1,0] = -1.
    elif change == "partial":
        arrays["determinants"] = arrays["determinants"][:,:4]
    elif change == "wrong_id":
        arrays["element_ids"][-1] = 999999
    elif change == "wrong_entity":
        arrays["entity_tags"][-1] = 999999
    elif change == "wrong_matrix":
        arrays["jacobians"][-1,-1,8] = 2.
    elif change == "nonfinite":
        arrays["coordinates"][-1,-1,2] = np.nan
    else:
        arrays["jacobians"] = arrays["jacobians"].astype("float32")
    np.savez(file,**arrays)
    mapping = h.read_json(ctx.output / "mapping.json")
    if change == "last_negative":
        quality = h.verify_jacobians(file,mapping,metadata,ctx.catalog)
        assert quality["status"] == "FAIL" and quality["bodies"][-1]["nonpositive_count"] == 1
    else:
        with pytest.raises(ValueError):
            h.verify_jacobians(file,mapping,metadata,ctx.catalog)


def test_per_body_one_percent_is_not_global_volume_compensation(produced):
    ctx,g,values = produced
    catalog = deepcopy(ctx.catalog)
    catalog["components"][0]["volume_mm3"] = (1/6)*1.02
    catalog["components"][1]["volume_mm3"] = (1/6)*.98
    quality = h.verify_jacobians(ctx.output / "jacobians.npz",h.read_json(ctx.output / "mapping.json"),values["jacobian_metadata"],catalog)
    assert quality["status"] == "FAIL" and sum(b["status"] == "FAIL" for b in quality["bodies"]) == 2


def test_invalid_sample_preserves_raw_and_prevents_export(context):
    g = ControlledSDK(context.catalog)
    original = g.jacobians
    def invalid(kind,points,tag):
        js, ds, cs = original(kind,points,tag)
        if tag == g.tags[d.ACTIVE[-1]]:
            js[-9] = -1.; ds[-1] = -1.
        return js,ds,cs
    g.model.mesh.getJacobians = invalid
    with pytest.raises(ValueError,match="FAILED"):
        w.produce(g,h,context.output,context.request,context.catalog)
    assert (context.output / "mapping.json").is_file() and (context.output / "jacobians.npz").is_file()
    assert h.read_json(context.output / "quality.json")["status"] == "FAIL"
    assert not (context.output / "mesh.msh").exists()


@pytest.mark.parametrize("change", ["revision","runtime","parent","limit","file","lifecycle"])
def test_output_binding_failures_refuse_positive_status(produced,change):
    ctx,g,values = produced
    result = positive_result(ctx,values)
    if change == "revision":
        result["mesh_revision"] = "f"*64
    elif change == "runtime":
        result["runtime_after"]["gmsh_version"] = "4.13.0"
    elif change == "parent":
        result["parent"] = {**result["parent"], "cad_revision": "f"*64}
    elif change == "limit":
        result["profile"] = deepcopy(result["profile"]); result["profile"]["limits"]["body_mesh_volume_relative"] = .1
    elif change == "file":
        (ctx.output / "mesh.msh").write_bytes(b"corrupted")
    else:
        lifecycle = h.read_json(ctx.output / "lifecycle.json")
        lifecycle["finalize_succeeded"] = False
        (ctx.output / "lifecycle.json").write_bytes(h.canonical(lifecycle))
        result["output_files"]["lifecycle.json"] = h.file_entry(ctx.output / "lifecycle.json")
    with pytest.raises(ValueError):
        h.verify_output(ctx.output,result,ctx.request)


@pytest.mark.parametrize("code", [0,1,17,-9])
def test_owned_nonzero_child_refuses_positive_payload_and_retains_bytes(context,code):
    result_path = context.output / "result.json"
    result_path.write_bytes(b'{"status":"VALID_PREPROCESSING","decision":"NOT_RELEASED"}\n')
    saved = result_path.read_bytes()
    calls = []
    class OwnedChild:
        pid = 0  # Never used to signal an OS process in these cold controls.
        returncode = None
        def wait(self,timeout=None):
            calls.append(timeout); self.returncode = code; return code
        def poll(self):
            return self.returncode
    child = OwnedChild()
    context.monkeypatch.setattr(h.subprocess,"Popen",lambda command,**kwargs: child)
    if code:
        with pytest.raises(RuntimeError,match=rf"^Assembly mesh worker exited with code {code}; no mesh admitted; evidence retained at "):
            h._invoke(context.output)
    else:
        assert h._invoke(context.output) == 0
    assert calls == [None] and result_path.read_bytes() == saved
    assert h.read_json(context.output / "process.json")["exit_code"] == code


def test_owned_cancel_preserves_partial_and_records_actual_cleanup(context):
    from caelab import execution_control as control
    class OwnedChild:
        pid = 0
        returncode = None
        def poll(self):
            return self.returncode
    child = OwnedChild()
    (context.output / "partial-native.txt").write_bytes(b"partial")
    stopped = []
    def wait(process,timeout):
        assert process is child and timeout is None
        raise control.ExecutionCancelled("Synthetic owned cancellation")
    def stop(process,isolated_group):
        assert process is child
        stopped.append(isolated_group); child.returncode = -9
    context.monkeypatch.setattr(h.subprocess,"Popen",lambda *args,**kwargs: child)
    context.monkeypatch.setattr(control,"wait_for_process",wait)
    context.monkeypatch.setattr(control,"stop_owned_process",stop)
    with pytest.raises(control.ExecutionCancelled):
        h._invoke(context.output)
    assert stopped == [True] and (context.output / "partial-native.txt").read_bytes() == b"partial"
    process = h.read_json(context.output / "process.json")
    assert process["interrupted"] is True and process["owned_leader_reaped"] is True and process["exit_code"] == -9


def test_imports_and_serializer_preserve_scope_and_declared_pins():
    assert "gmsh" not in sys.modules and "_captured_official_gmsh" not in sys.modules
    assert h.SDK_SHA256 == "275cd3fa7141a723e22c717ebd70a8760683e3a2692598f780874ce3386b9cb6"
    assert h.POLICY["writer"] == "adapter_msh2_ascii_17g" and h.POLICY["wall_timeout_seconds"] is None
    assert h.POLICY["cpu_limit_seconds"] == 86400 and h.POLICY["threads"] == 2
    assert sum(d.WEIGHTS) == pytest.approx(1/6) and len(d.POINTS) == 5


def test_capsule_drift_refused_before_helper_code_execution(context,tmp_path):
    marker = tmp_path / "forbidden-import-side-effect"
    (context.output / "capsule/fixture_assembly_mesh.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",encoding="utf-8")
    with pytest.raises(ValueError,match="Standalone source capsule drift before import: fixture_assembly_mesh.py"):
        w.bootstrap(context.output / "request.json")
    assert not marker.exists()


def test_historical_parent_and_failed_geometry_are_never_mesh_output(context):
    with pytest.raises(ValueError,match="historical parent"):
        h.prepare_request(context.result,context.parent,context.parent / "new-child",3.)
    assert not (context.parent / "new-child").exists()
    invalid = deepcopy(context.result)
    invalid["validations"] = [{"status": "FAIL"}]
    (context.parent / "result.json").write_bytes(h.canonical(invalid))
    with pytest.raises(ValueError,match="Invalid CAD parent validations"):
        h.validate_parent(invalid,context.parent)


@pytest.mark.parametrize("change", ["soname","missing","foreign","bytes"])
def test_actual_loaded_library_identity_is_observed_or_refused(context,tmp_path,change):
    import resource
    real_path = Path
    library = tmp_path / "libgmsh.so.4.12.1"
    library.write_bytes(b"SYNTHETIC_LIBRARY_NOT_LOADABLE")
    context.monkeypatch.setattr(h,"SDK_LIBRARY",library)
    context.monkeypatch.setattr(h,"SDK_LIBRARY_SHA256",h.file_entry(library)["sha256"])
    mapped = library
    if change == "foreign":
        mapped = tmp_path / "libgmsh.so.4.13.0"
        mapped.write_bytes(b"FOREIGN")
    if change == "bytes":
        library.write_bytes(b"CHANGED")
    text = "" if change == "missing" else f"1000-2000 r-xp 0000 00:00 1 {mapped}\n"
    def observed_path(value):
        if str(value) == "/proc/self/maps":
            return SimpleNamespace(read_text=lambda: text)
        return real_path(value)
    context.monkeypatch.setattr(w,"Path",observed_path)
    context.monkeypatch.setattr(resource,"getrlimit",lambda limit: (86400,86400))
    sdk = SimpleNamespace(libpath="libgmsh.so.4.12",__version__="4.12.1",__file__=str(h.SDK_FILE))
    if change == "soname":
        observed = w.runtime(sdk,h)
        assert observed["library_path"] == str(library) and observed["sdk_requested_library"] == "libgmsh.so.4.12"
        assert observed["python"] == sys.version.split()[0] and observed["library_evidence"] == "actual_/proc/self/maps"
    else:
        with pytest.raises(ValueError,match="library|identity"):
            w.runtime(sdk,h)


def test_high_order_optimizer_option_must_be_observed_before_generation(context):
    g = ControlledSDK(context.catalog)
    original = g.option.getNumber
    g.option.getNumber = lambda name: 0 if name == "Mesh.HighOrderOptimize" else original(name)
    with pytest.raises(ValueError,match="Actual Gmsh options differ"):
        w.produce(g,h,context.output,context.request,context.catalog)
    assert g.generated == 0 and not (context.output / "mesh.msh").exists()


@pytest.mark.parametrize("phase,unavailable", [("before",False),("after",False),("before",True),("after",True)])
def test_runtime_diagnostic_is_observed_or_unknown_without_admission(context,phase,unavailable):
    observation = {"python": "synthetic", "library_sha256": "synthetic-not-native"}
    def observe(g,helper):
        assert helper is h
        if unavailable:
            raise ValueError("Synthetic missing actual library observation")
        return deepcopy(observation)
    context.monkeypatch.setattr(w,"runtime",observe)
    if unavailable:
        with pytest.raises(ValueError,match="Synthetic missing"):
            w.runtime_snapshot(None,h,context.output,phase)
    else:
        assert w.runtime_snapshot(None,h,context.output,phase) == observation
    snapshot = h.read_json(context.output / f"runtime-{phase}.json")
    assert snapshot["diagnostic_only"] is True and snapshot["phase"] == phase
    assert snapshot["request_sha256"] == h.file_entry(context.output / "request.json")["sha256"]
    assert snapshot["runtime"] == (None if unavailable else observation)
    assert snapshot["observation_status"] == ("UNKNOWN" if unavailable else "OBSERVED")
    assert not (context.output / "mesh.msh").exists() and not (context.output / "result.json").exists()


def test_quality_failure_preserves_both_runtime_diagnostics_and_lifecycle(context):
    import resource
    import io
    events = []
    observed = {"python": "3.12.3", "gmsh_version": "4.12.1",
                "observation": "SYNTHETIC CONTROL; no SDK or native job"}
    # Exercise the actual worker control flow with explicitly controlled callbacks.
    # No real SDK source is imported or initialized; no OS CPU budget is changed.
    sdk = SimpleNamespace(initialize=lambda *a,**k: events.append("initialize"),
                          finalize=lambda: events.append("finalize"),
                          logger=SimpleNamespace(start=lambda: events.append("logger-start"),
                              get=lambda: ["SYNTHETIC quality failure"],stop=lambda: events.append("logger-stop")))
    context.monkeypatch.setattr(w,"bootstrap",lambda path: (h,context.request))
    context.monkeypatch.setattr(w,"_load",lambda *a,**k: sdk)
    context.monkeypatch.setattr(w,"runtime",lambda *a,**k: deepcopy(observed))
    context.monkeypatch.setattr(w,"sys",SimpleNamespace(version="3.12.3 synthetic-runtime",executable=sys.executable,stderr=io.StringIO()))
    context.monkeypatch.setattr(h,"SYSTEM_PYTHON",sys.executable)
    context.monkeypatch.setattr(resource,"getrlimit",lambda limit: (86400,resource.RLIM_INFINITY))
    context.monkeypatch.setattr(resource,"setrlimit",lambda *a,**k: events.append("declared-cpu-policy"))
    def rejected(g,helper,root,request,catalog):
        assert g is sdk and helper is h
        h.save(root / "quality.json",{"status":"FAIL","basis":"SYNTHETIC CONTROL; not actual field data"})
        raise ValueError("Actual five-point Jacobian/one-percent body-volume quality FAILED; no mesh exported")
    context.monkeypatch.setattr(w,"produce",rejected)
    assert w.main(context.output / "request.json") == 1
    for phase in ("before","after"):
        snapshot = h.read_json(context.output / f"runtime-{phase}.json")
        assert snapshot["runtime"] == observed and snapshot["observation_status"] == "OBSERVED"
        assert snapshot["diagnostic_only"] is True
    assert events == ["declared-cpu-policy","initialize","logger-start","logger-stop","finalize"]
    assert h.read_json(context.output / "lifecycle.json")["finalize_succeeded"] is True
    assert h.read_json(context.output / "quality.json")["status"] == "FAIL"
    assert h.read_json(context.output / "failure.json")["status"] == "REJECTED_PREPROCESSING"
    assert not (context.output / "mesh.msh").exists() and not (context.output / "result.json").exists()
