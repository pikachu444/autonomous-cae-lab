"""Bounded large-table and fresh-process reads for the existing Data recipe.

Run through scripts/native_check.py. No numerical job or provider is submitted.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from check_recipe_windows import (QApplication, DataWindow, DataProcessingInspectorDialog,
    DataProcessingRecipeDialog, ProcessingSampleTraceDialog, LabService, LabHTTPServer,
    RecordingClient, NumericalWindow, apply_appearance, canonical_hash, command, modal,
    picture, settled, wait)


def source_snapshot(output):
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import qVersion
    root = Path(__file__).resolve().parents[2]
    sources = [Path(__file__), Path(__file__).with_name('check_recipe_windows.py'),
        root / 'apps/research/data_processing_inspector.py', root / 'apps/research/data_window.py']
    hashes = {}
    for source in sources:
        raw = source.read_bytes(); hashes[str(source.relative_to(root))] = hashlib.sha256(raw).hexdigest()
        (output / ('checked-' + source.name)).write_bytes(raw)
    (output / 'source-manifest.json').write_text(json.dumps(dict(files=hashes, interpreter=sys.executable,
        pyside_version=pyside_version, qt_version=qVersion()), ensure_ascii=False, indent=2), encoding='utf-8')


def large(output):
    output.mkdir(parents=True, exist_ok=False)
    source_snapshot(output)
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    service = LabService(output / 'store'); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = RecordingClient(f'http://127.0.0.1:{server.server_port}'); windows = []
    try:
        raw = ('time,force\n' + ''.join(f'{i / 10:.1f},{i}\n' for i in range(1005))).encode()
        (output / 'input.csv').write_bytes(raw)
        source = client.upload('긴 하중 이력.csv', raw)
        column = dict(column=1, unit='N', measure='force', component='xx', location='material_point',
            frame='material_cartesian', row_selection={'exclude_rows': []}, axis=dict(column=0, name='time', unit='s'))
        document = client.document_open(kind='data', title=source['name'], draft=dict(data_id=source['id'],
            mapping=dict(delimiter=',', skip_header=1, columns={'force': column})))
        window = DataWindow(client, auto_open=False, poll_interval=0); windows.append(window); window.show()
        window.open_document(document_id=document['id'])
        wait(app, lambda: settled(window) and bool(window._preview) and bool(window._source_table), 'large raw preview and table')
        raw_preview = window._preview['table_preview']
        assert 0 < len(raw_preview['rows']) < 1005
        reads = client.reads.copy()
        for unit in ('kN', 'N'):
            window.mapping.item(1, 3).setText(unit); app.processEvents()
        assert client.reads == reads, 'local mapping edit performed source HTTP read'
        assert window.edited_draft()['mapping']['columns']['force']['axis']['unit'] == 's'
        assert window.edited_draft()['mapping']['columns']['force']['unit'] == 'N'
        # Apply the explicit final mapping, then exactly one existing import job.
        window.apply_inputs(); wait(app, lambda: settled(window) and not window.local_dirty)
        document = command(client, client.document_read(document['id']), 'data.import')
        job = document['runs'][-1]['job_id']
        wait(app, lambda: client.status(job)['state'] in ('SUCCEEDED', 'FAILED'), 'large import')
        assert client.status(job)['state'] == 'SUCCEEDED'
        window._show_document(client.document_read(document['id'])); window.refresh_result()
        wait(app, lambda: settled(window) and window.result_channel.count() == 1)
        recipe = dict(version=1, operations=[
            dict(id='Ostress', operation='nominal_stress', input='force', output='P11', settings=dict(A0=10., area_unit='mm2')),
            dict(id='Ogrid', operation='resample', input='P11', output='P_grid', settings=dict(method='linear', max_gap=.11, range=[0., 100.4], step=.05))])
        def edit(dialog): dialog.recipe = deepcopy(recipe); dialog._show(); dialog.accept()
        with modal(DataProcessingRecipeDialog, edit): window.processing_recipe_action.trigger()
        window.apply_inputs(); wait(app, lambda: settled(window) and not window.local_dirty)
        with modal(DataProcessingInspectorDialog, lambda dialog: dialog.accept()):
            window.preview_processing(); wait(app, lambda: settled(window) and len(window.document.get('processing_revisions', [])) == 1)
        window.save_document(); wait(app, lambda: settled(window) and not window.document['dirty'])
        document = client.document_read(document['id']); revision = document['processing_revisions'][0]['id']
        result = client.data_material('data.processing.result', dict(document_id=document['id'], processing_revision=revision))
        assert len(result['channels']['force']['values']) == 1005
        channel = result['channels']['P_grid']; assert len(channel['values']) == 2009
        assert channel['axis']['unit'] == 's' and channel['metadata']['unit'] == 'MPa'
        assert len(result['responses']['P_grid']['value']) == 2009
        inspector = DataProcessingInspectorDialog(result, window, retained=True); windows.append(inspector)
        inspector.show(); inspector.channel.setCurrentText('P_grid'); app.processEvents()
        assert inspector.table.rowCount() == 1000 and '2009개' in inspector.audit_count.text()
        assert '처음 1000' not in inspector.status.text()
        reads = client.reads.copy()
        inspector.page_start.setValue(1001); inspector.table.setCurrentCell(1, 0)
        sid = channel['samples'][1001]['sample_id']; trace = deepcopy(inspector._trace)
        assert inspector.selected_sample_index() == 1001 and trace['sample_id'] == sid
        assert sorted(term['raw_ref']['source_row'] for term in trace['terms']) == [501, 502]
        inspector.channel.setCurrentText('P11'); inspector.table.setCurrentCell(2, 0)
        inspector.channel.setCurrentText('P_grid')
        assert inspector.page_start.value() == 1001 and inspector.selected_sample_index() == 1001
        assert inspector._trace == trace
        picture(app, inspector, output / 'large-preview.png'); picture(app, inspector, output / 'large-preview-narrow.png', True)
        detail = ProcessingSampleTraceDialog(channel, 1001, trace, inspector._segments[1001], inspector); windows.append(detail)
        detail.show(); picture(app, detail, output / 'large-trace.png'); detail.close()
        inspector.page_start.setValue(2001)
        assert inspector.table.rowCount() == 9 and inspector.table.item(8, 0).text() == '2009'
        assert client.reads == reads, 'page/channel/trace inspection performed HTTP reload'
        assert client.document_read(document['id']) == document
        summary = dict(status='PASS', store=str((output / 'store').resolve()),
            data=[dict(document_id=document['id'], processing_revision=revision, result_sha256=canonical_hash(result))],
            raw_preview_rows=len(raw_preview['rows']), raw_processing_rows=1005, processed_samples=2009, displayed_page_rows=1000,
            selected_sample_id=sid, selected_trace=trace, page_selection_reads=0, imports=1, fit_solver_provider_runs=0)
        (output / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('data','selected_trace')}))
    finally:
        for window in reversed(windows):
            if hasattr(window, '_allow_close'): window._allow_close = True
            window.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


def cold(output, source):
    output.mkdir(parents=True, exist_ok=False)
    source_snapshot(output)
    expected = json.loads((source / 'result.json').read_text(encoding='utf-8'))
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    service = LabService(Path(expected['store'])); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = RecordingClient(f'http://127.0.0.1:{server.server_port}'); windows = []
    try:
        jobs = client.request('/api/workbench')['jobs']; traces = []
        from caelab.data_processing_lineage import trace_sample
        for index, receipt in enumerate(expected['data']):
            document = client.document_read(receipt['document_id'])
            result = client.data_material('data.processing.result', dict(document_id=document['id'], processing_revision=receipt['processing_revision']))
            assert canonical_hash(result) == receipt['result_sha256']
            name = 'P_grid' if 'processed_samples' in expected or index == 0 else 'P_segment'
            channel = result['channels'][name]; sample_index = 1001 if 'processed_samples' in expected else 1
            trace = trace_sample(channel, channel['samples'][sample_index]['sample_id'])
            traces.append(dict(document_id=document['id'], channel=name, trace=trace))
            inspector = DataProcessingInspectorDialog(result, retained=True, allow_plan=True); windows.append(inspector)
            inspector.show(); inspector.channel.setCurrentText(name)
            inspector.page_start.setValue(1001 if sample_index == 1001 else 1)
            inspector.table.setCurrentCell(1, 0)
            assert inspector._trace == trace
            picture(app, inspector, output / f'cold-{index}.png'); inspector.close()
            assert not document['dirty']
            if 'plan_document_id' in expected:
                # Exercise the real current preview action and cancel it. A
                # retained-result read alone is not evidence of this boundary.
                window = DataWindow(client, auto_open=False, poll_interval=0); windows.append(window); window.show()
                window.open_document(document_id=document['id'])
                wait(app, lambda: settled(window) and window.result_channel.count() == 2, 'cold source channel')
                before = client.document_read(document['id'])
                def cancel(dialog):
                    dialog.channel.setCurrentText('P_grid')
                    if index: dialog.table.setCurrentCell(3, 0)
                    picture(app, dialog, output / f'cancel-preview-{index}.png')
                    picture(app, dialog, output / f'cancel-preview-{index}-narrow.png', True)
                    dialog.reject()
                with modal(DataProcessingInspectorDialog, cancel):
                    window.preview_processing(); wait(app, lambda: settled(window), 'cancel current preview')
                assert client.document_read(document['id']) == before
                window._allow_close = True; window.close()
        if 'plan_document_id' in expected:
            plan = client.document_read(expected['plan_document_id'])
            args = server.workbench._document_owner(plan['id']).job_arguments(plan['draft'])
            assert args['frozen_inclusion'] == expected['frozen_inclusion'] and not plan['runs']
            numerical = NumericalWindow(client, document_id=plan['id'], poll_interval=0); windows.append(numerical); numerical.show()
            wait(app, numerical.can_stage_processed_trial, 'cold Plan')
            picture(app, numerical, output / 'cold-plan.png')
            # The previous incompatible editable Plan remains available and its
            # original existing compiler still refuses the same observation.
            rejected = []
            for row in client.documents()['documents']:
                if row['kind'] != 'numerical' or row['id'] in (plan['id'], expected.get('blocked_plan_document_id')): continue
                old = client.document_read(row['id'])
                try: server.workbench._document_owner(old['id']).job_arguments(old['draft'])
                except ValueError as error:
                    rejected.append(dict(document_id=old['id'], message=str(error), draft_diagnostics=old.get('diagnostics')))
        else:
            assert traces[0]['trace'] == expected['selected_trace']; rejected = []
        assert client.request('/api/workbench')['jobs'] == jobs
        summary = dict(status='PASS', cold_owner=True, exact_result_hashes=True, exact_frozen_inclusion='plan_document_id' in expected,
            traces=traces, preserved_refusals=rejected, jobs_before=len(jobs), jobs_after=len(jobs), new_runs=0)
        (output / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('traces', 'preserved_refusals')}))
    finally:
        for window in reversed(windows):
            if hasattr(window, '_allow_close'): window._allow_close = True
            window.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cold', type=Path)
    options = parser.parse_args()
    if options.cold: cold(options.output.resolve(), options.cold.resolve(strict=True))
    else: large(options.output.resolve())
