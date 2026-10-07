"""Isolated Fz Code_Aster accuracy probe; never edits the product worker.

The same mesh, material, loads, essential supports and field extraction are
retained. Only the constraint representation and linear solution method vary.
GCPC plus double-precision LDLT preconditioning targets a tighter linear
residual than the direct-MUMPS default; it is not an acceptance-limit change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import caelab.adapters.structural_family_codeaster as adapter_module
from caelab.adapters.structural_family_codeaster import StructuralFamilyCodeAsterAdapter
from plugins.structural_families.reference import specification


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--method", choices=("gcpc", "mumps-refined"), default="gcpc")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    source_folder = output.with_name(output.name + "-probe-source")
    worker_copy = source_folder / "structural_family_codeaster_worker.py"
    if output.exists() or source_folder.exists():
        raise FileExistsError("Probe output and worker copy must both be new")
    source = adapter_module.WORKER.read_text(encoding="utf-8")
    solver = ('SOLVEUR=_F(METHODE="GCPC", PRE_COND="LDLT_DP", RESI_RELA=1e-12, NMAX_ITER=1000))'
              if args.method == 'gcpc' else
              'SOLVEUR=_F(METHODE="MUMPS", POSTTRAITEMENTS="FORCE", RESI_RELA=1e-6))')
    replacements = (
        ("AFFE_CHAR_MECA, AFFE_MATERIAU", "AFFE_CHAR_MECA, AFFE_CHAR_CINE, AFFE_MATERIAU"),
        ("    load = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=imposed, FORCE_NODALE=forces)",
         "    support = AFFE_CHAR_CINE(MODELE=model, MECA_IMPO=imposed)\n"
         "    load = AFFE_CHAR_MECA(MODELE=model, FORCE_NODALE=forces)"),
        ('result = MECA_STATIQUE(MODELE=model, CHAM_MATER=material_field, EXCIT=_F(CHARGE=load), SOLVEUR=_F(METHODE="MUMPS"))',
         'result = MECA_STATIQUE(MODELE=model, CHAM_MATER=material_field,\n'
         '                          EXCIT=(_F(CHARGE=load), _F(CHARGE=support)),\n'
         '                          ' + solver),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise RuntimeError(f"Expected exactly one worker anchor: {before}")
        source = source.replace(before, after)
    source_folder.mkdir(parents=True, exist_ok=False)
    source = source.replace('"method": "MUMPS", "measured_linear_residual"',
                            '"method": ' + json.dumps(args.method) + ', "measured_linear_residual"')
    worker_copy.write_text(source, encoding="utf-8")
    adapter_module.WORKER = worker_copy
    adapter_module._SOURCE_PATHS["structural_family_codeaster_worker.py"] = worker_copy
    result = StructuralFamilyCodeAsterAdapter().solve(output, specification("ansys_vmd1_regular", "Fz"))
    print(json.dumps({"output": str(output), "worker_copy": str(worker_copy), "probe_method": args.method,
                      "status": result["status"], "solver_status": result["solver_status"],
                      "metrics": result["metrics"], "checks": result["checks"]}, allow_nan=False))


if __name__ == "__main__":
    main()
