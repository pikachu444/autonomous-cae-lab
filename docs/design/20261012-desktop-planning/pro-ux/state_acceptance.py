"""Portable stdlib regression checks for the isolated planning state; no solver or provider."""
import argparse
import sys
import importlib.util
import json
import hashlib
import tempfile
import subprocess
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,default=Path(__file__).parent)
parser.add_argument('--output',type=Path,default=Path(tempfile.mkdtemp(prefix='caelab-state-check-')))
args=parser.parse_args();ROOT=args.output;ROOT.mkdir(parents=True,exist_ok=True)
RUN=Path(tempfile.mkdtemp(prefix='run-',dir=ROOT));SOURCE=args.source.resolve()/'prototype_state.py'
spec = importlib.util.spec_from_file_location('prototype_state_review', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
results = []

def session(name):
    return m.ReviewSession(RUN / name)

def check(name, fn):
    try:
        detail = fn()
        results.append({'check': name, 'status': 'PASS', 'detail': detail})
    except Exception as exc:
        results.append({'check': name, 'status': 'FAIL', 'detail': f'{type(exc).__name__}: {exc}'})

def blocked(fn):
    try:
        fn()
    except m.ReviewError:
        return
    raise AssertionError('Operation continued when ReviewError was required')

def adoption():
    s = session('adoption')
    g = s.prepare_adoption('p19')
    assert g['owners']['cad']['expected_revision'] == 13
    assert g['owners']['material']['expected_revision'] == 18
    for key in ('cad', 'material'):
        s.apply_owner(g['id'], key)
    cad = s.save_adoption_owner(g['id'], 'cad')
    blocked(lambda: s.save_adoption_owner(g['id'], 'material', fail=True))
    assert s.doc('cad')['revision'] == 14 and not s.doc('cad')['dirty']
    assert s.doc('material')['revision'] == 18 and s.doc('material')['dirty']
    blocked(lambda: s.publish_group(g['id']))
    material = s.save_adoption_owner(g['id'], 'material')
    receipt = s.publish_group(g['id'])
    assert receipt['owners'] == {'cad': cad, 'material': material}
    assert cad['revision'] == 14 and material['revision'] == 19
    assert s.save_adoption_owner(g['id'], 'cad') == cad
    assert s.publish_group(g['id']) == receipt
    assert s.doc('cad')['revision'] == 14
    path = RUN / 'adoption-session.json'
    s.save_session(path)
    reopened = m.ReviewSession.open_session(path)
    assert reopened.dump() == s.dump()
    assert reopened.publish_group(g['id']) == receipt
    code = "import importlib.util; z=importlib.util.spec_from_file_location('review',%r); m=importlib.util.module_from_spec(z); z.loader.exec_module(m); s=m.ReviewSession.open_session(%r); g=next(iter(s.groups.values())); assert s.doc('cad')['revision']==14; assert s.doc('material')['revision']==19; assert s.publish_group(g['id'])==g['receipt']; assert s.dump()['F05']['value']==3.32295e-6; print('exact cold receipt PASS')" % (str(SOURCE), str(path))
    proc = subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert proc.returncode == 0, proc.stderr
    return 'CAD14/Material19 exact owner receipts; failed Material18 dirty retained; repeat and cold reopen stable'

def cancelled_continue():
    s = session('cancelled')
    g = s.prepare_adoption('p19')
    s.cancel_adoption(g['id'])
    blocked(lambda: s.apply_owner(g['id'], 'cad'))

def cancelled_publish():
    s = session('cancel-publish')
    g = s.prepare_adoption('p19')
    for key in ('cad', 'material'):
        s.apply_owner(g['id'], key)
        s.save_adoption_owner(g['id'], key)
    s.cancel_adoption(g['id'])
    blocked(lambda: s.publish_group(g['id']))

def stale_memory():
    s = session('stale-memory')
    g = s.prepare_adoption('p19')
    for key in ('cad', 'material'):
        s.apply_owner(g['id'], key)
        s.save_adoption_owner(g['id'], key)
    s.edit('cad', 'thickness', 99)
    blocked(lambda: s.publish_group(g['id']))

def stale_disk():
    s = session('stale-disk')
    g = s.prepare_adoption('p19')
    for key in ('cad', 'material'):
        s.apply_owner(g['id'], key)
        s.save_adoption_owner(g['id'], key)
    path = Path(s.doc('cad')['file'])
    raw = json.loads(path.read_text())
    raw['document']['revision'] = 15
    raw['document']['saved']['thickness'] = 99
    path.write_text(json.dumps(raw))
    blocked(lambda: s.publish_group(g['id']))

def data():
    s = session('data')
    old = m.clone(s.results['fixture-data-A301'])
    s.mask(['A82'])
    assert s.results['fixture-data-A301'] == old
    blocked(s.refresh_data_source)
    s.save_document('data')
    s.refresh_data_source()
    s.save_document('numerical')
    frozen = s.freeze('numerical')
    assert frozen['included_count'] == 300 and 'A82' not in frozen['included_ids']
    assert frozen['observation_ref'] == {'id': 'DATA-01', 'revision': 5}
    assert s.results['fixture-data-A301'] == old
    before = m.clone(s.doc('data')['draft'])
    ids = [f'A{i}' for i in range(78,86)]
    assert len(ids) == 8
    s.mask(ids)
    assert len(s.doc('data')['draft']['samples']) - len(s.doc('data')['draft']['quality_excluded']) == 293
    s.save_document('data')
    s.refresh_data_source()
    s.save_document('numerical')
    assert s.freeze('numerical')['included_count'] == 293
    assert s.history_step('data')
    assert s.doc('data')['draft'] == before
    return 'A301 retained; explicit saved refresh A300; inclusive A78..A85 excludes 8 total yielding293; undo exact'

def routes():
    s = session('routes')
    for key, doc_id, revision, backend in [('thermal','V-02',4,'thermal.fenicsx.rectangle'), ('thermoelastic','V-03',6,'structural.fenicsx.thermoelastic_rectangle')]:
        s.save_document(key)
        fresh = session('routes-cold-' + key)
        reopened = fresh.open_document(s.doc(key)['file'])
        actual_key, payload = fresh.resolve({'id': doc_id, 'revision': revision})
        assert reopened == key and actual_key == key and payload['backend'] == backend
        fresh.edit(key, 'backend', 'Code_Aster')
        assert fresh.resolve({'id': doc_id, 'revision': revision})[1]['backend'] == backend

def repair():
    s = session('repair')
    s.material_repair_scenario()
    original = SOURCE.parent / 'fixtures' / 'Tension.csv'
    checksum = hashlib.sha256(original.read_bytes()).hexdigest()
    d = s.doc('material')
    assert d['saved']['dependencies'][0]['sha256'] == checksum
    assert d['saved']['mu'] == .862
    assert d['saved']['adoption'] == {'candidate':'c017','fit_source':{'id':'MAT-01','revision':17},'plan':{'id':'N-FIT','revision':8},'result':'fixture-result-c017'}
    before = m.clone(d)
    out = s.repair_dependency('material','TENSION-A',original)
    assert out == {'kind':'IDENTICAL_REPAIR','id':'MAT-01','revision':19}
    assert s.doc('material') == before
    changed = RUN / 'repair-changed.csv'
    changed.write_bytes(b'public synthetic changed tension\n1,3\n')
    blocked(lambda: s.repair_dependency('material','TENSION-A',changed))
    assert s.doc('material') == before
    branch = s.repair_dependency('material','TENSION-A',changed, changed_branch=True)
    assert s.doc('material') == before
    assert branch['id'] != 'MAT-01'
    assert s.doc(branch['key'])['draft']['branch_of'] == {'id':'MAT-01','revision':19}
    assert s.doc('data')['saved']['calibration']['id'] == 'CAL-018'
    assert s.doc('data')['saved']['calibration']['file'] == 'Calibration.txt'
    return 'Actual fixture SHA used; c017 .862 MAT17/NFIT8 provenance; exact r19 intact after identical repair, declined changedcontent and branch; CAL-018 points to Calibration.txt'

def invalid():
    s = session('invalid')
    s.edit('material','mu',-1)
    receipt = s.save_document('material')
    assert receipt['revision'] == 19
    assert s.doc('material')['saved']['mu'] == -1
    blocked(lambda:s.freeze('material'))

def runner():
    s = session('runner')
    frozen = s.freeze('simulation')
    job = s.create_attempt(frozen['id'])
    s.edit('simulation','force',999)
    assert s.frozen[frozen['id']]['payload']['force'] == -250
    s.job_event(job['id'],'running')
    s.job_event(job['id'],'disconnect')
    attempt = job['attempt']
    s.job_event(job['id'],'reconnect')
    assert job['attempt'] == attempt and len(s.jobs)==1 and job['status']=='RUNNING_FIXTURE'
    s.job_event(job['id'],'cancel')
    assert job['status']=='CANCEL_REQUESTED'
    s.job_event(job['id'],'terminal')
    assert job['status']=='CANCELLED'
    s.job_event(job['id'],'result')
    result = s.results[job['result']]
    assert job['status']=='CANCELLED' and result['attempt']==attempt and result['input']==frozen['id']
    assert result['source']=={'id':'V-01','revision':7}
    blocked(lambda:s.job_event(job['id'],'running'))

def unsupported():
    s = session('unsupported')
    for key in ('thermal','thermoelastic','material','numerical','pde'):
        frozen = s.freeze(key)
        job = s.create_attempt(frozen['id'])
        before = m.clone(s.results)
        blocked(lambda:s.job_event(job['id'],'result'))
        assert s.results == before and job['result'] is None

def dynamic():
    s = session('dynamic')
    key='fit:material'
    payload = m.clone(s.doc('numerical')['saved'])
    payload['method']='Inverse'
    s.documents[key] = m.make_document(key,'Identification','Numerical','N-FIT',8,payload)
    old_base = m.clone(s.doc('numerical'))
    s.mask(['A82'])
    s.save_document('data')
    s.refresh_data_source(key)
    assert s.doc('numerical') == old_base
    s.save_document(key)
    assert s.freeze(key)['included_count'] == 300
    payload = m.clone(s.doc(key)['draft'])
    payload['variables'][0]['lower']=999
    s.change(key,payload,'invalid bound')
    s.save_document(key)
    blocked(lambda:s.freeze(key))

def parameters():
    cases=[('cad','thickness',0),('material','mu',0),('pde','k',0),('simulation','duration',0),('simulation','increments',-1),('simulation','increments',1.5),('simulation','time_step',0),('thermal','temperature',0),('thermoelastic','Tref',0),('numerical','budget',0),('numerical','budget',1.5),('evaluation','tolerance',0)]
    for i,(key,field,value) in enumerate(cases):
        s = session('invalid-param-'+str(i))
        s.edit(key,field,value)
        assert s.diagnostics(key), (key,field,value)
        s.save_document(key)
        blocked(lambda:s.freeze(key))
    for limit in ('', 'abc', float('inf')):
        s=session('constraint-'+str(limit))
        payload=m.clone(s.doc('numerical')['draft'])
        payload['responses'][2]['limit']=limit
        s.change('numerical',payload,'invalid response')
        assert s.diagnostics('numerical')
        blocked(lambda:s.freeze('numerical'))
    return '12 zero/negative/noninteger parameter cases; empty/text/infinite constraint diagnostic gates'

def expert():
    s = session('expert')
    turn = s.append_reply('local user reply','지그 강성')
    actual = [t for t in s.doc('expert')['draft']['turns'] if t['actual']]
    assert actual == [turn] and turn['role']=='사용자'
    assert s.doc('expert')['draft']['provider']=='UNCONNECTED'
    snap = s.dump()
    assert snap['qualification']=='UNKNOWN' and snap['release']=='NOT_RELEASED'
    assert snap['F05']=={'value':3.32295e-6,'tolerance':1e-6,'verdict':'FAIL'}

for name, fn in [('adoption_nominal_cold_reopen',adoption), ('cancelled_apply_must_block',cancelled_continue), ('cancelled_publish_must_block',cancelled_publish), ('memory_stale_publish_must_block',stale_memory), ('disk_stale_publish_must_block',stale_disk), ('data_observation_identity_selection_undo',data), ('thermal_exact_reopen_routing',routes), ('material_dependency_repair',repair), ('invalid_save_freeze_boundary',invalid), ('runner_exact_input_cancel_late_reconnect',runner), ('unsupported_owner_no_structural_result',unsupported), ('dynamic_numerical_refresh_freeze_validation',dynamic), ('invalid_parameter_gates',parameters), ('provider_and_release_boundary',expert)]:
    check(name,fn)
ROOT.joinpath('state-results-latest.json').write_text(json.dumps({'run':str(RUN),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'qt':'NOT_RUN','results':results},indent=2))
print(json.dumps(results,indent=2))

raise SystemExit(0 if all(r['status']=='PASS' for r in results) else 1)
