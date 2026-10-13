"""Transient same-user Qt result delivery; document owners remain in the service.

Only activation and reviewed result attachments cross this local endpoint.
A process-lifetime QLockFile prevents duplicate Windows named-pipe listeners.
No draft, result bytes, credentials or mailbox are persisted by this module.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import time
import uuid
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QLockFile, QStandardPaths, QThread, QThreadPool, QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QListWidget, QToolBar, QVBoxLayout

from caelab.research_operations import validate_result_reference
from caelab.storage import canonical_hash, check_id

MAX_FRAME = 65536
_ENDPOINTS = {}


def service_identity(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}):
        raise ValueError('Result return requires the existing local service base URL.')
    return 'http://loopback:' + str(parsed.port or 80)


def origin_id(run):
    source = run.get('draft', {}).get('source')
    if isinstance(source, dict):
        identifier = source.get('discussion_id')
        if isinstance(identifier, str) and identifier.startswith('X'):
            return check_id(identifier)
        identifier = source.get('document_id')
        if source.get('kind') == 'study' and isinstance(identifier, str) and identifier.startswith('S'):
            return check_id(identifier)
    return None


def result_message(client, target_id, session_id, reference, selection, *, delivery_id=None):
    message = {'version': 1, 'operation': 'result', 'service': service_identity(client.url),
               'target_id': target_id, 'session_id': session_id,
               'delivery_id': delivery_id or 'D' + uuid.uuid4().hex,
               'reference': deepcopy(reference), 'selection': deepcopy(selection)}
    validate_message(message)
    return message


def validate_message(message):
    common = {'version', 'operation', 'service', 'target_id', 'session_id'}
    if not isinstance(message, dict) or message.get('version') != 1:
        raise ValueError('Unsupported local result message.')
    operation = message.get('operation')
    expected = common | ({'delivery_id', 'reference', 'selection'} if operation == 'result' else
                         {'delivery_id'} if operation == 'status' else set())
    if operation not in {'result', 'activate', 'status'} or set(message) != expected:
        raise ValueError('Unsupported local operation or fields.')
    identifier = check_id(message['target_id'])
    if not identifier.startswith(('X', 'S')):
        raise ValueError('Return target must be an existing Expert or Study.')
    if not isinstance(message['session_id'], str) or not 1 <= len(message['session_id']) <= 160:
        raise ValueError('Missing service session.')
    if not isinstance(message['service'], str) or len(message['service']) > 200:
        raise ValueError('Invalid service identity.')
    if operation in {'result', 'status'}:
        check_id(message['delivery_id'])
    if operation == 'result':
        validate_result_reference(message['reference'])
        if not message['reference']['document_id'].startswith('N'):
            raise ValueError('This route returns a retained Numerical run.')
        selection = message['selection']
        if (not isinstance(selection, list) or len(selection) > 128
                or any(not isinstance(name, str) or not 1 <= len(name) <= 1024 for name in selection)
                or len(selection) != len(set(selection))):
            raise ValueError('Choose distinct actual top-level response channels.')
    if len(json.dumps(message, ensure_ascii=False).encode('utf-8')) > MAX_FRAME:
        raise ValueError('Local result message is too large.')


def _route(service, target_id):
    # Stable across service restart: a stale live editor must remain discoverable.
    folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation)) / 'autonomous-cae-lab' / 'desktop'
    folder.mkdir(parents=True, exist_ok=True)
    digest = canonical_hash({'service': service, 'target': target_id, 'user_directory': str(folder.resolve())})
    return 'caelab-research-' + digest, folder / (digest + '.lock')


def _lock(path):
    lock = QLockFile(str(path))
    lock.setStaleLockTime(0)  # No elapsed-time stealing of a living editor.
    return lock


def verify_result(client, message):
    """Read-only validation of exact bytes, original route and real channel names."""
    validate_message(message)
    reference, target_id = message['reference'], message['target_id']
    target = client.document_read(target_id)
    expected_kind = 'expert' if target_id.startswith('X') else 'study'
    if target.get('id') != target_id or target.get('kind') != expected_kind or target.get('session_id') != message['session_id']:
        raise ValueError('The target owner/session changed. Reopen or reconcile it explicitly.')
    source = client.document_read(reference['document_id'])
    run = next((row for row in source.get('runs', []) if row.get('job_id') == reference['job_id']), None)
    if run is None:
        raise ValueError('The selected Numerical run is absent.')
    original = origin_id(run)
    if original and original != target_id:
        raise ValueError('This run belongs to another original research document.')
    actual = client.document_result_reference(reference['document_id'], reference['job_id'])
    if actual != reference:
        raise ValueError('Retained input or result hash differs; no replacement result is attached.')
    catalog = client.document_result(reference['document_id'], reference['job_id'], selection={'metadata_only': True})
    if set(message['selection']) - set(catalog.get('responses', {})):
        raise ValueError('A selected top-level response is unavailable in this exact run.')
    resolved = client.research_reference({'kind': 'result', **reference, 'selection': message['selection']})
    if resolved.get('status') != 'AVAILABLE':
        raise ValueError('The exact retained result is unavailable.')
    return {'target': target, 'title': source.get('title', reference['document_id']),
            'state': catalog.get('execution_status', 'UNKNOWN'), 'candidate_count': len(catalog.get('candidates', []))}


class PendingResultReview(QObject):
    """One view's transient inbox. Review appends evidence to the latest local buffer."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.server = None
        self.lock = None
        self.route = None
        self.target = None
        self.pending = {}
        self.receipts = {}
        self.workers = []
        self.reviewing = False
        self.connections = set()
        self.action = QAction('Review returned result…', window)
        self.action.setVisible(False)
        self.action.triggered.connect(self.review_next)
        bars = window.findChildren(QToolBar)
        if bars:
            bars[0].addAction(self.action)
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.close)

    def bind(self, document):
        if not getattr(self.window.client, 'url', None):
            self.target = (document['id'], document['session_id'])
            return True  # In-process clients/tests still exercise the actual receiver.
        service = service_identity(self.window.client.url)
        name, path = _route(service, document['id'])
        if self.route == name:
            self.target = (document['id'], document['session_id'])
            return True
        existing = _ENDPOINTS.get(name)
        if existing is not None:
            existing.window.showNormal()
            existing.window.raise_()
            existing.window.activateWindow()
            self.window.message.setText('This document is already open. Its existing edits remain in that window.')
            return False
        lock = _lock(path)
        if not lock.tryLock(0):
            self.window.message.setText('This document has a live editor or is still opening. Use its existing window; this view was not replaced.')
            return False
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        server.setMaxPendingConnections(8)
        # Only the exclusive lock holder may clean an endpoint left by a dead process.
        QLocalServer.removeServer(name)
        if not server.listen(name):
            lock.unlock()
            server.deleteLater()
            self.window.message.setText('Local result receiver is unavailable: ' + server.errorString())
            return False
        self.close()
        self.server, self.lock, self.route = server, lock, name
        self.target = (document['id'], document['session_id'])
        _ENDPOINTS[name] = self
        server.newConnection.connect(self._connected)
        return True

    def close(self):
        if self.route and _ENDPOINTS.get(self.route) is self:
            del _ENDPOINTS[self.route]
        for socket in list(self.connections):
            socket.abort()
        self.connections.clear()
        if self.server:
            self.server.close()
            self.server.deleteLater()
        if self.lock:
            self.lock.unlock()
        self.server = self.lock = self.route = None
        self.target = None
        self.pending.clear()
        self.receipts.clear()
        self.action.setVisible(False)

    def _connected(self):
        while self.server and self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if len(self.connections) >= 8:
                socket.abort()
                socket.deleteLater()
                continue
            self.connections.add(socket)
            socket.setReadBufferSize(MAX_FRAME + 1)
            buffer = bytearray()
            timeout = QTimer(socket)
            timeout.setSingleShot(True)
            timeout.setInterval(3000)
            timeout.timeout.connect(socket.abort)
            timeout.start()
            def read(socket=socket, buffer=buffer, timeout=timeout):
                buffer.extend(bytes(socket.readAll()))
                if len(buffer) > MAX_FRAME:
                    socket.abort()
                    return
                if b'\n' not in buffer:
                    return
                timeout.stop()
                try:
                    message = json.loads(bytes(buffer).decode('utf-8'))
                    receipt = self.receive(message)
                except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
                    receipt = {'status': 'REJECTED', 'reason': str(error)}
                socket.write((json.dumps(receipt, ensure_ascii=False) + '\n').encode('utf-8'))
                socket.flush()
                socket.disconnectFromServer()
            socket.readyRead.connect(read)
            socket.disconnected.connect(lambda socket=socket: (self.connections.discard(socket), socket.deleteLater()))
            if socket.bytesAvailable():
                read()

    def receive(self, message):
        if QThread.currentThread() != self.window.thread():
            raise RuntimeError('Pending results must be received on the GUI thread.')
        validate_message(message)
        window, document = self.window, self.window.document
        if (not document or self.target != (document['id'], document['session_id'])
                or (message['target_id'], message['session_id']) != self.target
                or getattr(window, '_allow_close', False)
                or getattr(window.client, 'url', None) and service_identity(window.client.url) != message['service']):
            return {'status': 'REJECTED', 'reason': 'The original document/session is not active.'}
        operation = message['operation']
        identifier = message.get('delivery_id')
        base = {'target_id': document['id'], 'session_id': document['session_id']}
        if operation == 'activate':
            window.showNormal()
            window.raise_()
            window.activateWindow()
            return {**base, 'status': 'ACTIVATED'}
        if operation == 'status':
            return {**base, **self.receipts.get(identifier, {'status': 'UNKNOWN'}), 'delivery_id': identifier}
        signature = canonical_hash(message)
        if identifier in self.receipts:
            receipt = self.receipts[identifier]
            if receipt['signature'] != signature:
                return {**base, 'status': 'REJECTED', 'reason': 'Delivery ID has different content.'}
            return {**base, **receipt, 'delivery_id': identifier}
        if len(self.pending) >= 8:
            return {**base, 'status': 'BUSY', 'reason': 'Review or cancel the existing returned results first.'}
        self.pending[identifier] = deepcopy(message)
        self.receipts[identifier] = {'status': 'PRESENTED', 'signature': signature}
        while len(self.receipts) > 128:
            oldest = next((key for key in self.receipts if key not in self.pending), None)
            if oldest is None:
                break
            del self.receipts[oldest]
        self.action.setText('Review returned result… (' + str(len(self.pending)) + ')')
        self.action.setVisible(True)
        window.showNormal()
        window.raise_()
        window.activateWindow()
        window.message.setText('Numerical result ready for review. The current edits have not changed.')
        return {**base, 'status': 'PRESENTED', 'delivery_id': identifier}

    def _blocked(self):
        window = self.window
        return (not window.document or window.conflict or window._busy or getattr(window, '_callbacks', 0)
                or getattr(window, '_draft_problem', None) or getattr(window, '_raw_mode', False)
                or getattr(window, '_allow_close', False))

    def review_next(self):
        if not self.pending or self.reviewing or self._blocked():
            self.window.message.setText('Finish the current request or repair the draft/conflict before reviewing the returned result.')
            return False
        identifier = next(iter(self.pending))
        message = deepcopy(self.pending[identifier])
        context = (self.window.document['id'], self.window.document['session_id'],
                   canonical_hash(self.window.document['draft']))
        self.reviewing = True
        self.window._incoming_review = True
        self.window._update_actions()
        def relevant():
            document = self.window.document
            return (document and (document['id'], document['session_id'], canonical_hash(document['draft'])) == context
                    and not self._blocked() and identifier in self.pending)
        def failed(error):
            if identifier in self.receipts:
                self.receipts[identifier].update(status='REJECTED', reason=str(error))
            self.pending.pop(identifier, None)
            self._finish()
            self.window.message.setText('Result not attached; current edits retained. ' + error)
        def checked(payload):
            if not relevant() or canonical_hash(payload['target']['draft']) != context[2]:
                failed('The original owner or local editor changed. Reconcile it before retrying.')
                return
            if not self.confirm(message, payload):
                self.receipts[identifier]['status'] = 'CANCELLED'
                self.pending.pop(identifier, None)
                self._finish()
                self.window.message.setText('Return cancelled. Question, Study entries and evidence are unchanged.')
                return
            if not relevant():
                failed('The original editor changed during review.')
                return
            # Revalidate after a potentially long modal review; do not attach stale bytes.
            self._read(lambda: verify_result(self.window.client, message), attach, failed)
        def attach(payload):
            if not relevant() or canonical_hash(payload['target']['draft']) != context[2]:
                failed('The owner changed during review; evidence was not appended.')
                return
            status = self.append(message)
            self.receipts[identifier]['status'] = status
            self.pending.pop(identifier, None)
            self._finish()
            self.window.message.setText('Result evidence attached locally. Apply and Save remain explicit.' if status == 'ATTACHED'
                                       else 'This exact result and channel selection is already attached.')
        self._read(lambda: verify_result(self.window.client, message), checked, failed)
        return True

    def _read(self, function, accepted, rejected):
        from .expert_window import _Call
        worker = _Call(function)
        self.workers.append(worker)
        def finished(value, error):
            self.workers.remove(worker)
            if error:
                rejected(error)
            else:
                try:
                    accepted(value)
                except (ValueError, TypeError, KeyError, IndexError) as failure:
                    rejected(str(failure))
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def _finish(self):
        self.reviewing = False
        self.window._incoming_review = False
        self.action.setVisible(bool(self.pending))
        self.action.setText('Review returned result… (' + str(len(self.pending)) + ')')
        self.window._update_actions()

    def confirm(self, message, payload):
        dialog = QDialog(self.window)
        dialog.setWindowTitle('Attach Numerical result')
        dialog.resize(660, 360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(payload['title'] + ' → ' + self.window.document['title']))
        scope = ', '.join(message['selection']) if message['selection'] else 'No top-level response channels'
        label = QLabel('Run: ' + message['reference']['job_id'] + '\nChannels: ' + scope +
                       '\nRun evidence includes its candidate records; it is not a single-candidate attachment.')
        label.setWordWrap(True)
        layout.addWidget(label)
        details = QListWidget()
        for key, value in message['reference'].items():
            details.addItem(key + ': ' + str(value))
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Attach evidence')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def append(self, message):
        window = self.window
        draft = window.edited_draft()
        reference = {**deepcopy(message['reference']), 'selection': deepcopy(message['selection'])}
        if window.document['kind'] == 'expert':
            rows = draft['composer']['evidence']
            if reference in rows:
                return 'ALREADY_ATTACHED'
            rows.append(reference)
            window._buffer = draft
            window._update_evidence_label()
        else:
            reference = {'kind': 'result', **reference}
            if any(row.get('reference') == reference for row in draft['evidence']):
                return 'ALREADY_ATTACHED'
            draft['evidence'].append({'id': 'E' + uuid.uuid4().hex, 'label': 'Numerical result',
                                      'kind': 'result', 'reference': reference, 'note': ''})
            window._buffer = draft
            window._populate_evidence()  # Leave the current issue and its detail editor selected.
        window._edited()
        return 'ATTACHED'


def install_receiver(window):
    window._incoming_review = False
    window._result_return = PendingResultReview(window)


def bind_receiver(window, document):
    receiver = getattr(window, '_result_return', None)
    if receiver is None:
        install_receiver(window)
        receiver = window._result_return
    if receiver.reviewing:
        window.message.setText('Finish the pending result review before changing documents.')
        return False
    return receiver.bind(document)


def send_message(message, *, timeout_ms=2500):
    """Blocking local socket exchange: call from a worker or before a UI exists."""
    validate_message(message)
    name, path = _route(message['service'], message['target_id'])
    socket = QLocalSocket()
    socket.setReadBufferSize(MAX_FRAME + 1)
    socket.connectToServer(name)
    if not socket.waitForConnected(timeout_ms):
        error = socket.error()
        absent = error in {QLocalSocket.LocalSocketError.ServerNotFoundError, QLocalSocket.LocalSocketError.ConnectionRefusedError}
        if absent:
            probe = _lock(path)
            if probe.tryLock(0):
                probe.unlock()
                return {'status': 'ABSENT'}
        raise RuntimeError('The original editor is starting, busy or unreachable. No replacement window was opened.')
    socket.write((json.dumps(message, ensure_ascii=False) + '\n').encode('utf-8'))
    socket.flush()
    deadline, buffer = time.monotonic() + timeout_ms / 1000, bytearray()
    while b'\n' not in buffer and time.monotonic() < deadline:
        if not socket.bytesAvailable():
            socket.waitForReadyRead(max(1, int((deadline - time.monotonic()) * 1000)))
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > MAX_FRAME:
            raise RuntimeError('Invalid local result receipt.')
        if socket.state() == QLocalSocket.LocalSocketState.UnconnectedState and not socket.bytesAvailable():
            break
    socket.abort()
    if b'\n' not in buffer:
        raise RuntimeError('Delivery is unconfirmed; retry this same result instead of opening another editor.')
    receipt = json.loads(bytes(buffer).decode('utf-8'))
    if not isinstance(receipt, dict) or receipt.get('target_id') != message['target_id'] or receipt.get('session_id') != message['session_id']:
        raise RuntimeError('Original editor identity/session did not acknowledge delivery.')
    return receipt


def deliver_result(client, message, *, launch=None, timeout=12):
    """Reuse a live original; launch its exact existing ID only after confirmed absence."""
    if service_identity(client.url) != message['service']:
        raise ValueError('Return service differs from the selected Plan.')
    verify_result(client, message)
    receipt = send_message(message)
    if receipt.get('status') != 'ABSENT':
        return receipt
    if launch is None:
        from .desktop import _spawn
        launch = lambda: _spawn(client, ['expert' if message['target_id'].startswith('X') else 'study',
                                         '--document-id', message['target_id']])
    launch()
    deadline = time.monotonic() + timeout
    last = 'Original editor is still opening.'
    while time.monotonic() < deadline:
        try:
            receipt = send_message(message, timeout_ms=500)
            if receipt.get('status') != 'ABSENT':
                return receipt
        except RuntimeError as error:
            last = str(error)
        time.sleep(.05)
    raise RuntimeError(last + ' Return remains unconfirmed; retry without creating another research document.')


def activate_existing(client, target_id):
    """Return an activation receipt or ABSENT; never hide timeout/stale-owner errors."""
    document = client.document_read(check_id(target_id))
    message = {'version': 1, 'operation': 'activate', 'service': service_identity(client.url),
               'target_id': target_id, 'session_id': document['session_id']}
    receipt = send_message(message)
    if receipt.get('status') not in {'ACTIVATED', 'ABSENT'}:
        raise RuntimeError('Original editor was not activated: ' + str(receipt))
    return receipt
