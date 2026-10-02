"""Fresh-source coupled-region acceptance; independent polynomials and full fields.

Explicit CLI calls native solvers; source tests and partial failures do not qualify physics.
"""

import argparse
from copy import deepcopy
from collections import defaultdict
import json
import math
from pathlib import Path

from caelab import Lab
from caelab.adapters.fenicsx_coupled_worker import SOURCE_PATHS
from caelab.storage import canonical_hash, load_json, save_json, source_identity, utc_now
from plugins.pde_coupled.reference import manufactured_settings
from scripts.verify_vector_pde import (_QUADRATURE, _require, _sha, _close,
                                     _original_observations, _assessed_studies)

REPOSITORY = Path(__file__).resolve().parents[1]
BACKEND = "pde.fenicsx.coupled"
SOURCE_FILES = ("scripts/verify_coupled_pde.py", "scripts/verify_vector_pde.py",
                *[item[0] for item in SOURCE_PATHS.values()])
COMPONENTS = ["u0", "u1"]
REGIONS = ["left", "right"]


def specification():
    return manufactured_settings()


def _all_dirichlet(request):
    for side, row in request["problem"]["boundaries"].items():
        row["type"] = "dirichlet"
        row["value"] = {region: deepcopy(request["problem"]["reference"]["solution"][region])
                        for region in row["value"]}
    return request


def cases():
    accepted = {"E-coupled-mixed": specification(),
        "E-coupled-reaction": manufactured_settings(reaction=[[2., .25], [.25, 1.]]),
        "E-coupled-all-dirichlet": _all_dirichlet(specification()),
        "E-coupled-homogeneous": manufactured_settings(diffusions={region: [[2., .5], [.5, 1.]] for region in REGIONS}),
        "E-coupled-harmonic-mixed": manufactured_settings(case="harmonic"),
        "E-coupled-harmonic-all-dirichlet": _all_dirichlet(manufactured_settings(case="harmonic"))}
    rejected = {name: deepcopy(accepted["E-coupled-mixed"]) for name in
        ("E-coupled-reference-reject", "E-coupled-traction-reject", "E-coupled-source-swap-reject")}
    for region in REGIONS:
        rejected["E-coupled-reference-reject"]["problem"]["reference"]["solution"][region][1] = "0.0"
        rejected["E-coupled-source-swap-reject"]["problem"]["weak_form"]["rhs"][region].reverse()
    for side in ("xmax", "ymax"):
        for values in rejected["E-coupled-traction-reject"]["problem"]["boundaries"][side]["value"].values():
            values[1] = f"-({values[1]})"
    refused = {name: deepcopy(accepted["E-coupled-mixed"]) for name in
        ("E-coupled-invalid-expression", "E-coupled-invalid-components", "E-coupled-invalid-interface-D",
         "E-coupled-invalid-SPD", "E-coupled-invalid-PSD", "E-coupled-invalid-symmetry",
         "E-coupled-invalid-odd-mesh", "E-coupled-invalid-pure-neumann")}
    refused["E-coupled-invalid-expression"]["problem"]["weak_form"]["rhs"]["left"][0] = "x.__class__"
    refused["E-coupled-invalid-components"]["problem"]["weak_form"]["rhs"]["right"].pop()
    values = refused["E-coupled-invalid-interface-D"]["problem"]["boundaries"]["ymin"]["value"]["right"]
    values[1] = f"({values[1]})+1"
    refused["E-coupled-invalid-SPD"]["problem"]["weak_form"]["diffusion"]["right"] = [[1., 2.], [2., 1.]]
    refused["E-coupled-invalid-PSD"]["problem"]["weak_form"]["reaction"] = [[1., 0.], [0., -1.]]
    refused["E-coupled-invalid-symmetry"]["problem"]["weak_form"]["diffusion"]["left"][0][1] = .75
    refused["E-coupled-invalid-odd-mesh"]["mesh"]["cell_counts"] = [3, 6, 12]
    for row in refused["E-coupled-invalid-pure-neumann"]["problem"]["boundaries"].values():
        row["type"] = "neumann"
    return accepted, rejected, refused


def _source_pin():
    return {"core": source_identity(REPOSITORY),
            "files": {relative: _sha(REPOSITORY / relative) for relative in SOURCE_FILES}}


def _verify_source(pin, result=None, folder=None):
    _require(_source_pin() == pin, "Coupled source drift; original results retained")
    if result is None: return
    _require({key: result["provenance"].get(key) for key in pin["core"]} == pin["core"], "Coupled provenance drift")
    if folder is not None and (folder / "pde/command.json").exists():
        manifest = load_json(folder / "pde/source_manifest.json")
        _require(set(manifest["files"]) == set(SOURCE_PATHS), "Incomplete nine coupled source copies")
        for key, (repository_path, copied_path) in SOURCE_PATHS.items():
            item = manifest["files"][key]
            _require(item == {"repository_path": repository_path, "copied_path": copied_path,
                "sha256": pin["files"][repository_path]}, "Coupled manifest identity drift")
            _require(_sha(folder / "pde" / copied_path) == item["sha256"], "Coupled native copy bytes drift")


def _matvec(matrix, vector):
    return [sum(matrix[i][j]*vector[j] for j in range(2)) for i in range(2)]


def _math(experiment, settings, region, x, y):
    """Direct manufacturer derivatives; no Domain/AST/native interpretation."""
    weak = settings["problem"]["weak_form"]
    dl, dr = weak["diffusion"]["left"], weak["diffusion"]["right"]
    normal = _matvec(dl, [1., -2.])
    determinant = dr[0][0]*dr[1][1]-dr[0][1]*dr[1][0]
    right = [(dr[1][1]*normal[0]-dr[0][1]*normal[1])/determinant,
             (-dr[1][0]*normal[0]+dr[0][0]*normal[1])/determinant]
    a, beta = ([1., -2.] if region == "left" else right), [1., 2.]
    s = x-settings["problem"]["domain"]["lengths"][0]/2
    harmonic = experiment in ("E-coupled-harmonic-mixed", "E-coupled-harmonic-all-dirichlet")
    q, qx, qy, delta = (s*s-y*y, 2*s, -2*y, 0.) if harmonic else (s*s*y*y, 2*s*y*y, 2*s*s*y, 2*(y*y+s*s))
    u = [1+y+a[0]*s+q, 2-3*y+a[1]*s+2*q]
    gradient = [[a[i]+beta[i]*qx, [1., -3.][i]+beta[i]*qy] for i in range(2)]
    matrix = weak["diffusion"][region]
    diffusion_source, reaction = _matvec(matrix, [delta*value for value in beta]), _matvec(weak["reaction"], u)
    source = [reaction[i]-diffusion_source[i] for i in range(2)]
    flux = [[sum(matrix[i][j]*gradient[j][axis] for j in range(2)) for axis in range(2)] for i in range(2)]
    reference, reference_gradient = deepcopy(u), deepcopy(gradient)
    if experiment == "E-coupled-reference-reject": reference[1], reference_gradient[1] = 0., [0., 0.]
    if experiment == "E-coupled-source-swap-reject": source.reverse()
    return {"solution": u, "gradient": gradient, "rhs": source, "flux": flux,
            "reference": reference, "reference_gradient": reference_gradient}


def _side_value(experiment, settings, side, region, x, y):
    data = _math(experiment, settings, region, x, y)
    if settings["problem"]["boundaries"][side]["type"] == "dirichlet": return data["solution"]
    axis, sign = (0, -1) if side == "xmin" else (0, 1) if side == "xmax" else (1, -1) if side == "ymin" else (1, 1)
    value = [sign*data["flux"][component][axis] for component in range(2)]
    if experiment == "E-coupled-traction-reject" and side in ("xmax", "ymax"): value[1] = -value[1]
    return value


def _integrate_field(experiment, settings, field):
    """5×5 Duffy on each ORIGINAL region-conforming saved P1 triangle."""
    coordinates, values = dict(zip(field["node_ids"], field["coordinates"])), dict(zip(field["node_ids"], field["values"]))
    l2, h1 = [0., 0.], [0., 0.]
    interface = settings["problem"]["domain"]["lengths"][0]/2
    for cell in field["cell_node_ids"]:
        points, nodal = [coordinates[node] for node in cell], [values[node] for node in cell]
        lower, upper = min(p[0] for p in points), max(p[0] for p in points)
        # Native interface coordinates retain floating-point representation;
        # use the existing geometric comparison tolerance without rewriting them.
        crosses = (lower < interface and not math.isclose(lower, interface, rel_tol=1e-12, abs_tol=1e-12) and
                   upper > interface and not math.isclose(upper, interface, rel_tol=1e-12, abs_tol=1e-12))
        _require(not crosses, "Saved cell crosses coupled interface")
        region = "left" if sum(p[0] for p in points)/3<interface else "right"
        (x0,y0),(x1,y1),(x2,y2) = points
        det = (x1-x0)*(y2-y0)-(x2-x0)*(y1-y0)
        _require(det != 0., "Degenerate saved coupled triangle")
        basis = [[(y1-y2)/det,(x2-x1)/det],[(y2-y0)/det,(x0-x2)/det],[(y0-y1)/det,(x1-x0)/det]]
        gradients = [[sum(nodal[node][component]*basis[node][axis] for node in range(3)) for axis in range(2)] for component in range(2)]
        for r,wr in _QUADRATURE:
            for s,ws in _QUADRATURE:
                barycentric = [1-r-(1-r)*s,r,(1-r)*s]
                x,y = [sum(barycentric[node]*points[node][axis] for node in range(3)) for axis in range(2)]
                data,weight = _math(experiment,settings,region,x,y),abs(det)*(1-r)*wr*ws
                for component in range(2):
                    interpolated = sum(barycentric[node]*nodal[node][component] for node in range(3))
                    l2[component] += weight*(interpolated-data["reference"][component])**2
                    h1[component] += weight*sum((gradients[component][axis]-data["reference_gradient"][component][axis])**2 for axis in range(2))
    return {"component_l2":[math.sqrt(v) for v in l2],"component_h1":[math.sqrt(v) for v in h1],
            "l2":math.sqrt(sum(l2)),"h1":math.sqrt(sum(h1))}


def _fields(experiment, settings, result, folder):
    root,assessed_studies = folder/"pde",_assessed_studies(result, folder)
    studies = load_json(root/"worker_result.json")["mesh_studies"]
    _require(len(studies)==len(assessed_studies)==len(settings["mesh"]["cell_counts"]),"Incomplete coupled studies")
    _require(all(_original_observations(raw, assessed) for raw,assessed in zip(studies,assessed_studies)),"Adapter changed original coupled observations")
    _require(load_json(root/"progress.json")=={"schema_version":"1","status":"COMPLETED","completed":[{"cells_per_axis":n} for n in settings["mesh"]["cell_counts"]]},"Incomplete coupled native progress")
    previous,closure = None,[]
    for n,study in zip(settings["mesh"]["cell_counts"],studies):
        _require(study["cells_per_axis"]==n and study["global_nodes"]==(n+1)**2 and study["global_dofs"]==2*(n+1)**2 and study["dirichlet_dofs"]==2*study["dirichlet_nodes"] and study["block_size"]==2,"Wrong coupled block/scalar counts")
        expected={key:f"level_n{n}/{name}" for key,name in {"field":"field.xdmf","field_data":"field.h5","form_source":"forms.ufl.txt","dofs":"dofs.json","binding":"binding.json"}.items()}
        _require(study["files"]==expected,"Coupled retained filenames differ")
        for key,relative in expected.items():_require(_sha(root/relative)==study["artifact_sha256"][key],"Coupled artifact hash mismatch")
        _require(load_json(root/f"level_n{n}/observation.json")==study,"Coupled original observation differs")
        field,binding=load_json(root/expected["dofs"]),load_json(root/expected["binding"])
        _require(field["components"]==binding["components"]==COMPONENTS and field["block_size"]==2 and set(binding["regions"])==set(REGIONS),"Coupled binding component/region identity")
        _require(study["region_coefficients"]==settings["problem"]["weak_form"]["diffusion"] and study["reaction_matrix"]==settings["problem"]["weak_form"]["reaction"] and study["region_cell_counts"]=={region:n*n for region in REGIONS} and study["interface_facets"]==n,"Coupled native coefficient/tag observations differ")
        by_id=dict(zip(field["node_ids"],field["coordinates"]))
        _require(field["field_type"]=="vector" and len(field["values"])==len(field["coordinates"])==len(field["node_ids"])==len(by_id)==(n+1)**2 and all(len(row)==2 and all(math.isfinite(value) for value in row) for row in field["values"]),"Coupled full directed field shape differs")
        _require(len(field["cell_ids"])==len(field["cell_node_ids"])==len(field["cell_regions"])==2*n*n and set(field["cell_ids"])==set(range(2*n*n)),"Coupled cell identity/count coverage differs")
        region_by_cell,edge_cells= {},defaultdict(list)
        interface_x=settings["problem"]["domain"]["lengths"][0]/2
        for cell,triangle,region in zip(field["cell_ids"],field["cell_node_ids"],field["cell_regions"]):
            expected_region="left" if sum(by_id[node][0] for node in triangle)/3<interface_x else "right"
            _require(region==expected_region,"Retained material region contradicts original geometry")
            region_by_cell[cell]=expected_region
            for a,b in ((0,1),(1,2),(2,0)):edge_cells[tuple(sorted((triangle[a],triangle[b])))].append(cell)
        interface_nodes=sorted(node for node,point in by_id.items() if math.isclose(point[0],interface_x,rel_tol=1e-12,abs_tol=1e-12))
        interface_node_set=set(interface_nodes)
        interface_edges={edge:cells for edge,cells in edge_cells.items() if set(edge)<=interface_node_set and len(cells)==2}
        interface=field["interface"]
        _require(interface["node_ids"]==interface_nodes and len(interface_nodes)==n+1 and len(interface["facet_ids"])==len(interface["facet_node_ids"])==len(interface["adjacent_cell_ids"])==len(interface_edges)==n and len(set(interface["facet_ids"]))==n,"Coupled interface coverage differs")
        _require(interface["plus_x_normal"]==[1.,0.],"Interface common normal differs")
        _close(interface["measure"],settings["problem"]["domain"]["lengths"][1],"Interface measure differs")
        seen=set()
        for pair,adjacent in zip(interface["facet_node_ids"],interface["adjacent_cell_ids"]):
            edge=tuple(sorted(pair))
            _require(edge in interface_edges and edge not in seen and set(adjacent)==set(interface_edges[edge]) and len(adjacent)==2 and [region_by_cell[cell] for cell in adjacent]==REGIONS,"Coupled interface actual left/right adjacency differs")
            seen.add(edge)
        _require(seen==set(interface_edges),"Coupled interface edge omitted")
        for region in REGIONS:
            cells=[cell for cell,nodes in zip(field["cell_ids"],field["cell_node_ids"]) if ("left" if sum(by_id[node][0] for node in nodes)/3<settings["problem"]["domain"]["lengths"][0]/2 else "right")==region]
            cell_set=set(cells)
            nodes=sorted({node for cell,triangle in zip(field["cell_ids"],field["cell_node_ids"]) if cell in cell_set for node in triangle})
            row=binding["regions"][region]
            _require(row["cell_ids"]==sorted(cells) and row["node_ids"]==nodes and row["diffusion"]==settings["problem"]["weak_form"]["diffusion"][region] and row["reaction"]==settings["problem"]["weak_form"]["reaction"],"Coupled independent region/matrix binding differs")
            _require(len(row["rhs_values"])==len(row["reference_values"])==len(nodes),"Truncated region input trace")
            for i,node in enumerate(nodes):
                data=_math(experiment,settings,region,*by_id[node])
                for key,expected_values in (("rhs_values",data["rhs"]),("reference_values",data["reference"])):
                    _require(len(row[key][i])==2,"Missing region component")
                    for observed,value in zip(row[key][i],expected_values):_close(observed,value,"Independent region source/reference trace differs")
        lx,ly=settings["problem"]["domain"]["lengths"]
        _require(set(field["boundaries"])=={"xmin","xmax","ymin","ymax"},"Coupled named side omitted")
        exterior={edge for edge,cells in edge_cells.items() if len(cells)==1};seen_exterior=set();seen_facets=set()
        for side,segments in field["boundaries"].items():
            expected_regions={"left"} if side=="xmin" else {"right"} if side=="xmax" else set(REGIONS)
            _require(set(segments)==expected_regions,"Coupled split boundary region omitted")
            for region,boundary in segments.items():
                axis,slot=(0,0.) if side=="xmin" else (0,lx) if side=="xmax" else (1,0.) if side=="ymin" else (1,ly)
                expected_nodes={node for node,point in by_id.items() if math.isclose(point[axis],slot,rel_tol=1e-12,abs_tol=1e-12) and (axis==0 or (point[0]<=lx/2+1e-12 if region=="left" else point[0]>=lx/2-1e-12))}
                _require(boundary["dof_ids"]==sorted(expected_nodes),"Coupled segment DOF union differs")
                count=n if axis==0 else n//2
                _require(len(boundary["facet_ids"])==len(boundary["facet_node_ids"])==count and len(set(boundary["facet_ids"]))==count and not (set(boundary["facet_ids"]) & seen_facets),"Coupled segment facet counts/identity differ")
                seen_facets.update(boundary["facet_ids"])
                _require(len(boundary["prescribed_values"])==len(expected_nodes)==count+1 and all(len(row)==2 for row in boundary["prescribed_values"]) and len(boundary["prescribed_integral"])==2,"Coupled segment directed samples omitted")
                length=ly if axis==0 else lx/2
                _close(boundary["measure"],length,"Coupled segment measure differs")
                sign=-1 if side in ("xmin","ymin") else 1
                expected_normal=[0.,0.];expected_normal[axis]=sign*length
                _require(len(boundary["normal_integral"])==2,"Coupled segment normal missing")
                for value,expected_value in zip(boundary["normal_integral"],expected_normal):_close(value,expected_value,"Coupled segment outward normal differs")
                for pair in boundary["facet_node_ids"]:
                    edge=tuple(sorted(pair));_require(edge in exterior and edge not in seen_exterior and set(pair)<=expected_nodes,"Coupled split side differs from original exterior")
                    seen_exterior.add(edge)
                for node,observed in zip(boundary["dof_ids"],boundary["prescribed_values"]):
                    for value,expected_value in zip(observed,_side_value(experiment,settings,side,region,*by_id[node])):_close(value,expected_value,"Directed segment value differs")
                axis,constant=(0,0.) if side=="xmin" else (0,lx) if side=="xmax" else (1,0.) if side=="ymin" else (1,ly)
                start,length=(0.,ly) if axis==0 else ((0. if region=="left" else lx/2),lx/2)
                integrals=[0.,0.]
                for coordinate,weight in _QUADRATURE:
                    point=(constant,start+length*coordinate) if axis==0 else (start+length*coordinate,constant)
                    for component,value in enumerate(_side_value(experiment,settings,side,region,*point)):integrals[component]+=length*weight*value
                for value,expected_value in zip(boundary["prescribed_integral"],integrals):_close(value,expected_value,"Independent segment integral differs")
        _require(seen_exterior==exterior,"Coupled exterior edge omitted")
        integrated=_integrate_field(experiment,settings,field)
        for metric,key in (("l2_error","l2"),("h1_seminorm_error","h1")):
            _close(study[metric],integrated[key],"Independent coupled vector norm differs")
            for component in range(2):_close(study["components"][component][metric],integrated["component_"+key][component],"Independent coupled component norm differs")
        for metric,key in (("l2_convergence_rate","l2"),("h1_seminorm_convergence_rate","h1")):
            rate=math.log(previous[key]/integrated[key],2) if previous and previous[key]>0 and integrated[key]>0 else None
            _require(study[metric] is None if rate is None else math.isclose(study[metric],rate,rel_tol=1e-10,abs_tol=1e-12),"Independent coupled vector rate differs")
            for component in range(2):
                before=previous["component_"+key][component] if previous else None;current=integrated["component_"+key][component]
                rate=math.log(before/current,2) if before is not None and before>0 and current>0 else None
                observed=study["components"][component][metric]
                _require(observed is None if rate is None else math.isclose(observed,rate,rel_tol=1e-10,abs_tol=1e-12),"Independent coupled component rate differs")
        _require(study["ksp_convergence_reason"]>0 and study["linear_residual"]["relative"]<=settings["validation"]["max_residual_relative"],"Coupled actual residual/KSP failed")
        closure.append({"count":n,**integrated});previous=integrated
    return closure


def run(store):
    store = Path(store).resolve()
    _require(not store.exists(), "Coupled acceptance store must be new; historical bytes retained")
    pin = _source_pin()
    _require(pin["core"]["core_commit"] != "unavailable" and pin["core"]["core_dirty"] is False,
             "Coupled native acceptance requires committed clean source")
    accepted, rejected, refused = cases()
    store.mkdir(parents=True, exist_ok=False)
    plan = {"schema_version": "1", "created_utc": utc_now(), "source": pin,
            "accepted": accepted, "numerical_rejections": rejected, "preflight_rejections": refused,
            "qualification": "BOUNDED_MATHEMATICAL_ONLY", "release": "NOT_RELEASED"}
    save_json(store / "acceptance_plan.json", plan)
    plan_sha, reports = _sha(store / "acceptance_plan.json"), []
    lab = Lab(store)
    lab.create_study("S-coupled", "Directed coupled weak form and fixed reference controls",
        "Do both coupled components match independent references on every frozen mesh?",
        "P1 coupled L2 and full-gradient H1 converge at orders2 and1 with correctly directed traction.",
        "Retain complete coupled fields, numerical refusals and UNKNOWN qualification.")
    preserved = {}
    try:
        for category, requests in (("ACCEPTED", accepted), ("NUMERICAL_REJECTED", rejected), ("PREFLIGHT_REJECTED", refused)):
            for experiment, settings in requests.items():
                _verify_source(pin)
                _require(_sha(store / "acceptance_plan.json") == plan_sha, "Frozen coupled plan drift")
                result = lab.run_pde(study_id="S-coupled", experiment_id=experiment, settings=settings, backend=BACKEND)
                folder = store / "experiments" / experiment
                _verify_source(pin, result, folder)
                _require(_sha(store / "acceptance_plan.json") == plan_sha, "Frozen coupled plan drift during call")
                _require(result["decision"] == "NOT_RELEASED" and result["cad_revision"] is None and
                         "parent_experiment_id" not in result, "Coupled result acquired false engineering approval/CAD parent")
                unknown = {row["type"]:row["status"] for row in result["validations"]}
                _require(unknown.get("physical_validation") == unknown.get("model_qualification") == "UNKNOWN", "Coupled qualification changed")
                expected_solver = "NOT_RUN" if category == "PREFLIGHT_REJECTED" else "COMPLETED"
                _require(result["solver_status"] == expected_solver, "Wrong coupled native execution classification")
                _require(result["status"] == ("COMPLETED_REVIEW_REQUIRED" if category == "ACCEPTED" else "REJECTED"),
                         f"Wrong coupled numerical classification for {experiment}: {result['status']}; retained metrics={result['metrics']}")
                ledger = load_json(store / "ledger" / f"{experiment}.json")
                _require(ledger["experiment_id"] == experiment and ledger["result_sha256"] == _sha(folder / "result.json")
                         and ledger["thread_sha256"] == _sha(folder / "thread.json")
                         and lab.inspect_experiment(experiment) == result, "Coupled immutable ledger/result/thread mismatch")
                closure = []
                if category != "PREFLIGHT_REJECTED":
                    closure = _fields(experiment, settings, result, folder)
                    _require(all(metric["valid"] == (category == "ACCEPTED") for metric in result["metrics"].values()), "Wrong coupled metric validity")
                    if category == "NUMERICAL_REJECTED":
                        _require(all(metric.get("reason") for metric in result["metrics"].values()), "Lost coupled invalid-metric reasons")
                    from plugins.pde_coupled.reference import model_declaration
                    declaration = model_declaration(settings)
                    _require(result["model_revision"] == canonical_hash({"settings": settings, "declaration": declaration}), "Coupled declaration revision drift")
                else:
                    _require(not (folder / "pde/command.json").exists(), "Invalid coupled input launched native execution")
                reports.append({"experiment_id": experiment, "category": category, "status": result["status"],
                    "solver_status": result["solver_status"], "metrics": result["metrics"], "field_norm_closure": closure,
                    "model_revision": result["model_revision"], "artifact_manifest_sha256": canonical_hash(result["artifacts"]),
                    "result_sha256": _sha(folder / "result.json")})
                preserved.update({str(path.relative_to(store)).replace("\\", "/"): _sha(path)
                                  for path in folder.rglob("*") if path.is_file()})
                save_json(store / "acceptance_progress.json", {"status": "RUNNING", "source": pin, "cases": reports})
        _verify_source(pin)
        _require(_sha(store / "acceptance_plan.json") == plan_sha, "Frozen coupled plan drift at completion")
        for relative, digest in preserved.items():
            _require(_sha(store / relative) == digest, "A later coupled experiment overwrote previous bytes")
        report = {"schema_version": "1", "created_utc": utc_now(), "status": "PASS_BOUNDED_MATHEMATICAL",
                  "source": pin, "plan_sha256": plan_sha, "accepted": len(accepted), "numerical_rejections": len(rejected),
                  "preflight_rejections": len(refused), "native_processes": len(accepted)+len(rejected),
                  "native_meshes": sum(len(case["field_norm_closure"]) for case in reports), "cases": reports,
                  "preserved_artifact_hashes": preserved,
                  "decision": "NOT_RELEASED", "qualification": "UNKNOWN", "official_research_admission": "NOT_ADMITTED"}
        save_json(store / "acceptance.json", report)
        save_json(store / "acceptance_progress.json", {"status": "COMPLETED", "source": pin, "cases": reports})
        return report
    except BaseException as exc:
        save_json(store / "acceptance_progress.json", {"status": "FAILED_OR_PARTIAL", "source": pin, "cases": reports,
                 "error": f"{type(exc).__name__}: {exc}", "decision": "NOT_RELEASED"})
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    report = run(parser.parse_args().store)
    print(json.dumps({key: report[key] for key in ("status", "accepted", "numerical_rejections", "preflight_rejections",
                      "native_processes", "native_meshes", "decision")}, indent=2))


if __name__ == "__main__":
    main()
