"""Read frozen/native beam records, or explicitly delegate to the existing owner."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser=argparse.ArgumentParser(description='CAE Lab beam native input/result access')
    sub=parser.add_subparsers(dest='operation',required=True)
    read=sub.add_parser('result',help='Verify and read a saved run; never executes')
    read.add_argument('folder');read.add_argument('--component',choices=['UX','UY','UZ','V1','V2','N','Mt','M1','M2','RF_X_raw','RF_Y_raw','RF_Z_raw'])
    freeze=sub.add_parser('input',help='Verify frozen input; never executes');freeze.add_argument('manifest')
    view=sub.add_parser('view',help='Open the independent Qt result viewer');view.add_argument('folder')
    submit=sub.add_parser('submit',help='Explicitly submit one completed native freeze through existing JobManager')
    submit.add_argument('--service',required=True);submit.add_argument('--command-id',required=True)
    args=parser.parse_args(argv)
    if args.operation=='result':
        from .adapters.beam_fem import read_saved_run
        from .beam_results import channels
        value=read_saved_run(args.folder)
        if args.component:
            if not value['observed']:raise ValueError('No complete native beam fields; inspect the retained diagnostics')
            value={'execution_status':value['execution']['execution_status'],
                   'component':channels(value['observed']['frames'][-1])[args.component]}
    elif args.operation=='input':
        from .adapters.beam_fem import validate_snapshot
        manifest,model,_=validate_snapshot(Path(args.manifest).absolute())
        value={'manifest':manifest,'model':model}
    elif args.operation=='view':
        from apps.desktop_pre.beam_result_window import main as view_main
        return view_main([args.folder])
    else:
        from .workbench_client import Client
        value=Client(args.service).native_submit(args.command_id)
    print(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
