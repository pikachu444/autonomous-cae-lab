"""Actual MGIS prepared-library A->B->A and independent shear-history probe."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from caelab.evaluation import prepare
from caelab.storage import save_json


def _settings(output, shear):
    strain = [0., 0., 0., .001, 0., 0.] if shear else [.001, 0., 0., 0., 0., 0.]
    return {"output_root": str(output), "material": {"youngs_modulus_mpa": 200., "poisson_ratio": .25},
            "temperature_k": 293.15,
            "history": [{"time_s": 0., "strain": [0.] * 6}, {"time_s": 1., "strain": strain}]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    evidence = {}
    for name, component in (("axial", "stress_xx"), ("shear", "stress_xy")):
        with prepare("material.mfront.prepared", _settings(root / name, name == "shear")) as model:
            a = model.evaluate({"youngs_modulus_mpa": 200., "poisson_ratio": .25})
            b = model.evaluate({"youngs_modulus_mpa": 300., "poisson_ratio": .30})
            a_again = model.evaluate({"youngs_modulus_mpa": 200., "poisson_ratio": .25})
        assert all(row["execution_status"] == "SUCCEEDED" for row in (a, b, a_again))
        assert a["responses"][component]["value"] == a_again["responses"][component]["value"]
        assert a["responses"][component]["value"] != b["responses"][component]["value"]
        evidence[name] = {"component": component, "A": a["responses"][component],
                          "B": b["responses"][component], "A_again": a_again["responses"][component],
                          "candidate_ids": [row["diagnostics"]["candidate_id"] for row in (a, b, a_again)]}
    save_json(root / "summary.json", evidence)
    print(json.dumps({name: {"component": row["component"], "A": row["A"]["value"],
                             "B": row["B"]["value"], "A_again": row["A_again"]["value"]}
                      for name, row in evidence.items()}, allow_nan=False))


if __name__ == "__main__":
    main()
