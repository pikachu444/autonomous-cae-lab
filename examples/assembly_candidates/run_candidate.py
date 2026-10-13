"""One explicit real native candidate through the existing registered evaluator.

Use maintained service Python, installed FreeCAD/Gmsh and ccx on operator PATH.
No mock result and no automatic second attempt. Start only with --run-one.
"""
import argparse
from pathlib import Path
import json
import uuid

from caelab.workbench import Workbench
from caelab.native_inputs import register_native_input
from caelab.native_cad import sha
from caelab.cad_numerical import resolve_settings
from caelab.adapters.native_evaluation import NativeEvaluationFactory
from caelab.adapters.cad_analysis import BACKEND


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--freecad', type=Path, required=True)
    parser.add_argument('--value', type=float, required=True, help='coordinate in fixture.json unit')
    parser.add_argument('--run-one', action='store_true')
    args = parser.parse_args()
    if not args.run_one:
        parser.error('Use --run-one to explicitly execute one native candidate')
    source = json.loads(args.fixture.read_text(encoding='utf-8'))
    path = Path(source['project'])
    if sha(path) != source['sha256']:
        raise ValueError('Saved source changed')
    args.output.mkdir(parents=True, exist_ok=False)
    wb = Workbench(args.output / 'store',
                   configuration={'desktop': {'freecad_executable': str(args.freecad.resolve())}})
    try:
        registered = register_native_input(wb.root, path.parent, path, 'D' + uuid.uuid4().hex,
            root_id='public-assembly-example', relative=path.name, limit=2 * 1024**3)
        settings = {'data_id': registered['id'], 'source_sha256': registered['sha256'],
                    'recipe': source['recipe'],
                    'values': {row['id']: row['value'] for row in source['recipe']['variables']}}
        settings = resolve_settings(wb, settings)
        result_root = args.output / 'result'
        factory = NativeEvaluationFactory(BACKEND, result_root / 'evaluations', retained_root=result_root)
        with factory.prepare(settings) as evaluator:
            result = evaluator.evaluate({**settings['values'], 'pose': args.value})
        receipt = {'execution_status': result['execution_status'], 'responses': result.get('responses', {}),
                   'diagnostics': result.get('diagnostics', {}), 'attempts': factory.retained_attempts(),
                   'source_unchanged': sha(path) == source['sha256'],
                   'engineering_release': 'NOT_RELEASED'}
        (args.output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(receipt, ensure_ascii=False))
        return 0 if result['execution_status'] == 'SUCCEEDED' and receipt['source_unchanged'] else 1
    finally:
        wb.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
