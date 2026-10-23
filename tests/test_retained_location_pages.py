"""Retained channel/location navigation; no native solve or provider request.

The large catalog is TEST_ONLY metadata. The HTTP selection uses the existing
manufactured J2 native-record fixture, never a newly executed J2 calculation.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

from caelab.research_operations import result_metadata, response_locations
from apps.research.response_selection import response_choices


@pytest.fixture(autouse=True)
def no_solver_or_provider(monkeypatch):
    from caelab.workbench import Workbench
    def forbidden(*args, **kwargs):
        pytest.fail('Location lookup must not execute a solver, provider or subprocess')
    class ForbiddenProcess(subprocess.Popen):
        # Keep Popen[bytes] usable in the MCP SDK's runtime type annotations.
        # Instantiation still fails before any child could be started.
        def __init__(self, *args, **kwargs):
            forbidden(*args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', ForbiddenProcess)
    monkeypatch.setattr(Workbench, 'submit', forbidden)
    monkeypatch.setattr(Workbench, 'assistance_call', forbidden)


def large_catalog():
    source = {'backend': 'structural.code_aster.plasticity', 'artifact': 'analysis_raw.json',
              'sha256': hashlib.sha256(b'TEST_ONLY parsed bytes').hexdigest(),
              'sha256_kind': 'ARTIFACT_SHA256',
              'manifest_sha256': hashlib.sha256(b'TEST_ONLY dependency inventory').hexdigest(),
              'value_origin': 'NATIVE_COMPONENT',
              'native_origin': {'kind': 'NATIVE_COMPONENT', 'artifact': 'simulation/level_0/results.med',
                                'sha256': hashlib.sha256(b'TEST_ONLY native bytes').hexdigest()}}
    base = {'kind': 'series', 'unit': 'mm', 'component': 'DEPL.DX', 'quantity': 'displacement',
            'measure': 'native DEPL; infinitesimal displacement', 'coordinate_frame': 'global Cartesian mm',
            'location': 'exact native node', 'axes': [{'name': 'time', 'unit': 's',
                'semantics': 'NATIVE_INST_DECLARED_QUASI_STATIC_HISTORY_SECONDS'}], 'source': source,
            'qualification': {'physical': 'UNKNOWN', 'decision': 'NOT_RELEASED'}}
    nodes = [10000 + 7 * i for i in range(506)]
    gauss = [{'element_id': 8000 + i // 5, 'point': i % 5 + 1, 'subpoint': 1} for i in range(300)]
    channels = {}
    for i in range(11):
        name = 'j2.history' + str(i)
        channels[name] = {**deepcopy(base), 'source': {**deepcopy(source), 'selector': name}}
    for field in ('DEPL.DX', 'DEPL.DY', 'DEPL.DZ', 'REAC_NODA.DX', 'REAC_NODA.DY', 'REAC_NODA.DZ'):
        name = 'j2.mesh0.' + field
        item = {**deepcopy(base), 'component': field, 'node_ids': nodes,
                'selector_template': name + '@<node_id>'}
        if field.startswith('REAC'):
            item.update(unit='N', quantity='nodal_reaction', measure='native REAC_NODA component')
        channels[name] = item
    for field in ('SIEF_ELGA.SIXX', 'SIEF_ELGA.SIYY', 'VARI_ELGA.V1'):
        name = 'j2.mesh0.' + field
        item = {**deepcopy(base), 'component': field, 'gauss_ids': gauss,
                'selector_template': name + '@<element_id>:<point>:<subpoint>',
                'selector_count': len(gauss), 'selectors_truncated': True,
                'selectors': [{'label': str(p), 'selector': f"{name}@{p['element_id']}:{p['point']}:{p['subpoint']}"}
                              for p in gauss[:256]],
                'unit': '1' if field == 'VARI_ELGA.V1' else 'MPa',
                'quantity': 'equivalent_plastic_strain' if field == 'VARI_ELGA.V1' else 'stress',
                'measure': 'native V1' if field == 'VARI_ELGA.V1' else 'Cauchy stress; PETIT',
                'location': 'exact native Gauss point'}
        channels[name] = item
    return {'execution_status': 'SUCCEEDED', 'responses': {}, 'native_channels': channels,
            'diagnostics': {'TEST_ONLY': 'catalog shape, not a calculated mesh'}}


def test_all_channels_and_exact_locations_survive_large_catalog():
    result = large_catalog()
    original = deepcopy(result)
    metadata = result_metadata(result)
    choices = response_choices(metadata)
    assert len(choices) == len(result['native_channels'])
    groups = {item.get('channel'): item for item in choices if item.get('requires_location')}
    assert {'j2.mesh0.REAC_NODA.DZ', 'j2.mesh0.SIEF_ELGA.SIXX', 'j2.mesh0.VARI_ELGA.V1'} <= set(groups)
    for name, item in metadata['native_channels'].items():
        retained = result['native_channels'][name]
        assert item['source'] == retained['source']
        assert item['measure'] == retained['measure'] and item['axes'] == retained['axes']
        assert not {'node_ids', 'gauss_ids', 'selectors'} & set(item)
    name = 'j2.mesh0.DEPL.DX'
    pages, start = [], 0
    while start is not None:
        page = response_locations(result, name, start=start, count=128)
        assert len(page['locations']) <= 128 and page['source'] == result['native_channels'][name]['source']
        pages.extend(item['selector'] for item in page['locations'])
        start = page['next_start']
    assert pages == [name + '@' + str(node) for node in result['native_channels'][name]['node_ids']]
    name = 'j2.mesh0.SIEF_ELGA.SIXX'
    page = response_locations(result, name, start=256, count=128)
    assert page['total_count'] == 300 and len(page['locations']) == 44 and page['next_start'] is None
    assert page['locations'][-1]['selector'] == name + '@8059:5:1'
    found = response_locations(result, name, search='8059:5:1')
    assert found['matched_count'] == 1 and found['locations'] == page['locations'][-1:]
    assert result == original


@pytest.mark.parametrize('arguments', [
    {'channel': 'not-a-retained-channel'}, {'channel': 'j2.mesh0.DEPL.DX', 'start': -1},
    {'channel': 'j2.mesh0.DEPL.DX', 'start': True}, {'channel': 'j2.mesh0.DEPL.DX', 'count': 1025},
    {'channel': 'j2.mesh0.DEPL.DX', 'count': 0}, {'channel': 'j2.mesh0.DEPL.DX', 'search': 'x' * 241}])
def test_location_page_rejects_unknown_or_unbounded_request(arguments):
    with pytest.raises(ValueError):
        response_locations(large_catalog(), **arguments)


@pytest.fixture
def retained_http(tmp_path):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.evaluation import _outcome_evaluation, save_evaluation
    from caelab.storage import canonical_hash, save_json, utc_now
    from caelab.workbench_client import Client
    from test_retained_law_responses import saved_j2

    server = LabHTTPServer(LabService(tmp_path / 'workspace'), 0)
    wb = server.workbench
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        job_id = 'Jretained_location_fixture'
        output = wb.root / 'results' / job_id
        native = output / 'native'; native.mkdir(parents=True)
        outcome, fixture = saved_j2(native, selected=True)
        backend = 'structural.code_aster.plasticity'
        result = _outcome_evaluation(outcome, backend=backend, output=native)
        result.update(backend=backend, settings=deepcopy(fixture.settings))
        save_evaluation(result, output, existing=True)
        document = wb.document_open(kind='simulation', title='TEST_ONLY retained J2 record',
                                    draft={'backend': backend, 'settings': fixture.settings})
        arguments = deepcopy(document['draft'])
        job = {'id': job_id, 'job_id': job_id, 'workspace_id': 'local', 'operation': 'simulation.run',
               'arguments': arguments, 'request_id': None,
               'request_hash': canonical_hash({'operation': 'simulation.run', 'arguments': arguments, 'resources': {}}),
               'state': 'SUCCEEDED', 'status': 'SUCCEEDED', 'phase': 'FINISHED', 'created_utc': utc_now(),
               'resources': {}, 'result_refs': [f'results/{job_id}/result.json'], 'cancel_requested': False,
               'TEST_ONLY': 'seeded existing manufactured capture; no job submitted'}
        # Seed an existing-result fixture, then use the real owner/HTTP reader.
        with wb.manager._lock:
            wb.manager._jobs[job_id] = deepcopy(job)
            save_json(wb.root / 'jobs' / (job_id + '.json'), job)
        owner = wb.simulation_documents
        with owner._lock(document['id']):
            working = owner._documents[document['id']]
            working['runs'].append(owner._run_record(job, working['draft'], working['generation'],
                                                     working['input_revision'], owner.session_id))
            owner._persist_draft(working)
        client = Client('http://127.0.0.1:' + str(server.server_port))
        saved = client.document_command(document['id'], 'document.save', {}, session_id=document['session_id'],
                                        expected_generation=document['generation'], command_id='Cretain_fixture')['document']
        assert saved['runs'][0]['retained_result']
        yield SimpleNamespace(server=server, wb=wb, client=client, document=saved, job_id=job_id,
                              result=result, outcome=outcome, fixture=fixture, root=wb.root)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
        assert not thread.is_alive()


def fingerprints(root, *, live_lock=None):
    # A running JobManager's exact lock is not a retained result artifact.
    # Other lock-named files and unreadable retained bytes must still be checked.
    live_lock = None if live_lock is None else Path(live_lock)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p != live_lock and p.is_file()}


def test_http_owner_selects_exact_retained_j2_location_without_execution(retained_http):
    env = retained_http
    live_lock = env.wb.manager._owner.lock_file
    before = fingerprints(env.root, live_lock=live_lock)
    identifier, job = env.document['id'], env.job_id
    metadata = env.client.document_result_metadata(identifier, job)
    channel = 'j2.mesh0.SIEF_ELGA.SIXX'
    page = env.client.document_response_locations(identifier, job, channel, count=2)
    assert page['document_id'] == identifier and page['job_id'] == job and len(page['locations']) == 2
    assert page['source'] == env.result['native_channels'][channel]['source'] == metadata['native_channels'][channel]['source']
    selector = page['locations'][-1]['selector']
    response = env.client.document_result(identifier, job, selection={'responses': [selector]})['responses'][selector]
    assert response['source']['selector'] == selector
    assert response['source']['sha256'] == page['source']['sha256']
    assert response['source']['native_origin']['sha256'] == page['source']['native_origin']['sha256']
    assert response['axes'][0]['values'] == [s['time_s'] for s in env.outcome['mesh_records'][0]['states']]
    selected = response['source']['exact_selection']
    original_values = []
    for state in env.outcome['mesh_records'][0]['states']:
        table = env.fixture.files[f"simulation/level_0/order_{state['actual_result_order']}_sief_elga.table.json"]
        row = next(i for i, element in enumerate(table['MAILLE'])
                   if int(element.strip()) == selected['element_id'] and table['POINT'][i] == selected['point']
                   and table['SOUS_POINT'][i] == selected['subpoint'])
        original_values.append(table['SIXX'][row])
    assert response['value'] == original_values
    assert response['axes'][0]['semantics'] == 'NATIVE_INST_DECLARED_QUASI_STATIC_HISTORY_SECONDS'
    assert response['unit'] == 'MPa' and response['measure'] and response['qualification']['physical'] == 'UNKNOWN'
    from urllib.error import HTTPError
    for name, options in [('missing', {}), (channel, {'count': 1025})]:
        with pytest.raises(HTTPError) as caught:
            env.client.document_response_locations(identifier, job, name, **options)
        assert caught.value.code == 400
    assert len(env.wb.manager.list()) == 1 and fingerprints(env.root, live_lock=live_lock) == before


def test_mcp_location_wrapper_reads_same_http_owner(retained_http, monkeypatch):
    pytest.importorskip('mcp')
    import asyncio
    from openscience import workbench_mcp
    env = retained_http
    monkeypatch.setenv('CAELAB_SERVICE_URL', env.client.url)
    arguments = {'document_id': env.document['id'], 'job_id': env.job_id,
                 'channel': 'j2.mesh0.REAC_NODA.DX', 'start': 1, 'count': 3, 'search': ''}
    live_lock = env.wb.manager._owner.lock_file
    before = fingerprints(env.root, live_lock=live_lock)
    tool = next(t for t in asyncio.run(workbench_mcp.mcp.list_tools()) if t.name == 'document_response_locations')
    assert {'document_id', 'job_id', 'channel'} <= set(tool.inputSchema['required'])
    # FastMCP's actual tool invocation validates the same documented arguments.
    returned = asyncio.run(workbench_mcp.mcp.call_tool('document_response_locations', arguments))
    if isinstance(returned, tuple):
        content, structured = returned
        value = structured or json.loads(content[0].text)
    elif isinstance(returned, dict):
        value = returned
    else:
        value = json.loads(returned[0].text)
    expected = env.client.document_response_locations(env.document['id'], env.job_id,
                                                      arguments['channel'], start=1, count=3)
    assert value == expected and fingerprints(env.root, live_lock=live_lock) == before


@pytest.fixture
def qt_app():
    pytest.importorskip('PySide6')
    pytest.importorskip('matplotlib')
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def modal_choice(app, client, choice, drive, *, relevant=lambda: True):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog
    from apps.research.response_selection import choose_location
    errors, dialogs = [], []
    timer = QTimer(); timer.setInterval(5)
    deadline = time.monotonic() + 8
    def tick():
        dialog = app.activeModalWidget()
        if not isinstance(dialog, QDialog):
            return
        if not dialogs: dialogs.append(dialog)
        try:
            if time.monotonic() >= deadline:
                raise AssertionError('Controlled location dialog did not settle')
            drive(dialog)
        except BaseException as error:
            errors.append(error); dialog.reject()
    timer.timeout.connect(tick); timer.start()
    try:
        result = choose_location(None, client, 'Vexact', 'Jexact', choice, relevant=relevant)
    finally:
        timer.stop()
    if errors: raise errors[0]
    assert dialogs
    return result, dialogs[0]


def test_qt_location_next_search_and_exact_selection(qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialogButtonBox
    result = large_catalog(); calls = []
    choice = next(c for c in response_choices(result_metadata(result)) if c.get('channel') == 'j2.mesh0.DEPL.DX')
    class Pages:
        def document_response_locations(self, document, job, channel, **options):
            calls.append((document, job, channel, options))
            return response_locations(result, channel, **options) | {'document_id': document, 'job_id': job}
    state = [0]
    final_selector = choice['channel'] + '@13535'
    def drive(dialog):
        if dialog._busy: return
        if state[0] == 0 and dialog.items.count() == 128:
            assert dialog.next.isEnabled(); dialog.next.click(); state[0] = 1
        elif state[0] == 1 and dialog.start == 128:
            assert dialog.items.item(0).data(Qt.ItemDataRole.UserRole) == choice['channel'] + '@10896'
            QTest.keyClicks(dialog.search, '13535'); state[0] = 2
        elif state[0] == 2 and dialog.items.count() == 1:
            assert dialog.items.item(0).data(Qt.ItemDataRole.UserRole) == final_selector
            dialog.items.setCurrentRow(0)
            dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
    selected, dialog = modal_choice(qt_app, Pages(), choice, drive)
    assert selected['selector'] == final_selector and selected['requires_location'] is False
    assert selected['definition'] == choice['definition']
    assert any(c[-1]['start'] == 128 for c in calls) and any(c[-1]['search'] == '13535' for c in calls)
    assert all(c[:3] == ('Vexact', 'Jexact', choice['channel']) and c[-1]['count'] == 128 for c in calls)
    dialog.deleteLater(); qt_app.processEvents()


@pytest.mark.parametrize('mode', ['cancel_pending', 'target_changed', 'foreign_reply'])
def test_qt_location_cancel_and_late_target_reply_do_not_adopt(qt_app, mode):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QDialogButtonBox
    result = large_catalog()
    choice = next(c for c in response_choices(result_metadata(result)) if c.get('channel') == 'j2.mesh0.VARI_ELGA.V1')
    started, release = threading.Event(), threading.Event()
    current = [True]
    class Delayed:
        def document_response_locations(self, document, job, channel, **options):
            started.set()
            assert release.wait(8), 'Controlled read was not released'
            return response_locations(result, channel, **options) | {'document_id': document,
                'job_id': 'Jforeign' if mode == 'foreign_reply' else job}
    def drive(dialog):
        if not started.is_set(): return
        if mode == 'cancel_pending':
            dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
            return
        if not release.is_set():
            current[0] = mode != 'target_changed'; release.set()
        if not dialog._busy:
            assert dialog.items.count() == 0
            assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
            assert ('changed' if mode == 'target_changed' else 'another result') in dialog.message.text()
            dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
    try:
        selected, dialog = modal_choice(qt_app, Delayed(), choice, drive, relevant=lambda: current[0])
        assert selected is None
    finally:
        release.set()
        assert QThreadPool.globalInstance().waitForDone(3000)
        qt_app.processEvents()
    assert dialog.items.count() == 0 and dialog.selected is None
    dialog.deleteLater(); qt_app.processEvents()

