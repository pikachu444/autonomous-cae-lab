"""One fresh native prepared-resource wall-clock cost and A/B/A reuse probe."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
from time import perf_counter

from caelab.adapters.native_evaluation import NativeEvaluationFactory
from caelab.storage import save_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    settings = {"material": {"youngs_modulus_mpa": 200., "poisson_ratio": .25},
                "temperature_k": 293.15,
                "history": [{"time_s": 0., "strain": [0.] * 6},
                            {"time_s": 1., "strain": [.001, 0., 0., .0005, 0., 0.]}]}
    factory = NativeEvaluationFactory("material.mfront.prepared", output)
    begin = perf_counter()
    with factory.prepare(settings) as model:
        prepared_seconds = perf_counter() - begin
        rows = []
        for values in ({"youngs_modulus_mpa": 200., "poisson_ratio": .25},
                       {"youngs_modulus_mpa": 300., "poisson_ratio": .3},
                       {"youngs_modulus_mpa": 200., "poisson_ratio": .25}):
            started = perf_counter()
            result = model.evaluate(values)
            rows.append({"candidate_id": result["diagnostics"]["candidate_id"],
                         "elapsed_seconds": perf_counter() - started,
                         "xx_mpa": result["responses"]["stress_xx"]["value"][-1],
                         "xy_mpa": result["responses"]["stress_xy"]["value"][-1]})
    if rows[0]["xx_mpa"] != rows[2]["xx_mpa"] or rows[0]["xy_mpa"] != rows[2]["xy_mpa"]:
        raise AssertionError("Prepared A/B/A material state was not reset")
    receipt = {"prepare_wall_seconds": prepared_seconds,
               "candidate_wall_seconds": [row["elapsed_seconds"] for row in rows],
               "close_included_total_wall_seconds": perf_counter() - begin,
               "rows": rows,
               "rusage_children_maxrss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
               "qualification": "UNKNOWN; library is operator supplied"}
    save_json(output / "cost_receipt.json", receipt)
    print(json.dumps(receipt, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
