"""One-turn, approval-scoped adapter for the official OpenScience CLI.

The signed-in CLI receives only the tools furnished by this ephemeral MCP server.
The workbench process retains the live callbacks, authorization and budgets.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import secrets
import socket
import subprocess
import threading
import time

from ..execution_control import _current, check_cancelled, cancellation_scope, ExecutionCleanupFailed


def run_openscience(prompt, tools, budget, model, *, max_steps, profile_path=None, runtime_prefix=None):
    if not model.startswith('openai-codex/'):
        raise ValueError('OpenScience OAuth requires an explicit openai-codex model')
    if not isinstance(max_steps, int) or not 1 <= max_steps <= 32:
        raise ValueError('OpenScience model steps must be explicitly bounded')
    token = secrets.token_urlsafe(32)
    cancellation = _current.get()
    invocation_lock = threading.Lock()
    catalog = [{'name': name, 'parameters': row['parameters'],
                'description': row['description']} for name, row in tools.items()]

    def invoke(name, args):
        if name not in tools or not isinstance(args, dict):
            raise ValueError('Unknown tool or invalid arguments')
        # MCP calls can arrive concurrently. Approval-bearing closures and
        # budget counters are serial per expert turn.
        with invocation_lock:
            # HTTP/ASGI threads do not inherit the job's ContextVar. Nested
            # expert calls and queued submissions must share its owner token.
            with cancellation_scope(cancellation):
                check_cancelled()
                return tools[name]['call'](**args)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _reply(self, code, payload):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self):
            return secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)

        def do_GET(self):
            if not self._authorized():
                return self._reply(403, {'error': 'Access denied'})
            if self.path == '/tools':
                return self._reply(200, {'tools': catalog})
            if self.path == '/status':
                return self._reply(200, {'cancel_requested': bool(cancellation and cancellation.requested)})
            return self._reply(404, {'error': 'Unknown bridge endpoint'})

        def do_POST(self):
            if not self._authorized() or self.path != '/invoke':
                return self._reply(403, {'error': 'Access denied'})
            size = int(self.headers.get('Content-Length', 0))
            if size <= 0 or size > 100_000:
                return self._reply(413, {'error': 'Tool input too large'})
            try:
                request = json.loads(self.rfile.read(size))
                name = request['name']
                args = request['arguments']
                result = invoke(name, args)
                self._reply(200, {'result': result, 'is_error': False})
            except Exception as exc:
                self._reply(200, {'result': {'status': 'TOOL_REJECTED', 'error': type(exc).__name__,
                                             'reason': str(exc)}, 'is_error': True})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    mcp_server = None
    mcp_thread = None
    mcp_socket = None
    try:
        import uvicorn
        from .openscience_bridge import make_http_app

        mcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        mcp_socket.bind(('127.0.0.1', 0))
        mcp_socket.listen(128)
        mcp_socket.setblocking(False)
        mcp_port = mcp_socket.getsockname()[1]
        mcp_app = make_http_app(catalog, invoke, token)
        mcp_server = uvicorn.Server(uvicorn.Config(mcp_app, host='127.0.0.1', port=0,
            log_level='critical', access_log=False, lifespan='on', timeout_graceful_shutdown=3))
        mcp_thread = threading.Thread(target=mcp_server.run, kwargs={'sockets': [mcp_socket]}, daemon=True)
        mcp_thread.start()
        startup_deadline = min(budget.deadline, time.monotonic() + 5)
        while not mcp_server.started:
            if not mcp_thread.is_alive() or time.monotonic() >= startup_deadline:
                raise RuntimeError('Scoped MCP server did not start')
            time.sleep(.02)
        script = Path(__file__).with_name('openscience_host.ps1')
        windows_script = subprocess.check_output(['wslpath', '-w', str(script)], text=True).strip()
        request = {'prompt': prompt, 'model': model,
                   'bridge_url': f'http://127.0.0.1:{server.server_port}',
                   'mcp_url': f'http://127.0.0.1:{mcp_port}/mcp',
                   'bridge_token': token, 'deadline': max(1, int(budget.deadline - time.monotonic())),
                   'max_steps': max_steps, 'tool_names': list(tools),
                   'profile_path': profile_path, 'runtime_prefix': runtime_prefix}
        process = subprocess.Popen(['pwsh.exe', '-NoProfile', '-File', windows_script],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='strict')
        payload = json.dumps(request, ensure_ascii=False)
        cleanup_deadline = budget.deadline + 20
        cancellation_seen = None
        first = True
        while True:
            try:
                stdout, stderr = process.communicate(input=payload if first else None, timeout=.5)
                break
            except subprocess.TimeoutExpired:
                first = False
                if cancellation and cancellation.requested:
                    cancellation_seen = cancellation_seen or time.monotonic()
                if time.monotonic() >= cleanup_deadline or (cancellation_seen and time.monotonic() - cancellation_seen > 15):
                    # The Windows helper has not confirmed its owned CLI child
                    # stopped. Reap only our wrapper and report cleanup unknown.
                    process.terminate()
                    try:
                        process.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                    raise ExecutionCleanupFailed('OpenScience Windows child cleanup was not confirmed')
        try:
            response = json.loads(stdout)
        except (ValueError, TypeError):
            response = {}
        if cancellation and cancellation.requested:
            if process.returncode or response.get('cleanup_confirmed') is not True:
                raise ExecutionCleanupFailed('OpenScience Windows child cleanup was not confirmed')
            check_cancelled()
        if process.returncode:
            raise RuntimeError('OpenScience host failed: ' + stderr[-1500:])
        if response.get('status') != 'completed' or not response.get('text'):
            raise RuntimeError('OpenScience did not return a completed answer: ' + str(response.get('reason', response.get('status'))))
        return response['text']
    finally:
        if mcp_server is not None:
            mcp_server.should_exit = True
        if mcp_thread is not None:
            mcp_thread.join(timeout=5)
        if mcp_socket is not None:
            mcp_socket.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        if (mcp_thread is not None and mcp_thread.is_alive()) or thread.is_alive():
            raise ExecutionCleanupFailed('Scoped expert server cleanup was not confirmed')
