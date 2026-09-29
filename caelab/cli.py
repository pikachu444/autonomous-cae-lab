"""Stable, small command surface for engineers and research agents."""

import argparse
import json
from pathlib import Path
import sys

from .engine import Lab


def _json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser():
    p = argparse.ArgumentParser(prog="caelab")
    p.add_argument("--store", type=Path, default=Path("runs"))
    sub = p.add_subparsers(dest="command", required=True)
    study = sub.add_parser("study")
    study_sub = study.add_subparsers(dest="action", required=True)
    create = study_sub.add_parser("create")
    for arg in ("id", "name", "question", "hypothesis", "objective"):
        create.add_argument("--" + arg, required=True)
    study_sub.add_parser("inspect").add_argument("--id", required=True)
    model = sub.add_parser("model")
    model_sub = model.add_subparsers(dest="action", required=True)
    native_new = model_sub.add_parser("native-new")
    native_new.add_argument("--template", default="roller_support")
    native_import = model_sub.add_parser("native-import")
    native_import.add_argument("--path", type=Path, required=True)
    native_final = model_sub.add_parser("native-final")
    native_final.add_argument("--model", required=True)
    native_final.add_argument("--final", required=True)
    native_inspect = model_sub.add_parser("native-inspect")
    native_inspect.add_argument("--model", required=True)
    inspect = model_sub.add_parser("inspect")
    inspect.add_argument("--backend", default="fixture.cadquery")
    inspect.add_argument("--model", required=True)
    regen = model_sub.add_parser("regenerate")
    regen.add_argument("--study", required=True)
    regen.add_argument("--experiment", required=True)
    regen.add_argument("--backend", default="fixture.cadquery")
    regen.add_argument("--model", required=True)
    regen.add_argument("--values", required=True, help="JSON mapping of research IDs to numbers")
    params = sub.add_parser("parameters")
    params_sub = params.add_subparsers(dest="action", required=True)
    discover = params_sub.add_parser("discover")
    discover.add_argument("--backend", default="fixture.cadquery")
    discover.add_argument("--model", required=True)
    listing = params_sub.add_parser("list")
    listing.add_argument("--study", required=True)
    refresh = params_sub.add_parser("refresh")
    refresh.add_argument("--study", required=True)
    refresh.add_argument("--backend", default="fixture.cadquery")
    refresh.add_argument("--model", required=True)
    register = params_sub.add_parser("register")
    register.add_argument("--study", required=True)
    register.add_argument("--backend", default="fixture.cadquery")
    register.add_argument("--model", required=True)
    register.add_argument("--native-path", required=True)
    register.add_argument("--id", required=True)
    register.add_argument("--name", required=True)
    register.add_argument("--lower", required=True, type=float)
    register.add_argument("--upper", required=True, type=float)
    register.add_argument("--mode", choices=("free", "fixed"), default="free")
    register.add_argument("--kind", choices=("continuous", "integer"), default="continuous")
    ins = sub.add_parser("inspect")
    ins.add_argument("--experiment", required=True)
    val = sub.add_parser("validate")
    val.add_argument("--experiment", required=True)
    cmp = sub.add_parser("compare")
    cmp.add_argument("--experiments", nargs="+", required=True)
    report = sub.add_parser("report")
    report.add_argument("--experiment", required=True)
    for future in ("mesh", "solve", "pde", "doe", "optimize"):
        sub.add_parser(future)
    sub.add_parser("demo")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    lab = Lab(args.store)
    try:
        if args.command == "study":
            _json(lab.create_study(args.id, args.name, args.question, args.hypothesis, args.objective)
                  if args.action == "create" else lab.inspect_study(args.id))
        elif args.command == "parameters":
            if args.action == "discover":
                _json(lab.discover_parameters(args.backend, args.model))
            elif args.action == "list":
                _json(lab.registry(args.study))
            elif args.action == "refresh":
                _json(lab.refresh_registry(args.study, args.backend, args.model))
            else:
                _json(lab.register_parameter(args.study, args.backend, args.model,
                                             args.native_path, args.id, args.name,
                                             args.lower, args.upper, args.mode, args.kind))
        elif args.command == "model":
            if args.action == "native-new":
                _json(lab.create_native_model(template=args.template))
            elif args.action == "native-import":
                _json(lab.import_native_model(args.path))
            elif args.action == "native-final":
                _json(lab.select_native_final(args.model, args.final))
            elif args.action == "native-inspect":
                _json(lab.inspect_native_model(args.model))
            elif args.action == "inspect":
                _json({"backend": args.backend, "model": args.model,
                       "candidates": lab.discover_parameters(args.backend, args.model)})
            else:
                _json(lab.run_experiment(study_id=args.study, experiment_id=args.experiment,
                                         backend=args.backend, model=args.model,
                                         values=json.loads(args.values)))
        elif args.command == "inspect":
            _json(lab.inspect_experiment(args.experiment))
        elif args.command == "validate":
            _json(lab.inspect_experiment(args.experiment)["validations"])
        elif args.command == "compare":
            _json(lab.compare(args.experiments))
        elif args.command == "report":
            _json(lab.research_summary(args.experiment))
        elif args.command == "demo":
            lab.create_study("S-demo", "3-point bending fixture", "Does a wider roller support remain CAD-valid?",
                             "Widening the support from 32 to 38 mm retains hole clearance.",
                             "Compare geometry and record evidence; do not release the fixture.")
            lab.register_parameter("S-demo", "fixture.cadquery", "roller_support",
                                   "support_width_mm", "support_width", "Support width", 28, 60)
            lab.register_parameter("S-demo", "fixture.cadquery", "roller_support",
                                   "bolt_pitch_x_mm", "bolt_pitch", "Bolt pitch X", 18, 40)
            lab.run_experiment(study_id="S-demo", experiment_id="E-demo-width38",
                               backend="fixture.cadquery", model="roller_support",
                               values={"support_width": 38})
            lab.run_experiment(study_id="S-demo", experiment_id="E-demo-clearance-reject",
                               backend="fixture.cadquery", model="roller_support",
                               values={"bolt_pitch": 30})
            _json(lab.compare(["E-demo-width38", "E-demo-clearance-reject"]))
        else:
            raise ValueError(f"{args.command} capability not installed; no executable adapter")
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
