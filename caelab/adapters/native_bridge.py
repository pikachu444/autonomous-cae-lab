"""Process isolation for the upstream FreeCAD module's global design directory."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from .fixture_cadquery import UPSTREAM

sys.path.insert(0, str(UPSTREAM))
from fixturelab import native_cad


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
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "probe.FCStd"
            shutil.copy2(source, copied)
            native_cad._run({"action": "register", "document": str(copied),
                             "target": request["target"], "name": "caelab_probe_" + uuid.uuid4().hex[:12],
                             "min": request["lower"], "max": request["upper"],
                             "label": "CAE-Lab geometry probe"})
        answer = {"status": "PASS", "method": "upstream FreeCAD final-solid perturbation"}
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
