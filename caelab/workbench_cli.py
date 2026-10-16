"""Direct workbench commands; ordinary calculation needs no Study or AI."""
import argparse
import json
from pathlib import Path

COMMANDS = {'backends', 'doctor', 'evaluate', 'run', 'read', 'fit', 'doe', 'search', 'serve', 'submit', 'job', 'files', 'documents', 'command'}


def json_value(value):
    if value is None:
        return {}
    return json.loads(value if value.lstrip().startswith(('{', '[')) else Path(value).read_text(encoding='utf-8'))


def serializable(value):
    if hasattr(value, 'tolist'):
        return value.tolist()
    raise TypeError(type(value).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='caelab')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('backends', 'doctor'):
        command = sub.add_parser(name)
        command.add_argument('--probe', action='store_true', help='Check selected Python dependencies; never start every native solver')
        command.add_argument('--backend')
        if name == 'doctor':
            command.add_argument('--execute', action='store_true', help='Run a selected native calculation; requires --backend and a new --output')
            command.add_argument('--output', help='New directory for native doctor input, logs, and results')
    for name in ('evaluate', 'run', 'fit', 'doe', 'search'):
        command = sub.add_parser(name)
        command.add_argument('--backend', required=True)
        command.add_argument('--settings', default='{}', help='JSON or path to JSON')
        command.add_argument('--values', default='{}')
        command.add_argument('--output')
        if name in {'fit', 'doe', 'search'}:
            command.add_argument('--plan', required=True, help='JSON plan file')
    command = sub.add_parser('read')
    command.add_argument('path')
    command.add_argument('--response', action='append')
    command.add_argument('--verify', choices=['selected', 'all', 'none'], default='selected')
    command = sub.add_parser('serve')
    command.add_argument('--store', required=True)
    command.add_argument('--port', type=int, default=8766)
    command.add_argument('--workbench-config', help='Operator-owned runtime/expert/external backend JSON file')
    command = sub.add_parser('submit')
    command.add_argument('--url', default='http://127.0.0.1:8766')
    command.add_argument('--operation', required=True)
    command.add_argument('--arguments', default='{}')
    command.add_argument('--request-id')
    command = sub.add_parser('job')
    command.add_argument('id')
    command.add_argument('--url', default='http://127.0.0.1:8766')
    command.add_argument('--cancel', action='store_true')
    command = sub.add_parser('files', help='Use the shared service to register approved local inputs')
    actions = command.add_subparsers(dest='action', required=True)
    for name in ('roots', 'list', 'register', 'inspect', 'native'):
        action = actions.add_parser(name)
        action.add_argument('--url', default='http://127.0.0.1:8766')
        if name in {'list', 'register'}:
            action.add_argument('--root', required=True)
            action.add_argument('relative', nargs='?' if name == 'list' else None, default='')
        if name == 'list':
            action.add_argument('--cursor', type=int, default=0)
        if name in {'inspect', 'native'}:
            action.add_argument('id')
    command = sub.add_parser('documents', help='Open and edit the same document as GUI/MCP')
    actions = command.add_subparsers(dest='action', required=True)
    for name in ('list','open','read','apply','result','inspect','stages','stage','transfer','candidate','research-transfer'):
        action = actions.add_parser(name)
        action.add_argument('--url',default='http://127.0.0.1:8766')
        if name=='open':
            action.add_argument('--id')
            action.add_argument('--kind',choices=['material','data','numerical','pde','expert','simulation','evaluation','study'],default='material')
            action.add_argument('--title',default='Material research')
            action.add_argument('--draft')
        if name in {'read','apply','result','inspect','stages','stage','transfer','candidate','research-transfer'}:
            action.add_argument('id')
        if name=='apply':
            action.add_argument('--operation',required=True)
            action.add_argument('--arguments',default='{}')
            action.add_argument('--session',required=True)
            action.add_argument('--generation',type=int,required=True)
            action.add_argument('--command-id')
        if name=='research-transfer':
            action.add_argument('--kind',choices=['study','result_review','report'],required=True)
            action.add_argument('--selection',required=True,help='Stored research selection: JSON or path to JSON')
            action.add_argument('--session',required=True)
            action.add_argument('--generation',type=int,required=True)
            action.add_argument('--command-id',required=True)
        if name in {'result','stages','stage','transfer','candidate'}:
            action.add_argument('job_id')
        if name=='stage':
            action.add_argument('attempt_id')
        if name=='candidate':
            action.add_argument('candidate_id')
            action.add_argument('--evaluation-index',type=int)
            action.add_argument('--attempt-id')
            action.add_argument('--selection',help='Exact retained selection JSON; also supports the declared transfer page')
        if name=='transfer':
            action.add_argument('--transfer-id')
            action.add_argument('--iteration',type=int)
            action.add_argument('--start',type=int,default=0)
            action.add_argument('--count',type=int,default=256)
    command=sub.add_parser('command',help='Inspect or cancel a native owner command')
    command.add_argument('id')
    command.add_argument('--url',default='http://127.0.0.1:8766')
    action=command.add_mutually_exclusive_group()
    action.add_argument('--cancel',action='store_true')
    action.add_argument('--submit-frozen',action='store_true',help='Submit the exact completed native export through the shared JobManager')
    action.add_argument('--open-simulation',action='store_true',help='Open a supported completed native export in Simulation without starting a calculation')
    args = parser.parse_args(argv)
    if args.command in {'backends', 'doctor'}:
        from .backends import list_backends
        result = list_backends(probe=args.probe or args.command == 'doctor')
        if args.backend:
            result = [row for row in result if row['id'] == args.backend]
            if not result:
                parser.error('Unknown backend')
            if args.command == 'doctor':
                from .adapters.native_doctor import doctor_native_backend
                result[0]['native_diagnostic'] = doctor_native_backend(args.backend, execute=args.execute, output=args.output)
        elif args.command == 'doctor' and args.execute:
            parser.error('--execute requires one --backend; doctor never starts every native solver')
    elif args.command in {'documents','command'}:
        from .workbench_client import Client
        client=Client(args.url)
        if args.command=='command':
            result=(client.native_submit(args.id) if args.submit_frozen else
                    client.native_open_simulation(args.id) if args.open_simulation else
                    client.command_cancel(args.id) if args.cancel else client.command_status(args.id))
        elif args.action=='list':
            result=client.documents()
        elif args.action=='open':
            result=client.document_open(kind=args.kind,title=args.title,draft=json_value(args.draft) if args.draft else None,document_id=args.id)
        elif args.action=='read':
            result=client.document_read(args.id)
        elif args.action=='inspect':
            result=client.evaluation_inspect(args.id)
        elif args.action=='stages':
            result=client.evaluation_progress(args.id,args.job_id)
        elif args.action=='stage':
            result=client.evaluation_stage_result(args.id,args.job_id,args.attempt_id)
        elif args.action=='transfer':
            result=client.evaluation_transfer(args.id,args.job_id,args.transfer_id,args.iteration,start=args.start,count=args.count)
        elif args.action=='candidate':
            result=client.numerical_evaluation_result(args.id,args.job_id,args.candidate_id,
                evaluation_index=args.evaluation_index,attempt_id=args.attempt_id,
                selection=json_value(args.selection) if args.selection else None)
        elif args.action=='research-transfer':
            result=client.research_team_transfer(args.id,args.kind,json_value(args.selection),session_id=args.session,
                expected_generation=args.generation,command_id=args.command_id)
        elif args.action=='result':
            result=client.document_result(args.id,args.job_id)
        else:
            result=client.document_command(args.id,args.operation,json_value(args.arguments),session_id=args.session,
                                          expected_generation=args.generation,command_id=args.command_id)
    elif args.command == 'read':
        from .evaluation import read_result
        result = read_result(args.path, verify=args.verify, selection=args.response)
    elif args.command == 'serve':
        from apps.lab.server import main as serve
        options=['--store', args.store, '--port', str(args.port)]
        if args.workbench_config:
            options+=['--workbench-config',args.workbench_config]
        return serve(options)
    elif args.command == 'files':
        from .workbench_client import Client
        client = Client(args.url)
        if args.action == 'roots':
            result = client.local_roots()
        elif args.action == 'list':
            result = client.local_inputs(args.root, args.relative, cursor=args.cursor)
        elif args.action == 'register':
            result = client.register_local_input(args.root, args.relative)
        elif args.action == 'native':
            result = client.native_input(args.id)
        else:
            result = client.input_preview(args.id)
    elif args.command in {'submit', 'job'}:
        from .workbench_client import Client
        client = Client(args.url)
        if args.command == 'submit':
            result = client.submit(args.operation, json_value(args.arguments), request_id=args.request_id)
        else:
            result = client.cancel(args.id) if args.cancel else client.status(args.id)
    elif args.command in {'fit', 'doe', 'search'}:
        from . import numerical
        from .backends import get_backend
        plan = json_value(args.plan)
        record = {'path': args.output, 'level': 'selected'} if args.output else None
        evaluator=args.backend
        adapter=get_backend(args.backend)
        if not callable(adapter) and not callable(getattr(adapter,'prepare',None)):
            if not args.output:
                parser.error('Native numerical studies require --output to retain each real candidate')
            from .adapters.native_evaluation import NativeEvaluationFactory
            evaluator=NativeEvaluationFactory(args.backend,Path(args.output).with_name(Path(args.output).name+'-native'))
        if args.command == 'fit':
            result = numerical.fit_model(evaluator, plan.pop('variables'), plan.pop('experiments'), record=record, **plan)
        else:
            method = numerical.run_doe if args.command == 'doe' else numerical.optimize
            result = method(evaluator, settings=json_value(args.settings), record=record, **plan)
    else:
        from .evaluation import evaluate, run, save_evaluation
        settings = json_value(args.settings)
        if args.command == 'run':
            if not args.output:
                parser.error('run requires --output; native results are never discarded')
            result = run(args.backend, settings, output=args.output)
        else:
            result = evaluate(args.backend, settings, values=json_value(args.values))
            if args.output:
                save_evaluation(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=serializable, allow_nan=False))
    return 0
