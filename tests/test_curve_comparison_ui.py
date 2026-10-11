"""Actual offscreen Qt retained comparisons, no model/native evaluation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import math
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtWidgets import QApplication
from apps.research.curve_comparison_window import CurveComparisonWindow

A = {'document_id': 'Mactual', 'job_id': 'Jactual', 'response': 'stress'}
B = {'document_id': 'Pactual', 'job_id': 'Jpde', 'response': 'native-u@7'}


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    end = time.monotonic() + 6
    while time.monotonic() < end:
        app.processEvents()
        if predicate(): return
        time.sleep(.005)
    raise AssertionError('Retained comparison request did not settle')


def record():
    return {'id': 'Kexact', 'binding': {'source': {**A, 'input_revision': 'Iactual', 'input_sha256': 'a'*64, 'response_sha256': 'c'*64},
        'prediction_source': {**B, 'input_revision': 'Ipde', 'input_sha256': 'b'*64, 'response_sha256': 'd'*64}},
        'page': {'start': 0, 'count': 4, 'total': 4}, 'comparison': {
        'method': 'linear_axis_alignment', 'alignment_policy': 'exact_samples_preserving_calculation_gaps',
        'unit': 'Pa', 'rmse': .5, 'count': 3, 'prediction': [1.5, 2.5, 3.5, 4.5],
        'mask': [True, False, True, True], 'residual': [.1, .1, .1],
        'observation': {'kind': 'series', 'unit': 'Pa', 'value': [1., 2., 3., 4.],
            'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1., 2., 3.]}]},
        'observation_source_rows': [1, 2, 8, 9],
        'observation_segments': [{'rows': [0, 2], 'source_rows': [1, 2]}, {'rows': [2, 4], 'source_rows': [8, 9]}],
        'prediction_metadata': {'component': 'xx', 'measure': 'Cauchy', 'frame': 'declared frame'}}}


class RetainedClient:
    def __init__(self, saved=False):
        self.calls = []; self.fail_save = False; self.foreign = False
        self.entered, self.release = threading.Event(), threading.Event()
        self.delay = False
        self.docs = {
            'Mactual': {'id': 'Mactual', 'kind': 'material', 'title': 'Original Material', 'session_id': 'Sowner', 'generation': 2,
                'runs': [{'job_id': 'Jactual', 'input_revision': 'Iactual', 'input_sha256': 'a'*64}], 'comparisons': []},
            'Pactual': {'id': 'Pactual', 'kind': 'pde', 'title': 'Retained PDE', 'session_id': 'Sowner', 'generation': 0,
                'runs': [{'job_id': 'Jpde', 'input_revision': 'Ipde', 'input_sha256': 'b'*64}], 'comparisons': []},
        }
        if saved: self.retain(True)

    def retain(self, saved=False):
        payload = record()
        self.docs['Mactual']['comparisons'] = [{'id': payload['id'], 'binding': payload['binding'], 'metrics': {'rmse': .5, 'unit': 'Pa'},
                                               **({'retained_revision': 'Rsaved'} if saved else {})}]

    def documents(self): return {'documents': deepcopy(list(self.docs.values()))}
    def document_read(self, identifier): return deepcopy(self.docs[identifier])
    def document_result_metadata(self, identifier, job):
        self.calls.append(('metadata', identifier, job))
        return {'execution_counts': {'SUCCEEDED': 1}, 'responses': [{'response': 'stress', 'kind': 'series', 'unit': 'Pa'},
            {'response': 'maximum', 'kind': 'scalar', 'unit': 'Pa'}],
            'native_channels': {'native-u': {'kind': 'series', 'unit': 'Pa', 'node_ids': [7, 31], 'selector_template': 'native-u@<node_id>'},
                'force': {'unit': 'N', 'source': {'selector': 'exact-force'}},
                'gauss': {'unit': 'Pa', 'selectors': [{'label': 'Element 3 / Gauss 2', 'selector': 'stress@3:gp2'}]}}}

    def document_compare(self, source, prediction_source):
        self.calls.append(('compare', deepcopy(source), deepcopy(prediction_source)))
        if self.delay:
            self.entered.set(); assert self.release.wait(5)
        payload = record(); payload['binding']['prediction_source'].update(prediction_source)
        if self.foreign: payload['binding']['source']['job_id'] = 'Jforeign'
        self.retain(); self.docs['Mactual']['generation'] += 1
        return payload

    def document_comparison(self, identifier, comparison, *, start, count):
        self.calls.append(('page', identifier, comparison, start, count))
        payload = record(); stop = min(4, start + count)
        payload['page'] = {'start': start, 'count': max(0, stop - start), 'total': 4}
        c = payload['comparison']
        for key in ('prediction', 'mask', 'observation_source_rows'): c[key] = c[key][start:stop]
        c['observation']['value'] = c['observation']['value'][start:stop]
        c['observation']['axes'][0]['values'] = c['observation']['axes'][0]['values'][start:stop]
        c['observation_segments'] = [{'rows': [max(start, s['rows'][0]), min(stop, s['rows'][1])]} for s in c['observation_segments'] if max(start, s['rows'][0]) < min(stop, s['rows'][1])]
        return payload

    def document_command(self, **request):
        self.calls.append(('save', deepcopy(request)))
        if self.fail_save:
            self.fail_save = False
            raise OSError('controlled lost Save response')
        self.retain(True)
        return {'command_id': request['command_id'], 'document': self.document_read(request['identifier'])}


def opened(app, client, **options):
    window = CurveComparisonWindow(client, source=A, **options)
    wait(app, lambda: not window._busy and not window._queue and window.responses.count() > 0)
    window.documents.setCurrentIndex(window.documents.findData('Pactual'))
    wait(app, lambda: not window._busy and not window._queue and window.responses.count() > 0)
    window.responses.setCurrentIndex(window.responses.findData('native-u@7'))
    return window


def test_actual_catalog_and_selected_comparison_gap_table(app):
    client = RetainedClient(); window = opened(app, client)
    try:
        choices = [window.responses.itemData(i) for i in range(window.responses.count())]
        assert choices == ['stress', 'native-u@7', 'native-u@31', 'exact-force', 'stress@3:gp2']
        window.compare(); wait(app, lambda: not window._busy and not window._queue)
        assert ('compare', A, B) in client.calls
        assert window.values.rowCount() == 4
        assert window.values.item(2, 1).text() == '8'
        assert window.values.item(1, 6).text() == '—'
        assert window.values.item(2, 6).text() == '0.5'  # Actual B-A, not normalized fitting residual.
        assert len(window.axes.lines) == 4  # A and B independently preserve both original segments.
        assert math.isnan(window.axes.lines[2].get_ydata()[1])
        assert 'exact_samples_preserving_calculation_gaps' in window.detail.toPlainText()
        assert 'response_sha256' in window.detail.toPlainText()
    finally: window.close()


def test_saved_reopen_and_global_page_segments_without_compare(app):
    client = RetainedClient(saved=True); window = opened(app, client)
    try:
        assert window._comparison['id'] == 'Kexact'
        window.start.setValue(1); window.count.setValue(2); window.read_page()
        wait(app, lambda: not window._busy)
        assert ('page', 'Mactual', 'Kexact', 1, 2) in client.calls
        assert window.values.item(0, 0).text() == '1'
        assert window.values.item(1, 1).text() == '8'
        assert [list(line.get_xdata()) for line in window.axes.lines] == [[1.], [2.], [1.], [2.]]
        assert not any(row[0] == 'compare' for row in client.calls)
        assert window.count.maximum() == 4096
    finally: window.close()


def test_foreign_reply_keeps_previous_view(app):
    client = RetainedClient(saved=True); window = opened(app, client)
    try:
        before = deepcopy(window._comparison); client.foreign = True
        window.compare(); wait(app, lambda: not window._busy)
        assert window._comparison == before
        assert 'identity differs' in window.message.text()
    finally: window.close()


def test_unpaged_original_mask_rejected_without_replacing_view(app):
    client = RetainedClient(saved=True); window = opened(app, client)
    try:
        previous = deepcopy(window._comparison)
        page = client.document_comparison('Mactual', 'Kexact', start=1, count=2)
        page['comparison']['observation']['mask'] = [True, False, True, True]
        window._display(page)
        assert window._comparison == previous
        assert 'validity mask does not match' in window.message.text()
    finally: window.close()


def test_late_selected_response_reply_ignored_and_foreground_locked(app):
    client = RetainedClient(); window = opened(app, client)
    try:
        client.delay = True; window.compare(); wait(app, client.entered.is_set)
        assert not window.compare_button.isEnabled() and not window.responses.isEnabled()
        window.responses.setCurrentIndex(window.responses.findData('native-u@31'))
        client.release.set(); wait(app, lambda: not window._busy)
        assert window._comparison is None
        assert window.responses.currentData() == 'native-u@31'
    finally: client.release.set(); window.close()


def test_late_origin_owner_reply_ignored(app):
    client = RetainedClient(); current = [True]
    window = opened(app, client, relevant=lambda: current[0])
    try:
        client.delay = True; window.compare(); wait(app, client.entered.is_set)
        current[0] = False; client.release.set(); wait(app, lambda: not window._busy)
        assert window._comparison is None
        assert not window.save_button.isEnabled()
    finally: client.release.set(); window.close()


def test_save_fresh_generation_exact_receipt_retry_and_session_change(app):
    client = RetainedClient(saved=True); window = opened(app, client)
    try:
        client.docs['Mactual']['generation'] = 7; client.fail_save = True
        window.save(); wait(app, lambda: not window._busy and not window._queue)
        pending = deepcopy(window._save_request)
        assert pending['expected_generation'] == 7
        assert pending['operation'] == 'document.save' and pending['arguments'] == {}
        assert not window.compare_button.isEnabled() and not window.save_button.isEnabled()
        client.docs['Mactual']['session_id'] = 'Srestart'
        window.retry_save_receipt(); wait(app, lambda: not window._busy)
        assert window._save_request == pending
        assert len([c for c in client.calls if c[0] == 'save']) == 1
        client.docs['Mactual']['session_id'] = 'Sowner'
        window.retry_save_receipt(); wait(app, lambda: not window._busy and not window._queue)
        assert [c[1] for c in client.calls if c[0] == 'save'] == [pending, pending]
        assert window._save_request is None
    finally: window.close()


def test_owner_session_change_blocks_new_comparison(app):
    client = RetainedClient(); window = opened(app, client)
    try:
        client.docs['Mactual']['session_id'] = 'Srestart'
        window.compare(); wait(app, lambda: not window._busy)
        assert not any(c[0] == 'compare' for c in client.calls)
        assert 'session changed' in window.message.text()
    finally: window.close()


def test_refresh_preserves_explicit_b_job_and_response(app):
    client = RetainedClient()
    client.docs['Pactual']['runs'].append({'job_id': 'Jsecond', 'input_revision': 'Isecond', 'input_sha256': 'e'*64})
    window = opened(app, client)
    try:
        window.jobs.setCurrentIndex(window.jobs.findData('Jsecond'))
        wait(app, lambda: not window._busy and not window._queue)
        window.responses.setCurrentIndex(window.responses.findData('stress@3:gp2'))
        window.refresh(); wait(app, lambda: not window._busy and not window._queue)
        assert window.documents.currentData() == 'Pactual'
        assert window.jobs.currentData() == 'Jsecond'
        assert window.responses.currentData() == 'stress@3:gp2'
    finally: window.close()


def test_actual_csv_owner_compare_save_restart_reopen(app, tmp_path):
    from apps.lab.server import LabHTTPServer
    from apps.lab.service import LabService
    from caelab.data_document import default_draft
    from caelab.workbench_client import Client
    def serve():
        server = LabHTTPServer(LabService(tmp_path), 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
        thread.start()
        return server, thread, Client('http://127.0.0.1:' + str(server.server_port))
    def stop(server, thread):
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    server, thread, client = serve()
    wb = server.workbench
    def imported(name, shift):
        upload = wb.upload(name, f't,v\n0,{1+shift}\n1,nan\n2,{3+shift}\n'.encode())
        draft = default_draft(); draft['data_id'] = upload['id']; draft['mapping']['skip_header'] = 1
        spec = draft['mapping']['columns']['response']
        spec.update(unit='Pa', component='xx', location='point', measure='Cauchy', frame='global')
        spec['axis'].update(name='time', unit='s')
        spec['row_selection'] = {'exclude_rows': [2], 'reasons': {'2': 'recorded missing sample'}}
        doc = wb.document_open(kind='data', draft=draft, title=name)
        receipt = wb.document_command(doc['id'], 'data.import', {}, session_id=doc['session_id'], expected_generation=doc['generation'])
        job = receipt['job']['id']
        end = time.monotonic() + 6
        while wb.manager.status(job)['state'] not in ('SUCCEEDED', 'FAILED') and time.monotonic() < end: time.sleep(.005)
        assert wb.manager.status(job)['state'] == 'SUCCEEDED'
        return doc['id'], job
    window = None
    try:
        a, ja = imported('Independent A.csv', 0); b, jb = imported('Independent B.csv', .25)
        source = {'document_id': a, 'job_id': ja, 'response': 'response'}
        window = CurveComparisonWindow(client, source=source)
        wait(app, lambda: not window._busy and not window._queue and window.responses.count() > 0)
        window.documents.setCurrentIndex(window.documents.findData(b))
        wait(app, lambda: not window._busy and not window._queue and window.jobs.currentData() == jb and window.responses.count() > 0)
        window.compare(); wait(app, lambda: not window._busy and not window._queue)
        assert window._comparison['comparison']['rmse'] == pytest.approx(.25)
        assert [window.values.item(i, 1).text() for i in range(2)] == ['1', '3']
        assert len(window.axes.lines) == 4
        window.save(); wait(app, lambda: not window._busy and not window._queue)
        assert window._save_request is None
        assert wb.document_read(a)['comparisons'][0]['retained_revision']
        assert len(wb.manager.list()) == 2
        window.close(); stop(server, thread)
        server, thread, client = serve(); wb = server.workbench
        client.document_open(kind='data', document_id=a)
        window = CurveComparisonWindow(client, source=source)
        wait(app, lambda: not window._busy and not window._queue and window._comparison is not None)
        assert window._comparison['comparison']['rmse'] == pytest.approx(.25)
        assert len(wb.manager.list()) == 2  # Reopen submits no import/evaluation.
    finally:
        if window: window.close()
        stop(server, thread)
