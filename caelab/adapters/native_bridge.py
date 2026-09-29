"""Process isolation for the upstream FreeCAD module's global design directory."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from .fixture_cadquery import UPSTREAM
from .fixture_cadquery import _shape_difference

sys.path.insert(0, str(UPSTREAM))
from fixturelab import native_cad


def _preflight(model, native_values):
    """Compare each changed native value with its own counterfactual BREP.

    Temporary STEP exports are discarded; a failed check prevents the real
    experiment export. The upstream worker still owns its domain rules.
    """
    import cadquery as cq

    info = native_cad.inspect(model)
    parameters = {p["key"]: p for p in info["parameters"]}
    if set(native_values) - set(parameters):
        raise ValueError("CAD dimension is not registered in the editable FCStd")
    changed = {key: value for key, value in native_values.items()
               if abs(value - parameters[key]["value"]) > 1e-9}
    if not changed:
        return []
    proposal = {parameters[key]["name"]: value for key, value in changed.items()}
    source = native_cad._path(model)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copied = root / "preflight.FCStd"
        shutil.copy2(source, copied)
        proposal_dir = root / "proposal"
        result = native_cad._run({"action": "generate", "document": str(copied),
                                  "values": proposal, "output": str(proposal_dir)})
        if result["decision"] == "REJECTED":
            # The actual regenerate call records its detailed domain failure.
            return []
        shape = cq.importers.importStep(str(proposal_dir / "native.step")).val()
        checks = []
        for index, (key, value) in enumerate(changed.items()):
            baseline = dict(proposal)
            baseline[parameters[key]["name"]] = parameters[key]["value"]
            counter_dir = root / f"counter_{index}"
            counter = native_cad._run({"action": "generate", "document": str(copied),
                                       "values": baseline, "output": str(counter_dir)})
            if counter["decision"] == "REJECTED":
                checks.append({"code": "geometry_effect_" + key, "status": "UNKNOWN",
                               "observed": "Counterfactual is domain-invalid; effect cannot be isolated"})
                continue
            reference = cq.importers.importStep(str(counter_dir / "native.step")).val()
            difference = _shape_difference(shape, reference)
            threshold = max(1e-5, 1e-7 * reference.Volume())
            checks.append({"code": "geometry_effect_" + key,
                           "status": "PASS" if difference > threshold else "FAIL",
                           "observed": difference, "limit": threshold})
        return checks


def main():
    request = json.load(sys.stdin)
    store = Path(request["store"])
    native_cad.DESIGNS = store / "native_designs"
    action = request["action"]
    if action == "new":
        answer = native_cad.create_sample(request["template"])
    elif action == "import":
        answer = native_cad.import_document(Path(request["path"]).read_bytes())
    elif action == "discover":
        answer = native_cad.inspect(request["model"])
    elif action == "select_final":
        answer = native_cad.select_final(request["model"], request["final"])
    elif action == "probe":
        source = native_cad._path(request["model"])
        registered = {p["key"]: p for p in native_cad.inspect(request["model"])["parameters"]}
        if request["target"] in registered:
            p = registered[request["target"]]
            step = max(.05, abs(p["value"]) * .02)
            probe = (p["value"] + step if p["value"] + step <= request["upper"]
                     else p["value"] - step)
            if probe < request["lower"] or abs(probe - p["value"]) < 1e-9:
                raise ValueError("No room to test this CAD dimension")
            checks = _preflight(request["model"], {p["key"]: probe})
            if not checks or checks[0]["status"] != "PASS":
                raise ValueError("Registered CAD dimension has no verified measurable effect")
            answer = {"status": "PASS", "method": "named FreeCAD dimension; final-solid counterfactual"}
        else:
            with tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "probe.FCStd"
                shutil.copy2(source, copied)
                native_cad._run({"action": "register", "document": str(copied),
                                 "target": request["target"], "name": "caelab_probe_" + uuid.uuid4().hex[:12],
                                 "min": request["lower"], "max": request["upper"],
                                 "label": "CAE-Lab geometry probe"})
            answer = {"status": "PASS", "method": "upstream FreeCAD final-solid perturbation"}
    elif action == "preflight":
        answer = {"checks": _preflight(request["model"], request["values"])}
    elif action == "bind":
        inspect = native_cad.inspect(request["model"])
        matches = [p for p in inspect["parameters"] if p["key"] == request["target"]]
        if matches:
            if not matches[0]["min"] <= request["lower"] <= request["upper"] <= matches[0]["max"]:
                raise ValueError("Requested bounds exceed the existing FCStd parameter definition")
        else:
            native_cad.register(request["model"], request["target"], request["parameter_id"],
                                request["lower"], request["upper"], request["display_name"])
        answer = {"bound": True}
    elif action == "regenerate":
        inspect = native_cad.inspect(request["model"])
        mapping = {p["key"]: p["name"] for p in inspect["parameters"]}
        values = {}
        for native_key, value in request["values"].items():
            if native_key not in mapping:
                raise ValueError("CAD dimension is not registered in the editable FCStd")
            values[mapping[native_key]] = value
        answer = native_cad.execute(request["model"], values, Path(request["output"]))
    else:
        raise ValueError("Unknown native bridge action")
    if action != "regenerate":
        design = answer["design"] if action in ("new", "import") else request["model"]
        source = native_cad._path(design)
        answer["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    print(json.dumps(answer, ensure_ascii=False))


if __name__ == "__main__":
    main()
