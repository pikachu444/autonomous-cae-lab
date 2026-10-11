"""Portable PDE owner checks; no native solver is executed."""
from copy import deepcopy
import hashlib
import shutil

import pytest

from caelab.evaluation import read_result, save_evaluation
from caelab.pde_document import BACKENDS, PDEDocuments, default_draft, diagnostics
from caelab.storage import canonical_hash


class RecordedJobs:
    def __init__(self, root):
        self.root = root / 'jobs'
        self.jobs = {}

    def list(self):
        return list(self.jobs.values())

    def status(self, identifier):
        return deepcopy(self.jobs[identifier])

    def submit(self, operation, arguments, *, request_id):
        job = {'id': 'Jrecorded', 'operation': operation, 'arguments': deepcopy(arguments),
               'created_utc': '2026-10-11T00:00:00Z', 'request_id': request_id,
               'state': 'SUCCEEDED', 'result_refs': []}
        self.jobs[job['id']] = job
        return deepcopy(job)

    def result(self, identifier, *, selection=None):
        return read_result(self.root / 'results' / identifier, selection=selection)


def command(owner, document, operation, arguments=None, **extra):
    return owner.command(document['id'], operation, arguments or {},
                         session_id=document['session_id'], expected_generation=document['generation'], **extra)


@pytest.mark.parametrize('backend', BACKENDS)
def test_real_schema_defaults_without_native_imports(backend, monkeypatch):
    import builtins
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'dolfinx', 'ufl', 'petsc4py', 'gmsh', 'mpi4py'}:
            raise AssertionError('Owner imported a native runtime')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    draft = default_draft(backend)
    checks = diagnostics(draft)
    if backend.endswith('.imported'):
        assert checks  # No mesh bytes have been supplied.
    else:
        assert checks == []


def test_invalid_edit_save_reopen_undo_with_backend_absent(tmp_path):
    manager = RecordedJobs(tmp_path)
    def absent(*args, **kwargs):
        raise AssertionError('Editing/save must never submit a job')
    owner = PDEDocuments(tmp_path, 'Sfirst', absent, manager)
    original = owner.open()
    assert original['kind'] == 'pde' and original['id'].startswith('Q')
    draft = deepcopy(original['draft'])
    draft['settings']['problem']['weak_form']['rhs'] = '__import__("os").system("false")'
    draft['settings']['mesh']['degree'] = 'unfinished'
    edited = command(owner, original, 'pde.update', {'draft': draft}, command_id='Cedit')['document']
    assert edited['diagnostics'] and edited['draft'] == draft
    with pytest.raises(ValueError, match='Invalid draft'):
        command(owner, edited, 'pde.evaluate')
    saved = command(owner, edited, 'document.save')['document']
    recovered = PDEDocuments(tmp_path, 'Srestart', absent, manager).open(document_id=saved['id'])
    assert recovered['draft'] == draft and recovered['saved_revision'] == saved['saved_revision']
    assert recovered['session_id'] == 'Srestart'
    restarted = PDEDocuments(tmp_path, 'Sthird', absent, manager)
    reopened = restarted.open(document_id=saved['id'])
    undone = command(restarted, reopened, 'document.undo')['document']
    assert undone['draft'] == original['draft']
    assert command(restarted, undone, 'document.redo')['document']['draft'] == draft


@pytest.mark.parametrize('draft', [
    {'backend': [], 'settings': {}}, {'backend': None, 'settings': []},
    {'backend': 'unknown', 'settings': {'solver': 'python'}},
    {'backend': 'pde.fenicsx.rectangle', 'settings': {'problem': {'domain': []}}},
    {'backend': 'pde.fenicsx.rectangle', 'settings': {}, 'hidden': 1},
])
def test_malformed_draft_survives_public_read_and_save(tmp_path, draft):
    manager = RecordedJobs(tmp_path)
    owner = PDEDocuments(tmp_path, 'Ssession', manager.submit, manager)
    document = owner.open(draft=draft)
    assert document['diagnostics']
    assert command(owner, document, 'document.save')['document']['draft'] == draft


def test_exact_imported_content_and_identity_preserved_in_draft(tmp_path):
    from caelab.adapters.fenicsx_gmsh import manufactured_mesh
    draft = default_draft('pde.fenicsx.imported')
    draft['settings']['mesh']['levels'] = [manufactured_mesh('l_shape', n) for n in (1, 2, 4)]
    assert diagnostics(draft) == []
    frozen = PDEDocuments.job_arguments(draft)
    identity = canonical_hash(frozen)
    draft['settings']['mesh']['levels'][0]['source'] = 'renamed by a later edit'
    assert canonical_hash(frozen) == identity
    source = frozen['settings']['mesh']['levels'][0]
    assert hashlib.sha256(source['data'].encode('ascii')).hexdigest() == source['sha256']
    owner = PDEDocuments(tmp_path, 'Sowner', None, RecordedJobs(tmp_path))
    original = owner.open(draft=frozen)
    saved = command(owner, original, 'document.save')['document']
    assert saved['draft']['settings']['mesh']['levels'][0] == source


def test_submission_freezes_settings_and_saved_fields_survive_manager_loss(tmp_path):
    manager = RecordedJobs(tmp_path)
    owner = PDEDocuments(tmp_path, 'Sowner', manager.submit, manager)
    original = owner.open()
    receipt = command(owner, original, 'pde.evaluate', command_id='Cevaluate')
    document = receipt['document']
    assert receipt['job']['operation'] == 'pde.evaluate'
    assert receipt['job']['arguments'] == original['draft']
    folder = manager.root / 'results' / 'Jrecorded'
    result = {'execution_status': 'SUCCEEDED', 'responses': {}, 'checks': [],
              'diagnostics': {'fixture': 'RETAINED SOFTWARE CONTRACT, NO PHYSICS RUN', 'native_fields': [
                  {'name': 'fixture exact field', 'time': None, 'source': {'artifact': 'pde/dofs.json'},
                   'field': {'node_ids': [10, 20, 30], 'coordinates': [[0, 0], [1, 0], [0, 1]],
                             'values': [1., 2., 3.], 'field_unit': '1', 'coordinates_unit': '1'}}]}}
    save_evaluation(result, folder)
    manager.jobs['Jrecorded']['result_refs'] = [{'path': 'result.json'}]
    document = owner.read(document['id'])
    saved = command(owner, document, 'document.save')['document']
    shutil.rmtree(manager.root)
    reopened_owner = PDEDocuments(tmp_path, 'Srestart', None, RecordedJobs(tmp_path))
    reopened = reopened_owner.open(document_id=saved['id'])
    retained = reopened_owner.result(reopened['id'], 'Jrecorded')
    assert retained['diagnostics']['native_fields'][0]['field']['values'] == [1., 2., 3.]
    assert reopened['runs'][0]['settings'] == original['draft']['settings']
