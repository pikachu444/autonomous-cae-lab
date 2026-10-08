"""Persistent MGIS Elasticity point worker over one prepared native library.

Only JSON material values and a previously validated strain history enter stdin.
Every candidate receives a fresh MaterialDataManager; state advances only within
that candidate's history. This is a workbench path, separate from the fixed
MFront/MTest benchmark and its scientific verdict.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sys


ROOT = Path("/work")
LIBRARY = ROOT / "libBehaviour.so"
sys.path.insert(0, str(ROOT))
import mfront_material_worker as helpers  # noqa: E402 - copied, retained source


def _save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evaluate(binding, behaviour, request):
    material = request["material"]
    history = request["history"]
    temperature = request["temperature_k"]
    properties = {"YoungModulus": material["youngs_modulus_mpa"], "PoissonRatio": material["poisson_ratio"]}
    external = {"Temperature": temperature}
    initial = binding.MaterialDataManager(behaviour, 1)
    for state in (initial.s0, initial.s1):
        for name, value in properties.items():
            binding.setMaterialProperty(state, name, value)
        binding.setExternalStateVariable(state, "Temperature", temperature)
        for name, _ in helpers._state_buffers(behaviour):
            getattr(state, name).reshape(-1)[:] = 0.
    baseline = helpers.snapshot(initial.s0, properties, external, 0., behaviour)
    rows = [{"time_s": history[0]["time_s"], "strain_physical": [0.] * 6,
             "stress_physical_mpa": [0.] * 6, "native_status": "INITIAL_DECLARED"}]
    for previous, entry in zip(history, history[1:]):
        dt = entry["time_s"] - previous["time_s"]
        manager = helpers.fresh_manager(binding, behaviour, {**baseline, "dt_s": dt})
        manager.s1.gradients[0, :] = helpers.kelvin(entry["strain"])
        native = helpers._integrate(binding, manager, dt)
        if native["integration_return"] != 1:
            return {"execution_status": "REJECTED", "rows": rows,
                    "native_rejection": {"time_s": entry["time_s"], **native}}
        rows.append({"time_s": entry["time_s"], "strain_physical": list(entry["strain"]),
                     "stress_physical_mpa": helpers.physical(helpers._floats(manager.s1.thermodynamic_forces)),
                     "native_status": "INTEGRATED", "integration_return": native["integration_return"]})
        binding.update(manager)
        baseline = helpers.snapshot(manager.s0, properties, external, dt, behaviour)
    return {"execution_status": "SUCCEEDED", "rows": rows}


def main():
    import mgis.behaviour as binding
    library_sha = _sha(LIBRARY)
    behaviour = binding.load(str(LIBRARY), "Elasticity", binding.Hypothesis.Tridimensional)
    names = [property_.name for property_ in behaviour.material_properties]
    if names != ["YoungModulus", "PoissonRatio"]:
        raise ValueError("Prepared behavior does not expose the two declared material coefficients")
    print(json.dumps({"ready": True, "library_sha256": library_sha, "properties": names}), flush=True)
    for line in sys.stdin:
        request = None
        try:
            request = json.loads(line)
            if request == {"command": "STOP"}:
                print('{"stopped":true}', flush=True)
                return
            identifier = request["candidate_id"]
            if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
                raise ValueError("Candidate ID must be a generated lowercase UUID")
            if set(request) != {"candidate_id", "material", "temperature_k", "history"}:
                raise ValueError("Unexpected candidate request fields")
            properties = request["material"]
            if (not isinstance(properties, dict) or set(properties) != {"youngs_modulus_mpa", "poisson_ratio"} or
                    any(type(v) not in (int, float) or not math.isfinite(v) for v in properties.values())):
                raise ValueError("Invalid material values")
            folder = ROOT / "candidates" / identifier
            folder.mkdir(parents=True, exist_ok=False)
            _save(folder / "input.json", request)
            result = _evaluate(binding, behaviour, request)
            result.update(candidate_id=identifier, library_sha256=library_sha,
                          input_sha256=_sha(folder / "input.json"))
            _save(folder / "result.json", result)
            print(json.dumps({"candidate_id": identifier, "execution_status": result["execution_status"],
                              "result_sha256": _sha(folder / "result.json")}), flush=True)
        except Exception as exc:
            print(json.dumps({"candidate_id": request.get("candidate_id") if isinstance(request, dict) else None,
                              "execution_status": "FAILED", "reason": f"{type(exc).__name__}: {exc}"}), flush=True)


if __name__ == "__main__":
    main()
