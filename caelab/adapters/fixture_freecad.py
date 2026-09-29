"""Editable FCStd adapter wrapping the tested upstream FreeCAD worker."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from ..contracts import Candidate, Outcome, CapabilityUnavailable
from .fixture_cadquery import FixtureCadQueryAdapter


class FixtureFreeCADAdapter:
    backend = "fixture.freecad"
    version = "1"
    domain = "fixture_design"
    physics_domain = "structural"
    analysis_type = "cad_preflight"
    default_metrics = ["cad_bounds", "cad_volume"]

    def __init__(self, store: Path):
        self.store = Path(store)

    def document_id(self, model: str) -> str:
        return model

    def _call(self, action: str, **kwargs) -> dict[str, Any]:
        if not (os.environ.get("FREECAD_CMD") or shutil.which("FreeCADCmd") or shutil.which("freecadcmd")):
            raise CapabilityUnavailable("FreeCADCmd is required; set FREECAD_CMD to its executable")
        request = {"store": str(self.store), "action": action, **kwargs}
        run = subprocess.run([sys.executable, "-m", "caelab.adapters.native_bridge"],
                             input=json.dumps(request), capture_output=True, text=True,
                             cwd=Path(__file__).resolve().parents[2], timeout=180)
        if run.returncode:
            raise ValueError("FreeCAD adapter: " + (run.stderr or run.stdout)[-1500:])
        return json.loads(run.stdout)

    def create_sample(self, template: str = "roller_support") -> dict[str, Any]:
        return self._call("new", template=template)

    def import_document(self, source: Path) -> dict[str, Any]:
        return self._call("import", path=str(source.resolve()))

    def inspect_model(self, model: str) -> dict[str, Any]:
        return self._call("discover", model=model)

    def select_final(self, model: str, final: str) -> dict[str, Any]:
        return self._call("select_final", model=model, final=final)

    def discover(self, model: str) -> list[Candidate]:
        info = self._call("discover", model=model)
        registered = {p["key"]: p for p in info["parameters"]}
        candidates = [*info["candidates"], *info["parameters"]]
        return [Candidate(
            native={"backend": self.backend, "document": model,
                    "object": p["object"], "path": p["key"]},
            label=p.get("label") or p.get("dimension") or p["key"], unit="mm",
            value=p["value"], lower=registered[p["key"]]["min"] if p["key"] in registered else None,
            upper=registered[p["key"]]["max"] if p["key"] in registered else None,
            source_sha256=info["source_sha256"]) for p in candidates]

    def probe_effect(self, model: str, candidate: Candidate, lower: float, upper: float) -> dict[str, Any]:
        return self._call("probe", model=model, target=candidate.native["path"],
                          lower=lower, upper=upper)

    def bind(self, model: str, candidate: Candidate, parameter_id: str, display_name: str,
             lower: float, upper: float) -> str:
        return self._call("bind", model=model, target=candidate.native["path"],
                          parameter_id=parameter_id, display_name=display_name,
                          lower=lower, upper=upper)["source_sha256"]

    def regenerate(self, model: str, native_values: dict[str, float], output: Path) -> Outcome:
        result = self._call("regenerate", model=model, values=native_values, output=str(output))
        metrics: dict[str, dict[str, Any]] = {}
        if result["cad_generated"]:
            metrics = {
                "cad_bounds": {"value": result["bounds_mm"], "unit": "mm", "valid": True},
                "cad_volume": {"value": result["bom"][0]["volume_mm3"], "unit": "mm^3", "valid": True},
            }
        return Outcome(decision=result["decision"],
                       checks=[*result["checks"], *result["cad_checks"]],
                       generated=result["cad_generated"], metrics=metrics,
                       pending_validations=["machine_interface", "static_strength", "physical_load_test",
                                            "fatigue_durability"],
                       native_revision=result["source_sha256"],
                       source_sha256=result["source_sha256"], raw_result="cad/result.json")

    source_commit = staticmethod(FixtureCadQueryAdapter.source_commit)
