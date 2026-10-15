"""Windows entry point, using the existing invocation-owned native_check Job."""
import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freecad',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--timeout',required=True,type=float)
    parser.add_argument('--kind',choices=['shell','beam'],required=True)
    parser.add_argument('--run',action='store_true',help='explicitly launch this single solver job after preparation')
    parser.add_argument('--case',choices=['moment_1','moment_2','end_force'],default='moment_1')
    parser.add_argument('--angle',type=float,choices=[0.,90.],default=0.)
    parser.add_argument('--output-mode',choices=['raw_stress','section_forces'],default='raw_stress')
    parser.add_argument('--regional-axes',action='store_true')
    parser.add_argument('--reverse-second',action='store_true')
    args=parser.parse_args(argv)
    if os.name!='nt':parser.error('This entry point requires the existing Windows Job Object checker')
    root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
    executable=Path(args.freecad).resolve(strict=True)
    out=Path(args.output).absolute();out.mkdir(parents=True,exist_ok=False)
    (out/'options.json').write_text(json.dumps(vars(args),indent=2),encoding='utf-8')
    from scripts.native_check import run_native_check
    variables={'CAELAB_B13_REPOSITORY':str(root),'CAELAB_B13_CHECK_ROOT':str(out),
               'CAELAB_B13_OWNED_CHECK':'PRO-B13-SHELL-BEAM-20261015-03-DIRECT'}
    before={key:os.environ.get(key) for key in variables}
    try:
        os.environ.update(variables)
        receipt=run_native_check([str(executable),str(root/'examples/b13/CheckB13.FCMacro')],out/'process',args.timeout,cwd=root)
        observation=out/'b13-native-observation.json'
        if not observation.is_file():return 1
        result=json.loads(observation.read_text(encoding='utf-8'))
        expected='SUCCEEDED' if args.run else 'PREPARED_NOT_RUN'
        return receipt.exit_code or (1 if (receipt.timed_out or receipt.cleanup_error or
            result['execution']!=expected or result.get('owner_cleanup_error') or
            result.get('document_cleanup_errors')) else 0)
    finally:
        for key,value in before.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


if __name__=='__main__':raise SystemExit(main())
