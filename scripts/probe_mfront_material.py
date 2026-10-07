"""Two real MGIS/MTest material-point histories with distinct E and nu."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from caelab.adapters.mfront_material import MFrontMaterialAdapter
from caelab.storage import save_json
from plugins.material_point.reference import FIXED_LIMITS


def settings(young, poisson, shear=False):
    initial = {"time_s": 0., "strain": [0.] * 6}
    applied = [0., 0., 0., .001, 0., 0.] if shear else [.001, 0., 0., 0., 0., 0.]
    return {"case": "isotropic_small_strain", "material": {"youngs_modulus_mpa": young, "poisson_ratio": poisson},
            "temperature_k": 293.15, "history": [initial, {"time_s": 1., "strain": applied}],
            "limits": dict(FIXED_LIMITS)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    adapter = MFrontMaterialAdapter()
    report = {}
    for label, values in (("axial", (200., .25, False)), ("shear", (300., .30, True))):
        request = settings(*values)
        output = root / label
        outcome = adapter.solve(output, request)
        report[label] = {"input": request, "status": outcome["status"],
                         "solver_status": outcome["solver_status"], "metrics": outcome["metrics"],
                         "checks": outcome["checks"], "provenance": outcome["provenance"]}
    save_json(root / "summary.json", report)
    print(json.dumps({label: {"status": row["status"], "solver_status": row["solver_status"],
                              "metrics": {name: metric["value"] for name, metric in row["metrics"].items() if metric.get("valid") and name in {"stress_history", "energy_density_history"}}}
                      for label, row in report.items()}, allow_nan=False))


if __name__ == "__main__":
    main()
