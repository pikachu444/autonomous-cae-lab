"""Fresh immutable imported-mesh campaign; independent original-field integrals."""

import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from caelab import Lab
from caelab.adapters.fenicsx_imported import manufactured_settings
from caelab.adapters.fenicsx_gmsh import prepare
from caelab.adapters.fenicsx_imported_worker import SOURCE_PATHS
from caelab.storage import canonical_hash, load_json, save_json, source_identity, utc_now
from scripts.verify_vector_pde import _QUADRATURE, _require, _close, _original_observations, _assessed_studies

REPOSITORY = Path(__file__).resolve().parents[1]
BACKEND = "pde.fenicsx.imported"
SOURCE_FILES = [row[0] for row in SOURCE_PATHS.values()] + [
    "scripts/verify_imported_pde.py", "scripts/verify_vector_pde.py"]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_pin():
    return {"core": source_identity(REPOSITORY), "files": {
        name: _sha(REPOSITORY / name) for name in SOURCE_FILES}}


def _verify_source(pin, result=None, folder=None):
    _require(_source_pin() == pin, "Imported PDE source changed after freeze")
    if result is not None:
        _require(all(result["provenance"].get(key) == value for key, value in pin["core"].items()),
                 "Imported result source identity differs from the frozen source")
    if folder is not None and (folder / "pde/command.json").exists():
        entries = load_json(folder / "pde/source_manifest.json")["files"]
        _require(set(entries) == set(SOURCE_PATHS), "Imported native source manifest is incomplete")
        for key, (original, copied) in SOURCE_PATHS.items():
            row = entries[key]
            _require(row["repository_path"] == original and row["copied_path"] == copied and
                     row["sha256"] == pin["files"][original] == _sha(folder / "pde" / copied),
                     "Imported copied source differs from frozen original")


def _mesh_edit(settings, section, transform, level=0, rehash=True):
    selected = settings["mesh"]["levels"][level]
    lines = selected["data"].splitlines()
    start, end = lines.index("$" + section), lines.index("$End" + section)
    rows = transform(lines[start + 2:end])
    lines[start + 1:end] = [str(len(rows)), *rows]
    selected["data"] = "\n".join(lines) + "\n"
    if rehash:
        selected["sha256"] = hashlib.sha256(selected["data"].encode("ascii")).hexdigest()


def cases():
    accepted = {"E-imported-mixed": manufactured_settings(),
                "E-imported-reaction": manufactured_settings(diffusion=3., reaction=2.),
                "E-imported-harmonic": manufactured_settings(case="harmonic"),
                "E-imported-all-dirichlet": manufactured_settings(case="all_dirichlet"),
                "E-imported-rectangle": manufactured_settings(case="all_dirichlet", shape="rectangle")}
    rejected = {"E-imported-reference-reject": deepcopy(accepted["E-imported-mixed"]),
                "E-imported-flux-reject": deepcopy(accepted["E-imported-mixed"])}
    rejected["E-imported-reference-reject"]["problem"]["reference"]["solution"] = "0.0"
    for boundary in rejected["E-imported-flux-reject"]["problem"]["boundaries"].values():
        if boundary["type"] == "neumann": boundary["value"] = "-(" + boundary["value"] + ")"
    refused = {}
    for name in ("expression", "hash", "missing-name", "duplicate-name", "entity-tags",
                 "missing-line", "duplicate-cell", "corner", "pure-neumann", "polygon"):
        settings = deepcopy(accepted["E-imported-mixed"])
        if name == "expression": settings["problem"]["weak_form"]["rhs"] = "__import__('os').getcwd()"
        elif name == "hash": settings["mesh"]["levels"][0]["sha256"] = "0" * 64
        elif name == "missing-name": _mesh_edit(settings, "PhysicalNames", lambda rows: rows[1:])
        elif name == "duplicate-name":
            def duplicate_name(rows):
                body = next(index for index, row in enumerate(rows) if row.split()[0] == "2")
                side = next(row for row in rows if row.split()[0] == "1").split('"')[1]
                changed = rows[:]; changed[body] = rows[body].split('"')[0] + '"' + side + '"'
                return changed
            _mesh_edit(settings, "PhysicalNames", duplicate_name)
        elif name == "entity-tags":
            def mixed_entity(rows):
                changed = [row.split() for row in rows]
                a = next(row for row in changed if row[1] == "1")
                b = next(row for row in changed if row[1] == "1" and row[3] != a[3]); b[4] = a[4]
                return [" ".join(row) for row in changed]
            _mesh_edit(settings, "Elements", mixed_entity)
        elif name == "missing-line":
            def remove_line(rows):
                changed = rows[:]; changed.pop(next(i for i, row in enumerate(rows) if row.split()[1] == "1")); return changed
            _mesh_edit(settings, "Elements", remove_line)
        elif name == "duplicate-cell":
            def duplicate_cell(rows):
                changed = rows[:]; row = next(row for row in rows if row.split()[1] == "2").split()
                row[0] = str(max(int(row.split()[0]) for row in rows) + 1); changed.append(" ".join(row)); return changed
            _mesh_edit(settings, "Elements", duplicate_cell)
        elif name == "corner": settings["problem"]["boundaries"]["west"]["value"] = "2*x[1]+2"
        elif name == "pure-neumann":
            for boundary in settings["problem"]["boundaries"].values(): boundary.update(type="neumann", value="0.0")
        elif name == "polygon":
            def change_polygon(rows):
                changed = [row.split() for row in rows]
                for row in changed:
                    if float(row[1]) == 2.: row[1] = "2.01"
                return [" ".join(row) for row in changed]
            _mesh_edit(settings, "Nodes", change_polygon, level=2)
        refused["E-imported-invalid-" + name] = settings
    return accepted, rejected, refused


def _math(experiment, settings, x, y):
    harmonic = experiment == "E-imported-harmonic"
    sign = -1. if harmonic else 1.
    solution, gradient = x*x + sign*y*y + x + 2*y + 1., [2*x + 1., 2*sign*y + 2.]
    weak = settings["problem"]["weak_form"]
    reference = 0. if experiment == "E-imported-reference-reject" else solution
    reference_gradient = [0., 0.] if experiment == "E-imported-reference-reject" else gradient
    return {"solution": solution, "gradient": gradient, "reference": reference,
            "reference_gradient": reference_gradient,
            "rhs": -(2. + 2.*sign)*weak["diffusion"] + weak["reaction"]*solution}


def _integrate_field(experiment, settings, field):
    """Direct polynomial derivatives and Duffy over every ORIGINAL scalar P1 cell."""
    nodes = field["node_ids"]
    _require(len(nodes) == len(set(nodes)) == len(field["values"]) == len(field["coordinates"]), "Incomplete scalar saved field")
    coordinates, values = dict(zip(nodes, field["coordinates"])), dict(zip(nodes, field["values"]))
    l2, h1 = 0., 0.
    for cell in field["cell_node_ids"]:
        _require(len(cell) == len(set(cell)) == 3 and set(cell) <= set(coordinates), "Malformed saved triangle")
        points, nodal = [coordinates[node] for node in cell], [values[node] for node in cell]
        (x0,y0),(x1,y1),(x2,y2) = points
        determinant = (x1-x0)*(y2-y0) - (x2-x0)*(y1-y0)
        _require(math.isfinite(determinant) and determinant != 0., "Degenerate saved triangle")
        basis = [[(y1-y2)/determinant,(x2-x1)/determinant], [(y2-y0)/determinant,(x0-x2)/determinant], [(y0-y1)/determinant,(x1-x0)/determinant]]
        gradient = [sum(nodal[node]*basis[node][axis] for node in range(3)) for axis in range(2)]
        for r,wr in _QUADRATURE:
            for s,ws in _QUADRATURE:
                barycentric = [1-r-(1-r)*s,r,(1-r)*s]
                x,y = [sum(barycentric[node]*points[node][axis] for node in range(3)) for axis in range(2)]
                expected = _math(experiment,settings,x,y)
                weight = abs(determinant)*(1-r)*wr*ws
                interpolated = sum(barycentric[node]*nodal[node] for node in range(3))
                l2 += weight*(interpolated-expected["reference"])**2
                h1 += weight*sum((gradient[axis]-expected["reference_gradient"][axis])**2 for axis in range(2))
    return {"l2": math.sqrt(l2), "h1": math.sqrt(h1)}


def _geometry(field, mesh):
    """Bijections keep native DOF/cell/facet IDs separate from original MSH IDs."""
    node_ids, source_ids = field["node_ids"], field["source_node_ids"]
    source_nodes = {row["id"]: row["coordinates"] for row in mesh["nodes"]}
    _require(len(node_ids) == len(set(node_ids)) == len(source_ids) == len(set(source_ids)) == len(source_nodes)
             and set(source_ids) == set(source_nodes), "Original/native node mapping is not a bijection")
    for original, coordinates in zip(source_ids, field["coordinates"]):
        for actual, expected in zip(coordinates, source_nodes[original]): _close(actual,expected,"Imported original coordinate changed")
    by_id = dict(zip(node_ids,field["coordinates"])); original_by_dof = dict(zip(node_ids,source_ids))
    source_cells = {row["id"]:row for row in mesh["cells"]}
    _require(len(field["cell_ids"]) == len(set(field["cell_ids"])) == len(field["source_cell_ids"])
             == len(field["cell_node_ids"]) == len(source_cells) and set(field["source_cell_ids"]) == set(source_cells),
             "Original/native cell mapping is incomplete")
    edges, h, area = defaultdict(list), 0., 0.
    for source, cell in zip(field["source_cell_ids"],field["cell_node_ids"]):
        _require(set(original_by_dof[node] for node in cell) == set(source_cells[source]["node_ids"]), "Original cell connectivity changed")
        a,b,c = [by_id[node] for node in cell]
        area += abs((b[0]-a[0])*(c[1]-a[1]) - (c[0]-a[0])*(b[1]-a[1]))/2
        for i,j,k in ((0,1,2),(1,2,0),(2,0,1)):
            edge = tuple(sorted((cell[i],cell[j]))); edges[edge].append(cell[k])
            h = max(h,math.dist(by_id[edge[0]],by_id[edge[1]]))
    return by_id,original_by_dof,edges,h,area


def _boundaries(experiment, settings, field, mesh, by_id, original_by_dof, edges):
    _require(set(field["boundaries"]) == set(mesh["boundaries"]), "Physical boundary names changed")
    seen, selected = set(), set()
    for name, boundary in field["boundaries"].items():
        original = {row["id"]:row for row in mesh["boundaries"][name]["elements"]}
        facets, pairs, source_ids = boundary["facet_ids"], boundary["facet_node_ids"], boundary["source_element_ids"]
        _require(len(facets) == len(set(facets)) == len(pairs) == len(source_ids) == len(original)
                 and set(source_ids) == set(original) and not set(facets)&seen, "Incomplete/disjoint original boundary facets")
        seen.update(facets); expected_nodes, measure, normal_integral, prescribed_integral = set(),0.,[0.,0.],0.
        node_values = {}
        for pair, source in zip(pairs,source_ids):
            edge = tuple(sorted(pair)); _require(len(edges[edge]) == 1, "Named facet is not an actual exterior edge")
            _require(set(original_by_dof[node] for node in pair) == set(original[source]["node_ids"]), "Original boundary element changed")
            expected_nodes.update(pair); a,b = [by_id[node] for node in pair]; length=math.dist(a,b)
            normal=[(b[1]-a[1])/length,-(b[0]-a[0])/length]; third=by_id[edges[edge][0]]
            if sum(normal[axis]*(third[axis]-(a[axis]+b[axis])/2) for axis in range(2)) > 0: normal=[-v for v in normal]
            for node in pair:
                data = _math(experiment,settings,*by_id[node])
                value = data["solution"] if settings["problem"]["boundaries"][name]["type"] == "dirichlet" else settings["problem"]["weak_form"]["diffusion"]*sum(data["gradient"][axis]*normal[axis] for axis in range(2))
                if experiment == "E-imported-flux-reject" and settings["problem"]["boundaries"][name]["type"] == "neumann": value=-value
                if node in node_values: _close(node_values[node],value,"Canonical boundary has inconsistent normal/node input")
                node_values[node] = value
            measure += length
            for axis in range(2): normal_integral[axis] += length*normal[axis]
            for t,weight in _QUADRATURE:
                point=[a[axis]+t*(b[axis]-a[axis]) for axis in range(2)]; data=_math(experiment,settings,*point)
                value=data["solution"] if settings["problem"]["boundaries"][name]["type"] == "dirichlet" else settings["problem"]["weak_form"]["diffusion"]*sum(data["gradient"][axis]*normal[axis] for axis in range(2))
                if experiment == "E-imported-flux-reject" and settings["problem"]["boundaries"][name]["type"] == "neumann": value=-value
                prescribed_integral += length*weight*value
        _require(len(boundary["dof_ids"]) == len(boundary["prescribed_values"]) == len(expected_nodes) and
                 set(boundary["dof_ids"]) == expected_nodes and len(boundary["normal_integral"]) == 2,
                 "Physical boundary DOFs/inputs incomplete")
        for node,value in zip(boundary["dof_ids"],boundary["prescribed_values"]): _close(value,node_values[node],"Directed physical group input differs")
        _close(boundary["measure"],measure,"Physical boundary measure differs")
        for actual,expected in zip(boundary["normal_integral"],normal_integral): _close(actual,expected,"Actual outward boundary normals differ")
        _close(boundary["prescribed_integral"],prescribed_integral,"Directed boundary integral differs")
        if settings["problem"]["boundaries"][name]["type"] == "dirichlet":
            selected.update(expected_nodes)
            for node,prescribed in zip(boundary["dof_ids"],boundary["prescribed_values"]):
                _close(prescribed,_math(experiment,settings,*by_id[node])["solution"],"Directed D value differs")
                _close(field["values"][field["node_ids"].index(node)],prescribed,"Actual selected D value differs")
    _require(len(seen) == sum(len(v)==1 for v in edges.values()),"Native exterior facets lost")
    _require(set(field["dirichlet_node_ids"]) == selected,"Dirichlet union differs")


def _mapping(field, mapping, mesh, original_sha, dense_sha):
    original_nodes = sorted(row["id"] for row in mesh["nodes"])
    count, cells = len(original_nodes), len(mesh["cells"])
    _require(mapping["schema_version"] == "1" and mapping["original_sha256"] == original_sha and
             mapping["dense_sha256"] == dense_sha and mapping["dense_node_ids"] == list(range(1,count+1)) and
             mapping["original_node_ids"] == original_nodes,"Derived mesh original/dense identity differs")
    geometry_input = mapping["geometry_input_indices"]
    _require(len(geometry_input) == count and set(geometry_input) == set(range(count)),"Incomplete geometry input mapping")
    _require(mapping["geometry_source_node_ids"] == [original_nodes[index] for index in geometry_input],"Geometry input/source mapping differs")
    vertices, geometry, dofs = mapping["vertex_ids"],mapping["vertex_geometry_indices"],mapping["vertex_dof_ids"]
    _require(len(vertices) == len(geometry) == len(dofs) == count and set(vertices) == set(range(count)) and
             set(geometry) == set(range(count)) and set(dofs) == set(field["node_ids"]),"Vertex/geometry/DOF bijection differs")
    field_sources = dict(zip(field["node_ids"],field["source_node_ids"]))
    for geometry_index,dof in zip(geometry,dofs):
        _require(field_sources[dof] == mapping["geometry_source_node_ids"][geometry_index],"Vertex identity assumes DOF=geometry")
    importer, indices = mapping["importer_cell_source_ids"],mapping["original_cell_index"]
    _require(len(importer) == len(indices) == cells and set(importer) == {row["id"] for row in mesh["cells"]}
             and set(indices) == set(range(cells)) and mapping["cell_ids"] == field["cell_ids"] and
             mapping["source_cell_ids"] == field["source_cell_ids"] == [importer[index] for index in indices],
             "Native cell mapping assumes raw MSH row ordering")
    groups = {mesh["body"]["name"]:{"dim":2,"tag":mesh["body"]["tag"]}, **{
        name:{"dim":1,"tag":row["tag"]} for name,row in mesh["boundaries"].items()}}
    _require(mapping["physical_groups"] == groups,"Native physical name/dim/tag map differs")
    _require(mapping["boundary_source_elements"] == {name:row["source_element_ids"] for name,row in field["boundaries"].items()},"Native boundary source mapping differs")
    expected = {"argv":[],"read_config_files":False,"finalized":True}
    _require(_original_observations(expected,mapping["gmsh_initialization"]) and
             _original_observations(mapping["gmsh_initialization"],expected),"Owned Gmsh initialization/finalization differs")
    return groups


def _fields(experiment, settings, result, folder):
    root = folder/"pde"
    studies = load_json(root/"worker_result.json")["mesh_studies"]
    assessed = _assessed_studies(result,folder)
    meshes = prepare(settings)
    _require(len(studies) == len(assessed) == len(meshes),"Incomplete imported native mesh collection")
    _require(all(_original_observations(raw,checked) for raw,checked in zip(studies,assessed)),"Adapter changed original imported observations")
    progress = load_json(root/"progress.json")
    _require(progress == {"schema_version":"1","status":"COMPLETED","completed":[{"level":index}for index in range(len(meshes))]},"Incomplete imported native progress")
    previous, closure = None,[]
    for index,(level,mesh,study) in enumerate(zip(settings["mesh"]["levels"],meshes,studies)):
        _require(study["level"] == index and study["degree"] == 1 and study["cell_type"] == "triangle","Wrong imported P1 level identity")
        names = {"original":"original.msh","dense":"dense-import.msh","mapping":"import_mapping.json",
                 "field":"field.xdmf","field_data":"field.h5","form_source":"forms.ufl.txt","dofs":"dofs.json","binding":"binding.json"}
        expected_files = {key:f"level_{index}/{name}" for key,name in names.items()}
        _require(study["files"] == expected_files,"Imported retained filenames differ")
        for key,relative in expected_files.items(): _require(_sha(root/relative) == study["artifact_sha256"][key],"Imported retained artifact changed")
        _require((root/expected_files["original"]).read_bytes() == level["data"].encode("ascii") and
                 study["source_sha256"] == level["sha256"],"Original MSH bytes were rewritten")
        original_sha,dense_sha = _sha(root/expected_files["original"]),_sha(root/expected_files["dense"])
        _require(original_sha == level["sha256"] and dense_sha == study["dense_sha256"],"Imported original/derived hashes differ")
        _require(load_json(root/f"level_{index}/observation.json") == study,"Imported observation changed")
        field,binding,mapping = [load_json(root/expected_files[name])for name in ("dofs","binding","mapping")]
        _require(field["schema_version"] == binding["schema_version"] == "1" and
                 field["coordinates_unit"] == field["field_unit"] == "1","Wrong imported field schema/units")
        _require(all(isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) for value in field["values"]),"Nonfinite/nonscalar native values")
        by_id,original_by_dof,edges,h,area = _geometry(field,mesh)
        _require(study["global_nodes"] == study["global_dofs"] == len(mesh["nodes"]) and
                 study["global_cells"] == len(mesh["cells"]),"Native counts differ from original imported mesh")
        _close(study["max_edge_h"],h,"Native measured h differs from retained triangles")
        _close(area,2. if experiment == "E-imported-rectangle" else 3.,"Imported canonical domain area changed")
        _boundaries(experiment,settings,field,mesh,by_id,original_by_dof,edges)
        _require(study["dirichlet_nodes"] == study["dirichlet_dofs"] == len(field["dirichlet_node_ids"]),"Dirichlet DOF union/count differs")
        groups = _mapping(field,mapping,mesh,original_sha,dense_sha)
        _require(study["physical_groups"] == groups and study["coefficients"] == {
            key:settings["problem"]["weak_form"][key]for key in ("diffusion","reaction")},"Native tag/Constant observations differ")
        _require(binding["source_sha256"] == original_sha and binding["dense_sha256"] == dense_sha and
                 binding["node_ids"] == field["node_ids"] and binding["source_node_ids"] == field["source_node_ids"] and
                 len(binding["rhs_values"]) == len(binding["reference_values"]) == len(field["node_ids"]),"Input/field original identity differs")
        for key in ("diffusion","reaction"): _close(binding[key],settings["problem"]["weak_form"][key],"Actual Constant binding differs")
        for position,point in enumerate(field["coordinates"]):
            expected = _math(experiment,settings,*point)
            _close(binding["rhs_values"][position],expected["rhs"],"Original directed RHS binding differs")
            _close(binding["reference_values"][position],expected["reference"],"Original reference binding differs")
        integral = _integrate_field(experiment,settings,field)
        _close(study["l2_error"],integral["l2"],"Independent imported L2 differs")
        _close(study["h1_seminorm_error"],integral["h1"],"Independent imported full-gradient H1 differs")
        if previous is None:
            _require(study["l2_convergence_rate"] is None and study["h1_seminorm_convergence_rate"] is None,"First h-level acquired a fictitious rate")
        else:
            _require(h < previous["h"],"Actual imported maximum edge is not decreasing")
            for error,rate in (("l2","l2_convergence_rate"),("h1","h1_seminorm_convergence_rate")):
                expected = math.log(previous[error]/integral[error])/math.log(previous["h"]/h)
                _close(study[rate],expected,"Independent measured-h order differs")
        residual = study["linear_residual"]
        _require(study["ksp_convergence_reason"] > 0 and residual["normalization"] == ("rhs_l2_norm"if residual["rhs_norm"]else"absolute_for_zero_rhs"),"Actual constrained solve/residual normalization differs")
        _close(residual["relative"],residual["absolute"]/residual["rhs_norm"]if residual["rhs_norm"]else residual["absolute"],"Residual normalization changed")
        previous = {"h":h,**integral};closure.append({"level":index,"source_sha256":original_sha,"dense_sha256":dense_sha,"h":h,**integral})
    return closure


def run(store):
    store = Path(store).resolve()
    _require(not store.exists(),"Imported acceptance store must be new; preserve prior attempts")
    pin = _source_pin()
    _require(pin["core"]["core_dirty"] is False and pin["core"]["core_commit"] != "unavailable","Native acceptance requires committed clean source")
    accepted,rejected,refused = cases()
    lab = Lab(store)
    lab.create_study("S-imported", "Original meshes and named physical boundaries",
                     "Do imported mesh identities and complete weak-form fields reproduce direct polynomial references?",
                     "Real P1 fields converge with preserved original input/tag/DOF/geometry mappings.",
                     "Mathematical evidence and finite numerical rejections do not release physical models.")
    save_json(store/"acceptance_plan.json",{"schema_version":"1","source":pin,"accepted":accepted,
        "numerical_rejections":rejected,"preflight_rejections":refused,"qualification":"UNKNOWN","decision":"NOT_RELEASED"})
    plan_sha = _sha(store/"acceptance_plan.json")
    reports,preserved = [],{}
    try:
        for category,requests in (("ACCEPTED",accepted),("NUMERICAL_REJECTED",rejected),("PREFLIGHT_REJECTED",refused)):
            for experiment,settings in requests.items():
                _verify_source(pin);_require(_sha(store/"acceptance_plan.json") == plan_sha,"Frozen imported plan changed")
                result = lab.run_pde(study_id="S-imported",experiment_id=experiment,backend=BACKEND,settings=settings)
                folder = store/"experiments"/experiment
                _verify_source(pin,result,folder)
                _require(_sha(store/"acceptance_plan.json") == plan_sha,"Frozen imported plan changed during execution")
                _require(result["status"] == ("COMPLETED_REVIEW_REQUIRED"if category == "ACCEPTED"else"REJECTED") and
                         result["solver_status"] == ("NOT_RUN"if category == "PREFLIGHT_REJECTED"else"COMPLETED"),
                         f"Wrong imported classification for {experiment}: {result['status']};metrics={result['metrics']}")
                _require(result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None and "parent_experiment_id"not in result,"False imported physical/CAD approval")
                unknown = {row["type"]:row["status"]for row in result["validations"]}
                _require(unknown.get("physical_validation") == unknown.get("model_qualification") == "UNKNOWN","Imported qualification changed")
                ledger = load_json(store/"ledger"/f"{experiment}.json")
                _require(ledger["result_sha256"] == _sha(folder/"result.json") and ledger["thread_sha256"] == _sha(folder/"thread.json")
                         and lab.inspect_experiment(experiment) == result,"Imported immutable Core/ledger/revision mismatch")
                closure = []
                if category != "PREFLIGHT_REJECTED":
                    closure = _fields(experiment,settings,result,folder)
                    _require(result["converged"] is True and result["metrics"] and all(row["valid"] is (category == "ACCEPTED")for row in result["metrics"].values()),"Invalid imported metric classification")
                    if category == "NUMERICAL_REJECTED": _require(all(row.get("reason")for row in result["metrics"].values()),"Lost invalid imported reasons")
                    declaration = lab.pde_adapters[BACKEND].describe_model(deepcopy(settings))
                    _require(result["model_revision"] == canonical_hash({"settings":settings,"declaration":declaration}),"Imported declaration revision differs")
                else: _require(not(folder/"pde/command.json").exists(),"Invalid imported input launched native work")
                reports.append({"experiment_id":experiment,"category":category,"status":result["status"],
                    "solver_status":result["solver_status"],"metrics":result["metrics"],"field_norm_closure":closure,
                    "model_revision":result["model_revision"],"result_sha256":_sha(folder/"result.json")})
                preserved.update({str(p.relative_to(store)).replace("\\","/"):_sha(p)for p in folder.rglob("*")if p.is_file()})
                save_json(store/"acceptance_progress.json",{"status":"RUNNING","source":pin,"cases":reports})
        _verify_source(pin);_require(_sha(store/"acceptance_plan.json") == plan_sha,"Frozen imported plan changed at completion")
        for relative,digest in preserved.items(): _require(_sha(store/relative) == digest,"A later imported experiment overwrote previous bytes")
        report = {"schema_version":"1","created_utc":utc_now(),"status":"PASS_BOUNDED_MATHEMATICAL","source":pin,
            "plan_sha256":plan_sha,"accepted":len(accepted),"numerical_rejections":len(rejected),"preflight_rejections":len(refused),
            "native_processes":len(accepted)+len(rejected),"native_meshes":sum(len(row["field_norm_closure"])for row in reports),
            "cases":reports,"preserved_artifact_hashes":preserved,"qualification":"UNKNOWN","decision":"NOT_RELEASED","official_research_admission":"NOT_ADMITTED"}
        save_json(store/"acceptance.json",report);save_json(store/"acceptance_progress.json",{"status":"COMPLETED","source":pin,"cases":reports})
        return report
    except BaseException as exc:
        save_json(store/"acceptance_progress.json",{"status":"FAILED_OR_PARTIAL","source":pin,"cases":reports,"error":f"{type(exc).__name__}: {exc}","decision":"NOT_RELEASED"})
        raise


def main():
    parser = argparse.ArgumentParser();parser.add_argument("--store",type=Path,required=True)
    report = run(parser.parse_args().store)
    print(json.dumps({key:report[key]for key in ("status","accepted","numerical_rejections","preflight_rejections","native_processes","native_meshes","decision")},indent=2))


if __name__ == "__main__":
    main()
