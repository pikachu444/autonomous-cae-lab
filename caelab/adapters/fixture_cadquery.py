"""Reuse the exact pinned fixture implementation; keep its rules outside Core."""

import math
from pathlib import Path
import subprocess
import sys
from typing import Any

from ..contracts import Candidate, Outcome


UPSTREAM = Path(__file__).resolve().parents[2] / "plugins/fixture_design/upstream"


def _upstream():
    if not (UPSTREAM / "fixturelab/model_cad.py").is_file():
        raise RuntimeError("Fixture submodule missing: git submodule update --init")
    if str(UPSTREAM) not in sys.path:
        sys.path.insert(0, str(UPSTREAM))
    from fixturelab import model_cad
    return model_cad


def _signature(shape: Any) -> tuple[float, ...]:
    b = shape.BoundingBox()
    c = shape.Center()
    return (shape.Volume(), shape.Area(), b.xmin, b.xmax, b.ymin, b.ymax,
            b.zmin, b.zmax, c.x, c.y, c.z)


def _shape_difference(first: Any, second: Any) -> float:
    return first.cut(second).Volume() + second.cut(first).Volume()


def _shape_from_build(model: Any, values: dict[str, float]):
    built = model.build(values)
    if not built.success or len(built.results) != 1:
        return None
    shape = built.first_result.shape
    shape = shape.val() if hasattr(shape, "val") else shape
    return shape if shape.isValid() and len(shape.Solids()) == 1 and shape.Volume() > 0 else None


class FixtureCadQueryAdapter:
    backend = "fixture.cadquery"
    version = "1"
    domain = "fixture_design"
    physics_domain = "structural"
    analysis_type = "cad_preflight"
    default_metrics = ["cad_bounds", "cad_volume"]

    def document_id(self, model: str) -> str:
        return model + ".py"

    def discover(self, model: str) -> list[Candidate]:
        info, _, _ = _upstream().definition(model)
        return [Candidate(
            native={"backend": self.backend, "document": self.document_id(model),
                    "object": model, "path": p["name"]},
            label=p["label"], unit=p["unit"], value=p["default"],
            lower=p["min"], upper=p["max"], source_sha256=info["source_sha256"])
                for p in info["parameters"]]

    def probe_effect(self, model: str, candidate: Candidate, lower: float, upper: float) -> dict[str, Any]:
        info, cad_model, _ = _upstream().definition(model)
        name = candidate.native["path"]
        defaults = {p["name"]: p["default"] for p in info["parameters"]}
        first = _shape_from_build(cad_model, defaults)
        if first is None:
            raise ValueError("Baseline CAD model does not regenerate")
        base = _signature(first)
        for value in (min(upper, candidate.value + max(0.05, abs(candidate.value) * 0.02)),
                      max(lower, candidate.value - max(0.05, abs(candidate.value) * 0.02))):
            if value == candidate.value or not math.isfinite(value):
                continue
            second = _shape_from_build(cad_model, {**defaults, name: value})
            if second is None:
                continue
            if not second.isValid() or len(second.Solids()) != 1:
                continue
            after = _signature(second)
            changed = any(abs(a - b) > max(1e-6, 1e-7 * max(abs(a), abs(b)))
                          for a, b in zip(base, after))
            if not changed:
                # Symmetric movement of bores can preserve every gross metric.
                difference = _shape_difference(first, second)
                changed = difference > max(1e-5, 1e-7 * first.Volume())
            if changed:
                return {"status": "PASS", "method": "CAD recomputation; signature and symmetric difference",
                        "native_value": candidate.value, "probe_value": value,
                        "source_sha256": info["source_sha256"]}
        return {"status": "FAIL", "method": "CAD recomputation; signature and symmetric difference",
                "reason": "No measurable final-solid effect at safe probe values"}

    def preflight_effects(self, model: str, native_values: dict[str, float]) -> list[dict[str, Any]]:
        """Check each proposed changed value against the final BREP before export."""
        info, cad_model, _ = _upstream().definition(model)
        defaults = {p["name"]: p["default"] for p in info["parameters"]}
        proposal = {**defaults, **native_values}
        final = _shape_from_build(cad_model, proposal)
        if final is None:
            return []  # Let the upstream model report its exact relation failure.
        checks = []
        for name, value in native_values.items():
            if value == defaults[name]:
                continue
            reference = _shape_from_build(cad_model, {**proposal, name: defaults[name]})
            if reference is None:
                checks.append({"code": "geometry_effect_" + name, "status": "UNKNOWN",
                               "observed": "Counterfactual baseline is invalid; effect cannot be isolated"})
                continue
            difference = _shape_difference(final, reference)
            threshold = max(1e-5, 1e-7 * reference.Volume())
            checks.append({"code": "geometry_effect_" + name,
                           "status": "PASS" if difference > threshold else "FAIL",
                           "observed": difference, "limit": threshold})
        return checks

    def regenerate(self, model: str, native_values: dict[str, float], output: Path) -> Outcome:
        result = _upstream().execute(model, native_values, output)
        checks = [*result["checks"], *result["cad_checks"]]
        metrics: dict[str, dict[str, Any]] = {}
        if result["cad_generated"]:
            part = result["bom"][0]
            metrics = {
                "cad_volume": {"value": part["volume_mm3"], "unit": "mm^3", "valid": True},
                "cad_bounds": {"value": part["bounds_mm"], "unit": "mm", "valid": True},
            }
        return Outcome(
            decision=result["decision"], checks=checks, generated=result["cad_generated"], metrics=metrics,
            pending_validations=["machine_interface", "static_strength", "physical_load_test",
                                 "fatigue_durability"],
            native_revision=result["source_sha256"], source_sha256=result["source_sha256"],
            raw_result="cad/result.json")

    @staticmethod
    def source_commit() -> str:
        try:
            return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=UPSTREAM,
                                           text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"
