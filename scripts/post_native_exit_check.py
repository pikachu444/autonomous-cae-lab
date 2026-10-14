"""Interactive Windows ParaView check, using the root-owned Job Object runner.

Does not drive guessed menu coordinates, kill by process name, start a solver,
or label a user's declared route as automatically observed keyboard input.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]


def load_job_runner(repo: Path = REPO):
    source = repo / 'scripts/native_check.py'
    if not source.is_file():
        raise RuntimeError('ROOT_INPUT_MISSING: scripts/native_check.py is absent. Restore the existing '
                           'root-owned Windows Job runner; no process was started.')
    spec = importlib.util.spec_from_file_location('cae_post_root_native_check', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.run_native_check


def validate_project(project: Path, run_dir: Path) -> dict:
    project, run_dir = project.resolve(strict=True), run_dir.resolve(strict=True)
    scratch = (run_dir / 'scratch').resolve(strict=True)
    if not project.is_relative_to(scratch):
        raise ValueError('Only a dedicated project under run-dir/scratch may be edited by this check')
    record = json.loads(project.read_text(encoding='utf-8'))
    root = Path(record.get('project_root', '')).resolve(strict=True)
    if not root.is_relative_to(scratch):
        raise ValueError('The saved project_root points outside the scratch check directory')
    if record.get('kind') != 'external-result':
        raise ValueError('Use the existing managed external/result workspace contract')
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paraview-root', type=Path, required=True)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--scratch-project', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--service-url', required=True, help='Existing CAE service; not a new web UI')
    parser.add_argument('--route', required=True, choices=['file-exit', 'action-shortcut', 'window-x', 'alt-f4'])
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args()
    try:
        run_native_check = load_job_runner()  # Missing root input fails before any launch.
        if os.name != 'nt':
            raise RuntimeError('This check requires a Windows interactive desktop')
        if not 1 <= args.timeout <= 3600:
            raise ValueError('Timeout must be between 1 and 3600 seconds')
        validate_project(args.scratch_project, args.run_dir)
        sys.path.insert(0, str(REPO))
        from apps.desktop_post.native_exit_abi import verify_artifact
        verify_artifact(args.plugin, args.paraview_root)
        case = args.run_dir / ('check-' + args.route)
        case.mkdir(exist_ok=False)  # Never overwrite past failures/receipts.
        config = dict(route_declared=args.route, route_automatically_observed=False,
                      home=str(REPO / 'apps/desktop_post'), plugin=str(args.plugin.resolve()),
                      runtime=str(args.paraview_root.resolve()), project=str(args.scratch_project.resolve()),
                      service_url=args.service_url, output=str(case.resolve()))
        config_path = case / 'config.json'
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        # Environment is changed only for this synchronous child launch and restored.
        previous = os.environ.get('CAE_POST_EXIT_CHECK_CONFIG')
        os.environ['CAE_POST_EXIT_CHECK_CONFIG'] = str(config_path.resolve())
        try:
            result = run_native_check([str(args.paraview_root.resolve() / 'bin/paraview.exe'),
                '--dr', '--script=' + str(REPO / 'apps/desktop_post/native_exit_check.py')],
                case / 'job', args.timeout)
        finally:
            if previous is None:
                os.environ.pop('CAE_POST_EXIT_CHECK_CONFIG', None)
            else:
                os.environ['CAE_POST_EXIT_CHECK_CONFIG'] = previous
        summary = {'pid': result.pid, 'exit_code': result.exit_code, 'timed_out': result.timed_out,
                   'job_receipt': str(result.receipt), 'native_acceptance': 'REQUIRES_REVIEW',
                   'declared_route_is_not_input_proof': True}
        (case / 'launch-result.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if result.exit_code == 0 and not result.timed_out else 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
