"""Public example declaration / owned-runner contract tests. NO native runs."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import runpy
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.motion_formula import compile_drives
from apps.desktop_pre.motion_occurrence import hierarchy
from apps.desktop_pre.motion_relation import validate_raw_relation

BASE = Path(__file__).resolve().parents[1]/'examples'/'assembly_relations'


def module(name):
    spec = importlib.util.spec_from_file_location('example_'+name, BASE/(name+'.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def plain_context():
    joints = {n: NS(Name='Joint'+n, Label='회전 '+n, Group=[], TypeId='App::FeaturePython') for n in 'ABCLX'}
    group = NS(Name='Joints',Label='관절',TypeId='Assembly::JointGroup',Group=list(joints.values()))
    root = NS(Name='Rig',Label='기준 조립',TypeId='Assembly::AssemblyObject',Group=[group])
    return {'assembly':root,'joints':joints,'moving':{n:NS(Name='Link'+n) for n in 'ABCLX'}}


@pytest.mark.parametrize('case', ['linear','changed','nonlinear'])
def test_public_declaration_validates_without_running_native(case):
    factory = module('create_relations'); context = plain_context()
    definition = factory.definition_for(context,case)
    paths = hierarchy(context['assembly'])
    joints = {obj.Name: {'type':'Revolute' if n in 'ABC' else 'Slider','path':paths[obj.Name][0]['path']}
        for n,obj in context['joints'].items()}
    compiled,errors = compile_drives(definition['drives'],(0.,1.),joints)
    assert not errors and len(compiled)==5
    for raw in (False,True):
        editor = factory.editor_for(definition,invalid=raw)
        if raw:
            for drive in editor['definition_draft']['drives']:
                if drive.get('relation') is not None: validate_raw_relation(drive['relation'])
            assert editor['definition_draft']['drives'][3]['relation']['constants'][0]['value']=='1e'
        else: assert editor['definition_draft'] is None
    if case=='changed':
        prior = factory.definition_for(context,'linear')
        assert prior['drives'][3:] == definition['drives'][3:]
        assert prior['drives'][0]['formula'] != definition['drives'][0]['formula']


def test_fixture_oracle_is_exact_copy_of_submitted_arithmetic_reference():
    assert (BASE/'reference-oracle.json').read_bytes() == (Path(__file__).parent/'data'/'m1_relation_oracle.json').read_bytes()


def test_import_is_inert_and_nonwindows_refusal_starts_nothing(tmp_path,monkeypatch):
    check = module('native_check'); calls = []
    monkeypatch.setattr(check,'os',NS(name='posix'))
    monkeypatch.setattr(check.runpy,'run_path',lambda *a,**kw: calls.append(a))
    with pytest.raises(OSError,match='Windows'): check.run('FreeCAD.exe',tmp_path/'evidence')
    assert not calls and not (tmp_path/'evidence').exists()


@pytest.mark.parametrize('fault',['timeout','no-report','failed','wrong-pid','cleanup'])
def test_existing_job_receipt_is_not_mistaken_for_native_acceptance(tmp_path,monkeypatch,fault):
    check = module('native_check')
    monkeypatch.setattr(check,'os',NS(name='nt'))  # launcher DOUBLE, not os globally
    executable = tmp_path/'FreeCAD.exe'; executable.write_text('not executable; never started')
    calls = []
    def runner(command,output,timeout_seconds,cwd):
        calls.append(command); output.mkdir()
        assert '--user-cfg' in command and '--system-cfg' in command
        assert 'single-instance' not in ' '.join(command)
        receipt = output/'native-check.json'; receipt.write_text('{"test_double":true}')
        if fault!='no-report':
            (output.parent/'result.json').write_text(json.dumps({'completed':fault not in ('timeout','failed'),
                'pid':100 if fault=='wrong-pid' else 99,'kind':'test-double-not-native'}))
        return NS(receipt=str(receipt),exit_code=124 if fault=='timeout' else 0,timed_out=fault=='timeout',
            cleanup='unverified' if fault=='cleanup' else 'job_empty',pid=99)
    monkeypatch.setattr(check.runpy,'run_path',lambda path: {'run_native_check':runner})
    with pytest.raises(RuntimeError,match='실패/미확인'): check.run(executable,tmp_path/'out',15)
    assert len(calls)==1  # no cold-read process after a failed compute phase
    report = json.loads((tmp_path/'out'/'acceptance.json').read_text(encoding='utf-8'))
    assert not report['completed'] and report['phases'][0]['phase']=='compute'
    assert (tmp_path/'out'/'compute'/'run.FCMacro').is_file()
    # Preserve failure receipts/logs on subsequent attempts, never overwrite.
    previous = (tmp_path/'out'/'acceptance.json').read_bytes()
    with pytest.raises(FileExistsError): check.run(executable,tmp_path/'out',15)
    assert (tmp_path/'out'/'acceptance.json').read_bytes()==previous
