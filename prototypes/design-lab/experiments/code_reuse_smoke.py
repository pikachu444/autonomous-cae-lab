"""Small local integration probe for planning evidence; not product code."""
from pathlib import Path
import json

from caelab.evaluation import evaluate, read_result, run

root = Path(__file__).resolve().parent / "code-reuse-smoke"
root.mkdir(exist_ok=True)
csv = root / "시험_힘.csv"
csv.write_text("시간,하중\n0,0\n0.1,10\n0.2,20\n", encoding="utf-8")
table = evaluate("files.table", {
    "path": str(csv),
    "delimiter": ",",
    "columns": {
        "force": {
            "column": "하중", "unit": "N", "component": "z", "location": "support",
            "axis": {"column": "시간", "name": "time", "unit": "s"},
        }
    },
})
material_settings = {
    "model": "linear_elastic",
    "time": [0.0, 1.0],
    "deformation_gradient": [
        [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        [[1.001, 0, 0], [0, 1, 0], [0, 0, 1]],
    ],
    "stress_unit": "MPa",
    "parameters": {"E": 1000.0, "nu": 0.25},
}
material = run("material.felupe", material_settings, output=root / "material-result")
selected = read_result(root / "material-result", selection={"responses": ["stress_xx"]})
print(json.dumps({
    "table_status": table["execution_status"],
    "table_force": table["responses"]["force"]["value"].tolist(),
    "table_unit": table["responses"]["force"]["unit"],
    "material_status": material["execution_status"],
    "stress_xx": selected["responses"]["stress_xx"]["value"],
    "stress_measure": selected["responses"]["stress_xx"]["measure"],
    "result_file": str(root / "material-result" / "result.json"),
}, ensure_ascii=False))
