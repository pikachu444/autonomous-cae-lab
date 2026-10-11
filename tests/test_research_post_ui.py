"""Actual Qt companion controls with a labelled native-command transport fixture.

No ParaView calculation is fabricated here: controlled command results exercise
GUI request ownership. Native physics/render readiness is tested separately.
"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog

from apps.research.post_window import PostWindow, defaults


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError('Post companion Qt command did not settle')


def source(ref, label):
    return {'source_ref': ref, 'label': label, 'reader_name': label, 'input_id': 'D' + ref,
        'available': True, 'metadata': {'arrays': [{'name': 'stress', 'association': 'POINTS', 'components': 1}]},
        'native_metadata': {'coordinate_units': 'mm', 'coordinate_frame': 'lab',
            'arrays': [{'name': 'stress', 'association': 'POINTS', 'components': 1, 'quantity': 'stress',
                'units': 'MPa', 'measure': 'Cauchy', 'frame': 'lab'}]}}


class NativeClient:
    """Explicit software fixture; QUEUED/RUNNING/completion use real Qt polling."""
    def __init__(self):
        self.document = {'id': 'Dpost', 'session_id': 'Snative', 'kind': 'post', 'title': 'Native fixture',
            'generation': 0, 'connected': True, 'state': {'analysis': {
                'sources': [source('Sfirst', 'Original A'), source('Ssecond', 'Original B')],
                'objects': [], 'active_object': None, 'restore_issues': []},
                'sources': [{'source_id': '101', 'label': 'Original A'}, {'source_id': '102', 'label': 'Original B'}]}}
        self.calls, self.commands, self.execute_count = [], {}, {}
        self.release = True
        self.lose_reply = False

    def document_read(self, identifier):
        assert identifier == self.document['id']
        return deepcopy(self.document)

    def document_command(self, identifier, operation, arguments, **options):
        assert identifier == self.document['id'] and options['session_id'] == 'Snative'
        assert options['expected_generation'] == self.document['generation']
        command_id = options['command_id']
        self.calls.append((command_id, operation, deepcopy(arguments)))
        if command_id not in self.commands:
            self.commands[command_id] = {'command_id': command_id, 'state': 'QUEUED', 'operation': operation,
                'arguments': deepcopy(arguments), 'polls': 0}
        if self.lose_reply:
            self.lose_reply = False
            raise ValueError('CONTROLLED response loss after registration')
        return deepcopy(self.commands[command_id])

    def command_status(self, identifier):
        command = self.commands[identifier]
        if command['state'] == 'SUCCEEDED':
            return deepcopy(command)
        command['polls'] += 1
        if command['polls'] == 1 or not self.release:
            command['state'] = 'RUNNING'
        else:
            payload = self._execute(command)
            command.update(state='SUCCEEDED', outcome={'state': 'SUCCEEDED', 'result':
                {'status': 'COMPLETED', 'result': payload}})
        return deepcopy(command)

    def _execute(self, command):
        operation, args = command['operation'], command['arguments']
        self.execute_count[command['command_id']] = self.execute_count.get(command['command_id'], 0) + 1
        analysis = self.document['state']['analysis']
        if operation.endswith('_edit'):
            kind = operation.removeprefix('post.').removesuffix('_edit')
            obj = next((item for item in analysis['objects'] if item['id'] == args.get('object_ref')), None)
            if obj is None:
                obj = {'id': 'A' + str(len(analysis['objects']) + 1), 'kind': kind, 'title': kind,
                       'history': [], 'position': -1, 'preview': None, 'diagnostics': []}
                analysis['objects'].append(obj)
            obj['draft'] = deepcopy(args['draft'])
            analysis['active_object'] = obj['id']
            payload = deepcopy(obj)
        elif operation == 'post.mapping_validate':
            obj = next(item for item in analysis['objects'] if item['id'] == args['object_ref'])
            obj['preview'] = {'id': 'Vpreview', 'recipe': deepcopy(obj['draft']), 'summary': {'fixture': 'CONTROLLED native result'}}
            payload = deepcopy(obj['preview'])
        elif operation == 'post.apply':
            obj = next(item for item in analysis['objects'] if item['id'] == args['object_ref'])
            obj['history'].append(deepcopy(obj['preview']))
            obj['position'] = len(obj['history']) - 1
            payload = deepcopy(obj['history'][-1])
        elif operation == 'post.sample':
            payload = {'object_ref': args['object_ref'], 'rows': [
                {'point_index': 4, 'a': 0, 'b': None, 'valid': False, 'validity_reason': 'outside_domain'},
                {'point_index': 7, 'a': 2, 'b': 3, 'valid': True, 'validity_reason': 'valid'}]}
        elif operation == 'post.measurement_capture':
            obj = {'id': 'Acaptured', 'kind': 'measurement', 'title': 'Original point selection', 'history': [],
                'position': -1, 'preview': None, 'diagnostics': [], 'draft': {'source_ref': args['source_ref'],
                'measurement': 'point', 'array': args['array'], 'association': 'POINTS', 'point_indices': [2, 8]}}
            analysis['objects'].append(obj)
            payload = deepcopy(obj)
        elif operation == 'post.inspect':
            payload = {'data': {'arrays': analysis['sources'][0]['metadata']['arrays']}}
        elif operation in ('post.source_add', 'post.source_repair'):
            payload = {'source_ref': args.get('source_ref', 'Snew')}
        else:
            payload = {'fixture': 'CONTROLLED ' + operation}
        self.document['generation'] += 1
        return payload

    def register_local_input(self, root, relative):
        assert root == 'approved'
        return {'id': 'Dregistered', 'name': relative}


def edit(window, path, value):
    field = window.fields[path][0]
    if isinstance(field, QComboBox):
        if path[-1] == 'source_ref':
            field.setCurrentIndex(field.findData(value))
        else:
            field.setCurrentText(value)
    else:
        field.setText(value)
        window._edited()


@pytest.fixture
def window(app):
    client = NativeClient()
    window = PostWindow(client, document_id='Dpost', session_id='Snative', auto_open=False, poll_interval=0)
    window.refresh_document(initial=True)
    wait(app, lambda: window.document is not None and not window._busy)
    yield window
    client.release = True
    if window._pending:
        window.recover_request()
        wait(app, lambda: window._pending is None and not window._busy)
    window._allow_close = True
    window.close()


def test_comparison_declarations_preview_apply_actual_sample_callbacks(app, window):
    from apps.research.post_window import SIDE_FIELDS
    assert window.edited_draft() == defaults('comparison')
    assert window.comparison_table.rowCount() == len(SIDE_FIELDS)
    assert [window.comparison_table.horizontalHeaderItem(column).text() for column in range(3)] == ['Field', 'A', 'B']
    for row, key in enumerate(SIDE_FIELDS):
        for column, side in ((1, 'a'), (2, 'b')):
            field = window.comparison_table.cellWidget(row, column)
            assert field is window.fields[(side, key)][0]
            assert field.objectName() == 'post.' + side + '.' + key
    for side, ref in (('a', 'Sfirst'), ('b', 'Ssecond')):
        edit(window, (side, 'source_ref'), ref)
        edit(window, (side, 'array'), 'stress')
        window.use_declarations(side)
    edit(window, ('tolerance',), '0.001')
    draft = window.edited_draft()
    assert draft['a']['units'] == draft['b']['units'] == 'MPa'
    assert draft['a']['time'] is None and draft['a']['time_origin'] is None
    window.preview()
    wait(app, lambda: len(window.client.calls) == 2 and window._pending is None and not window._busy)
    assert [row[1] for row in window.client.calls] == ['post.comparison_edit', 'post.mapping_validate']
    assert window._object_ref == 'A1' and window.apply_button.isEnabled()
    window.apply_button.click()
    wait(app, lambda: window._pending is None and not window._busy)
    assert window.client.calls[-1][1:] == ('post.apply', {'object_ref': 'A1'})
    window.point_index.setText('4')
    window.read_samples()
    wait(app, lambda: window._samples is not None and window._pending is None and not window._busy)
    assert window.client.calls[-1][2]['point_index'] == 4
    headers = [window.samples.horizontalHeaderItem(i).text() for i in range(window.samples.columnCount())]
    assert window.samples.item(0, headers.index('b')).text() == 'null'
    assert window.samples.item(0, headers.index('validity_reason')).text() == 'outside_domain'
    assert all(count == 1 for count in window.client.execute_count.values())


def test_late_draft_edits_survive_completion_without_preview_or_save_continuation(app, window):
    window.client.release = False
    edit(window, ('a', 'units'), 'Pa')
    window.preview()
    wait(app, lambda: window._pending is not None and window._pending.get('command') is not None)
    assert not window.apply_button.isEnabled() and not window.preview_button.isEnabled()
    edit(window, ('a', 'units'), 'MPa')
    window.client.release = True
    wait(app, lambda: window._pending is None and not window._busy)
    assert window.document['generation'] == 1
    assert window.local_dirty and window.edited_draft()['a']['units'] == 'MPa'
    assert window.client.document['state']['analysis']['objects'][0]['draft']['a']['units'] == 'Pa'
    assert [row[1] for row in window.client.calls] == ['post.comparison_edit']


def test_lost_submission_reply_recovers_same_id_without_repeat(app, window):
    window.client.lose_reply = True
    window.store_draft()
    wait(app, lambda: not window._busy and window._pending is not None and 'unconfirmed' in window.progress.text())
    identifier = window._pending['request']['command_id']
    assert window.retry_button.isEnabled()
    window.recover_request()
    wait(app, lambda: not window._busy and window._pending is None)
    assert [row[0] for row in window.client.calls] == [identifier]
    assert window.client.execute_count[identifier] == 1
    assert window._object_ref == 'A1'


def test_fresh_generation_preflight_refuses_silent_native_overwrite(app, window):
    edit(window, ('a', 'frame'), 'explicit frame')
    window.client.document['generation'] = 9
    window.store_draft()
    wait(app, lambda: not window._busy)
    assert not window.client.calls and window.conflict and window.local_dirty
    window.refresh_document(explicit=True)
    wait(app, lambda: not window._busy)
    assert window.document['generation'] == 9 and not window.conflict
    assert window.edited_draft()['a']['frame'] == 'explicit frame'


def test_filter_settings_original_measurement_capture_and_source_registration(app, window):
    window._source_ref = 'Sfirst'
    window.new_object('filter')
    window.filter_kind.setCurrentText('PlotOverLine')
    edit(window, ('settings', 'array'), 'stress')
    for key, text in [('point1', '0, 0, 0'), ('point2', '1, 2, 3'), ('resolution', '25'), ('tolerance', '0.01')]:
        edit(window, ('settings', key), text)
    draft = window.edited_draft()
    assert draft['settings']['point2'] == [1, 2, 3] and draft['settings']['resolution'] == 25
    window.store_draft()
    wait(app, lambda: not window._busy and window._pending is None)
    window.new_object('measurement')
    edit(window, ('array',), 'stress')
    window.capture_selection()
    wait(app, lambda: not window._busy and window._pending is None)
    assert window.edited_draft()['point_indices'] == [2, 8]
    assert window._object_ref == 'Acaptured'
    window.register_source('approved', '큰 결과.vtu')
    wait(app, lambda: not window._busy and window._pending is None and window.client.calls[-1][1] == 'post.source_add')
    assert window.client.calls[-1][2] == {'input_id': 'Dregistered'}
    window._source_ref = 'Sfirst'
    window.inspect_source()
    wait(app, lambda: not window._busy and window._pending is None)
    assert window.client.calls[-1][2] == {'target': {'source_id': '101'}}


def test_unavailable_source_keeps_object_editable_and_background_keeps_selection(app, window):
    window.client.document['state']['analysis']['sources'][0]['available'] = False
    window._source_ref = 'Sfirst'
    window._tree_selection = ('source', 'Sfirst')
    edit(window, ('a', 'measure'), 'unfinished physical measure')
    snapshot = window.edited_draft()
    window.refresh_document()
    wait(app, lambda: not window._busy)
    assert window.edited_draft() == snapshot and window.local_dirty
    assert window.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == ('source', 'Sfirst')
    assert window.repair_button.isEnabled()


@pytest.mark.parametrize('repair', [False, True])
def test_modal_folder_registration_native_continuation_cannot_be_lost_to_timer_reads(app, window, monkeypatch, repair):
    window._source_ref = 'Sfirst'
    selections = []
    window.client.local_roots = lambda: {'roots': [{'id': 'approved'}]}
    def listed(root, relative, **kwargs):
        selections.append(relative)
        return {'entries': [{'name': 'nested', 'relative': 'nested', 'directory': True}]} if not relative else {
            'entries': [{'name': '실제 결과.vtu', 'relative': 'nested/실제 결과.vtu', 'directory': False}]}
    window.client.local_inputs = listed
    def choose(*args, **kwargs):
        assert window._busy and window._accepting
        assert window.refresh_document() is False
        app.processEvents()
        choices = args[3]
        return next(label for label in choices if label != '.. parent folder'), True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    window.choose_source(repair=repair)
    wait(app, lambda: not window._busy and window._pending is None and bool(window.client.calls))
    assert selections == ['', 'nested']
    expected = {'input_id': 'Dregistered'}
    if repair:
        expected['source_ref'] = 'Sfirst'
    assert [row[1:] for row in window.client.calls] == [('post.source_repair' if repair else 'post.source_add', expected)]
    assert all(count == 1 for count in window.client.execute_count.values())


def test_changed_source_during_modal_choice_does_not_repair_another_source(app, window, monkeypatch):
    window._source_ref = 'Sfirst'
    window.client.local_roots = lambda: {'roots': [{'id': 'approved'}]}
    def choose(*args, **kwargs):
        assert window._busy and window._accepting
        window._source_ref = 'Ssecond'
        app.processEvents()
        return 'approved', True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    window.choose_source(repair=True)
    wait(app, lambda: not window._busy)
    assert not window.client.calls and window._pending is None


def test_exact_native_view_selection_apply_show_overlay_source_and_disappeared_view(app, window):
    window.client.document['state']['views'] = [
        {'view_id': '301', 'type': 'RenderView'}, {'view_id': '302', 'type': 'XYChartView'}]
    window.refresh_document(explicit=True)
    wait(app, lambda: not window._busy)
    before_draft = window.edited_draft()
    window.view_selector.setCurrentIndex(window.view_selector.findData('302'))
    assert window.edited_draft() == before_draft and not window.local_dirty
    window.new_object('measurement')
    window.measurement_kind.setCurrentText('path')
    window.preview()
    wait(app, lambda: not window._busy and window._pending is None and len(window.client.calls) == 2)
    window.apply_button.click()
    wait(app, lambda: not window._busy and window._pending is None)
    assert window.client.calls[-1][1:] == ('post.apply', {'object_ref': 'A1', 'view_id': '302'})
    edit(window, ('array',), 'unfinished new local array')
    snapshot = window.edited_draft()
    assert window.show_applied_button.isEnabled()
    window.show_applied_button.click()
    wait(app, lambda: not window._busy and window._pending is None)
    assert window.client.calls[-1][1:] == ('post.show_analysis', {'object_ref': 'A1', 'view_id': '302'})
    assert window.edited_draft() == snapshot and window.local_dirty
    window._source_ref = 'Sfirst'
    assert window.show_source() is False  # A chart is not a source RenderView.
    window.view_selector.setCurrentIndex(window.view_selector.findData('301'))
    window.show_source()
    wait(app, lambda: not window._busy and window._pending is None)
    assert window.client.calls[-1][1:] == ('post.source_select', {'source_ref': 'Sfirst', 'show': True, 'view_id': '301'})
    window.client.document['state']['views'] = []
    window.refresh_document(explicit=True)
    wait(app, lambda: not window._busy)
    assert window.view_selector.currentData() == '301'
    before = len(window.client.calls)
    assert window.object_command('post.show_analysis') is False
    assert len(window.client.calls) == before and 'unavailable' in window.message.text()


def test_measurement_optional_declarations_stay_unknown_until_explicit_edit(app, window):
    from apps.research.post_window import MEASUREMENT_DECLARATIONS
    window.new_object('measurement')
    assert window.view_selector.itemText(0) == 'Owned view / new appropriate view'
    assert not any(key in window.edited_draft() for key in MEASUREMENT_DECLARATIONS)
    supplied = {'quantity': 'stress', 'units': 'MPa', 'measure': 'Cauchy', 'frame': 'lab',
                'coordinate_units': 'mm', 'coordinate_frame': 'lab'}
    for key, value in supplied.items():
        edit(window, (key,), value)
    window.measurement_kind.setCurrentText('time')
    assert all(window.edited_draft()[key] == value for key, value in supplied.items())
    window.store_draft()
    wait(app, lambda: not window._busy and window._pending is None)
    retained = window.client.calls[-1][2]['draft']
    assert all(retained[key] == value for key, value in supplied.items())


def test_actual_http_native_command_queue_and_exact_proxy_inspection(app, tmp_path):
    """Actual local HTTP/Qt; native owner dispatch is an explicit software fixture."""
    import threading
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.workbench_client import Client

    server = LabHTTPServer(LabService(tmp_path / 'workspace'), 0)
    controller = server.workbench.native_commands
    descriptor = deepcopy(NativeClient().document)
    descriptor.pop('session_id')
    descriptor.pop('connected')
    descriptor.update(view_generation=0, dirty=False, capabilities=['post.inspect', 'document.save'])
    registration = controller.register(host_id='Hfixture', session_id='Snative', application='paraview',
        version='CONTROLLED SOFTWARE OWNER FIXTURE', execution_mode='gui', documents=[descriptor], registration_nonce='a' * 40)
    stop, dispatched = threading.Event(), []

    def owner_fixture():
        while not stop.is_set():
            request = controller.next('Hfixture', session_id='Snative', host_token=registration['host_token'])['command']
            if request is None:
                time.sleep(.005)
                continue
            dispatched.append(deepcopy(request))
            controller.event('Hfixture', session_id='Snative', host_token=registration['host_token'],
                event='started', command_id=request['command_id'])
            assert request['operation'] == 'post.inspect' and request['target'] == {'source_id': '101'}
            result = {'status': 'COMPLETED', 'result': {'data': {'arrays': [{'name': 'CONTROLLED_ARRAY',
                'association': 'POINTS', 'components': 1, 'units': None, 'metadata_status': 'UNKNOWN'}]}}}
            controller.event('Hfixture', session_id='Snative', host_token=registration['host_token'],
                event='finished', command_id=request['command_id'], documents=[descriptor],
                outcome={'state': 'SUCCEEDED', 'result': result})

    serve = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    native = threading.Thread(target=owner_fixture, daemon=True)
    serve.start()
    native.start()
    client = Client('http://127.0.0.1:' + str(server.server_port))
    window = PostWindow(client, document_id='Dpost', session_id='Snative', auto_open=False, poll_interval=0)
    try:
        window.refresh_document(initial=True)
        wait(app, lambda: not window._busy and window.document is not None)
        window._source_ref = 'Sfirst'
        window.inspect_source()
        wait(app, lambda: not window._busy and window._pending is None and bool(dispatched))
        assert len(dispatched) == 1
        assert window.array_table.item(0, 0).text() == 'CONTROLLED_ARRAY'
        assert window.array_table.item(0, 3).text() == 'null'
        assert client.command_status(dispatched[0]['command_id'])['state'] == 'SUCCEEDED'
    finally:
        window._allow_close = True
        window.close()
        stop.set()
        native.join(timeout=2)
        server.shutdown()
        server.server_close()
        serve.join(timeout=2)
        server.workbench.shutdown()
