"""Noninteractive wrapper around pinned upstream INP2RAD, in an owned child."""
import argparse
import builtins
import importlib.util
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('input', type=Path)
    args = parser.parse_args(argv)
    path = args.input.resolve(strict=True)
    if path.suffix.lower() != '.inp':
        raise ValueError('An admitted flattened INP is required')
    source = Path(__file__).resolve().parents[2] / 'third_party/inp2rad/inp2rad.py'
    spec = importlib.util.spec_from_file_location('caelab_pinned_inp2rad', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.or_gui, module.run_timer, module.radversion = True, False, 2025
    def noninteractive(*_):
        raise ValueError('Converter requested interactive input; definition is not supported')
    builtins.input = noninteractive
    ok = module.start(str(path))
    return 0 if ok and all(path.with_name(path.stem + tail).is_file()
                            for tail in ('_0000.rad','_0001.rad')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
