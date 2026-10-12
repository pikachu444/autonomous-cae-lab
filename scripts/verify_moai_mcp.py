"""Read-only local MoAI MCP handshake/probe; never requests model inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import subprocess
import threading


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tool', help='Read-only tool name discovered by tools/list')
    parser.add_argument('--arguments', default='{}')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    executable = 'C:/Users/pikac/AppData/Local/Programs/moai/moai.exe'
    process = subprocess.Popen([executable, 'mcp-server'], cwd=root,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8')
    replies: queue.Queue[str] = queue.Queue()
    diagnostics: list[str] = []

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            replies.put(line)

    def read_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            diagnostics.append(line)

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()
    sequence = 0

    def request(method: str, params: dict | None = None, *, notification: bool = False) -> dict:
        nonlocal sequence
        sequence += 1
        message = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notification:
            message['id'] = sequence
        assert process.stdin is not None
        process.stdin.write(json.dumps(message)+'\n')
        process.stdin.flush()
        if notification:
            return {}
        while True:
            response = json.loads(replies.get(timeout=15))
            if response.get('id') == sequence:
                if 'error' in response:
                    raise RuntimeError(response['error'])
                return response['result']

    try:
        initialized = request('initialize', {'protocolVersion': '2024-11-05',
                              'capabilities': {},
                              'clientInfo': {'name': 'caelab-local-verification', 'version': '1'}})
        request('notifications/initialized', notification=True)
        available = request('tools/list')
        receipt = {'transport': 'local stdio subprocess; host-exposed call recorded in tool_connection.json',
                   'initialize': initialized,
                   'tool_names': [tool['name'] for tool in available['tools']],
                   'read_tool_inputs': {tool['name']: {'required': tool['inputSchema'].get('required', []),
                                                     'properties': list(tool['inputSchema'].get('properties', {}))}
                                        for tool in available['tools']
                                        if tool['name'] in {'spec_audit', 'spec_drift', 'spec_progress', 'todo_list'}},
                   'provider_or_model_called': False}
        if args.tool:
            names = {tool['name'] for tool in available['tools']}
            read_only = {'spec_audit', 'spec_drift', 'spec_progress', 'todo_list'}
            if args.tool not in names or args.tool not in read_only:
                raise ValueError('Only a discovered read/status/list/view tool may be probed')
            receipt['tool_call'] = {'name': args.tool,
                                   'result': request('tools/call', {'name': args.tool,
                                                       'arguments': json.loads(args.arguments)})}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'server': initialized.get('serverInfo'),
                          'tools': [tool['name'] for tool in available['tools']],
                          'call': args.tool, 'provider_or_model_called': False}))
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=3)


if __name__ == '__main__':
    main()
