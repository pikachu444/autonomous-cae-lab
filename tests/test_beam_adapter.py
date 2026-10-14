"""Execution-owner doubles; these tests do NOT run CalculiX or FreeCAD."""
from pathlib import Path
from types import SimpleNamespace as NS
import json
import pytest
from test_beam_support import model,frd,snapshot
from caelab.adapters import beam_fem
from caelab.execution_control import ExecutionCancelled,ExecutionCleanupFailed


def runner(monkeypatch,tmp_path,value=None,*,diagnostic='',version='2.22',cut=False,stop=None,change=None):
    value=value or model();binary=tmp_path/'ccx-double';binary.write_bytes(b'not a solver binary')
    calls=[]
    monkeypatch.setattr(beam_fem.shutil,'which',lambda _:str(binary))
    def command(argv,cwd,label,**kwargs):
        calls.append((argv,cwd,label,kwargs))
        assert kwargs.get('owned_tree') is True
        assert argv[-2:]==['-i','beam']
        text=frd(value,(.5,1.)).replace('Version 2.22', 'Version '+version)
        if cut:
            lines=text.splitlines(True);i=max(j for j,l in enumerate(lines) if ' -4 FORC' in l)
            text=''.join(lines[:i+5])+lines[i+5][:22]
        (cwd/'beam.frd').write_text(text,encoding='ascii')
        (cwd/'ccx_beam.stdout.log').write_text(diagnostic or 'synthetic command completion',encoding='ascii')
        if change:change(cwd)
        if stop:raise stop('explicit process-owner test double')
        return NS(returncode=0,stdout=diagnostic,stderr='')
    monkeypatch.setattr(beam_fem,'run_owned_command',command)
    return calls


def test_run_uses_existing_owner_and_reopen_never_executes(monkeypatch,tmp_path):
    source=snapshot(tmp_path/'source');original={p.name:p.read_bytes() for p in source.parent.iterdir()}
    calls=runner(monkeypatch,tmp_path)
    out=tmp_path/'run1';result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=out)
    assert result['execution_status']=='SUCCEEDED' and result['responses']['M1']['unit']=='Nmm'
    assert len(calls)==1 and result['engineering_valid'] is False
    assert result['post_artifact']['relative']=='post/beam.pvd'
    monkeypatch.setattr(beam_fem,'run_owned_command',lambda *_a,**_k:pytest.fail('Reopening must not execute'))
    saved=beam_fem.read_saved_run(out);assert saved['observed']['frames'][-1]['static']['load_parameter']==1
    assert original=={p.name:p.read_bytes() for p in source.parent.iterdir()}
    with pytest.raises(ValueError,match='overwrite'):beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=out)


@pytest.mark.parametrize('diagnostic',['*ERROR in gen3d: rotational MPC','*WARNING in gen3d: invalid moment axis'])
def test_exit_zero_with_native_error_or_warning_is_not_success(monkeypatch,tmp_path,diagnostic):
    source=snapshot(tmp_path/'source');runner(monkeypatch,tmp_path,diagnostic=diagnostic)
    result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert result['execution_status']=='FAILED' and result['responses']=={}
    assert result['diagnostics']['has_unreviewed_native_diagnostic']
    assert (tmp_path/'run'/'solver'/'beam.frd').is_file()
    assert beam_fem.read_saved_run(tmp_path/'run')['execution']['execution_status']=='FAILED'


@pytest.mark.parametrize('version',['2.21','2.23',''])
def test_wrong_solver_output_is_not_admitted(monkeypatch,tmp_path,version):
    source=snapshot(tmp_path/'source');calls=runner(monkeypatch,tmp_path,version=version)
    result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert result['execution_status']=='FAILED' and len(calls)==1
    assert result['responses']=={} and 'post_artifact' not in result
    assert (tmp_path/'run'/'solver'/'beam.inp').exists()


@pytest.mark.parametrize('status,stop',[('FAILED',None),('CANCELLED',ExecutionCancelled)])
def test_partial_and_cancel_keep_whole_previous_increment(monkeypatch,tmp_path,status,stop):
    source=snapshot(tmp_path/'source');runner(monkeypatch,tmp_path,cut=True,stop=stop)
    result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert result['execution_status']==status and result['responses']=={}
    assert result['complete_native_frames']==1
    assert beam_fem.read_saved_run(tmp_path/'run')['observed']['frames'][0]['static']['load_parameter']==.5


def test_cleanup_not_confirmed_must_not_seal_results(monkeypatch,tmp_path):
    source=snapshot(tmp_path/'source');runner(monkeypatch,tmp_path,stop=ExecutionCleanupFailed)
    with pytest.raises(ExecutionCleanupFailed):
        beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert not (tmp_path/'run'/'beam_execution.json').exists()


def test_changed_executed_deck_has_no_field_admission(monkeypatch,tmp_path):
    source=snapshot(tmp_path/'source')
    runner(monkeypatch,tmp_path,change=lambda cwd:(cwd/'beam.inp').write_text('changed'))
    result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert result['execution_status']=='FAILED' and result['responses']=={} and 'post_artifact' not in result


def test_changed_pins_and_result_bytes_are_rejected(monkeypatch,tmp_path):
    source=snapshot(tmp_path/'source');runner(monkeypatch,tmp_path)
    beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    (tmp_path/'run'/'solver'/'beam.frd').write_text('modified')
    with pytest.raises(ValueError,match='changed'):beam_fem.read_saved_run(tmp_path/'run')
    (source.parent/'beam.inp').write_text('modified')
    result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'rejected')
    assert result['execution_status']=='REJECTED' and not (tmp_path/'rejected'/'solver').exists()


def test_oblique_diagnostic_cannot_become_general_success(monkeypatch,tmp_path):
    v=model(direction=(.7,1.4,-2),diagnostic=True);source=snapshot(tmp_path/'source',v);runner(monkeypatch,tmp_path,v)
    result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert result['execution_status']=='FAILED' and result['diagnostic_only'] and result['responses']=={}


def test_retry_uses_a_new_output_and_does_not_touch_failed_attempt(monkeypatch,tmp_path):
    source=snapshot(tmp_path/'source');runner(monkeypatch,tmp_path,diagnostic='*ERROR synthetic')
    adapter=beam_fem.BeamFemCalculixAdapter();adapter.run({'snapshot_path':str(source)},output=tmp_path/'old')
    before={p.relative_to(tmp_path/'old'):p.read_bytes() for p in (tmp_path/'old').rglob('*') if p.is_file()}
    runner(monkeypatch,tmp_path)
    result=adapter.run({'snapshot_path':str(source)},output=tmp_path/'new')
    assert result['execution_status']=='SUCCEEDED'
    assert before=={p.relative_to(tmp_path/'old'):p.read_bytes() for p in (tmp_path/'old').rglob('*') if p.is_file()}


def test_reopen_changed_executed_deck_never_restores_disallowed_fields(monkeypatch,tmp_path):
    source=snapshot(tmp_path/'source')
    runner(monkeypatch,tmp_path,change=lambda cwd:(cwd/'beam.inp').write_text('wrong load'))
    beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    restored=beam_fem.read_saved_run(tmp_path/'run')
    assert restored['model'] is not None and restored['observed'] is None
    assert 'executed beam deck' in restored['execution']['saved_reader_error']


def test_post_conversion_error_does_not_leave_false_success(monkeypatch,tmp_path):
    source=snapshot(tmp_path/'source');runner(monkeypatch,tmp_path)
    def fail(*args,**kwargs):raise ValueError('synthetic conversion failure')
    monkeypatch.setattr(beam_fem,'write_post',fail)
    result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert result['execution_status']!='SUCCEEDED' and result['responses']=={}
    assert result['native_execution_status']=='SUCCEEDED' and 'post_artifact' not in result


@pytest.mark.parametrize('variant,expected', [('success','SUCCEEDED'),('warning','FAILED'),('cancel','CANCELLED'),('missing_solver','FAILED')])
def test_actual_common_evaluation_save_and_solver_free_reopen(monkeypatch,tmp_path,variant,expected):
    from caelab.evaluation import run,read_result
    source=snapshot(tmp_path/'source')
    runner(monkeypatch,tmp_path,diagnostic='*WARNING synthetic' if variant=='warning' else '',
        stop=ExecutionCancelled if variant=='cancel' else None)
    if variant=='missing_solver':monkeypatch.setattr(beam_fem.shutil,'which',lambda _:None)
    # A real registered adapter, common normalizer, array storage, and verified
    # read path; only the operating-system solver call is a process double.
    from caelab.backends import list_backends
    if 'structure.calculix.beam' not in {entry['id'] for entry in list_backends()}:
        pytest.skip('Apply integration.patch to test the common evaluation entrypoint')
    output=tmp_path/'common-run'
    result=run('structure.calculix.beam',{'snapshot_path':str(source)},output=output)
    assert result['execution_status']==expected
    assert (output/'result.json').is_file() and (output/'beam_execution.json').is_file()
    monkeypatch.setattr(beam_fem,'run_owned_command',lambda *_a,**_k:pytest.fail('Read cannot run a solver'))
    restored=read_result(output,verify='all')
    assert restored['execution_status']==expected
    native=beam_fem.read_saved_run(output)
    assert native['execution']['execution_status']==expected
    if expected=='SUCCEEDED':
        assert restored['responses']['M1']['unit']=='Nmm'
        assert restored['responses']['M1']['value']==native['execution']['responses']['M1']['value']
    else:assert restored['responses']=={}
    if variant=='warning':assert restored['native_output_status']=='PARTIAL_FAILURE'
