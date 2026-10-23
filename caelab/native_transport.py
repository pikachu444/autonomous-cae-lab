"""Shared queue/HTTP transport. Native API calls stay in each host main thread."""
from pathlib import Path
import queue
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
import uuid


class DispatchGate:
    """Plain thread-safe acknowledgement; it never reads a native object.

    The GUI stages a request, then starts native work on a later tick only after
    the service has recorded APPLYING. A nested native event loop cannot enter
    a second command while the first call is still executing.
    """
    def __init__(self):
        self.request = None
        self.started = threading.Event()
        self.executing = False

    def stage(self, request, outgoing):
        self.started.clear()
        self.request = request
        outgoing.put({'event': 'started', 'command_id': request['command_id']})

    def acknowledge_started(self, command_id):
        if self.request is not None and self.request['command_id'] == command_id:
            self.started.set()

    def take(self):
        if self.request is None or not self.started.is_set() or self.executing:
            return None
        self.executing = True
        return self.request

    def complete(self):
        self.request = None
        self.started.clear()
        self.executing = False


class BrokerIO:
    def __init__(self, dispatcher, service_url, *, application, version, log=None, tick_timeout=30):
        self.dispatcher = dispatcher
        self.service_url = service_url
        self.log = log or (lambda *_args, **_kwargs: None)
        self.stop = threading.Event()
        self.registered = threading.Event()
        dispatcher.broker_stop = self.stop
        self.tick_timeout = tick_timeout
        self.registration_nonce = secrets.token_urlsafe(32)
        self.host_id = "H" + uuid.uuid4().hex
        self.session_id = dispatcher.owner.session_id
        self.application, self.version = application, str(version)
        self.active_command_id = None
        self.completion_only = False
        self.worker = threading.Thread(target=self.run, name="CAE native broker I/O", daemon=True)

    def start(self):
        self.worker.start()
        return self

    def require_tick(self):
        if self.active_command_id is not None:
            # An acknowledged native call may block its GUI. This means only
            # 'waiting for this outcome', not a fresh GUI tick or progress.
            return
        if self.dispatcher.last_tick is None or time.monotonic() - self.dispatcher.last_tick > self.tick_timeout:
            raise RuntimeError("GUI_DISPATCH_UNAVAILABLE: native owner timer stopped; I/O polling is not an owner heartbeat")

    def deliver_event(self, client, identity, event):
        """Recover start/finish receipts by exact ID; never rerun a native call."""
        path = "/api/workbench/hosts/" + self.host_id + "/events"
        while not self.stop.is_set():
            try:
                receipt = client.request(path, dict(identity, **event))
                if receipt.get('accepted') is not True:
                    raise RuntimeError('Native event was not acknowledged')
                return True
            except HTTPError:
                # A rejected session/contract is not a transient transport loss.
                raise
            except (URLError, TimeoutError, ConnectionError):
                if event['event'] not in {'started', 'finished'}:
                    raise
                self.log('native_receipt_delivery_pending', command_id=event['command_id'], phase=event['event'])
                try:
                    status = client.command_status(event['command_id'])
                    if (status.get('host_id'), status.get('session_id')) != (self.host_id, self.session_id):
                        raise RuntimeError('Native receipt belongs to a different owner session')
                    if event['event'] == 'started' and status.get('state') == 'RUNNING' and status.get('phase') == 'APPLYING':
                        return True  # Service recorded the start; now the GUI may apply once.
                    if status.get('state') in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}:
                        if event['event'] == 'finished' and status.get('outcome') == event['outcome']:
                            return True  # The first report arrived; only its response was lost.
                        if not (event['event'] == 'finished' and status.get('completion_recoverable')):
                            raise RuntimeError('Native outcome is unconfirmed or conflicts with the retained command')
                except HTTPError:
                    raise
                except (URLError, TimeoutError, ConnectionError):
                    pass
                self.stop.wait(.2)
        return False

    def run(self):
        # This worker handles only JSON/queues/HTTP; it never reads native proxies.
        from .workbench_client import Client
        try:
            client = Client(self.service_url)
            ready = None
            while not self.stop.is_set() and ready is None:
                try:
                    ready = self.dispatcher.outgoing.get(timeout=.2)
                except queue.Empty:
                    continue
            if ready is None:
                return
            self.require_tick()
            receipt = client.request("/api/workbench/hosts/register", {
                "host_id": self.host_id, "session_id": self.session_id, "application": self.application,
                "version": self.version, "execution_mode": "gui", "documents": ready["documents"],
                "registration_nonce": self.registration_nonce})
            identity = {"session_id": self.session_id, "host_token": receipt["host_token"]}
            self.registered.set()
            self.log("bridge_registered", host_id=self.host_id, session_id=self.session_id)
            while not self.stop.is_set():
                while not self.dispatcher.outgoing.empty():
                    event = self.dispatcher.outgoing.get_nowait()
                    if self.completion_only and event['event'] == 'heartbeat':
                        continue  # Lost polling is not repaired by a fabricated GUI lease.
                    if not self.deliver_event(client, identity, event):
                        return
                    if event['event'] == 'started':
                        self.active_command_id = event['command_id']
                        self.dispatcher.command_gate.acknowledge_started(event['command_id'])
                    elif event['event'] == 'finished':
                        self.active_command_id = None
                        if self.completion_only:
                            # The exact outstanding result was delivered. Do not
                            # take another mutation through an uncertain bridge.
                            self.deliver_event(client, identity, {'event': 'closed'})
                            self.log('native_completion_delivered_bridge_closed', command_id=event['command_id'])
                            return
                    if event["event"] == "closed":
                        return
                self.require_tick()
                if self.completion_only:
                    self.stop.wait(.2)
                    continue
                # While APPLYING this authenticated poll renews only transport
                # presence. The service returns no next command and does not
                # treat the poll as a GUI tick or native progress.
                try:
                    response = client.request("/api/workbench/hosts/" + self.host_id + "/commands/next", identity)
                except HTTPError:
                    raise  # Authentication/owner-service rejection stays terminal.
                except (URLError, TimeoutError, ConnectionError):
                    if self.active_command_id is None:
                        raise
                    # Keep the sender for the already-acknowledged native call.
                    # Neither re-poll for work nor re-dispatch its mutation.
                    self.completion_only = True
                    self.log('native_poll_lost_waiting_for_completion', command_id=self.active_command_id)
                    continue
                request = response.get("command")
                if request is not None:
                    if request.get("host_id") != self.host_id or request.get("session_id") != self.session_id:
                        raise RuntimeError("Broker delivered a command for a different owner")
                    self.dispatcher.incoming.put(request, timeout=1)
                self.stop.wait(.2)
        except Exception as error:
            # Reconnecting after response loss must not replay an applied mutation.
            self.log("bridge_io_stopped", error_type=type(error).__name__, message=str(error))
            self.stop.set()
        finally:
            self.registered.clear()
            self.stop.set()

    def close(self):
        self.dispatcher.outgoing.put({"event": "closed"})
