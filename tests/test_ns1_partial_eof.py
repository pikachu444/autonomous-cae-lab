"""Explicit FRD/STA and process doubles, not solver or native GUI validation."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
from types import SimpleNamespace as NS
import pytest

from test_contact_execution import model
from test_ns1_pipeline import nonlinear_model, outputs, status_text, snapshot_of
from caelab.contact_deck import validate_model
from caelab.contact_status import read_status, retained_prefix
from caelab.adapters import contact_fem
from caelab.execution_control import ExecutionCancelled


def cut_last_pe(text):
    lines = text.splitlines(keepends=True)
    field = max(i for i, line in enumerate(lines) if line.split()[:2] == ['-4', 'PE'])
    return ''.join(lines[:field+3]) + lines[field+3][:20]


def test_last_committed_pe_eof_keeps_the_previous_complete_increment(model, tmp_path):
    value = nonlinear_model(model, single=True)
    text, _, materials = outputs(value)
    raw = cut_last_pe(text).encode('ascii')
    frd, sta = tmp_path/'native.frd', tmp_path/'native.sta'
    frd.write_bytes(raw); sta.write_text(status_text(), encoding='ascii')
    status = read_status(sta, value); original_status = deepcopy(status)
    nodes, elements, _ = validate_model(value)
    result = retained_prefix(frd, tmp_path/'derived.frd', nodes, elements, materials, value, status)
    assert len(result['frames']) == 1
    frame = result['frames'][0]
    assert frame['static']['increment'] == 1 and frame['static']['load_parameter'] == .5
    assert {'STRESS', 'TOSTRAIN', 'PE'} <= set(frame['fields'])
    assert frame['fields']['PE'][next(iter(nodes))] == [.00615]
    assert frd.read_bytes() == raw and status == original_status
    assert sta.read_text() == status_text()


def case(original, kind):
    if kind in ('single', 'contact'):
        value = nonlinear_model(original, single=kind == 'single')
        frd, dat, materials = outputs(value)
        return value, frd, dat, materials, status_text()
    if kind == 'tie':
        from test_contact_tie import tie_draft, _native_tie_outputs
        value = deepcopy(original); value['contacts'][0]['draft'] = tie_draft()
        frd, materials = _native_tie_outputs(value)
        return value, frd, '', materials, status_text()
    from test_contact_steps import staged, two_step_outputs
    value = staged(original, dynamic=kind == 'dynamic')
    frd, dat, materials = two_step_outputs(value)
    return value, frd, dat, materials, '1 1 1 3 .5 .5 .5\n2 1 1 4 1.0 .5 .5\n'


def cut_field(text, cut, *, field_index=-1):
    lines = text.splitlines(keepends=True)
    field = [i for i, l in enumerate(lines) if l.split()[:1] == ['-4']][field_index]
    data = field+1
    while lines[data].split()[:1] == ['-5']: data += 1
    end = next(i for i in range(data, len(lines)) if lines[i].strip() == '-3')
    if cut == 'vector': return ''.join(lines[:data+1]) + lines[data+1][:20]
    if cut == 'records': return ''.join(lines[:data+1])
    if cut == 'labels': return ''.join(lines[:field+1])
    if cut == 'label_fragment': return ''.join(lines[:field+1]) + lines[field+1][:9]
    if cut == 'terminator': return ''.join(lines[:end])
    if cut == 'terminator_fragment': return ''.join(lines[:end]) + ' -'
    if cut == 'between_fields': return ''.join(lines[:field-2])
    if cut == 'field_header': return ''.join(lines[:field])
    if cut == 'definition_fragment': return ''.join(lines[:field]) + lines[field][:9]
    raise AssertionError(cut)


@pytest.mark.parametrize('kind', ['single', 'contact', 'tie', 'multistep', 'dynamic'])
@pytest.mark.parametrize('cut', ['vector', 'records', 'labels', 'label_fragment', 'terminator',
                                'terminator_fragment', 'between_fields', 'field_header', 'definition_fragment'])
def test_structural_eof_discards_the_whole_increment_not_only_one_field(model, tmp_path, kind, cut):
    from caelab.adapters.frozen_fem import read_frd
    from caelab.contact_steps import profile
    value, text, _, materials, sta_text = case(model, kind)
    raw = cut_field(text, cut).replace('\n', '\r\n').encode('ascii')
    frd, sta, target = tmp_path/'native.frd', tmp_path/'native.sta', tmp_path/'derived.frd'
    frd.write_bytes(raw); sta.write_text(sta_text, encoding='ascii')
    status = read_status(sta, value); before = deepcopy(status)
    nodes, elements, _ = validate_model(value)
    options = dict(contact_materials=materials, contact_profile=profile(value), require_contact=kind not in ('single','tie'))
    with pytest.raises(ValueError): read_frd(frd, nodes, elements, **options)
    result = retained_prefix(frd, target, nodes, elements, materials, value, status)
    assert len(result['frames']) == 1
    assert result['frames'][0]['static'] == {'step':1, 'increment':1, 'load_parameter':.5}
    reread = read_frd(target, nodes, elements, **options)
    from caelab.contact_steps import validate_frames
    validate_frames(value, reread, complete=False)
    assert reread['frames'] == result['frames']
    assert result['retention']['reason'] == 'incomplete_increment_at_eof'
    assert result['retention']['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert frd.read_bytes() == raw and sta.read_text() == sta_text and status == before


@pytest.mark.parametrize('damage', ['interior_vector','interior_label','geometry','short_closed_line',
                                    'bad_final_value','foreign_partial_node','duplicate_partial_node',
                                    'interior_end','missing_closed_row','missing_middle_channel'])
def test_damage_is_not_downgraded_to_a_recoverable_eof(model, tmp_path, damage):
    value = nonlinear_model(model, single=True)
    text, _, materials = outputs(value)
    lines = cut_last_pe(text).splitlines(keepends=True)
    if damage == 'interior_vector':
        i = next(i for i,l in enumerate(lines) if l.split()[:2] == ['-4','STRESS']) + 7
        lines[i] = lines[i][:20]+'\n'
    elif damage == 'interior_label':
        lines = [l.replace('EXX 1 4 1 1','EXY 1 4 1 2') for l in lines]
    elif damage == 'geometry':
        i = next(i for i,l in enumerate(lines) if l.split()[:1] == ['2C'])+1
        lines[i] = lines[i][:13]+f'{999.:12.5E}'+lines[i][25:]
    elif damage == 'short_closed_line':
        lines[-1] += '\n'
    elif damage == 'bad_final_value':
        lines[-1] = lines[-1][:13]+' BAD_NUMBER!'
    elif damage == 'foreign_partial_node':
        lines[-1] = ' -1'+f'{999:10d}'+' 1.2300'
    elif damage == 'duplicate_partial_node':
        lines[-1] = lines[-2][:20]
    elif damage == 'interior_end':
        i = next(i for i,l in enumerate(lines) if l.split()[:1] == ['1PSTEP'] and int(l[36:48]) == 2)
        lines.insert(i, ' 9999\n')
    elif damage == 'missing_closed_row':
        i = next(i for i,l in enumerate(lines) if l.split()[:2] == ['-4','PE'])+2
        lines.pop(i)
    else:
        i = next(i for i,l in enumerate(lines) if l.split()[:2] == ['-4','PE'])-2
        end = next(j for j in range(i+1,len(lines)) if lines[j].split()[:1] == ['1PSTEP'])
        del lines[i:end]
        # Preserve field counters to test missing channel, not a counter error.
        count=0
        for j,l in enumerate(lines):
            if l.split()[:1] == ['1PSTEP']:
                count+=1; lines[j]=l[:24]+f'{count:12d}'+l[36:]
    raw = ''.join(lines).encode('ascii')
    frd, sta, target = tmp_path/'native.frd', tmp_path/'native.sta', tmp_path/'derived.frd'
    frd.write_bytes(raw); sta.write_text(status_text(), encoding='ascii')
    nodes, elements, _ = validate_model(value)
    with pytest.raises(ValueError):
        retained_prefix(frd, target, nodes, elements, materials, value, read_status(sta,value))
    assert not target.exists() and frd.read_bytes() == raw


@pytest.mark.parametrize('single', [False, True])
@pytest.mark.parametrize('cancelled', [False, True])
def test_adapter_preserves_failure_and_raw_bytes_with_eof_prefix(model, tmp_path, monkeypatch, single, cancelled):
    value = nonlinear_model(model, single=single)
    snapshot = snapshot_of(value, tmp_path/'input')
    executable = tmp_path/'ccx'; executable.write_bytes(b'EXPLICIT_PROCESS_DOUBLE_NOT_A_SOLVER')
    monkeypatch.setattr(contact_fem.shutil, 'which', lambda _: str(executable))
    text, dat, materials = outputs(value)
    raw = cut_last_pe(text).encode('ascii'); sta_raw = status_text().encode('ascii')
    calls = []
    def command(argv, cwd, label):
        calls.append(argv)
        (cwd/'contact.frd').write_bytes(raw); (cwd/'contact.sta').write_bytes(sta_raw)
        (cwd/'contact.dat').write_text(dat, encoding='ascii')
        if cancelled: raise ExecutionCancelled('Explicit process cancellation double')
        return NS(returncode=2)
    monkeypatch.setattr(contact_fem, 'run_owned_command', command)
    attempt = tmp_path/'attempt'
    result = contact_fem.ContactFemCalculixAdapter().run({'snapshot_path': str(snapshot)}, output=attempt)
    assert result['execution_status'] == ('CANCELLED' if cancelled else 'FAILED')
    assert result['responses'] == {} and not result['engineering_valid']
    assert result['partial_result']['frame_count'] == 1, result['diagnostics']
    retention = result['partial_result']['frd_retention']
    assert retention['reason'] == 'incomplete_increment_at_eof'
    assert retention['last_retained_increment']['load_parameter'] == .5
    assert result['increment_history']['last_converged']['total'] == 1.
    assert (attempt/'solver/contact.frd').read_bytes() == raw
    assert (attempt/'solver/contact.sta').read_bytes() == sta_raw
    assert (attempt/'frozen_input/contact.inp').read_bytes() == (snapshot.parent/'contact.inp').read_bytes()
    assert len(calls) == 1
    # Fresh OS process reads the retained derived copy, with no solver installed.
    import subprocess, sys
    executable.unlink()
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in attempt.rglob('*') if p.is_file()}
    script = '''import json,sys
from pathlib import Path
from caelab.adapters.frozen_fem import read_frd
from caelab.contact_deck import validate_model
from caelab.contact_steps import profile
root=Path(sys.argv[1]); model=json.loads((root/'frozen_input/mesh.json').read_text(encoding='utf-8'))
nodes,elements,bodies=validate_model(model)
materials=json.loads(sys.argv[2]); materials['elements']={int(k):v for k,v in materials['elements'].items()}
result=read_frd(root/'partial/committed.frd',nodes,elements,contact_materials=materials,contact_profile=profile(model),require_contact=bool(model['contacts']))
assert len(result['frames'])==1
assert result['frames'][0]['static']['load_parameter']==.5
record=json.loads((root/'contact_execution.json').read_text(encoding='utf-8'))
assert record['execution_status'] in ('FAILED','CANCELLED')
print('REOPEN_WITHOUT_SOLVER')
'''
    # One representative fresh-process reopen is sufficient; all four adapter
    # failure/cancellation routes still check their persisted records and bytes.
    persisted = json.loads((attempt/'contact_execution.json').read_text(encoding='utf-8'))
    assert persisted['partial_result'] == result['partial_result']
    assert persisted['execution_status'] == result['execution_status']
    if single and cancelled:
        process = subprocess.run([sys.executable, '-c', script, str(attempt), json.dumps(materials)],
                                 capture_output=True, text=True, timeout=20)
        assert process.returncode == 0, process.stderr
        assert process.stdout.strip() == 'REOPEN_WITHOUT_SOLVER'
    assert len(calls) == 1
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p,digest in before.items())


def test_no_complete_first_increment_and_source_alias_are_never_published(model, tmp_path):
    value = nonlinear_model(model, single=True); text, _, materials = outputs(value)
    # The first PE belongs to the first frame; there is no earlier complete frame.
    raw = cut_field(text, 'vector', field_index=4).encode('ascii')
    frd, sta, target = tmp_path/'native.frd', tmp_path/'native.sta', tmp_path/'derived.frd'
    frd.write_bytes(raw); sta.write_text(status_text(), encoding='ascii')
    status = read_status(sta, value); nodes, elements, _ = validate_model(value)
    with pytest.raises(ValueError): retained_prefix(frd, target, nodes, elements, materials, value, status)
    assert not target.exists()
    with pytest.raises(ValueError, match='raw solver'):
        retained_prefix(frd, frd, nodes, elements, materials, value, status)
    assert frd.read_bytes() == raw


@pytest.mark.parametrize('ending', ['complete', 'only_file_terminator_missing', 'closed_but_torn_field'])
def test_end_of_file_and_end_markers_have_distinct_meanings(model, tmp_path, ending):
    value = nonlinear_model(model, single=True); text, _, materials = outputs(value)
    if ending == 'only_file_terminator_missing': text = text.replace(' 9999\n', '')
    if ending == 'closed_but_torn_field': text = cut_last_pe(text) + '\n 9999\n'
    frd, sta, target = tmp_path/'native.frd', tmp_path/'native.sta', tmp_path/'derived.frd'
    frd.write_bytes(text.encode('ascii')); sta.write_text(status_text(), encoding='ascii')
    nodes, elements, _ = validate_model(value); status = read_status(sta, value)
    if ending == 'closed_but_torn_field':
        with pytest.raises(ValueError): retained_prefix(frd, target, nodes, elements, materials, value, status)
        assert not target.exists()
    else:
        result = retained_prefix(frd, target, nodes, elements, materials, value, status)
        assert len(result['frames']) == 2
        assert result['retention']['reason'] == 'complete_converged_output'
    assert frd.read_bytes() == text.encode('ascii')


@pytest.mark.parametrize('marker', [' 9', ' 99', ' 999'])
@pytest.mark.parametrize('increments', [1, 2])
def test_eof_truncated_file_marker_keeps_every_complete_converged_increment(model, tmp_path, marker, increments):
    from caelab.adapters.frozen_fem import read_frd
    from caelab.contact_steps import profile, validate_frames
    value = nonlinear_model(model, single=True)
    text, _, materials = outputs(value)
    if increments == 1:
        lines = text.splitlines(keepends=True)
        start = next(i for i, line in enumerate(lines) if line.split()[:1] == ['1PSTEP'] and int(line[36:48]) == 2)
        text = ''.join(lines[:start]) + ' 9999\n'
    nodes, elements, _ = validate_model(value)
    options = dict(contact_materials=materials, contact_profile=profile(value), require_contact=False)
    complete = read_frd(None, nodes, elements, data=text.encode('ascii'), **options)
    validate_frames(value, complete, complete=False)
    raw = text.replace(' 9999\n', marker).replace('\n', '\r\n').encode('ascii')
    frd, sta, target = tmp_path/'native.frd', tmp_path/'native.sta', tmp_path/'derived.frd'
    frd.write_bytes(raw); sta.write_text(status_text(), encoding='ascii')
    status = read_status(sta, value); before = deepcopy(status)
    with pytest.raises(ValueError, match='file terminator'):
        read_frd(frd, nodes, elements, **options)
    result = retained_prefix(frd, target, nodes, elements, materials, value, status)
    assert len(result['frames']) == increments
    assert result['frames'] == complete['frames']
    assert result['retention']['reason'] == 'partial_end_marker_at_eof'
    assert result['retention']['retained_line_count'] == len(raw.decode('ascii').splitlines()) - 1
    assert result['retention']['synthetic_end_marker']
    reread = read_frd(target, nodes, elements, **options)
    validate_frames(value, reread, complete=False)
    assert reread['frames'] == complete['frames']
    assert frd.read_bytes() == raw and sta.read_text() == status_text() and status == before


@pytest.mark.parametrize('incomplete', ['missing_pe', 'unconverged'])
def test_torn_file_marker_does_not_admit_missing_required_field_or_unconverged_frame(model, tmp_path, incomplete):
    value = nonlinear_model(model, single=True)
    text, _, materials = outputs(value, omit=[(2, 'PE')] if incomplete == 'missing_pe' else ())
    raw = text.replace(' 9999\n', ' 999').encode('ascii')
    sta_text = status_text(failed=incomplete == 'unconverged')
    frd, sta, target = tmp_path/'native.frd', tmp_path/'native.sta', tmp_path/'derived.frd'
    frd.write_bytes(raw); sta.write_text(sta_text, encoding='ascii')
    nodes, elements, _ = validate_model(value)
    result = retained_prefix(frd, target, nodes, elements, materials, value, read_status(sta, value))
    assert len(result['frames']) == 1
    assert result['frames'][0]['static']['increment'] == 1
    assert result['retention']['reason'] == ('incomplete_increment_at_eof' if incomplete == 'missing_pe' else 'first_nonconverged_increment')
    assert frd.read_bytes() == raw and sta.read_text() == sta_text


@pytest.mark.parametrize('damage', ['closed_marker', 'bad_marker', 'marker_midstream',
                                    'trailing_complete_marker', 'partial_pe_marker'])
def test_partial_file_marker_does_not_hide_field_or_interior_corruption(model, tmp_path, damage):
    value = nonlinear_model(model, single=True)
    text, _, materials = outputs(value)
    if damage == 'closed_marker': text = text.replace(' 9999\n', ' 999\n')
    elif damage == 'bad_marker': text = text.replace(' 9999\n', ' 999X')
    elif damage == 'marker_midstream': text = text.replace('    1PSTEP', ' 999\n    1PSTEP', 1)
    elif damage == 'trailing_complete_marker': text += ' 999'
    else: text = cut_last_pe(text) + '\n 999'
    raw = text.encode('ascii')
    frd, sta, target = tmp_path/'native.frd', tmp_path/'native.sta', tmp_path/'derived.frd'
    frd.write_bytes(raw); sta.write_text(status_text(), encoding='ascii')
    nodes, elements, _ = validate_model(value)
    with pytest.raises(ValueError):
        retained_prefix(frd, target, nodes, elements, materials, value, read_status(sta, value))
    assert not target.exists() and frd.read_bytes() == raw and sta.read_text() == status_text()


def test_absent_tie_strain_and_pe_are_not_synthesized_as_zero(model, tmp_path):
    from caelab.adapters.contact_results import write_post
    import xml.etree.ElementTree as ET
    value, text, _, materials, sta_text = case(model, 'tie')
    frd, sta = tmp_path/'native.frd', tmp_path/'native.sta'
    frd.write_text(cut_field(text, 'vector'), encoding='ascii'); sta.write_text(sta_text, encoding='ascii')
    nodes, elements, _ = validate_model(value)
    result = retained_prefix(frd, tmp_path/'derived.frd', nodes, elements, materials, value, read_status(sta,value))
    assert not {'PE', 'TOSTRAIN'} & set(result['frames'][0]['fields'])
    metadata = write_post(tmp_path/'post', value, result['frames'], [])
    assert metadata['field_availability']['PE']['present_frames'] == 0
    assert metadata['field_availability']['TOSTRAIN']['present_frames'] == 0
    names = {item.get('Name') for item in ET.parse(tmp_path/'post/frame0001.vtu').findall('.//PointData/DataArray')}
    assert not {'PEEQ_1', 'EXX_1'} & names
