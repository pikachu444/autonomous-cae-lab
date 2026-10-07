"""Real browser/workbench smoke with an owned temporary service and synthetic inputs.

Requires the dev and material extras plus Chromium. No existing service/store,
AI account, external search or native solver is used. Output is software evidence,
not measured material qualification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time


def start_service(root, store, log):
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
    process = subprocess.Popen([sys.executable, '-m', 'apps.lab', '--store', str(store), '--port', '0'],
                               cwd=root, stdout=subprocess.PIPE, stderr=log, text=True,
                               creationflags=creation)
    lines = queue.Queue()
    def read_output():
        for line in process.stdout:
            lines.put(line)
    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Owned workbench failed during startup; inspect server.log')
        try:
            line = lines.get(timeout=.2)
        except queue.Empty:
            continue
        match = re.search(r'http://127\.0\.0\.1:(\d+)', line)
        if match:
            return process, 'http://127.0.0.1:' + match[1]
    process.terminate()
    process.wait(timeout=5)
    raise RuntimeError('Owned workbench did not announce its service URL within 30 seconds')


def stop_service(process):
    if process.poll() is None:
        process.send_signal(signal.CTRL_BREAK_EVENT if sys.platform == 'win32' else signal.SIGINT)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired as error:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise RuntimeError('Owned controller failed cooperative shutdown') from error
    if process.returncode != 0:
        raise RuntimeError(f'Owned controller exited with {process.returncode}; inspect server.log')


def browser_flows(url, output, executable=None):
    from playwright.sync_api import sync_playwright, expect
    errors, receipts = [], []
    with sync_playwright() as playwright:
        options = {'headless': True}
        if executable:
            options['executable_path'] = executable
        browser = playwright.chromium.launch(**options)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(url + '/workbench')
            expect(page.locator('#workspace-name')).to_contain_text('local')

            def submit(selector):
                with page.expect_response(lambda response: response.url.endswith('/api/workbench/jobs') and
                                          response.request.method == 'POST') as response:
                    page.click(selector)
                job = response.value.json()
                assert response.value.status == 202, job
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    job = page.request.get(url + '/api/workbench/jobs/' + job['id']).json()
                    if job['state'] in ['SUCCEEDED', 'FAILED', 'PARTIAL_FAILURE', 'CANCELLED', 'INTERRUPTED']:
                        break
                    page.wait_for_timeout(100)
                assert job['state'] == 'SUCCEEDED', job
                result = page.request.get(url + '/api/workbench/results/' + job['id']).json()
                receipts.append({'operation': job['operation'], 'id': job['id'], 'state': job['state'],
                                 'arguments': job['arguments'], 'result': result})
                page.click('#refresh')
                expect(page.locator('#result-select option[value="' + job['id'] + '"]')).to_be_attached()
                return job, result

            page.click('#synthetic-history')
            page.fill('#parameter-a', '1500')
            page.fill('#parameter-b', '.29')
            observation, _ = submit('#evaluate')
            # A distinct synthetic loading condition checks held-out response handling.
            for index, row in enumerate(page.locator('#history-rows tr').all()):
                row.locator('[data-key=f11]').fill(str(1 + .002 * index))
            holdout, _ = submit('#evaluate')
            for index, row in enumerate(page.locator('#history-rows tr').all()):
                row.locator('[data-key=f11]').fill(str(1 + .001 * index))
            page.fill('#parameter-a', '900')
            row = page.locator('#variable-rows tr').first
            for key, value in {'id': 'E', 'unit': 'MPa', 'lower': '500', 'upper': '2500', 'value': '900'}.items():
                row.locator('[data-key=' + key + ']').fill(value)
            row = page.locator('#experiment-rows tr').first
            for key, value in {'id': 'axial-fit', 'response': 'stress_xx', 'observation_response': 'stress_xx'}.items():
                row.locator('[data-key=' + key + ']').fill(value)
            row.locator('[data-key=observation_job]').select_option(observation['id'])
            page.click('#add-experiment')
            row = page.locator('#experiment-rows tr').last
            for key, value in {'id': 'different-amplitude-holdout', 'response': 'stress_xx',
                               'observation_response': 'stress_xx'}.items():
                row.locator('[data-key=' + key + ']').fill(value)
            row.locator('[data-key=role]').select_option('holdout')
            row.locator('[data-key=observation_job]').select_option(holdout['id'])
            row.locator('[data-key=settings]').fill(json.dumps(holdout['arguments']['settings']))
            page.select_option('#study-operation', 'fit')
            page.fill('#study-budget', '60')
            fitted, result = submit('#run-study')
            assert abs(result['parameters']['E'] - 1500) < 1e-3, result['parameters']
            assert {curve['role'] for curve in result['curves']} == {'fit', 'holdout'}
            page.select_option('#result-select', fitted['id'])
            page.click('#load-result')
            expect(page.locator('#response-select option').last).to_contain_text('predicted')
            with page.expect_download() as download:
                page.click('#export-report')
            download.value.save_as(output / 'fit-holdout-report.html')
            report = (output / 'fit-holdout-report.html').read_text()
            assert report.count('<svg ') == 2 and 'RMSE' in report and 'MPa' in report

            page.select_option('#study-operation', 'doe')
            page.fill('#study-budget', '8')
            doe, result = submit('#run-study')
            assert len(result['candidates']) == 8
            page.select_option('#analysis-job', doe['id'])
            page.fill('#analysis-response', 'stress_xx')
            page.fill('#analysis-unit', 'MPa')
            page.select_option('#analysis-reduction', 'max')
            _, result = submit('#analyze')
            assert result['sensitivity'] and result['candidate_count'] == 8

            page.locator('#upload-file').set_input_files({'name': 'forces.csv', 'mimeType': 'text/csv',
                'buffer': b'time,load\n0,0\n1,10\n2,30\n'})
            with page.expect_response(lambda response: response.url.endswith('/api/workbench/upload')) as uploaded:
                page.locator('#upload-form button').click()
            data = uploaded.value.json()
            expect(page.locator('#input-select')).to_have_value(data['id'])
            page.fill('#axis-column', 'time')
            row = page.locator('#mapping-rows tr').first
            for key, value in {'name': 'force', 'column': 'load', 'unit': 'N', 'component': 'y', 'location': 'support'}.items():
                row.locator('[data-key=' + key + ']').fill(value)
            imported, result = submit('#map-form > button:last-child')
            assert result['responses']['force']['value'] == [0, 10, 30]
            page.select_option('#result-select', imported['id'])
            page.click('#load-result')
            expect(page.locator('#response-select option[value=force]')).to_be_attached()
            page.select_option('#response-select', 'force')
            expect(page.locator('#plot svg')).to_be_visible()
            with page.expect_download() as download:
                page.click('#export-report')
            download.value.save_as(output / 'imported-force-report.html')
            page.screenshot(path=output / 'workbench-flows.png', full_page=True)
            assert not errors, errors
            (output / 'receipts.json').write_text(json.dumps({'evidence': 'SYNTHETIC_SOFTWARE_CHECK',
                'errors': errors, 'flows': receipts}, indent=2))
            return [{'operation': receipt['operation'], 'id': receipt['id']} for receipt in receipts]
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New evidence directory (never reuses an existing store)')
    parser.add_argument('--browser-executable', help='Installed Chromium path; otherwise detect chromium/chromium-browser')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    output = (args.output or root / 'artifacts' / ('workbench-ui-' + stamp)).resolve()
    output.mkdir(parents=True, exist_ok=False)
    executable = args.browser_executable or shutil.which('chromium') or shutil.which('chromium-browser')
    with tempfile.TemporaryDirectory(prefix='caelab-ui-owned-') as directory:
        with (output / 'server.log').open('w') as log:
            process, url = start_service(root, Path(directory), log)
            try:
                flows = browser_flows(url, output, executable)
            finally:
                stop_service(process)
    print(json.dumps({'status': 'PASSED', 'output': str(output), 'flows': flows, 'owned_server_stopped': True}))


if __name__ == '__main__':
    main()
