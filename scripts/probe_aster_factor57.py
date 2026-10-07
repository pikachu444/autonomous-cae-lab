"""Fresh canonical Fz Code_Aster run for a controlled direct-solver probe."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from caelab.adapters.structural_family_codeaster import StructuralFamilyCodeAsterAdapter
from plugins.structural_families.reference import specification


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = StructuralFamilyCodeAsterAdapter().solve(
        Path(args.output), specification("ansys_vmd1_regular", "Fz"))
    print(json.dumps({"output": args.output, "status": result["status"],
                      "solver_status": result["solver_status"],
                      "metrics": result["metrics"], "checks": result["checks"]},
                     allow_nan=False))


if __name__ == "__main__":
    main()
