"""Direct workbench commands; ordinary calculation needs no Study or AI."""
import argparse
import json
from pathlib import Path

COMMANDS = {'backends', 'doctor', 'evaluate', 'run', 'read', 'fit', 'doe', 'search', 'serve', 'submit', 'job'}


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
    args = parser.parse_args(argv)
    if args.command in {'backends', 'doctor'}:
        from .backends import list_backends
        result = list_backends(probe=args.probe or args.command == 'doctor')
        if args.backend:
            result = [row for row in result if row['id'] == args.backend]
            if not result:
                parser.error('Unknown backend')
    elif args.command == 'read':
        from .evaluation import read_result
        result = read_result(args.path, verify=args.verify, selection=args.response)
    elif args.command == 'serve':
        from apps.lab.server import main as serve
        options=['--store', args.store, '--port', str(args.port)]
        if args.workbench_config:
            options+=['--workbench-config',args.workbench_config]
        return serve(options)
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
