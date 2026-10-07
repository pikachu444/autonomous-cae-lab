"""Preserve actual default and finer vector PDE convergence observations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from caelab.adapters.fenicsx_vector import FenicsxVectorPDEAdapter
from caelab.storage import save_json
from plugins.pde_vector.reference import manufactured_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    adapter = FenicsxVectorPDEAdapter()
    summary = {}
    for label, counts in (("original", [8, 16, 32]), ("finer", [16, 32, 64])):
        request = manufactured_settings()
        request["mesh"]["cell_counts"] = counts
        result = adapter.solve(output / label, request)
        summary[label] = {"status": result["status"], "solver_status": result["solver_status"],
                          "metrics": result["metrics"], "checks": result["checks"],
                          "counts": counts, "raw_result": str(output / label / "result.json")}
    save_json(output / "summary.json", summary)
    print(json.dumps({label: {"status": value["status"], "metrics": value["metrics"]}
                      for label, value in summary.items()}, allow_nan=False))


if __name__ == "__main__":
    main()
