"""Narrow Data Q correction tests; no C1/26/59 full-suite repetition."""
from copy import deepcopy
from pathlib import Path
import os
import shutil
import pytest

from caelab.portable_project import open_project
from caelab.portable_project_recovery import read_archive
from examples.portable_connection_data_c2_public import (
    prepare, selection, review, execute, certificate, guarded, file_tree)


@pytest.fixture(scope='module')
def source_copy(tmp_path_factory):
    existing = os.environ.get('DATA_C2_PREPARED_COPY')
    return Path(existing) if existing else prepare(tmp_path_factory.mktemp('data-c2') / 'fixture')


@pytest.fixture
def copy_folder(tmp_path, source_copy):
    dest = tmp_path / '다른 위치 사본'
    shutil.copytree(source_copy, dest)
    return dest


def test_resume_retains_acknowledged_calibration(copy_folder, monkeypatch):
    row = selection(copy_folder)
    before = file_tree(copy_folder / 'portable')
    with guarded() as calls:
        wb = open_project(copy_folder)
        try:
            layers = read_archive(copy_folder, row['archive_id'])
            cert = certificate(layers)
            preview = read_archive(copy_folder, row['archive_id'], facet='source-preview', selection={'data_id': cert})
            assert 'gain,offset' in preview['text']
            initial = wb.document_read(row['document_id'])
            assert cert not in initial.get('retained_inputs', {})
            def no_registry_fallback(*args, **kwargs):
                raise AssertionError('No registration/store fallback is permitted in this cold case')
            monkeypatch.setattr(wb.data_documents, 'resolve_input', no_registry_fallback)
            token, proposal = review(wb, row)
            assert cert not in wb.document_read(initial['id']).get('retained_inputs', {})
            packet = execute(wb, token, proposal)
            assert cert in packet['document'].get('retained_inputs', {}), 'ACKNOWLEDGED_CALIBRATION_NOT_RETAINED'
        finally:
            closed = wb.shutdown()
            assert closed['joined'] and not closed['pending']
            assert not calls
            assert file_tree(copy_folder / 'portable') == before


@pytest.mark.parametrize('fault', ['missing_source', 'tampered_source', 'tampered_input_json'])
def test_declared_calibration_loss_rejects_without_current_mutation(copy_folder, fault):
    from caelab.portable_project_recovery import archive_row
    from caelab.portable_project_io import PortableProjectError
    from caelab.storage import canonical_hash
    with guarded() as calls:
        wb = open_project(copy_folder)
        try:
            row = selection(copy_folder)
            path = archive_row(copy_folder, row['archive_id'])[1]
            layer = read_archive(copy_folder, row['archive_id'])
            cert = certificate(layer)
            record = next(r for r in layer['capsule']['acknowledged']['data_inputs'] if r['data_id'] == cert)
            token, proposal = review(wb, row)
            source = path.with_suffix('.assets') / record['source_file']
            metadata = path.with_suffix('.assets') / record['metadata_file']
            original_source, original_metadata = source.read_bytes(), metadata.read_bytes()
            state = file_tree(wb.data_documents._folder(row['document_id']))
            try:
                if fault == 'missing_source':
                    source.unlink()
                elif fault == 'tampered_source':
                    source.write_bytes(b'gain,offset\n2,0\n')
                else:
                    metadata.write_bytes(original_metadata + b' ')
                with pytest.raises((ValueError, OSError, PortableProjectError)):
                    execute(wb, token, proposal)
                assert file_tree(wb.data_documents._folder(row['document_id'])) == state
                assert cert not in wb.document_read(row['document_id']).get('retained_inputs', {})
                assert not list((wb.root / 'inputs').rglob('input.json'))
            finally:
                source.write_bytes(original_source)
                metadata.write_bytes(original_metadata)
        finally:
            closed = wb.shutdown()
            assert closed['joined'] and not closed['pending'] and not calls


@pytest.mark.parametrize('loss', ['response', 'durable_before_memory'])
def test_data_retention_lost_reply_reuses_whole_poststate(copy_folder, monkeypatch, loss):
    import caelab.material_document as material
    with guarded() as calls:
        wb = open_project(copy_folder)
        try:
            row = selection(copy_folder)
            token, proposal = review(wb, row)
            owner = wb.data_documents
            with monkeypatch.context() as patch:
                if loss == 'response':
                    original = material.save_json
                    def interrupted(path, value, *args, **kwargs):
                        if Path(path).name == proposal['command_id'] + '.json' and 'response' in value:
                            raise OSError('Data C2 response receipt loss')
                        return original(path, value, *args, **kwargs)
                    patch.setattr(material, 'save_json', interrupted)
                else:
                    original = owner._persist_draft
                    def interrupted(document):
                        original(document)
                        raise OSError('Data C2 durable write before memory loss')
                    patch.setattr(owner, '_persist_draft', interrupted)
                with pytest.raises(OSError, match='Data C2'):
                    execute(wb, token, proposal)
            packet = execute(wb, token, proposal)
            cert = certificate(read_archive(copy_folder, row['archive_id']))
            assert cert in packet['document']['retained_inputs']
            before = file_tree(owner._folder(row['document_id']))
            assert execute(wb, token, proposal) == packet
            assert file_tree(owner._folder(row['document_id'])) == before
            # Same input but a later actual acknowledged command is not the
            # recorded whole poststate. No-op UPDATE is a real owner command.
            from examples.portable_connection_public import command
            newer = command(wb, packet['document'], 'data.update', {'draft': packet['document']['draft']})
            assert newer['input_revision'] == packet['document']['input_revision']
            before = file_tree(owner._folder(row['document_id']))
            with pytest.raises(ValueError, match='after the recorded'):
                execute(wb, token, proposal)
            assert file_tree(owner._folder(row['document_id'])) == before
        finally:
            closed = wb.shutdown()
            assert closed['joined'] and not closed['pending'] and not calls


def test_new_current_source_tamper_cannot_replay_as_success(copy_folder):
    with guarded() as calls:
        wb = open_project(copy_folder)
        try:
            row = selection(copy_folder)
            token, proposal = review(wb, row)
            packet = execute(wb, token, proposal)
            cert = certificate(read_archive(copy_folder, row['archive_id']))
            source, _ = wb.data_documents._retained_source(packet['document'], cert)
            original = source.read_bytes()
            try:
                source.write_bytes(b'tampered retained certificate')
                with pytest.raises(ValueError, match='changed or is missing'):
                    execute(wb, token, proposal)
            finally:
                source.write_bytes(original)
            assert execute(wb, token, proposal) == packet
        finally:
            closed = wb.shutdown()
            assert closed['joined'] and not closed['pending'] and not calls


@pytest.mark.parametrize('field', ['approved', 'buffer', 'session', 'generation'])
def test_current_authority_is_required_before_retaining(copy_folder, field):
    from caelab.portable_recovery_resume import resume
    from examples.portable_connection_public import command
    with guarded() as calls:
        wb = open_project(copy_folder)
        try:
            row = selection(copy_folder)
            token, proposal = review(wb, row)
            kwargs = dict(approved=True, overwrite_approved=True, live_buffer=deepcopy(token), command_id=proposal['command_id'])
            if field == 'approved': kwargs['approved'] = False
            elif field == 'buffer': kwargs['live_buffer']['editor_revision'] += 'changed'
            elif field == 'session':
                # No changes to the source identity/Q; the actual current owner
                # session changes and refuses an earlier operational request.
                wb.data_documents.session_id = 'SDataC2OtherSession'
            else:
                current = wb.document_read(row['document_id'])
                draft = deepcopy(current['draft']); draft['test_metadata']['protocol'] += ' peer edit'
                command(wb, current, 'data.update', {'draft': draft})
            before = file_tree(wb.data_documents._folder(row['document_id']))
            with pytest.raises(ValueError): resume(wb, proposal, **kwargs)
            assert file_tree(wb.data_documents._folder(row['document_id'])) == before
        finally:
            closed = wb.shutdown()
            assert closed['joined'] and not closed['pending'] and not calls


def test_raw_only_identity_path_is_not_a_retention_or_registration_request(copy_folder, tmp_path):
    from caelab.related_save_recovery import RawRecoveryDrafts
    from caelab.portable_project import inspect_copy, create_copy
    from caelab.portable_project_recovery import read_archive
    from examples.portable_connection_public import save
    from caelab.portable_recovery_resume import buffer_token, preview_resume
    raw_id = 'DRawOnlyNotAcknowledged'
    with guarded() as calls:
        wb = open_project(copy_folder)
        try:
            row = selection(copy_folder)
            token, proposal = review(wb, row)
            packet = execute(wb, token, proposal)
            current = save(wb, packet['document'])
            raw = deepcopy(packet['raw'])
            raw['local_draft']['data_id'] = raw_id
            raw['paste'] = {'raw_text': r'C:\unapproved\other-certificate.csv', 'committed': False}
            raw['editor_revision'] = 'URawOnlyDataC2'
            recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
            kept = recovery.execute(recovery.prepare([{'identity': recovery.identity(current), 'raw': raw}]))
            assert kept['all_kept'], kept
            cid = kept['targets'][0]['capsule_id']
            dest = tmp_path / 'raw-only-copy'
            plan = inspect_copy(wb, [current['id']], draft_policy='saved_only',
                recovery_archives=[{'document_id': current['id'], 'capsule_id': cid}])
            assert plan['status'] == 'READY', plan
            create_copy(wb, plan, dest, approved=True, command_id='CDataRawOnlyCopy', session_id=wb.session_id)
        finally:
            closed = wb.shutdown(); assert closed['joined'] and not closed['pending']
        wb = open_project(dest)
        try:
            row = selection(dest)
            layer = read_archive(dest, row['archive_id'])
            assert layer['capsule']['raw']['local_draft']['data_id'] == raw_id
            for requested in (raw_id, r'C:\unapproved\other-certificate.csv'):
                with pytest.raises((ValueError, KeyError)):
                    read_archive(dest, row['archive_id'], facet='source-preview', selection={'data_id': requested})
            token, proposal = review(wb, row)
            packet = execute(wb, token, proposal)
            assert packet['raw']['local_draft']['data_id'] == raw_id
            assert packet['document']['draft']['data_id'] != raw_id
            assert raw_id not in packet['document']['retained_inputs']
            assert not (wb.root / 'inputs' / raw_id).exists()
        finally:
            closed = wb.shutdown()
            assert closed['joined'] and not closed['pending'] and not calls


def test_local_retained_metadata_raw_bytes_survive_owner_save(copy_folder):
    """Actual input.json whitespace is not regenerated by subsequent saves."""
    from caelab.storage import load_json, save_json
    from caelab.evaluation import file_hash
    from examples.portable_connection_public import save
    # Extra white space is supplied as original evidence in a NEW local current
    # registration before Keep. Never alter the fixture's immutable Q.
    with guarded() as calls:
        wb = open_project(copy_folder)
        try:
            row = selection(copy_folder)
            token, proposal = review(wb, row)
            packet = execute(wb, token, proposal)
            # The present path already contains an exact original metadata file;
            # serialise a new registered certificate with deliberately distinct
            # whitespace in its own current registration before it is retained.
            receipt = wb.upload('새 명시 보정.csv', b'gain,offset\n1,0\n')
            metadata = wb.root / 'inputs' / receipt['id'] / 'input.json'
            value = load_json(metadata)
            import json
            metadata.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n\n', encoding='utf-8')
            draft = deepcopy(packet['document']['draft'])
            draft['mapping']['columns']['stress']['calibration']['source'] = {'data_id': receipt['id'], 'sha256': receipt['sha256'], 'name': receipt['name']}
            from examples.portable_connection_public import command
            current = command(wb, packet['document'], 'data.update', {'draft': draft})
            from caelab.related_save_recovery import RawRecoveryDrafts
            recovery = RawRecoveryDrafts(wb.root, wb._document_owner)
            kept = recovery.execute(recovery.prepare([{'identity': recovery.identity(current), 'raw': packet['raw']}]))
            assert kept['all_kept']
            # Reuse exact acknowledged Q selection and copied owner to exercise
            # the relocation source; that source's actual metadata has whitespace.
            from caelab.portable_project import inspect_copy, create_copy
            dest = copy_folder.parent / 'metadata-copy'
            q = {'document_id': current['id'], 'capsule_id': kept['targets'][0]['capsule_id']}
            plan = inspect_copy(wb, [current['id']], draft_policy='saved_only', recovery_archives=[q])
            assert plan['status'] == 'READY', plan
            create_copy(wb, plan, dest, approved=True, command_id='CDataMetadataCopy', session_id=wb.session_id)
            expected = metadata.read_bytes()
        finally:
            closed = wb.shutdown(); assert closed['joined'] and not closed['pending']
        wb = open_project(dest)
        try:
            token, proposal = review(wb, selection(dest)); packet = execute(wb, token, proposal)
            current = save(wb, packet['document'])
            binding = current['retained_inputs'][receipt['id']]
            metadata = wb.data_documents._folder(current['id']) / 'revisions' / binding['revision'] / binding['metadata']
            assert metadata.read_bytes() == expected
            assert not wb.manager.list()
        finally:
            closed = wb.shutdown(); assert closed['joined'] and not closed['pending'] and not calls


def test_unpublished_retention_write_failure_preserves_current_owner(copy_folder, monkeypatch):
    with guarded() as calls:
        wb = open_project(copy_folder)
        try:
            row = selection(copy_folder)
            token, proposal = review(wb, row)
            owner = wb.data_documents
            state = owner.acknowledged_state(row['document_id'])['document']
            folder = owner._folder(row['document_id'])
            before_revisions = file_tree(folder / 'revisions')
            before_working = (folder / 'working.json').read_bytes()
            original = owner._retain_inputs
            def interrupted(*args, **kwargs):
                original(*args, **kwargs)
                raise OSError('Data C2 injected unpublished retention write failure')
            with monkeypatch.context() as patch:
                patch.setattr(owner, '_retain_inputs', interrupted)
                with pytest.raises(OSError, match='unpublished retention write failure'):
                    execute(wb, token, proposal)
            assert owner.acknowledged_state(row['document_id'])['document'] == state
            assert (folder / 'working.json').read_bytes() == before_working
            assert file_tree(folder / 'revisions') == before_revisions
            # Preserve unconfirmed admission rather than fabricate a success.
            from caelab.storage import load_json
            receipt = load_json(folder / 'commands' / (proposal['command_id'] + '.json'))
            assert receipt['state'] == 'APPLYING' and 'response' not in receipt
            with pytest.raises(ValueError, match='unconfirmed'):
                execute(wb, token, proposal)
        finally:
            closed = wb.shutdown(); assert closed['joined'] and not closed['pending'] and not calls


def test_data_full_roundtrip_in_separate_processes(copy_folder, tmp_path):
    import subprocess
    import sys
    import json
    from caelab.storage import load_json
    reports = []
    destination = tmp_path / '다음 이동 사본'
    def child(phase, folder, *extra):
        args = [sys.executable, '-B', '-m', 'examples.portable_connection_data_c2_public', phase, str(folder), *map(str, extra)]
        proc = None
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
            stdout, stderr = proc.communicate(timeout=45)
            reports.append({'phase': phase, 'pid': proc.pid, 'returncode': proc.returncode, 'stdout': stdout, 'stderr': stderr})
            assert proc.returncode == 0, stdout + '\n' + stderr
            value = json.loads(stdout)
            assert value['status'] == 'PASS' and value['shutdown']['joined'] and not value['shutdown']['pending']
            assert value['cold_execution_calls'] == []
            return value
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
                if proc.stdout: proc.stdout.close()
                if proc.stderr: proc.stderr.close()
            (tmp_path / 'owned-cold-processes.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    original = file_tree(copy_folder / 'portable')
    row = selection(copy_folder)
    layer = read_archive(copy_folder, row['archive_id'])
    preview = read_archive(copy_folder, row['archive_id'], facet='source-preview',
                           selection={'data_id': certificate(layer)})
    assert 'gain,offset' in preview['text']
    finished = child('finish', copy_folder)
    child('recover-recopy', copy_folder, '--destination', destination)
    assert file_tree(copy_folder / 'portable') == original
    offline = copy_folder.with_name(copy_folder.name + '-offline-preserved')
    copy_folder.rename(offline)
    assert not copy_folder.exists() and file_tree(offline / 'portable') == original
    last = child('read-recopied', destination)
    assert len(last['archives']) == 2
    assert finished['original_raw_sha256'] in {r['raw_sha256'] for r in last['archives']}
