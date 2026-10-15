"""Activation-aware native-shaped output, adapter retention and cold-read checks.

Byte fixtures/process doubles below test contracts; they do not qualify a solver.
"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from test_contact_execution import model, native_outputs
from test_contact_recover1 import state_model
from test_contact_steps import write_snapshot
from caelab.contact_activation import compile_states, output_pairs, require_contact
from caelab.contact_deck import render, validate_model
from caelab.contact_steps import profile, validate_frames
from caelab.adapters.frozen_fem import read_frd
from caelab.adapters.contact_results import read_dat, write_post
from caelab.contact_inspection import load
from caelab.contact_resultants import history
from caelab.contact_status import read_status, retained_prefix


@pytest.mark.parametrize('stdout,stderr,code,accepted',[
    ('This is Version 2.22\n','',201,True),
    ('This is Version 2.22\n','native error',201,False),
    ('Version 2.22\nERROR','',201,False),
    ('This is Version 2.21\n','',201,False),
    ('This is Version 2.22\n','',1,False)])
def test_version_stop_code_only_identifies_clean_version_probe(tmp_path,model,stdout,stderr,code,accepted):
    from caelab.contact_execution_extensions import require_runtime
    def probe(*args,**kwargs):return NS(stdout=stdout,stderr=stderr,returncode=code)
    if accepted:
        receipt=require_runtime(Path(sys.executable),tmp_path,state_model(model),probe)
        assert receipt['version_probe_return_code']==201 and receipt['contact_extension_qualification']=='UNKNOWN'
    else:
        with pytest.raises(ValueError,match='VERSION_UNKNOWN'):
            require_runtime(Path(sys.executable),tmp_path,state_model(model),probe)


def activation_outputs(value):
    frd, dat, materials = native_outputs(value)
    initial = frd.split('    1PSTEP', 1)[0].splitlines()
    fields = frd.split('    1PSTEP')[1:3]
    nodes = {r['node_id'] for r in value['nodes']}
    lines = list(initial)
    records = []
    counter = 0
    schedule = compile_states(value)
    template = dat[:dat.index(' S T E P 1\n INCREMENT 2')]
    for index, stage in enumerate(schedule['steps'], 1):
        active = bool(output_pairs(value['contacts'], schedule, index))
        for name, source in zip(('DISP', 'CONTACT'), fields):
            if name == 'CONTACT' and not active:
                continue
            counter += 1
            rows = source.splitlines()
            lines.append('    1PSTEP'+' '*14+f'{counter:12d}{1:12d}{index:12d}'+' '*10)
            lines.append('  100CL'+f'{100+index:5d}{index*.5:12.9f}{len(nodes):12d}'+' '*21+'0'+f'{index:5d}'+' '*11+'1')
            lines.extend(rows[2:])
        if active:
            block = template.replace(' S T E P 1', ' S T E P '+str(index))
            block = block.replace('5.0000000E-01', f'{index*.5:.7E}')
            records.append(block)
    lines.append(' 9999')
    return '\n'.join(lines)+'\n', ''.join(records), materials


def parse_outputs(tmp_path, value):
    frd, dat, materials = activation_outputs(value)
    f, d = tmp_path/'contact.frd', tmp_path/'contact.dat'
    f.write_text(frd, encoding='ascii', newline='\n')
    d.write_text(dat, encoding='ascii', newline='\n')
    nodes, elements, _ = validate_model(value)
    observed = read_frd(f, nodes, elements, contact_materials=materials,
                        contact_profile=profile(value), require_contact=require_contact(value))
    validate_frames(value, observed)
    rows = read_dat(d, value['contacts'], observed['frames'], activation=compile_states(value))
    return observed, rows, (f, d), materials


def test_activation_native_requests_and_actual_output_coverage(model, tmp_path):
    value = state_model(model)
    blocks = render(value).split('*STEP,')[1:]
    assert ['*CONTACT PRINT,FREQUENCY=0' in b for b in blocks] == [True, False, True]
    assert ['CF,CFN,CFS' in b for b in blocks] == [False, True, False]
    assert ['CDIS,CSTR' in b for b in blocks] == [False, True, False]
    observed, rows, _, _ = parse_outputs(tmp_path, value)
    assert [set(f['fields']) for f in observed['frames']] == [{'DISP'}, {'DISP','CONTACT'}, {'DISP'}]
    assert len(rows) == 3 and {r['static']['step'] for r in rows} == {2}
    metadata = write_post(tmp_path/'post', value, observed['frames'], rows, provenance={
        'snapshot_id':'Factivation','snapshot_sha256':'a'*64,'raw_frd_sha256':'b'*64,'raw_dat_sha256':'c'*64})
    restored = load(tmp_path/'post/contact.pvd', metadata['contact_inspection'])
    selected = history(restored, 'Contact', 'CFN', 2)
    assert [r['valid'] for r in selected['rows']] == [False, True, False]
    assert [r['reason'] for r in selected['rows']] == ['NOT_PRODUCED', None, 'NOT_PRODUCED']
    assert [r['input_activation'] for r in selected['rows']] == ['inactive','active','inactive']
    assert all(r['value'] is None for r in (selected['rows'][0], selected['rows'][2]))
    assert restored['frames'][2]['pair_output_availability'] == {'Contact':'not_requested_input_inactive'}
    assert [f['field_availability']['CONTACT'] for f in restored['frames']] == [
        'not_requested_input_inactive', 'available', 'not_requested_input_inactive']


def test_active_missing_and_inactive_extra_native_outputs_are_not_accepted(model, tmp_path):
    value = state_model(model)
    observed, rows, (_, d), _ = parse_outputs(tmp_path, value)
    missing = deepcopy(observed)
    del missing['frames'][1]['fields']['CONTACT']
    with pytest.raises(ValueError, match='active pair'):
        validate_frames(value, missing)
    active_dat = d.read_text()
    d.write_text(active_dat.replace(' S T E P 2', ' S T E P 1').replace('1.0000000E+00','5.0000000E-01'))
    with pytest.raises(ValueError, match='inactive|unrequested'):
        read_dat(d, value['contacts'], observed['frames'], activation=compile_states(value))
    d.write_text('')
    with pytest.raises(ValueError, match='Missing'):
        read_dat(d, value['contacts'], observed['frames'], activation=compile_states(value))


def test_all_inactive_has_no_dat_requirement_and_prefix_retains_inactive_step(model, tmp_path):
    value = state_model(model, ('inactive','inactive','inactive'))
    observed, rows, (f, d), materials = parse_outputs(tmp_path, value)
    assert rows == [] and all('CONTACT' not in row['fields'] for row in observed['frames'])
    d.unlink()
    assert read_dat(d, value['contacts'], observed['frames'], activation=compile_states(value)) == []
    sta = tmp_path/'contact.sta'
    sta.write_text(' 1 1 1 3 .5 .5 .5\n 2 1 1 3 1.0 .5 .5\n 3 1 1 3 1.5 .5 .5\n')
    nodes, elements, _ = validate_model(value)
    before = f.read_bytes()
    retained = retained_prefix(f, tmp_path/'derived.frd', nodes, elements, materials, value, read_status(sta, value))
    assert len(retained['frames']) == 3 and f.read_bytes() == before


def test_pair_specific_requests_preserve_order_with_tie_and_different_availability(model, tmp_path):
    value = state_model(model)
    second = deepcopy(value['contacts'][0]); second['object_id'] = 'Second'
    tied = deepcopy(second); tied['object_id'] = 'Tied'
    tied['draft'].update(normal_law='tie', tangential_law='tied', tie_tolerance_mm='.1')
    value['contacts'] += [second, tied]
    for index, stage in enumerate(value['analysis_steps']['steps']):
        stage['contact_states'] += [{'pair_id':'Second','state':'active' if index < 2 else 'inactive'},
                                    {'pair_id':'Tied','state':'active'}]
    schedule = compile_states(value)
    assert [[r['object_id'] for r in output_pairs(value['contacts'], schedule, i)] for i in (1,2,3)] == [
        ['Second'], ['Contact','Second'], []]
    blocks = render(value).split('*STEP,')[1:]
    assert 'SLAVE=DEPContact' not in blocks[0] and 'SLAVE=DEPSecond' in blocks[0]
    assert blocks[1].index('SLAVE=DEPContact') < blocks[1].index('SLAVE=DEPSecond')
    assert 'SLAVE=DEPTied' not in ''.join(blocks)
    _, dat, _ = native_outputs(value)
    raw_blocks = re.findall(r' statistics for slave set.*?(?= statistics for slave set| S T E P|\Z)', dat, re.S)
    first = ''.join(raw_blocks[3:6])  # Second only; Contact is not requested.
    second = ''.join(raw_blocks[:6]).replace('5.0000000E-01', '1.0000000E+00')
    path = tmp_path/'pair-order.dat'
    path.write_text(' S T E P 1\n INCREMENT 1\n'+first+' S T E P 2\n INCREMENT 1\n'+second)
    frames = [{'static':{'step':i,'increment':1,'load_parameter':i*.5}, 'load_parameter_token':f'{i*.5:.7E}'} for i in (1,2,3)]
    rows = read_dat(path, value['contacts'], frames, activation=schedule)
    assert [(r['pair_id'], r['quantity']) for r in rows] == [
        (pid, q) for pid in ('Second','Contact','Second') for q in ('CF','CFN','CFS')]
    assert not any(r['static']['step'] == 3 for r in rows)


@pytest.mark.parametrize('returncode', [0, 1])
def test_adapter_native_boundary_save_cold_and_failed_state_preserved(model, tmp_path, monkeypatch, returncode):
    from caelab.adapters import contact_fem
    from caelab.evaluation import normalize_evaluation, save_evaluation, read_result
    value = state_model(model)
    snapshot = write_snapshot(value, tmp_path/'input')
    frd, dat, _ = activation_outputs(value)
    before = {p.name:p.read_bytes() for p in snapshot.parent.iterdir()}
    solver_calls = []
    monkeypatch.setattr(contact_fem.shutil, 'which', lambda _:sys.executable)
    def native(command, cwd, label, **kwargs):
        if command[-1] == '-v':
            return NS(returncode=0, stdout='Version 2.22', stderr='')
        solver_calls.append(command)
        (cwd/'contact.frd').write_text(frd, encoding='ascii', newline='\n')
        (cwd/'contact.dat').write_text(dat, encoding='ascii', newline='\n')
        (cwd/'contact.sta').write_text(' 1 1 1 3 .5 .5 .5\n 2 1 1 3 1.0 .5 .5\n 3 1 1 3 1.5 .5 .5\n')
        return NS(returncode=returncode, stdout='', stderr='controlled failure' if returncode else '')
    monkeypatch.setattr(contact_fem, 'run_owned_command', native)
    attempt = tmp_path/'attempt'
    result = normalize_evaluation(contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(snapshot)}, output=attempt))
    assert len(solver_calls) == 1
    assert before == {p.name:p.read_bytes() for p in snapshot.parent.iterdir()}
    assert result['execution_status'] == ('FAILED' if returncode else 'SUCCEEDED'), result['diagnostics']
    if returncode:
        assert result['responses'] == {} and result['partial_result']['frame_count'] == 3
        assert result['partial_result']['complete_analysis'] is False
    else:
        assert result['responses']['COPEN']['value'] == []
        assert result['responses']['COPEN']['metadata']['pair_output_availability']['Contact'] == 'not_requested_input_inactive'
        assert len(result['responses']['Contact.CFN.FZ']['value']) == 1
        # The ordinary evaluation.run saves in the native attempt directory.
        save_evaluation(result, attempt, existing=True)
        saved = read_result(attempt/'result.json', verify='all')
        assert saved['execution_status'] == 'SUCCEEDED'
        assert saved['responses']['Contact.CFN.FZ']['value'] == result['responses']['Contact.CFN.FZ']['value']
        original = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in attempt.rglob('*') if p.is_file()}
        rebuilt = contact_fem.regenerate_post(attempt, tmp_path/'rebuilt')
        assert rebuilt['solver_execution'] == 'NOT_PERFORMED' and rebuilt['frame_count'] == 3
        assert original == {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in original}
        bundle = attempt/'post/contact.pvd'
        meta = result['post_artifact']['native_metadata']['contact_inspection']
        code = ('import json,sys;from pathlib import Path;from caelab.contact_inspection import load;'
                'from caelab.contact_resultants import history;'
                'b=load(Path(sys.argv[1]),json.loads(sys.argv[2]));'
                'r=history(b,"Contact","CFN",2);'
                'assert [x["input_activation"] for x in r["rows"]]==["inactive","active","inactive"];'
                'assert [x["valid"] for x in r["rows"]]==[False,True,False];print("COLD_ACTIVATION_READ_PASS")')
        cold = subprocess.run([sys.executable,'-c',code,str(bundle),json.dumps(meta)],capture_output=True,text=True,timeout=20)
        assert cold.returncode == 0, cold.stderr
        assert 'COLD_ACTIVATION_READ_PASS' in cold.stdout and len(solver_calls) == 1
