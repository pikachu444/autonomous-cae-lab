"""Read two preserved invalid samples only; never import or process new data."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from check_recipe_windows import (QApplication, DataProcessingInspectorDialog,
    ProcessingSampleTraceDialog, LabService, LabHTTPServer, RecordingClient,
    apply_appearance, canonical_hash, modal, picture)
from PySide6.QtWidgets import QLabel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acceptance', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    expected = json.loads(args.acceptance.read_text(encoding='utf-8'))
    receipt = expected['data'][1]
    root = Path(__file__).resolve().parents[2]
    snapshots = {}
    for source in (Path(__file__), root / 'apps/research/data_processing_inspector.py'):
        raw = source.read_bytes(); (output / ('checked-' + source.name)).write_bytes(raw)
        snapshots[str(source.relative_to(root))] = hashlib.sha256(raw).hexdigest()
    app = QApplication.instance() or QApplication([]); apply_appearance(app)
    service = LabService(Path(expected['store'])); server = LabHTTPServer(service, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    client = RecordingClient(f'http://127.0.0.1:{server.server_port}'); windows = []; actual = []
    try:
        document = client.document_read(receipt['document_id']); jobs = client.request('/api/workbench')['jobs']
        result = client.data_material('data.processing.result', dict(document_id=document['id'], processing_revision=receipt['processing_revision']))
        assert canonical_hash(result) == receipt['result_sha256']
        original = deepcopy(result); channel = result['channels']['P_grid']
        inspector = DataProcessingInspectorDialog(result, retained=True); windows.append(inspector); inspector.show()
        inspector.channel.setCurrentText('P_grid')
        failed_stage = next(stage for stage in result['stages'] if stage['id'] == 'Obefore')
        row = next(i for i in range(inspector.stages.rowCount()) if inspector.stages.item(i, 0).text() == 'P_before')
        message = inspector.stages.item(row, 2)
        original_message = failed_stage['error']['message']
        if not args.baseline:
            assert message.text() == '간격이 일정하지 않아 평활화하지 못했습니다. 먼저 재표본화하세요.'
            assert message.toolTip() == original_message
            assert inspector.stage_recovery.text() == message.text()
            assert inspector.stage_recovery.toolTip() == original_message
        for index, rows in ((3, [2, 3]), (7, [4, 5])):
            sample = channel['samples'][index]
            assert sample['source_rows'] == [] and sample['validity_source_rows'] == rows
            assert channel['values'][index] is None
            inspector.table.setCurrentCell(index, 0); app.processEvents()
            assert inspector._trace['terms'] == []
            summary = inspector.sample_status.text()
            def inspect(dialog):
                windows.append(dialog)
                labels = [label.text() for label in dialog.findChildren(QLabel) if '판정 원행' in label.text()]
                assert len(labels) == 1
                status = labels[0]
                if not args.baseline:
                    assert '값 기여 원행: 없음' in status
                    assert '판정 원행: ' + ', '.join(map(str, rows)) in status
                    assert '값 기여 원행 없음' in summary
                    assert '판정 원행 ' + ', '.join(map(str, rows)) in summary
                assert dialog.terms.rowCount() == 0
                picture(app, dialog, output / f'index-{index}-trace.png')
                picture(app, dialog, output / f'index-{index}-trace-narrow.png', True)
                actual.append(dict(index=index, sample_id=sample['sample_id'], value_rows=sample['source_rows'],
                    validity_rows=rows, summary=summary, detail=status, trace_terms=0, value=channel['values'][index]))
                dialog.reject()
            with modal(ProcessingSampleTraceDialog, inspect): inspector.trace_button.click()
            picture(app, inspector, output / f'index-{index}-selection.png')
            picture(app, inspector, output / f'index-{index}-selection-narrow.png', True)
        assert result == original
        assert client.document_read(document['id']) == document and client.request('/api/workbench')['jobs'] == jobs
        result_hash = canonical_hash(client.data_material('data.processing.result', dict(document_id=document['id'], processing_revision=receipt['processing_revision'])))
        assert result_hash == receipt['result_sha256']
        summary = dict(status='KNOWN_P2_BASELINE' if args.baseline else 'PASS', source_snapshots=snapshots,
            document_id=document['id'], processing_revision=receipt['processing_revision'], result_sha256=result_hash,
            samples=actual, stage_original_message=original_message, stage_shown_message=message.text(), stage_tooltip=message.toolTip(),
            document_unchanged=True, jobs_before=len(jobs), jobs_after=len(jobs), new_import_process_fit_solver_provider=0)
        (output / 'result.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('samples', 'source_snapshots')}, ensure_ascii=False))
    finally:
        for window in reversed(windows): window.close()
        app.processEvents(); server.shutdown(); server.server_close(); service.shutdown(); thread.join(5)


if __name__ == '__main__': main()
