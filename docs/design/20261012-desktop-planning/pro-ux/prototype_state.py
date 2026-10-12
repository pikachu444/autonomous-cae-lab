"""Pure-stdlib state for the isolated UX prototype, never a production owner.

Only explicit user actions change this fixture state. No solver, provider,
native application, optimization or network operation is present.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

FORMAT = "caelab-ux-review/1"
HERE = Path(__file__).resolve().parent
TOOL_NAMES = {
    "cad": "CAD / FE", "simulation": "Simulation", "thermal": "Simulation",
    "thermoelastic": "Simulation", "post": "Post", "data": "Data",
    "material": "Material", "pde": "PDE", "numerical": "Numerical",
    "runner": "Runner", "expert": "Expert", "study": "Study",
    "evaluation": "Evaluation", "workbench": "Workbench",
}
METHODS = {
    "DOE": ("Design matrix", "Responses", "Effects"),
    "Inverse": ("Observations", "Residuals", "Holdout"),
    "Optimization": ("Candidates", "Objectives", "Constraints"),
    "Sobol sensitivity": ("Sampling design", "First / total order", "Convergence"),
    "UQ": ("Distributions", "Propagation", "Intervals"),
    "RBF surrogate": ("Training cases", "Validation split", "Prediction support"),
    "MOO": ("Candidates", "Pareto front", "Constraints"),
    "MDO": ("Disciplines", "Coupling", "Objectives"),
}
METHOD_INPUTS = {
    "DOE": [("Sampling","Latin hypercube"),("Design points",20),("Replicates",1)],
    "Inverse": [("Algorithm","Least squares"),("Loss","Huber"),("Residual scale",1.0),("Observation weight",1.0),("Holdout","Tension B")],
    "Optimization": [("Algorithm","Differential evolution"),("Population",15),("Relative tolerance",1e-6)],
    "Sobol sensitivity": [("Design","Saltelli A/B/crossed"),("Base samples",128),("Bootstrap replicates",200),("Input dependence","Independent")],
    "UQ": [("Sampling","Monte Carlo"),("Samples",1000),("Quantiles","0.05, 0.50, 0.95"),("Failure threshold",.35)],
    "RBF surrogate": [("Kernel","Thin plate spline"),("Smoothing",0.0),("Holdout fraction",.2),("Extrapolation","Block outside support")],
    "MOO": [("Method","Epsilon constraint"),("Primary objective","Mass"),("Error thresholds [%]","2.0, 2.5, 3.0, 4.0"),("Feasibility tolerance",1e-6)],
    "MDO": [("Architecture","Existing Evaluation"),("Coupling","Lagged Picard"),("Iteration limit",25),("Coupling tolerance",1e-6)],
}

RESPONSE_ROLES = ("Minimize", "Maximize", "Upper bound", "Lower bound", "Target", "Observe")
EVALUATORS = ("Unassigned", "Clamp / material response", "Structural Simulation",
              "Material response", "PDE response", "Thermal expansion Evaluation")
VARIABLE_BINDINGS = {
    "cad": {"thickness":"mm", "width":"mm", "height":"mm"},
    "material": {"mu":"MPa", "bulk":"MPa"},
    "simulation": {"force":"N", "duration":"s", "time_step":"s", "initial_velocity":"m/s"},
    "pde": {"k":"declared", "f":"declared", "mesh":"m"},
    "thermal": {"temperature":"K"}, "thermoelastic": {"alpha":"1/K", "Tref":"K"},
}


class ReviewError(Exception):
    """A recoverable operation error that must be shown in context."""


def clone(value: Any) -> Any:
    return copy.deepcopy(value)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def token(prefix: str) -> str:
    return prefix + "-" + uuid.uuid4().hex[:12]


def atomic_json(path: Path, content: Any) -> None:
    """Write locally, replacing a file only after complete serialization."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False)
    fd, name = tempfile.mkstemp(prefix=".review-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def binding_ids(variables):
    """Stable field identity for an editable method matrix, independent of row order."""
    return [{"owner":v["owner"],"field":v["field"],"unit":v["unit"]} for v in variables]


def remap_method_bindings(old, new):
    if binding_ids(old.get("variables", [])) == binding_ids(new.get("variables", [])):
        return new
    payload = clone(new)
    current = binding_ids(payload.get("variables", []))
    for method, sheet in payload.get("method_sheets", {}).items():
        previous = sheet.get("bindings", binding_ids(old.get("variables", [])))
        rows = sheet.get("primary", [])
        if method in ("DOE", "Optimization", "Sobol sensitivity", "RBF surrogate"):
            lead = 2 if method == "Sobol sensitivity" else 1
            tail = 0 if method == "Sobol sensitivity" else 2 if method == "RBF surrogate" else 1
            remapped = []
            for row in rows:
                if len(row) != lead + len(previous) + tail:
                    sheet["stale"] = True
                    continue
                values = [row[lead + previous.index(b)] if b in previous else "" for b in current]
                remapped.append(row[:lead] + values + (row[-tail:] if tail else []))
            if not sheet.get("stale"):sheet["primary"] = remapped
        elif method == "UQ":
            by_name = {row[0]:row for row in rows if row}
            sheet["primary"] = [by_name.get(v["owner"]+"."+v["field"],
                [v["owner"]+"."+v["field"],"Uniform",v["start"],(v["upper"]-v["lower"])/6,v["lower"],v["upper"]])
                for v in payload["variables"]]
            sheet.pop("secondary", None)
        sheet["bindings"] = current
    return payload


def observation_groups(data):
    obs = data.get("observation_snapshot", {})
    excluded = set(obs.get("quality_excluded", []))
    train = set(data.get("train_samples", []))
    groups = {"Tension A":[s["id"] for s in obs.get("samples", [])
                            if s["id"] not in excluded and s["id"] in train]}
    groups[data.get("holdout", "Tension B")] = ["B"+str(i) for i in range(81)]
    return groups


def method_sheet(data, candidates=(), front=()):
    """One editable definition shared by the Qt tables and submission checks."""
    method = data["method"]; variables = data["variables"]
    names = [v["owner"]+"."+v["field"]+" ["+v["unit"]+"]" for v in variables]
    if method in ("DOE", "Optimization"):
        return ["Case"]+names+["Use"], [], ["Control","Value"], [["Design","Editable candidate matrix"],["Result","No evaluation"]]
    if method == "Sobol sensitivity":
        return ["Block","Row"]+names, [], ["Pairing rule","Value"], [["Base blocks","A, B"],["Crossed blocks","A_B per variable"],["Input dependence","Independent"],["Second order","Off"]]
    if method == "UQ":
        return ["Variable","Distribution","Location","Scale","Lower","Upper"], [[v["owner"]+"."+v["field"],"Uniform",v["start"],(v["upper"]-v["lower"])/6,v["lower"],v["upper"]] for v in variables], ["Variable pair","Correlation"], [[variables[i]["field"]+" / "+variables[j]["field"],0.0] for i in range(len(variables)) for j in range(i+1,len(variables))]
    if method == "Inverse":
        groups=observation_groups(data)
        return ["Observation","Use","Weight","Residual scale","Included","Unit"], [[name,"Train" if name=="Tension A" else "Holdout",1.0 if name=="Tension A" else 0.0,1.0,len(ids),"MPa"] for name,ids in groups.items()], ["Residual definition","Value"], [["Measure","First Piola / engineering strain"],["Objective","Weighted train residual RMS"],["Holdout","Excluded from fit objective"]]
    if method == "RBF surrogate":
        return ["Case"]+names+["Response","Split"], [], ["Support / validation","Value"], [["Validation","Independent holdout"],["Out of range","Unavailable"],["Prediction","Separate from new evaluation"]]
    if method == "MDO":
        return ["Discipline","Owner","Input","Output"], [["Heat","V-02","Boundary temperature [K]","Temperature [K]"],["Expand","V-03","Temperature [K]","Displacement [m]"]], ["Transfer","Value"], [["Evaluation","EVAL-01"],["Association","POINTS"],["Mapping","exact_same_mesh"],["Actual source field","PENDING"]]
    return ["Objective / constraint","Limit","Role"], [[r["name"],str(r["limit"]),r["role"]] for r in data["responses"]], ["Front membership","Value"], [[c["id"],"Non-dominated" if c["id"] in front else "Dominated" if c["status"]=="Retained fixture" else c["status"]] for c in candidates]


def active_training(data):
    """Return precisely the selected observation groups; no residual is calculated."""
    headers, defaults, _, _ = method_sheet(data)
    rows = data.get("method_sheets", {}).get("Inverse", {}).get("primary", defaults)
    groups = observation_groups(data)
    included = []; weights = {}; holdout = []
    for row in rows:
        if len(row) != 6 or row[0] not in groups:continue
        if row[1] == "Train":
            try:weight,scale = float(row[2]),float(row[3])
            except (ValueError, TypeError):continue
            if weight <= 0 or scale <= 0:continue
            for sid in groups[row[0]]:
                included.append(sid);weights[sid] = {"weight":weight,"scale":scale,"group":row[0]}
        elif row[1] == "Holdout":holdout.extend(groups[row[0]])
    return included, weights, holdout


def method_diagnostics(data):
    errors = []; method=data["method"]; variables=data["variables"]
    if method not in METHOD_INPUTS:return [("method","Choose a supported planning method.")]
    settings = dict(METHOD_INPUTS[method]);settings.update(data.get("method_settings",{}).get(method,{}))
    sheet=data.get("method_sheets",{}).get(method,{})
    headers,defaults,second_headers,second_defaults=method_sheet(data)
    rows=sheet.get("primary",defaults);secondary=sheet.get("secondary",second_defaults)
    def error(message):errors.append(("method_inputs",message))
    def numeric(value, minimum=None, integer=False, strict=False):
        v=float(value)
        if not math.isfinite(v) or (minimum is not None and (v<=minimum if strict else v<minimum)) or (integer and not v.is_integer()):raise ValueError()
        return v
    try:
        budget=numeric(data["budget"],1,True)
        requests = {"DOE":lambda:numeric(settings["Design points"],1,True)*numeric(settings["Replicates"],1,True),
                    "Sobol sensitivity":lambda:numeric(settings["Base samples"],2,True)*(len(variables)+2),
                    "UQ":lambda:numeric(settings["Samples"],1,True),
                    "Optimization":lambda:numeric(settings["Population"],1,True)}
        if method in requests and requests[method]() > budget:error("Requested evaluations exceed the total budget. Edit Method or reduce the design.")
    except (ValueError,TypeError,KeyError):error("Correct the method sample count and evaluation budget.")
    if sheet.get("stale") or (sheet.get("bindings") is not None and sheet["bindings"]!=binding_ids(variables)):
        error("The matrix uses different variable fields. Rebuild the example matrix or enter a new design.")
        return errors
    if any(len(row)!=len(headers) for row in rows):
        error("Complete each method row; its columns must match the current variable bindings.")
        return errors
    if method in ("DOE","Optimization","RBF surrogate","Sobol sensitivity"):
        lead=2 if method=="Sobol sensitivity" else 1
        identifiers=[]
        for row in rows:
            if not str(row[0]).strip():error("Each case or block needs a name.")
            try:
                for variable,value in zip(variables,row[lead:lead+len(variables)]):
                    v=numeric(value)
                    if v<float(variable["lower"]) or v>float(variable["upper"]):raise ValueError()
            except (ValueError,TypeError):error("Every matrix value must be finite and within its variable bounds.")
            if method!="Sobol sensitivity":identifiers.append(str(row[0]))
        if len(identifiers)!=len(set(identifiers)):error("Case names must be unique.")
    if method in ("DOE","Optimization") and rows:
        if any(row[-1] not in ("Yes","No") for row in rows):error("Use must be Yes or No.")
        active=sum(row[-1]=="Yes" for row in rows)
        if not active:error("Select at least one design case.")
        try:
            if method=="DOE" and active!=numeric(settings["Design points"],1,True):error("Design points must equal the number of active matrix rows.")
            if active*numeric(settings.get("Replicates",1),1,True)>numeric(data["budget"],1,True):error("Active matrix evaluations exceed the budget.")
        except (ValueError,TypeError):pass
    if method=="Sobol sensitivity" and rows:
        blocks={};expected={"A","B"}|{"A_B:"+v["field"] for v in variables}
        for row in rows:
            group=blocks.setdefault(str(row[0]),{})
            if str(row[1]) in group:error("Sobol block row IDs must be unique.")
            group[str(row[1])]=row[2:]
        if set(blocks)!=expected:error("Include A, B and one A_B block per variable.")
        a=blocks.get("A",{});b=blocks.get("B",{})
        if set(a)!=set(b) or not a:error("Pair A and B using the same nonempty row IDs.")
        try:
            if len(a)!=numeric(settings["Base samples"],2,True):error("Base samples must equal paired A/B rows.")
        except (ValueError,TypeError):pass
        for j,var in enumerate(variables):
            crossed=blocks.get("A_B:"+var["field"],{})
            if set(crossed)!=set(a):error("Every crossed block needs the same A/B row IDs.")
            for rid,values in crossed.items():
                if rid not in a or rid not in b:continue
                try:
                    wanted=[float(b[rid][k] if k==j else a[rid][k]) for k in range(len(variables))]
                    if [float(v) for v in values]!=wanted:error("A_B values must copy A except for the named variable from B.")
                except (ValueError,TypeError,IndexError):error("Correct crossed-block numeric values.")
        if settings.get("Input dependence")!="Independent":error("This Sobol design requires independent inputs; retain correlated studies under UQ.")
    if method=="Inverse":
        groups=observation_groups(data);seen=[]
        for row in rows:
            seen.append(row[0])
            if row[0] not in groups:error("Bind the observation row to Tension A or the retained Tension B fixture.");continue
            if row[1] not in ("Train","Holdout","Exclude"):error("Observation Use must be Train, Holdout or Exclude.")
            try:
                numeric(row[2],0,strict=row[1]=="Train");numeric(row[3],0,strict=True)
                if numeric(row[4],0,True)!=len(groups[row[0]]):error("Included count must match this observation source and quality selection. Refresh observations.")
            except (ValueError,TypeError):error("Use a positive training weight and residual scale; Holdout/Exclude may use zero weight.")
            if row[5]!="MPa":error("This stress residual fixture uses MPa.")
        if len(seen)!=len(set(seen)):error("Each observation group may appear only once.")
        included,_,_=active_training(data)
        if not included:error("Choose at least one observation with Train and a positive weight.")
    if method=="UQ":
        names=[v["owner"]+"."+v["field"] for v in variables]
        if [row[0] for row in rows]!=names:error("Distribution rows must match the variable bindings.")
        for row in rows:
            if row[1] not in ("Uniform","Normal","Lognormal","Triangular"):error("Choose Uniform, Normal, Lognormal or Triangular.")
            try:
                location=numeric(row[2]);numeric(row[3],0,strict=True);lo=numeric(row[4]);hi=numeric(row[5])
                if lo>=hi or (row[1]=="Triangular" and not lo<=location<=hi):raise ValueError()
                if row[1]=="Lognormal" and lo<=0:raise ValueError()
            except (ValueError,TypeError):error("Correct the distribution location, positive scale and ordered bounds.")
        matrix=[[float(i==j) for j in range(len(variables))] for i in range(len(variables))]
        try:
            values=[numeric(row[1]) for row in secondary]
            if len(values)!=len(variables)*(len(variables)-1)//2 or any(abs(v)>1 for v in values):raise ValueError()
            index=0
            for i in range(len(variables)):
                for j in range(i+1,len(variables)):matrix[i][j]=matrix[j][i]=values[index];index+=1
            # Small LDL check for a valid correlation matrix, not a UQ engine.
            for k in range(len(matrix)):
                pivot=matrix[k][k]
                if pivot < -1e-12:raise ValueError()
                if abs(pivot)<1e-12:
                    if any(abs(matrix[i][k])>1e-12 for i in range(k+1,len(matrix))):raise ValueError()
                    continue
                for i in range(k+1,len(matrix)):
                    for j in range(i,len(matrix)):matrix[i][j]-=matrix[i][k]*matrix[j][k]/pivot;matrix[j][i]=matrix[i][j]
        except (ValueError,TypeError,IndexError):error("Correlations must form a symmetric positive-semidefinite matrix with values in [-1, 1].")
        try:
            quantiles=[numeric(v.strip()) for v in str(settings["Quantiles"]).split(",")]
            if quantiles!=sorted(set(quantiles)) or any(not 0<v<1 for v in quantiles):raise ValueError()
        except (ValueError,TypeError):error("Enter increasing, unique quantiles between 0 and 1.")
    if method=="RBF surrogate":
        if not rows:error("Add training and holdout cases before reviewing a surrogate fit.")
        if rows and not ({row[-1] for row in rows}>={"Train","Holdout"}):error("Provide separate Train and Holdout cases.")
        for row in rows:
            if row[-1] not in ("Train","Holdout","Exclude"):error("Split must be Train, Holdout or Exclude.")
            try:numeric(row[-2])
            except (ValueError,TypeError):error("Each included surrogate case requires a finite measured or evaluated response.")
        if secondary!=second_defaults:error("Only independent holdout and blocked extrapolation are connected in this review prototype.")
    if method=="MDO":
        if rows!=defaults:error("Bind Heat to V-02 and Expand to V-03 in the existing Evaluation definition.")
        if secondary!=second_defaults:error("Review the temperature / POINTS / exact_same_mesh transfer in Evaluation; no new scheduler is created.")
    return list(dict.fromkeys(errors))


def make_document(key, name, owner, doc_id, revision, payload):
    return {"key": key, "name": name, "owner": owner, "id": doc_id,
            "revision": revision, "generation": 0, "saved": clone(payload),
            "draft": clone(payload), "file": None, "undo": [], "redo": [],
            "history": [{"revision": revision, "payload": clone(payload),
                         "source": "PUBLIC_SYNTHETIC_FIXTURE"}],
            "dirty": False, "buffers": {}}


def structural_fields(displacement=.31):
    return {
        "Displacement":{"unit":"mm","association":"POINTS","values":[0,displacement*.38,displacement*.74,displacement]},
        "Contact pressure":{"unit":"MPa","association":"CELLS","values":[0,.8,1.5,2.4]},
        "Normal force":{"unit":"N","association":"FIELD","values":[0,95,180,250]},
    }


def initial_documents():
    docs = {}
    def add(*args):
        doc = make_document(*args)
        docs[doc["key"]] = doc
    add("cad", "Clamp fixture", "native_pre", "CAD-01", 13, {
        "thickness": 14.0, "width": 72.0, "height": 28.0, "unit": "mm",
        "geometry_type": "Clamp", "instances": 2,
        "conditions": [{"type":"Fixed support","face":"Base/Face2","axis":"All","value":0,"unit":"mm"},
                       {"type":"Force","face":"Clamp/Pad/Face6","axis":"Z","value":-250,"unit":"N"}],
        "material": {"id": "MAT-01", "revision": 18},
        "sketch": {"length_constraint": "72", "fully_constrained": True},
        "joint": {"type": "Revolute", "angle": 15.0, "preview_angle": 15.0},
        "mesh": {"size": 2.0, "quality_limit": .25, "bad_elements": [314, 829]},
        "contact": {"law": "Coulomb", "mu": .15, "gap": .20,
                    "set_a": ["Clamp/Pad/Face6", "Clamp/Pad/Face7"],
                    "set_b": ["Base/Face2"], "resolved": True},
        "capability": "PROTOTYPE_ONLY", "qualification": "UNKNOWN",
        "release": "NOT_RELEASED"})
    add("simulation", "Clamp load", "Simulation", "V-01", 7, {
        "family": "Nonlinear implicit", "model_ref": {"id": "CAD-01", "revision": 13},
        "step": "Load", "duration": 1.0, "increments": 100,
        "geometry": "Large deformation", "force": -250.0, "force_unit": "N",
        "required_response": "U / reaction / contact pressure",
        "failure": "Interface damage", "initial_velocity": -3.43,
        "angular_velocity": 0.0, "time_step": 1e-6,
        "backend": "Code_Aster", "capability": "UNCONNECTED"})
    add("thermal", "Plate heating", "Simulation", "V-02", 4, {
        "family": "Thermal", "backend": "thermal.fenicsx.rectangle",
        "field": "temperature", "unit": "K", "length_unit": "m",
        "mesh": "P1 triangular / same plate", "temperature": 323.15,
        "boundary": "Uniform Dirichlet", "capability": "NOT_EXECUTED"})
    add("thermoelastic", "Plate expansion", "Simulation", "V-03", 6, {
        "family": "Thermoelastic", "backend": "structural.fenicsx.thermoelastic_rectangle",
        "field": "displacement", "unit": "m", "length_unit": "m",
        "mesh": "P1 triangular / same plate", "Tref": 293.15,
        "alpha": 1.2e-5, "state": "Plane stress / free expansion",
        "thermal_ref": {"id": "V-02", "revision": 4}, "capability": "NOT_EXECUTED"})
    samples = [{"id": f"A{i}", "time": i * .01, "extension": i * .004,
                "force": round(195 * (i / 300) ** .82, 5), "temperature": 23.0}
               for i in range(301)]
    add("data", "Tension", "Data", "DATA-01", 4, {
        "columns": [{"key": "time", "name": "Time", "unit": "s", "role": "X", "formula": ""},
                    {"key": "extension", "name": "Extension", "unit": "mm", "role": "Y", "formula": ""},
                    {"key": "force", "name": "Force", "unit": "N", "role": "Y", "formula": ""},
                    {"key": "temperature", "name": "Temperature", "unit": "degC", "role": "None", "formula": ""}],
        "samples": samples, "quality_excluded": [], "exclusion_reasons": {},
        "recipe": {"L0": 50.0, "A0": 20.0, "strain_measure": "engineering",
                   "stress_measure": "first_Piola", "displacement": "gauge extension"},
        "calibration": {"id": "CAL-018", "revision": 2, "file": "Calibration.txt",
                        "locator": "Force channel / calibration row 18",
                        "range": "0–2000 N", "status": "SYNTHETIC / not a certificate",
                        "sha256": hashlib.sha256((HERE/"fixtures"/"Calibration.txt").read_bytes()).hexdigest()
                            if (HERE/"fixtures"/"Calibration.txt").exists() else None}})
    add("material", "Rubber", "Material", "MAT-01", 18, {
        "law": "Neo-Hookean", "mu": .90, "bulk": 100.0, "unit": "MPa",
        "parameters": {"E":210000.0,"nu":.3,"yield":250.0,"hardening":1000.0,
                       "cohesion":12.0,"friction_angle":30.0,"dilation_angle":5.0,
                       "g1":.35,"tau1":1.0,"g2":.15,"tau2":10.0},
        "history": [[0,"Stretch F11",1,""],[1,"Stretch F11",1.2,""],[60,"Hold",1.2,""]],
        "initial_state": [["Plastic strain",0],["Damage",0],["Lateral traction",0]],
        "protocol": "Uniaxial traction-free", "train": "Tension A",
        "holdout": "Tension B", "L0": 50.0, "A0": 20.0,
        "observations": {"id": "DATA-01", "revision": 4},
        "dependencies": [{"id": "TENSION-A", "name": "Tension.csv",
                          "sha256": hashlib.sha256((HERE/"fixtures"/"Tension.csv").read_bytes()).hexdigest()
                              if (HERE/"fixtures"/"Tension.csv").exists() else "",
                          "missing": not (HERE/"fixtures"/"Tension.csv").exists()}],
        "capability": "UNCONNECTED"})
    add("pde", "Diffusion", "PDE", "PDE-01", 3, {
        "field": "u", "space": "P1", "domain": "Rectangle",
        "equation": "-div(k*grad(u)) = f", "k": 1.0, "f": 1.0,
        "bc": "u = 0", "selection": "Left edge", "mesh": .05,
        "width":1.0,"height":.6,"initial":"0","study_type":"Stationary",
        "time_range":"0:0.1:1","field_unit":"1","bc_type":"Dirichlet",
        "boundaries":{"Left edge":"u = 0","Right edge":"n·k·grad(u) = 0","Top edge":"n·k·grad(u) = 0","Bottom edge":"n·k·grad(u) = 0"},
        "form": "Registered PDE", "capability": "UNCONNECTED"})
    add("numerical", "Clamp trade-off", "Numerical", "N-MOO", 4, {
        "method": "MOO", "evaluator": "Clamp / material response",
        "budget": 40, "seed": 17, "method_settings": {},
        "sources": {"cad": {"id": "CAD-01", "revision": 12},
                    "material": {"id": "MAT-01", "revision": 17},
                    "data": {"id": "DATA-01", "revision": 4}},
        "observation_snapshot": clone(docs["data"]["saved"]),
        "variables": [{"owner": "cad", "field": "thickness", "unit": "mm", "start": 14.0,
                       "lower": 12.0, "upper": 16.0, "free": True},
                      {"owner": "material", "field": "mu", "unit": "MPa", "start": .85,
                       "lower": .60, "upper": 1.40, "free": True}],
        "responses": [{"name": "Mass", "role": "Minimize", "unit": "kg", "limit": ""},
                      {"name": "Gauge error", "role": "Minimize", "unit": "%", "limit": ""},
                      {"name": "Displacement", "role": "Upper bound", "unit": "mm", "limit": .35},
                      {"name": "Clearance", "role": "Lower bound", "unit": "mm", "limit": .10}],
        "train_samples": [s["id"] for s in samples], "holdout": "Tension B",
        "failure_policy": "Invalid objective; retain diagnostic", "data_source_stale": False})
    add("post", "Clamp result", "native_post", "POST-01", 3, {
        "result": "fixture-result-clamp", "array": "Displacement", "association": "POINTS",
        "unit": "mm", "time": .04, "available_times": [0, .01, .02, .04],
        "filter": "Surface", "pending_filter": "Surface", "mapping": "Unverified",
        "basis": "Global Cartesian", "selection": "Gauge endpoints",
        "deformation_scale": 10, "qualification": "UNKNOWN", "release": "NOT_RELEASED"})
    add("expert", "Clamp compliance", "Discussion", "DISC-01", 2, {
        "question": "지그 유연성이 측정 변위에 얼마나 섞이는가?",
        "provider": "UNCONNECTED", "paused": True, "pending_text": "",
        "reply_to": None,
        "topics": ["지그 강성", "접촉과 마찰", "측정 위치", "판별 시험"],
        "roles": ["구조", "시험", "재료"],
        "turns": [{"id": "question-example", "role": "사용자 예시", "actual": False,
                   "text": "재료 상수와 지그 유연성 중 무엇이 관측 차이를 만드는지 비교하고 싶다.",
                   "topic": "지그 강성", "reply_to": None, "evidence": []}],
        "evidence": [{"id": "fixture-result-clamp", "locator": "Gauge / t = 0.04 s",
                      "label": "Clamp displacement", "synthetic": True}],
        "plan_proposal": {"objective": "Separate fixture compliance from specimen response",
                          "variables": "Thickness, contact friction",
                          "response": "Gauge extension and machine displacement", "budget": 12},
        "study_ref": {"id": "STUDY-01", "revision": 2}})
    add("study", "Clamp compliance", "Study", "STUDY-01", 2, {
        "question": "지그 유연성이 측정 변위에 얼마나 섞이는가?",
        "hypotheses": [{"id": "H1", "text": "지그 유연성이 주요 원인", "judgment": "Undecided"},
                       {"id": "H2", "text": "재료 모델이 주요 원인", "judgment": "Undecided"},
                       {"id": "H3", "text": "계측 위치 또는 영점 영향", "judgment": "Undecided"}],
        "evidence": [{"ref": "fixture-result-clamp", "locator": "Gauge / t = 0.04 s",
                      "hypothesis": "H1", "relation": "Neutral", "synthetic": True}],
        "judgment": "Undecided", "reason": "", "next_research": "Independent gauge measurement",
        "qualification": "UNKNOWN", "release": "NOT_RELEASED"})
    add("evaluation", "Thermal expansion", "Evaluation", "EVAL-01", 5, {
        "stages": [{"stage": "Heat", "ref": {"id": "V-02", "revision": 4}, "operation": "thermal"},
                   {"stage": "Expand", "ref": {"id": "V-03", "revision": 6}, "operation": "thermoelastic"}],
        "transfer": "Temperature [K] / POINTS / exact_same_mesh",
        "static_connection": "Checked in fixture", "actual_field": "PENDING",
        "convergence": "NOT_EVALUATED", "iteration": "Lagged Picard",
        "tolerance": 1e-6, "limit": 25})
    add("workbench", "Clamp research", "Study links", "LINKS-01", 1, {
        "links": [["cad", "simulation"], ["simulation", "runner"], ["runner", "post"],
                  ["post", "numerical"], ["data", "material"], ["expert", "study"]],
        "positions": {}})
    add("runner", "Jobs", "JobManager view", "JOBS-VIEW", 1, {"filter": "All"})
    return docs


class ReviewSession:
    """Small serializable interaction fixture. Production services are not called."""
    def __init__(self, workspace=None):
        self.workspace = Path(workspace or tempfile.mkdtemp(prefix="caelab-ux-"))
        self.documents = initial_documents()
        self.jobs = []
        self.frozen = {}
        self.results = {
            "fixture-result-clamp": {"id": "fixture-result-clamp", "synthetic": True,
                 "source": {"id": "CAD-01", "revision": 12}, "attempt": "fixture-attempt-03",
                 "time": .04, "status": "RETAINED_FIXTURE",
                 "metrics": {"displacement": .31, "mass": .42, "clearance": .12}},
            "fixture-data-A301": {"id": "fixture-data-A301", "synthetic": True,
                 "source": {"id": "DATA-01", "revision": 4}, "included_count": 301,
                 "included_ids": [f"A{i}" for i in range(301)], "status": "RETAINED_FIXTURE"}}
        self.candidates = [
            {"id": "p04", "thickness": 14.6, "mu": .9, "mass": .49, "error": 2.9,
             "displacement": .29, "clearance": .16, "status": "Retained fixture"},
            {"id": "p19", "thickness": 13.7, "mu": 1.12, "mass": .42, "error": 2.1,
             "displacement": .31, "clearance": .12, "status": "Retained fixture"},
            {"id": "p27", "thickness": 12.8, "mu": 1.18, "mass": .38, "error": 4.7,
             "displacement": .41, "clearance": .08, "status": "Constraint violation"},
            {"id": "p31", "thickness": 12.1, "mu": .72, "mass": None, "error": None,
             "displacement": None, "clearance": None, "status": "Failed fixture"}]
        for candidate in self.candidates:
            cid = candidate["id"]
            candidate["result_ref"] = ("fixture-result-clamp" if cid == "p19" else "fixture-result-"+cid) if candidate["mass"] is not None else None
            candidate["plan_ref"] = {"id": "N-MOO", "revision": 4}
            candidate["diagnostic"] = "Synthetic evaluator failure; no response curve." if cid == "p31" else ""
            if candidate["result_ref"]:
                self.results[candidate["result_ref"]] = {
                    "id": candidate["result_ref"], "synthetic": True, "kind": "structural",
                    "source": {"id": "CAD-01", "revision": 12}, "plan": clone(candidate["plan_ref"]),
                    "candidate": cid, "attempt": "fixture-attempt-"+cid, "time": .04,
                    "input_values": {"thickness": candidate["thickness"], "mu": candidate["mu"]},
                    "geometry": {**clone(self.documents["cad"]["saved"]),"thickness":candidate["thickness"]},
                    "status": "RETAINED_FIXTURE",
                    "metrics": {k:candidate[k] for k in ("mass","displacement","clearance")},
                    "times": [0,.01,.02,.04],
                    "fields": structural_fields(candidate["displacement"])}
        self.groups = {}
        self.relocations = {}
        self.events = []
        self.selected = {"tool": "cad", "candidate": "p19", "samples": [], "topic": "지그 강성"}
        self.paths = {}

    def doc(self, key):
        if key in self.documents:
            return self.documents[key]
        for doc in self.documents.values():
            if doc["id"] == key:
                return doc
        raise ReviewError("Document is not in this review session: " + str(key))

    def resolve(self, ref):
        """Route by document identity AND requested saved revision, never screen label."""
        doc = self.doc(ref["id"])
        for item in doc["history"]:
            if item["revision"] == ref["revision"]:
                return doc["key"], clone(item["payload"])
        raise ReviewError("This exact saved revision is not retained. Current draft was not substituted.")

    def change(self, key, payload, label, buffers=None):
        doc = self.doc(key)
        if doc["owner"] == "native_pre" and any(payload.get(k) != doc["draft"].get(k) for k in ("thickness","width","height","geometry_type")):
            payload = clone(payload)
            payload["mesh"]["stale"] = True
        if doc["owner"] == "Numerical":
            payload = remap_method_bindings(doc["draft"], payload)
        next_buffers = clone(doc["buffers"] if buffers is None else buffers)
        if payload == doc["draft"] and next_buffers == doc["buffers"]:
            doc["dirty"] = doc["draft"] != doc["saved"] or bool(doc["buffers"])
            return
        doc["undo"].append({"payload": clone(doc["draft"]), "buffers": clone(doc["buffers"]), "label": label})
        doc["redo"].clear()
        doc["draft"] = clone(payload)
        doc["buffers"] = next_buffers
        doc["generation"] += 1
        doc["dirty"] = doc["draft"] != doc["saved"] or bool(doc["buffers"])
        self.events.append({"action": label, "owner": doc["id"], "kind": "UI_EDIT"})

    def edit(self, key, field, value):
        payload = clone(self.doc(key)["draft"])
        payload[field] = value
        self.change(key, payload, "Edit " + field)

    def history_step(self, key, redo=False):
        doc = self.doc(key)
        src, dst = ("redo", "undo") if redo else ("undo", "redo")
        if not doc[src]:
            return False
        entry = doc[src].pop()
        doc[dst].append({"payload": clone(doc["draft"]), "buffers": clone(doc["buffers"]), "label": entry["label"]})
        doc["draft"] = entry["payload"]
        doc["buffers"] = clone(entry.get("buffers", {}))
        doc["generation"] += 1
        doc["dirty"] = doc["draft"] != doc["saved"] or bool(doc["buffers"])
        return True

    def mask(self, sample_ids, exclude=True, reason="Quality exclusion"):
        doc = self.doc("data")
        payload = clone(doc["draft"])
        valid_ids = {s["id"] for s in payload["samples"]}
        if not set(sample_ids) <= valid_ids:
            raise ReviewError("Selection contains an unknown sample.")
        excluded = set(payload["quality_excluded"])
        if exclude:
            excluded.update(sample_ids)
        else:
            excluded.difference_update(sample_ids)
        payload["quality_excluded"] = sorted(excluded, key=lambda x: int(x[1:]))
        for sid in sample_ids:
            if exclude:
                payload["exclusion_reasons"][sid] = reason
            else:
                payload["exclusion_reasons"].pop(sid, None)
        self.change("data", payload, "Exclude selected samples" if exclude else "Restore selected samples")

    def diagnostics(self, key):
        doc, errors = self.doc(key), []
        data = doc["draft"]
        def positive(field, allow_zero=False):
            value = data.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or (
                    value < 0 if allow_zero else value <= 0):
                errors.append((field, "Enter a finite " + ("nonnegative" if allow_zero else "positive") + " value."))
        if doc["owner"] == "native_pre":
            for field in ("thickness", "width", "height"):
                positive(field)
            if data["contact"].get("active",True) and not data["contact"]["resolved"]:
                errors.append(("contact", "Required contact faces are unresolved."))
            if data["contact"].get("active",True) and (not data["contact"]["set_a"] or not data["contact"]["set_b"]):
                errors.append(("contact", "Both contact face sets are required."))
            if data["mesh"].get("stale"):
                errors.append(("mesh", "Geometry changed. Review the rebuilt mesh before freezing."))
            valid_faces=({"Base/Face2","Clamp/Pad/Face6","Clamp/Pad/Face7","Clamp/Pad/Face8","Clamp/Pad/Face9","Clamp/Leg/Face1","Clamp/Leg/Face2"}
                         if data.get("geometry_type","Clamp")=="Clamp" else {"Plate/Pad/Face6"})
            if data["contact"].get("active",True) and any(f not in valid_faces for f in data["contact"]["set_a"]+data["contact"]["set_b"]):
                errors.append(("contact","Select contact faces that exist on the current geometry."))
            for condition in data.get("conditions",[]):
                if condition.get("face") not in valid_faces:errors.append(("conditions","Rebind the condition target to the current geometry."))
                if not isinstance(condition.get("value"),(int,float)) or not math.isfinite(condition["value"]):errors.append(("conditions","Use a finite condition value."))
            if not isinstance(data["mesh"].get("size"),(int,float)) or data["mesh"]["size"]<=0:errors.append(("mesh","Use a positive element size."))
            mu=data["contact"]["mu"]
            if not isinstance(mu,(int,float)) or not math.isfinite(mu) or mu<0:
                errors.append(("contact.mu","Friction must be finite and nonnegative."))
        elif doc["owner"] == "Material":
            for field in ("mu", "bulk", "L0", "A0"):
                positive(field)
            for dep in data["dependencies"]:
                if dep["missing"] and dep["id"] not in self.relocations:
                    errors.append(("dependencies", "Locate the missing original: " + dep["name"]))
        elif doc["owner"] == "PDE":
            for field in ("k", "mesh", "width", "height"):
                positive(field)
            if data.get("pending_boundaries"):errors.append(("boundary","Apply or reset the edited boundary condition."))
            if not data.get("field", "").isidentifier():errors.append(("field","Use a valid unknown field name."))
            if not data["equation"].strip():
                errors.append(("equation", "An equation is required."))
        elif doc["owner"] == "Simulation":
            if data["family"] not in ("Thermal","Thermoelastic"):
                for field in ("duration","increments","time_step"):
                    positive(field)
                increments=data.get("increments")
                for name in ("residual_tolerance","max_iterations","cfl","gravity"):
                    if name in data:positive(name)
                for name in ("mass_scaling","drop_height"):
                    if name in data:positive(name,True)
                if "steps" in data and not data["steps"]:errors.append(("steps","At least one analysis step is required."))
                for step in data.get("steps",[]):
                    if not step.get("name") or not isinstance(step.get("duration"),(int,float)) or not math.isfinite(step["duration"]) or step["duration"]<=0:
                        errors.append(("steps","Each analysis step needs a name and positive duration."))
                if isinstance(increments,(float,int)) and not float(increments).is_integer():
                    errors.append(("increments","Use an integer increment limit."))
            elif data["family"]=="Thermal":
                positive("temperature")
            else:
                positive("Tref")
        elif doc["owner"] == "Numerical":
            if data.get("evaluator") not in EVALUATORS or data.get("evaluator")=="Unassigned":
                errors.append(("evaluator","Select an evaluator."))
            if not data["variables"] or not data["responses"]:
                errors.append(("definition","Add at least one variable and required response."))
            positive("budget")
            if isinstance(data.get("budget"),(int,float)) and not float(data["budget"]).is_integer():
                errors.append(("budget","Use an integer evaluation budget."))
            for var in data["variables"]:
                owner=self.documents.get(var.get("owner"))
                binding=VARIABLE_BINDINGS.get(var.get("owner"),{})
                if not owner or var.get("field") not in binding or var.get("unit") != binding.get(var.get("field")):
                    errors.append(("variables", "Choose a valid owner, field and unit binding."))
                try:
                    vals = [float(var[f]) for f in ("lower", "start", "upper")]
                    if not all(math.isfinite(x) for x in vals) or not vals[0] <= vals[1] <= vals[2]:
                        raise ValueError()
                except (ValueError, TypeError):
                    errors.append((var["field"], "Required bounds must contain the start value."))
            numeric_rules={
                "Design points":(1,None,True),"Replicates":(1,None,True),"Population":(1,None,True),
                "Base samples":(2,None,True),"Bootstrap replicates":(1,None,True),"Samples":(1,None,True),
                "Iteration limit":(1,None,True),"Relative tolerance":(1e-15,None,False),"Coupling tolerance":(1e-15,None,False),
                "Feasibility tolerance":(1e-15,None,False),"Residual scale":(1e-15,None,False),"Observation weight":(0,None,False),
                "Smoothing":(0,None,False),"Holdout fraction":(1e-12,1-1e-12,False),"Failure threshold":(None,None,False)}
            method_settings = dict(METHOD_INPUTS.get(data["method"], []));method_settings.update(data.get("method_settings",{}).get(data["method"],{}))
            for name,value in method_settings.items():
                if name in numeric_rules:
                    lo,hi,integer=numeric_rules[name]
                    try:
                        v=float(value)
                        if not math.isfinite(v) or (lo is not None and v<lo) or (hi is not None and v>hi) or (integer and not v.is_integer()):raise ValueError()
                    except (ValueError,TypeError):errors.append(("method", "Correct "+name+" for "+data["method"]+"."))
            response_units={"Mass":"kg","Gauge error":"%","Displacement":"mm","Clearance":"mm","Normal force":"N", "Stress residual":"MPa","Temperature":"K","Compliance":"N mm","Damage":"1"}
            for response in data["responses"]:
                if response.get("name") in response_units and response.get("unit")!=response_units[response["name"]]:
                    errors.append(("responses","Unit does not match "+response["name"]+"."))
                if "time" in response:
                    try:
                        if not math.isfinite(float(response["time"])) or float(response["time"])<0:raise ValueError()
                    except (ValueError,TypeError):errors.append(("responses","Response time must be finite and nonnegative."))
                if response.get("role") not in RESPONSE_ROLES:
                    errors.append(("responses", "Choose a response role from Minimize, Maximize, Upper bound, Lower bound, Target or Observe."))
                if not response.get("name", "").strip():
                    errors.append(("responses", "A response quantity is required."))
                if response["role"] in ("Upper bound","Lower bound","Target"):
                    try:
                        if not math.isfinite(float(response["limit"])):raise ValueError()
                    except (ValueError,TypeError):
                        errors.append((response["name"],"A finite numeric response limit is required."))
            errors.extend(method_diagnostics(data))
        elif doc["owner"] == "Evaluation":
            refs=[s["ref"]["id"] for s in data["stages"]]
            if refs != ["V-02","V-03"]:
                errors.append(("stages","This thermal fixture requires Heat before Expand."))
            if data.get("transfer_draft"):
                errors.append(("transfer","Review and apply edited transfer fields."))
            positive("tolerance")
            positive("limit")
            if isinstance(data.get("limit"),(int,float)) and not float(data["limit"]).is_integer():errors.append(("limit","Use an integer iteration limit."))
        errors.extend((field, "Unfinished input: " + str(value)) for field, value in doc["buffers"].items())
        return errors

    def pareto_ids(self):
        """Classify retained synthetic minimization examples; no optimizer is run."""
        feasible=[c for c in self.candidates if c["mass"] is not None and c["error"] is not None
                  and c["displacement"]<=.35 and c["clearance"]>=.10]
        return [c["id"] for c in feasible if not any(
            d["mass"]<=c["mass"] and d["error"]<=c["error"] and
            (d["mass"]<c["mass"] or d["error"]<c["error"]) for d in feasible if d is not c)]

    def post_frame(self, key, result_id=None):
        """Read one exact retained synthetic frame; never interpolate or compute."""
        view=self.doc(key)["draft"]
        result=self.results.get(result_id or view["result"], {})
        times=result.get("times", [])
        field=result.get("fields", {}).get(view["array"])
        available=(view["time"] in times and field is not None and
                   view["association"]==field["association"])
        index=times.index(view["time"]) if view["time"] in times else None
        return {"available":available,"time":view["time"],"array":view["array"],
                "unit":field["unit"] if field else view.get("unit", ""),
                "association":field["association"] if field else "UNAVAILABLE",
                "value":field["values"][index] if available else None,
                "measurements":{name:{"value":f["values"][index] if index is not None else None,
                                       "unit":f["unit"]} for name,f in result.get("fields",{}).items()},
                "times":times,"curve":field["values"] if field else []}

    def save_document(self, key, path=None, fail=False):
        doc = self.doc(key)
        if fail:
            raise ReviewError("Simulated write failure. Saved revision and draft are retained.")
        path = Path(path or doc["file"] or self.workspace / (doc["name"] + ".json"))
        if path.exists():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                disk = previous.get("document", {})
                if disk.get("id") != doc["id"]:
                    raise ReviewError("Different document at this path. Choose another file.")
                if disk.get("revision") != doc["revision"] and str(path) == doc["file"]:
                    raise ReviewError("The saved document changed outside this window. Inspect the conflict.")
            except (json.JSONDecodeError, UnicodeError):
                raise ReviewError("The chosen file is not a review document. Original file is unchanged.")
        saved = clone(doc)
        if doc["dirty"]:
            saved["revision"] += 1
            saved["saved"] = clone(doc["draft"])
            saved["history"].append({"revision": saved["revision"], "payload": clone(doc["draft"]),
                                     "source": "EXPLICIT_REVIEW_SAVE"})
        saved["dirty"] = bool(saved["buffers"])
        saved["file"] = str(path)
        attachments = {}
        if doc["owner"] == "native_post":
            result_id = saved["draft"].get("result")
            if result_id in self.results:
                attachments["result"] = clone(self.results[result_id])
                job = next((j for j in self.jobs if j.get("result") == result_id), None)
                if job:
                    attachments["job"] = clone(job)
                    attachments["input"] = clone(self.frozen.get(job["input"]))
        atomic_json(path, {"format": FORMAT, "kind": "document", "document": saved,
                           "attachments": attachments, "draft_valid": not self.diagnostics(key)})
        self.documents[doc["key"]] = saved
        self.paths[doc["id"]] = str(path)
        return {"id": saved["id"], "revision": saved["revision"],
                "payload_hash": digest(saved["saved"]), "path": str(path)}

    def refresh_data_source(self, key="numerical"):
        data = self.doc("data")
        if data["dirty"]:
            raise ReviewError("Save Data before using its new observations.")
        plan = clone(self.doc(key)["draft"])
        plan["sources"]["data"] = {"id": data["id"], "revision": data["revision"]}
        plan["observation_snapshot"] = clone(data["saved"])
        plan["data_source_stale"] = False
        groups=observation_groups(plan)
        for row in plan.get("method_sheets",{}).get("Inverse",{}).get("primary",[]):
            if row and row[0] in groups and len(row)==6:row[4]=len(groups[row[0]])
        self.change(key, plan, "Refresh saved observations")

    def freeze(self, key):
        doc = self.doc(key)
        errors = self.diagnostics(key)
        if errors:
            raise ReviewError("; ".join(x[1] for x in errors))
        if doc["dirty"]:
            raise ReviewError("Save the current document before freezing its input.")
        frozen_id = token("review-input")
        payload = clone(doc["saved"])
        item = {"id": frozen_id, "mode": "UI_REPLAY_ONLY",
                "source": {"id": doc["id"], "revision": doc["revision"]},
                "payload": payload, "hash": digest(payload)}
        if doc["owner"] == "Numerical":
            obs = payload["observation_snapshot"]
            mask = set(obs["quality_excluded"])
            keep = set(payload["train_samples"])
            item["included_ids"] = [s["id"] for s in obs["samples"] if s["id"] not in mask and s["id"] in keep]
            if payload["method"] == "Inverse":
                item["included_ids"],item["observation_weights"],item["holdout_ids"] = active_training(payload)
            item["included_count"] = len(item["included_ids"])
            item["observation_ref"] = clone(payload["sources"]["data"])
        self.frozen[frozen_id] = item
        return clone(item)

    def create_attempt(self, frozen_id):
        item = self.frozen[frozen_id]
        job = {"id": token("review-job"), "attempt": token("review-attempt"),
               "name": self.doc(item["source"]["id"])["name"],
               "input": frozen_id, "source": clone(item["source"]), "result": None,
               "status": "PREPARED", "mode": "UI_REPLAY_ONLY", "executed": False,
               "remote": False, "connected": True,
               "log": ["Review attempt created. No process was submitted."]}
        self.jobs.append(job)
        return job

    def job_event(self, job_id, event):
        job = next(j for j in self.jobs if j["id"] == job_id)
        if event == "cancel":
            if job["status"] in ("CANCELLED", "RETAINED_FIXTURE", "FAILED"):
                raise ReviewError("The selected review attempt is already terminal.")
            job["status"] = "CANCEL_REQUESTED"
        elif event == "terminal":
            if job["status"] != "CANCEL_REQUESTED":
                raise ReviewError("A terminal cancel receipt is only valid after a request.")
            job["status"] = "CANCELLED"
        elif event == "disconnect":
            job["connected"] = False
        elif event == "reconnect":
            job["connected"] = True
        elif event in ("running", "failed"):
            if job["status"] in ("CANCELLED", "RETAINED_FIXTURE", "FAILED"):
                raise ReviewError("A terminal attempt cannot restart. Create a new attempt.")
            job["status"] = "RUNNING_FIXTURE" if event == "running" else "FAILED"
        elif event == "result":
            if job["result"]:
                return job
            result_id = token("review-result")
            owner=self.doc(job["source"]["id"])["owner"]
            input_payload=self.frozen[job["input"]]["payload"]
            family=input_payload.get("family","")
            if not (owner=="native_pre" or (owner=="Simulation" and family not in ("Thermal","Thermoelastic"))):
                raise ReviewError("No retained result fixture is provided for this input type. The attempt remains unevaluated.")
            geometry=clone(input_payload) if owner=="native_pre" else self.resolve(input_payload["model_ref"])[1]
            self.results[result_id] = {"id": result_id, "synthetic": True, "kind":"structural",
                "geometry":geometry,
                "source": clone(job["source"]), "input": job["input"],
                "attempt": job["attempt"], "time": .04, "status": "RETAINED_FIXTURE",
                "metrics": {"displacement": .31, "mass": .42, "clearance": .12},
                "times":[0,.01,.02,.04],"fields":structural_fields(.31)}
            job["result"] = result_id
            # A late retained fixture belongs to the original cancelled attempt.
            if job["status"] not in ("CANCELLED", "CANCEL_REQUESTED"):
                job["status"] = "RETAINED_FIXTURE"
        else:
            raise ReviewError("Unknown review event.")
        job["log"].append("Synthetic review event: " + event)
        return job

    def prepare_adoption(self, candidate_id):
        candidate = next(c for c in self.candidates if c["id"] == candidate_id)
        if candidate["status"] != "Retained fixture":
            raise ReviewError("Only a retained feasible review candidate can be proposed.")
        group_id = token("review-adoption")
        group = {"id": group_id, "candidate": candidate_id, "status": "PROPOSAL",
                 "result": candidate["result_ref"], "source_plan": clone(candidate["plan_ref"]),
                 "receipt": None, "owners": {}}
        for key, field in (("cad", "thickness"), ("material", "mu")):
            doc = self.doc(key)
            group["owners"][key] = {
                "field": field, "candidate": candidate[field],
                "proposal_base_revision": 12 if key == "cad" else 17,
                "expected_revision": doc["revision"], "expected_generation": doc["generation"],
                "before": doc["saved"][field], "status": "PENDING", "saved_receipt": None}
        self.groups[group_id] = group
        return group

    def apply_owner(self, group_id, key):
        group, doc = self.groups[group_id], self.doc(key)
        if group["status"]=="CANCELLED":
            raise ReviewError("This proposal was cancelled. Prepare a new proposal explicitly.")
        row = group["owners"][key]
        if row["status"] in ("APPLIED", "SAVED"):
            return row
        if doc["revision"] != row["expected_revision"] or doc["generation"] != row["expected_generation"]:
            raise ReviewError("The target changed. Inspect and prepare a fresh proposal; current data is unchanged.")
        if doc["dirty"]:
            raise ReviewError("Save or undo this owner's local edits before applying a candidate.")
        payload = clone(doc["draft"])
        payload[row["field"]] = row["candidate"]
        self.change(key, payload, "Apply " + group["candidate"])
        row["applied_hash"] = digest(self.doc(key)["draft"])
        row["status"] = "APPLIED"
        group["status"] = "PARTIAL"
        return row

    def save_adoption_owner(self, group_id, key, path=None, fail=False):
        group, doc = self.groups[group_id], self.doc(key)
        if group["status"]=="CANCELLED":
            raise ReviewError("This proposal was cancelled. Saved owners are retained.")
        row = group["owners"][key]
        if row["status"] == "SAVED":
            return clone(row["saved_receipt"])
        if row["status"] != "APPLIED":
            raise ReviewError("Apply this owner explicitly before saving it.")
        if digest(doc["draft"]) != row["applied_hash"]:
            raise ReviewError("The applied draft changed. Review the candidate again.")
        receipt = self.save_document(key, path, fail)
        row["saved_receipt"] = receipt
        row["status"] = "SAVED"
        return receipt

    def publish_group(self, group_id):
        group = self.groups[group_id]
        if group["status"]=="CANCELLED":
            raise ReviewError("A cancelled proposal cannot be published.")
        if group["receipt"]:
            return clone(group["receipt"])
        if not all(r["status"] == "SAVED" for r in group["owners"].values()):
            raise ReviewError("Save each applied owner. A partial result is not a published group.")
        for key, row in group["owners"].items():
            doc, receipt = self.doc(key), row["saved_receipt"]
            if doc["dirty"] or doc["revision"] != receipt["revision"] or digest(doc["saved"]) != receipt["payload_hash"]:
                raise ReviewError("A target changed after its save. Re-inspect the group.")
            try:
                disk=json.loads(Path(receipt["path"]).read_text(encoding="utf-8"))["document"]
                if disk["id"]!=receipt["id"] or disk["revision"]!=receipt["revision"] or digest(disk["saved"])!=receipt["payload_hash"]:
                    raise ReviewError("A saved target changed outside this window. Re-inspect the group.")
            except (OSError,ValueError,KeyError) as error:
                raise ReviewError("A saved target cannot be verified. Re-open its file before publication.") from error
        receipt = {"group": group_id, "candidate": group["candidate"],
                   "source_plan": clone(group["source_plan"]), "result": group["result"],
                   "owners": {k: clone(v["saved_receipt"]) for k, v in group["owners"].items()},
                   "mode": "UI_REPLAY_ONLY"}
        atomic_json(self.workspace / (group_id + ".json"), receipt)
        group["receipt"], group["status"] = receipt, "PUBLISHED"
        return clone(receipt)

    def cancel_adoption(self, group_id):
        group = self.groups[group_id]
        if group["receipt"]:
            raise ReviewError("This group is already published. Open its saved receipt.")
        group["status"] = "CANCELLED"
        # Already-applied drafts and already-saved revisions remain explicitly visible.

    def mark_dependency_missing(self, key="material"):
        doc = self.doc(key)
        if doc["revision"] != 19:
            raise ReviewError("Use the saved Material revision 19 scenario, or finish the p19 save first.")
        dep = doc["saved"]["dependencies"][0]
        dep["missing"] = True
        doc["draft"]["dependencies"][0]["missing"] = True
        for item in doc["history"]:
            if item["revision"] == 19:
                item["payload"]["dependencies"][0]["missing"] = True

    def repair_dependency(self, key, dep_id, candidate_path, changed_branch=False):
        doc = self.doc(key)
        dep = next(d for d in doc["saved"]["dependencies"] if d["id"] == dep_id)
        candidate_path = Path(candidate_path)
        checksum = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        if checksum == dep["sha256"]:
            self.relocations[dep_id] = {"path": str(candidate_path), "sha256": checksum,
                                       "document": doc["id"], "revision": doc["revision"]}
            return {"kind": "IDENTICAL_REPAIR", "id": doc["id"], "revision": doc["revision"]}
        if not changed_branch:
            raise ReviewError("Content changed. Original revision is preserved; create a separate branch.")
        new_doc = clone(doc)
        new_doc["key"] = token("material-branch")
        new_doc["id"] = token("MAT")
        new_doc["revision"], new_doc["file"], new_doc["history"] = 0, None, []
        new_doc["draft"]["dependencies"][0].update(sha256=checksum, missing=False)
        new_doc["draft"]["branch_of"] = {"id": doc["id"], "revision": doc["revision"]}
        new_doc["dirty"], new_doc["undo"], new_doc["redo"] = True, [], []
        self.documents[new_doc["key"]] = new_doc
        self.relocations[new_doc["id"] + "/" + dep_id] = {"path": str(candidate_path), "sha256": checksum}
        return {"kind": "CHANGED_CONTENT_BRANCH", "key": new_doc["key"], "id": new_doc["id"]}

    def append_reply(self, text, topic, reply_to=None, key="expert", evidence=None):
        if not text.strip():
            raise ReviewError("Write a reply first.")
        payload = clone(self.doc(key)["draft"])
        turn = {"id": token("user-turn"), "role": "사용자", "actual": True,
                "text": text.strip(), "topic": topic, "reply_to": reply_to, "evidence": clone(evidence or [])}
        payload["turns"].append(turn)
        payload["pending_text"] = ""
        payload["reply_to"] = None
        payload["pending_evidence"] = []
        self.change(key, payload, "Save user reply")
        return turn

    def material_repair_scenario(self):
        doc = self.doc("material")
        doc["revision"] = 19
        doc["saved"]["mu"] = .862
        doc["saved"]["adoption"]={"candidate":"c017","fit_source":{"id":"MAT-01","revision":17},
                                  "plan":{"id":"N-FIT","revision":8},"result":"fixture-result-c017"}
        doc["draft"] = clone(doc["saved"])
        doc["history"].append({"revision": 19, "payload": clone(doc["saved"]), "source": "FIXTURE"})
        self.mark_dependency_missing()

    def dump(self):
        return {"format": FORMAT, "kind": "session", "documents": self.documents,
                "jobs": self.jobs, "frozen": self.frozen, "results": self.results,
                "candidates": self.candidates, "groups": self.groups,
                "relocations": self.relocations, "selected": self.selected,
                "paths": self.paths, "events": self.events,
                "qualification": "UNKNOWN", "release": "NOT_RELEASED",
                "F05": {"value": 3.32295e-6, "tolerance": 1e-6, "verdict": "FAIL"}}

    def save_session(self, path):
        atomic_json(Path(path), self.dump())

    @classmethod
    def open_session(cls, path):
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("format") != FORMAT or raw.get("kind") != "session":
            raise ReviewError("Choose a UX review session file.")
        session = cls(path.parent)
        for field in ("documents", "jobs", "frozen", "results", "candidates", "groups",
                      "relocations", "selected", "paths", "events"):
            setattr(session, field, clone(raw[field]))
        return session

    def open_document(self, path):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("format") != FORMAT or raw.get("kind") != "document":
            raise ReviewError("Choose a UX review document file.")
        doc = raw["document"]
        key = doc["key"]
        if key in self.documents and self.documents[key]["dirty"]:
            raise ReviewError("An unsaved document is open. Save or undo it before reopening.")
        doc["file"] = str(Path(path))
        attachments = raw.get("attachments", {})
        result = attachments.get("result")
        if result:
            if result["id"] != doc["draft"].get("result") or not result.get("synthetic"):
                raise ReviewError("The attached result does not match this synthetic review document.")
            if result["id"] in self.results and self.results[result["id"]] != result:
                raise ReviewError("A different result has this identity. Open the document in a separate review session.")
            self.results[result["id"]] = clone(result)
            job = attachments.get("job")
            if job and not any(j["id"] == job["id"] for j in self.jobs):self.jobs.append(clone(job))
            frozen = attachments.get("input")
            if frozen:self.frozen[frozen["id"]] = clone(frozen)
        self.documents[key] = doc
        return key
