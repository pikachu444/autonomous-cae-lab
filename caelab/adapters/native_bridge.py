"""Process isolation for the upstream FreeCAD module's global design directory."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

from .fixture_cadquery import UPSTREAM
from .fixture_cadquery import _shape_difference
from .freecad_parameters import unique_paths

sys.path.insert(0, str(UPSTREAM))
from fixturelab import native_cad


def _parameter_run(request):
    """The pinned transport hardcodes its worker; keep this worker path trusted."""
    command = os.environ.get("FREECAD_CMD") or shutil.which("freecadcmd") or shutil.which("FreeCADCmd")
    if not command:
        raise RuntimeError("FreeCADCmd is required; set FREECAD_CMD to its executable")
    worker = Path(__file__).resolve().with_name("freecad_parameter_worker.py")
    with tempfile.TemporaryDirectory() as directory:
        source, result = Path(directory) / "request.json", Path(directory) / "result.json"
        source.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        env = {**os.environ, "FIXTURE_FREECAD_REQUEST": str(source), "FIXTURE_FREECAD_RESULT": str(result),
               "CAELAB_FREECAD_PARAMETER_WORKER": str(worker)}
        run = subprocess.run([command, str(worker)], cwd=UPSTREAM, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=150)
        if not result.is_file():
            raise RuntimeError("FreeCADCmd produced no result: " + (run.stderr or run.stdout)[-1000:])
        answer = json.loads(result.read_text(encoding="utf-8"))
        if not isinstance(answer, dict) or not isinstance(answer.get("ok"), bool):
            raise RuntimeError("FreeCADCmd produced an invalid worker result")
        if not answer["ok"]:
            raise ValueError("FreeCAD: " + str(answer.get("error", "Worker refused the document")))
        if run.returncode:
            raise RuntimeError("FreeCADCmd returned an error")
        if not isinstance(answer.get("result"), dict):
            raise RuntimeError("FreeCADCmd produced an invalid native CAD result")
        return answer["result"]


def _inspect(model):
    source = native_cad._path(model)
    info = _parameter_run({"action": "inspect", "document": str(source)})
    if info["source_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest():
        raise ValueError("Native CAD source changed after inspection; rediscover the document")
    unique_paths([*info["parameters"], *info["candidates"]])
    return {"design": model, **info, "preview": f"/designs/{model}/preview.png",
            "surface": f"/designs/{model}/surface.json" if (source.parent / "surface.json").exists() else None,
            "editable": f"/designs/{model}/editable.FCStd"}


def _preflight(model, native_values, info=None):
    """Compare each changed native value with its own counterfactual BREP.

    Temporary STEP exports are discarded; a failed check prevents the real
    experiment export. The upstream worker still owns its domain rules.
    """
    import cadquery as cq

    info = info if info is not None else native_cad.inspect(model)
    unique_paths(info["parameters"])
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
        answer = _inspect(answer["design"])
    elif action == "import":
        # Validate current registered identities before the reused importer
        # generates a baseline from the supplied native document.
        inspected = _parameter_run({"action": "inspect", "document": request["path"]})
        payload = Path(request["path"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != inspected["source_sha256"]:
            raise ValueError("NATIVE_SOURCE_CHANGED: Native CAD input changed after inspection")
        answer = native_cad.import_document(payload)
        answer = _inspect(answer["design"])
    elif action == "discover":
        answer = _inspect(request["model"])
    elif action == "select_final":
        _inspect(request["model"])
        answer = native_cad.select_final(request["model"], request["final"])
        answer = _inspect(request["model"])
    elif action == "probe":
        source = native_cad._path(request["model"])
        inspect = _inspect(request["model"])
        registered = {p["key"]: p for p in inspect["parameters"]}
        if request["target"] in registered:
            p = registered[request["target"]]
            step = max(.05, abs(p["value"]) * .02)
            probe = (p["value"] + step if p["value"] + step <= request["upper"]
                     else p["value"] - step)
            if probe < request["lower"] or abs(probe - p["value"]) < 1e-9:
                raise ValueError("No room to test this CAD dimension")
            checks = _preflight(request["model"], {p["key"]: probe}, inspect)
            if not checks or checks[0]["status"] != "PASS":
                raise ValueError("Registered CAD dimension has no verified measurable effect")
            answer = {"status": "PASS", "method": "named FreeCAD dimension; final-solid counterfactual"}
        else:
            with tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / "probe.FCStd"
                shutil.copy2(source, copied)
                _parameter_run({"action": "register", "document": str(copied),
                                 "target": request["target"], "name": "caelab_probe_" + uuid.uuid4().hex[:12],
                                 "min": request["lower"], "max": request["upper"],
                                 "label": "CAE-Lab geometry probe", "source_sha256": request.get("source_sha256")})
            answer = {"status": "PASS", "method": "upstream FreeCAD final-solid perturbation"}
    elif action == "preflight":
        answer = {"checks": _preflight(request["model"], request["values"], _inspect(request["model"]))}
    elif action == "bind":
        inspect = _inspect(request["model"])
        matches = [p for p in inspect["parameters"] if p["key"] == request["target"]]
        if matches:
            if not matches[0]["min"] <= request["lower"] <= request["upper"] <= matches[0]["max"]:
                raise ValueError("Requested bounds exceed the existing FCStd parameter definition")
        else:
            _parameter_run({"action": "register", "document": str(native_cad._path(request["model"])),
                            "target": request["target"], "name": request["parameter_id"],
                            "min": request["lower"], "max": request["upper"], "label": request["display_name"],
                            "source_sha256": request.get("source_sha256")})
        answer = {"bound": True}
    elif action == "regenerate":
        inspect = _inspect(request["model"])
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
        source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        if "source_sha256" in answer and answer["source_sha256"] != source_sha256:
            raise ValueError("Native CAD source changed before the adapter result")
        answer["source_sha256"] = source_sha256
    print(json.dumps(answer, ensure_ascii=False))


if __name__ == "__main__":
    main()
