"""Run bounded local native histories and independently select retained channels.

This command creates a fresh output root; it never modifies existing runs.
Each result remains the adapter's original input, native files and outcome.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from caelab.adapters.native_responses import catalog_native_responses, read_native_response
from caelab.storage import save_json


def run(output):
    from caelab.adapters.fenicsx_transient import FenicsxTransientPDEAdapter
    from caelab.adapters.openradioss import OpenRadiossAdapter
    from plugins.pde_transient.reference import manufactured_settings
    from scripts.verify_openradioss import specification

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    pde_settings = manufactured_settings()
    pde = FenicsxTransientPDEAdapter()
    pde_path = output / "pde"
    pde_outcome = pde.solve(pde_path, pde_settings)
    pde_catalog = catalog_native_responses(pde.backend, pde_outcome, pde_path)
    pde_name = "pde.study2.u"
    pde_node = pde_catalog[pde_name]["node_ids"][len(pde_catalog[pde_name]["node_ids"]) // 2]
    pde_selected = read_native_response(pde.backend, pde_outcome, pde_path, f"{pde_name}@{pde_node}")

    explicit_settings = specification()
    # The adapter's unmodified reference schedule has a fully retained native
    # terminal sample. A short 0.002 s probe is kept as a separate failed run.
    explicit = OpenRadiossAdapter()
    explicit_path = output / "explicit"
    explicit_outcome = explicit.solve(explicit_path, explicit_settings)
    explicit_catalog = catalog_native_responses(explicit.backend, explicit_outcome, explicit_path)
    explicit_selected = read_native_response(explicit.backend, explicit_outcome, explicit_path, "radioss-center-vz")

    receipt = {
        "pde": {"status": pde_outcome["status"], "solver_status": pde_outcome["solver_status"],
                "converged": pde_outcome["converged"], "versions": pde_outcome["provenance"]["versions"],
                "catalog": sorted(pde_catalog), "selected": pde_selected},
        "explicit": {"status": explicit_outcome["status"], "solver_status": explicit_outcome["solver_status"],
                     "converged": explicit_outcome["converged"], "versions": explicit_outcome["provenance"]["versions"],
                     "catalog": sorted(explicit_catalog), "selected": explicit_selected},
    }
    save_json(output / "selection_receipt.json", receipt)
    print(json.dumps({"output": str(output), "pde_status": pde_outcome["status"],
                      "pde_samples": len(pde_selected["value"]), "pde_selector": f"{pde_name}@{pde_node}",
                      "explicit_status": explicit_outcome["status"],
                      "explicit_samples": len(explicit_selected["value"]),
                      "explicit_selector": "radioss-center-vz"}, allow_nan=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
