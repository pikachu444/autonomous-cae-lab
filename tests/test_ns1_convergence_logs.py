"""Supplied Windows native logs are read, not rerun. Error cases are synthetic."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pytest

from caelab.calculix_convergence import (read_convergence, read_cvg, read_stdout,
    combine, reopen_convergence)

FIXTURE = Path(__file__).parent / 'fixtures/ns1_convergence_0548ee0'


def supplied():
    return json.loads((FIXTURE/'contact_execution.json').read_bytes())


def header():
    return 'SUMMARY OF C0NVERGENCE INFORMATION\n'


def cvgrow(step=1,inc=1,att=1,it=1,r=50.,c=100.):
    return f'  {step:4d}  {inc:4d}  {att:4d}  {it:4d}  {0:7d} {r:11.4E} {c:11.4E} {0.:11.4E} {0.:11.4E}\n'


def stdoutblock(inc=1,att=1,total=.1,local=.1,delta=.1,decision='convergence',ls=None):
    return (f' increment {inc} attempt {att}\n increment size= {delta:.6e}\n'
            f' actual step time= {local:.6e}\n actual total time= {total:.6e}\n iteration 1\n'+
            (f'line search factor={ls}\n' if ls is not None else '')+
            ' average force= 10.000000\n time avg. forc= 9.000000\n'
            ' largest residual force= 0.002500 in node 7 and dof 3\n'
            ' largest increment of disp= 1.000000e-02\n'
            ' largest correction to disp= 1.000000e-03 in node 8 and dof 1\n'+decision+'\n')


def stdout(*blocks):
    return ('CalculiX Version 2.22, Copyright\n'+''.join(blocks)).encode()


def test_supplied_10_increment_25_iteration_native_record_is_read_only():
    record=supplied();before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.iterdir() if p.is_file()}
    h=read_convergence(FIXTURE,record['executed_setup'],record['increment_history'],execution_status='SUCCEEDED',flat=True)
    assert len(h['rows'])==25
    assert len({(r['step'],r['increment'],r['attempt']) for r in h['rows']})==10
    assert all(v['status']=='records' for v in h['sources'].values())
    first,last=h['rows'][0],h['rows'][-1]
    assert last['cvg']['values']['residual_force_pct']==.003752
    assert last['cvg']['values']['correction_disp_pct']==.08743
    assert first['stdout']['values']['residual_force']['token']=='0.020567'
    assert first['stdout']['values']['residual_force']['node']==662
    assert first['stdout']['values']['residual_force']['dof']==3
    assert last['stdout']['values']['average_force']['value']!=last['stdout']['values']['time_average_force']['value']
    ninth=[r for r in h['rows'] if (r['increment'],r['iteration'])==(9,3)][0]
    assert ninth['cvg']['values']['correction_disp_pct']>1.
    assert ninth['iteration_status']=='converged'  # No independent threshold verdict.
    assert h['axis']['unit']=='1' and h['sources']['cvg']['thermal_channels'].startswith('inactive')
    assert 'line_search_factor' not in last['stdout']['values']
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.iterdir() if p.is_file()}


@pytest.mark.parametrize('eol',['\n','\r\n'])
def test_cvg_torn_final_record_retains_prefix_but_not_a_fake_iteration(eol):
    text=(header()+cvgrow()+cvgrow(it=2)[:-5]).replace('\n',eol)
    r=read_cvg('unused',data=text.encode())
    assert r['status']=='partial_eof' and len(r['rows'])==1
    assert r['diagnostics'][0]['line']==3


@pytest.mark.parametrize('bad',[
    '1 1 1 2 0 NaN 1.0000E+00 0.0000E+00 0.0000E+00\n',
    cvgrow(it=1),cvgrow(it=3),cvgrow(it=2).replace('1.0000E+02','1.0000E+0x'),
    'not a numeric convergence row\n'])
def test_cvg_interior_damage_is_not_skipped_to_later_good_rows(bad):
    result=read_cvg('unused',data=(header()+cvgrow()+bad+cvgrow(it=4)).encode())
    assert result['status']=='corrupt' and len(result['rows'])==1


def test_missing_empty_and_inactive_thermal_columns_are_distinct(tmp_path):
    setup=supplied()['executed_setup']
    h=read_convergence(tmp_path,setup,flat=True)
    assert h['rows']==[] and h['sources']['cvg']['status']=='missing'
    (tmp_path/'contact.cvg').write_bytes(b'')
    h=read_convergence(tmp_path,setup,flat=True)
    assert h['sources']['cvg']['status']=='empty'
    assert h['sources']['stdout']['status']=='missing'


@pytest.mark.parametrize('tail',[
    ' iteration ', ' average force= 1e-', ' largest residual force= 0.00',
    ' largest correction to disp= 1e-03 in node 8 and do', 'converg'])
def test_stdout_tail_does_not_create_complete_or_accepted_iteration(tail):
    setup=supplied()['executed_setup']
    text=stdout(stdoutblock())+b' increment 2 attempt 1\n actual step time= .2\n actual total time= .2\n'
    if not tail.startswith(' iteration'):
        text+=b' iteration 1\n'
    r=read_stdout('unused',setup,data=text+tail.encode())
    assert r['status']=='partial_eof'
    assert r['rows'][0]['record_status']=='complete'
    assert not any(x['decision']=='converged' for x in r['rows'][1:])


@pytest.mark.parametrize('mutation',[
    lambda s:s.replace('0.002500 in node','bad in node'),
    lambda s:s.replace('iteration 1','iteration broken'),
    lambda s:s.replace('actual total time=', 'actual total time=bad'),
    lambda s:s.replace('in node 7 and dof 3','in node 7 and dof 8'),
])
def test_stdout_interior_corruption_is_not_silently_recovered(mutation):
    setup=supplied()['executed_setup']
    r=read_stdout('unused',setup,data=stdout(stdoutblock(),mutation(stdoutblock(inc=2,total=.2,local=.2)),stdoutblock(inc=3,total=.3,local=.3)))
    assert r['status']=='corrupt'
    assert not any(row['increment']==3 for row in r['rows'])


def test_rejected_retries_and_step_reset_are_keyed_not_flattened():
    setup={'step':{'period':1},'program':{'procedure':'static','steps':[{'duration':1},{'duration':1}]}}
    out=read_stdout('x',setup,data=stdout(stdoutblock(decision='no convergence'),
        stdoutblock(att=2,total=.05,local=.05,delta=.05),stdoutblock(total=1.1,local=.1,ls=.7)))
    cvg=read_cvg('x',data=(header()+cvgrow()+cvgrow(att=2)+cvgrow(step=2)).encode())
    status={'rows':[{'step':s,'increment':1,'attempt':a,'iterations':1,'converged':ok,
                    'total':t,'increment_size':delta,'line':i} for i,(s,a,ok,t,delta) in enumerate(
                        [(1,1,False,0,.1),(1,2,True,.05,.05),(2,1,True,1.1,.1)],1)]}
    merged=combine(cvg,out,status,execution_status='CANCELLED')
    assert [(r['step'],r['attempt'],r['attempt_status']) for r in merged]==[(1,1,'rejected'),(1,2,'converged'),(2,1,'converged')]
    assert all(r['job_status']=='CANCELLED' for r in merged)
    assert merged[-1]['stdout']['values']['line_search_factor']['value']==.7


def test_unresolved_step_and_wrong_banner_are_not_attributed_to_cvg():
    setup=supplied()['executed_setup'];cvg=read_cvg('x',data=(header()+cvgrow()).encode())
    raw=stdout(stdoutblock()).replace(b' actual total time= 1.000000e-01\n',b'')
    out=read_stdout('x',setup,data=raw)
    assert out['rows'][0]['identity_status']=='unresolved_step'
    assert 'stdout' not in combine(cvg,out)[0]
    out=read_stdout('x',setup,data=stdout(stdoutblock()).replace(b'2.22',b'2.23'))
    assert out['status']=='corrupt' and 'stdout' not in combine(cvg,out)[0]


def test_sta_stdout_conflicting_success_is_not_promoted():
    setup=supplied()['executed_setup'];out=read_stdout('x',setup,data=stdout(stdoutblock()))
    status={'rows':[{'step':1,'increment':1,'attempt':1,'iterations':2,'converged':False,
                    'total':0,'increment_size':.1,'line':1}]}
    merged=combine({'rows':[]},out,status,execution_status='FAILED')
    assert merged[0]['attempt_status']=='conflict' and merged[0]['job_status']=='FAILED'


def make_retained(tmp_path):
    root=tmp_path/'attempt';(root/'solver').mkdir(parents=True)
    record=supplied()
    for filename in ('contact.cvg','ccx_contact.stdout.log'):
        (root/'solver'/filename).write_bytes((FIXTURE/filename).read_bytes())
    record['artifacts']=[{'relative':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,
                         'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (root/'solver').iterdir()]
    (root/'contact_execution.json').write_text(json.dumps(record))
    return root


def test_reopen_checks_pins_and_new_process_needs_no_solver(tmp_path):
    root=make_retained(tmp_path);before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    assert len(reopen_convergence(root)['rows'])==25
    script='from caelab.calculix_convergence import reopen_convergence; import sys,json; h=reopen_convergence(sys.argv[1]); print(json.dumps([len(h["rows"]),h["rows"][-1]["job_status"]]))'
    import os
    env=dict(os.environ,PATH='');p=subprocess.run([sys.executable,'-c',script,str(root)],env=env,text=True,capture_output=True,timeout=10,check=True)
    assert json.loads(p.stdout)==[25,'SUCCEEDED']
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    with (root/'solver/contact.cvg').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='변경'):reopen_convergence(root)


def test_closed_interior_missing_quantity_is_not_eof_recovery():
    setup=supplied()['executed_setup']
    first=stdoutblock().replace(' time avg. forc= 9.000000\n','')
    parsed=read_stdout('x',setup,data=stdout(first,stdoutblock(inc=2,total=.2,local=.2)))
    assert parsed['status']=='corrupt' and not any(r['increment']==2 for r in parsed['rows'])


def test_cvg_partial_header_and_active_thermal_scope_are_not_zero_data():
    h=read_cvg('x',data=b'SUMMARY OF C0NVERGENCE INF')
    assert h['status']=='partial_eof' and h['rows']==[]
    data=(header()+cvgrow().rsplit('0.0000E+00',1)[0]+'1.0000E+00\n').encode()
    h=read_cvg('x',data=data)
    assert h['status']=='unsupported_scope' and h['rows']==[]


def test_reopening_parses_the_verified_bytes_not_a_changed_second_read(tmp_path,monkeypatch):
    from caelab import calculix_convergence as module
    root=make_retained(tmp_path)
    original=module.read_convergence
    def race(*args,**kwargs):
        (root/'solver/contact.cvg').write_text('foreign replacement')
        return original(*args,**kwargs)
    monkeypatch.setattr(module,'read_convergence',race)
    h=module.reopen_convergence(root)
    assert len(h['rows'])==25 and h['sources']['cvg']['status']=='records'
    with pytest.raises(ValueError):module.reopen_convergence(root)
