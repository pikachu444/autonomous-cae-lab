"""Audit retained Code_Aster REAC_NODA free versus restrained DOFs.

Read-only with respect to native runs. Uses the saved native-to-source map and
declared support components; full-precision summation does not alter acceptance.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _audit(level: Path) -> dict:
    expected = json.loads((level / "expected_mesh.json").read_text(encoding="utf-8"))
    native = json.loads((level / "native_mesh_checks.json").read_text(encoding="utf-8"))
    table = json.loads((level / "reac_noda.table.json").read_text(encoding="utf-8"))
    node_map = native["source_node_ids_by_native_index"]
    supports = {row["node_id"]: set(row["components"]) for row in expected["supports"]}
    if len(table["NOEUD"]) != len(node_map) or len(set(table["NOEUD"])) != len(node_map):
        raise ValueError("Native reaction rows are incomplete")
    rows = {}
    for i, label in enumerate(table["NOEUD"]):
        node = node_map[int(label) - 1]
        rows[node] = [table[name][i] for name in ("DX", "DY", "DZ")]
    result = {}
    for axis, name in enumerate(("x", "y", "z"), 1):
        free = [values[axis - 1] for node, values in rows.items()
                if axis not in supports.get(node, set())]
        fixed = [values[axis - 1] for node, values in rows.items()
                 if axis in supports.get(node, set())]
        if not all(math.isfinite(value) for value in (*free, *fixed)):
            raise ValueError("Nonfinite native reaction")
        result[name] = {"free_sum_n": math.fsum(free), "restrained_sum_n": math.fsum(fixed),
                        "all_sum_n": math.fsum((*free, *fixed)),
                        "max_abs_free_n": max(map(abs, free), default=0.),
                        "free_count": len(free), "restrained_count": len(fixed)}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError("Use a fresh audit output")
    result = {}
    for name in args.run:
        root = Path(name).resolve(strict=True)
        result[str(root)] = {level.name: _audit(level) for level in sorted(root.glob("level_*"))
                             if (level / "reac_noda.table.json").is_file()}
    output.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "runs": list(result)}, allow_nan=False))


if __name__ == "__main__":
    main()
