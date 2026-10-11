"""Connections between existing native owners, retained inputs and JobManager.

No executable paths or arbitrary source roots are accepted from a client.
Native exporters write into this workspace's private exchange directory.
"""
from copy import deepcopy
from pathlib import Path
import os
import shutil
import sys
import threading
import uuid

from .native_inputs import register_frozen_input
from .storage import canonical_hash, check_id, load_json, save_json


class DesktopLinks:
    def __init__(self, workbench):
        self.workbench = workbench
        self.root = workbench.root / 'native_exchange'
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def context(self):
        config = self.workbench.config.get('desktop', {})
        return {'service_session_id': self.workbench.session_id,
                'export_root': str(self.root), 'python': sys.executable,
                'repo_root': str(Path(__file__).resolve().parents[1]),
                'freecad_executable': config.get('freecad_executable') or os.getenv('CAELAB_FREECAD_EXE') or shutil.which('FreeCAD') or shutil.which('freecad'),
                'paraview_executable': config.get('paraview_executable') or os.getenv('CAELAB_PARAVIEW_EXE') or shutil.which('paraview')}

    def submit_frozen(self, command_id):
        """Retry one completed export without registering/submitting it twice."""
        wb = self.workbench
        command_id = check_id(command_id)
        with self._lock:
            command = wb.native_commands.status(command_id)
            if command['operation'] != 'pre.freeze' or command['state'] != 'SUCCEEDED':
                raise ValueError('A completed native pre.freeze command is required')
            envelope = command.get('outcome', {}).get('result', {})
            result = envelope.get('result', {})
            if envelope.get('status') != 'COMPLETED':
                raise ValueError('Native export has no completed outcome')
            relative = result.get('snapshot_relative')
            from .workbench import contained
            manifest = contained(self.root, relative)
            if manifest.name != 'snapshot.json' or manifest.parent.parent.name != command['document_id']:
                raise ValueError('Export must belong to this exact native document exchange folder')
            record = self.root / 'submissions' / (command_id + '.json')
            if record.exists():
                previous = load_json(record)
                if previous['command_hash'] != command['request_hash']:
                    raise ValueError('Native submission command changed')
                receipt = previous['input']
                wb.input_path(receipt['id'])
            else:
                receipt = register_frozen_input(wb.root, self.root, manifest, 'D' + uuid.uuid4().hex,
                    root_id='native-owner:' + command['document_id'], relative=relative,
                    limit=wb.config.get('local_input_max_bytes', 2 * 1024 ** 3))
                save_json(record, {'command_hash': command['request_hash'], 'input': receipt})
            origin = {'kind': 'pre', 'document_id': command['document_id'],
                      'session_id': command['session_id'], 'generation': command.get('final_generation', command['expected_generation']),
                      'command_id': command_id, 'input_id': receipt['id']}
            job = wb.submit('run', {'backend': 'structure.calculix.frozen',
                'settings': {'data_id': receipt['id']}, 'origin': origin,
                'label': result.get('label', 'FreeCAD FEM analysis')[:160]},
                request_id='native-frozen:' + command_id)
            return {'job': job, 'input': receipt, 'origin': origin}

    def navigation(self, job_id):
        wb = self.workbench
        job = wb.manager.status(check_id(job_id))
        result = {'job_id': job_id, 'origin_document': None, 'post_input': None,
                  'retained_design_input_id': None}
        origin = job['arguments'].get('origin', {})
        if job['arguments'].get('backend') == 'structure.calculix.frozen':
            result['retained_design_input_id'] = job['arguments']['settings']['data_id']
        if origin.get('kind') == 'pre':
            try:
                current = wb.native_commands.read(origin['document_id'])
                result['origin_document'] = {key: current.get(key) for key in
                    ('id', 'kind', 'title', 'session_id', 'generation', 'connected')}
            except KeyError:
                pass
            result['frozen_origin'] = deepcopy(origin)
        else:
            for owner in (wb.material_documents, wb.data_documents, wb.numerical_documents):
                match = next((doc for doc in owner.list() if any(row['job_id'] == job_id for row in doc['runs'])), None)
                if match:
                    result['origin_document'] = {key: match.get(key) for key in ('id', 'kind', 'title', 'session_id', 'generation')}
                    result['origin_document']['connected'] = True
                    break
        if job.get('result_refs'):
            summary = wb.result(job_id, selection={'responses': []})
            post = summary.get('post_input')
            if post:
                wb.input_path(post['id'])
                result['post_input'] = deepcopy(post)
        return result

    def adopt(self, plan_id, job_id, candidate_id, *, material_document_id,
              session_id, expected_generation, command_id):
        """The Plan owns the search; only its selected coefficients edit Material."""
        from .numerical_document import adopted_draft
        wb = self.workbench
        plan = wb.numerical_documents.read(check_id(plan_id))
        run = next((row for row in plan['runs'] if row['job_id'] == job_id), None)
        if run is None:
            raise ValueError('Selected run does not belong to this Numerical Plan')
        frozen = run['draft']['material']
        if frozen['document_id'] != material_document_id:
            raise ValueError('Candidate belongs to a different Material document')
        result = wb.numerical_documents.result(plan_id, check_id(job_id))
        draft = adopted_draft(run, result, candidate_id)
        # Reuse the exact verified retained run on retries. A result read above
        # already verified its immutable revision; adoption does not need to
        # copy every Plan result to another revision on each lost HTTP response.
        retained = run.get('retained_result')
        if retained and run.get('retention_complete'):
            revision = retained['revision']
        else:
            saved = wb.numerical_documents.command(plan_id, 'document.save', {},
                session_id=plan['session_id'], expected_generation=plan['generation'])['document']
            revision = saved['saved_revision']
        source = {'plan_id': plan_id, 'plan_revision': revision, 'job_id': job_id,
                  'candidate_id': candidate_id, 'input_sha256': run['input_sha256'],
                  'coefficient_sha256': canonical_hash(draft['settings']['parameters'])}
        return wb.material_documents.adopt(material_document_id, draft, source,
            expected_input_revision=frozen['input_revision'], expected_input_hash=canonical_hash(frozen['draft']),
            session_id=session_id, expected_generation=expected_generation, command_id=command_id)
