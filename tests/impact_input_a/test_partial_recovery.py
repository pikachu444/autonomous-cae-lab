"""Reader-only recovery. Boundary doubles are not native execution evidence."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from caelab.adapters import impact
from caelab.adapters.impact_results import history_prefix,GLOBAL_NAMES
from caelab.evaluation import run,file_hash
from caelab.impact_retained import artifact_receipt,reference,catalog,select_frame,context
from caelab.storage import save_json,canonical_hash
from caelab.workbench import Workbench
from support import install_boundary_double
from test_native import definition
from test_owner_and_results import change,wait


def _csv(rows):
    return ','.join(['time',*GLOBAL_NAMES])+',\n'+''.join(','.join(row)+',\n' for row in rows)


@pytest.mark.parametrize('bad',[
    ['0.002','1'],                         # incomplete final record
    ['nan',*(['1']*23)],                  # invalid clock
    ['0.0005',*(['1']*23)],               # duplicate clock
    ['0.002','inf',*(['1']*22)],          # invalid channel, not a missing sample
    ['0.002','wrong',*(['1']*22)],
])
def test_csv_prefix_stops_at_first_bad_record_and_never_skips(tmp_path,bad):
    path=tmp_path/'history.csv';valid=[['0',*(['1']*23)],['0.0005',*(['2']*23)]]
    path.write_text(_csv([*valid,bad,['0.003',*(['3']*23)]]),encoding='utf-8')
    responses,table=history_prefix(path)
    assert table['recovery']['status']=='PARTIAL'
    assert table['recovery']['first_unverified_record']['source_row']==4
    assert table['recovery']['after_first_invalid']=='UNVERIFIED_NOT_SKIPPED'
    assert responses['global_2']['axes'][0]['values']==[0.,.0005]
    assert responses['global_2']['value']==[.001,.002]
    assert responses['global_2']['metadata']['history_recovery']['native_history_correspondence'].startswith('UNKNOWN')


def test_no_prefix_or_wrong_layout_cannot_become_zero_history(tmp_path):
    path=tmp_path/'history.csv';path.write_text(_csv([['nan',*(['1']*23)]]))
    responses,table=history_prefix(path)
    assert responses=={} and table['recovery']['status']=='UNKNOWN'
    path.write_text('time,wrong\n0,0\n')
    with pytest.raises(ValueError,match='layout'):history_prefix(path)


def test_finite_but_unterminated_last_csv_record_is_not_blessed(tmp_path):
    path=tmp_path/'history.csv';path.write_text(_csv([['0',*(['1']*23)],['0.001',*(['2']*23)]]).rstrip('\n'))
    responses,table=history_prefix(path)
    assert responses['global_2']['value']==[.001]
    assert table['recovery']['first_unverified_record']['source_row']==3


def _reader_source(monkeypatch,template,mode,source_state):
    """Admit a distinct controlled source attempt; never edit an old receipt."""
    def source_run(self,settings,*,output,runtime=None):
        output=Path(output)
        shutil.copytree(template,output,dirs_exist_ok=True,
            ignore=lambda src,names:{'result.json','result.sha256.json','arrays'} if Path(src)==template else set())
        native=output/'native';record=json.loads((output/'impact_execution.json').read_text(encoding='utf-8'))
        if mode in ('missing','combined'):
            for name in ('impactT01','impactT01_TITLES'):(native/name).unlink()
        if mode in ('tail','combined'):
            path=native/'history.csv';lines=path.read_bytes().splitlines(keepends=True)
            path.write_bytes(b''.join(lines[:-1])+lines[-1][:15])
        if mode in ('frame','combined'):
            paths=sorted(native.glob('frame*.vtk'));paths[len(paths)//2].write_bytes(b'# broken converter payload\n')
        if mode=='stale_frame_pin':
            path=native/'frame0001.vtk';path.write_bytes(path.read_bytes().replace(b'-100',b'-200'))
        if mode=='no_history':
            for name in ('impactT01','impactT01_TITLES','history.csv'):(native/name).unlink()
        record['execution_status']=source_state
        record['diagnostics']['reason']='Controlled retained attempt, no solver execution in this check'
        record['retained_native']=artifact_receipt(output,record['retained_native']['frames'])
        if mode=='pin_damage':
            paths=sorted(native.glob('frame*.vtk'));paths[len(paths)//2].write_bytes(b'# changed after original pin\n')
        save_json(output/'impact_execution.json',record)
        result=deepcopy(record);result['diagnostics']['native_outcome']=reference(output)
        result['native_channels']=catalog(self.backend,result['diagnostics']['native_outcome'],output)
        result['native_result']={'backend':self.backend,'directory':'.'}
        # Original Post pins refer to the unmodified saved template. They are not
        # relabelled as recovered Post artifacts in this source failure fixture.
        result['post_artifacts']=[]
        return result
    monkeypatch.setattr(impact.ImpactAdapter,'run',source_run)


def _exercise_owner(tmp_path,monkeypatch,template,mode,source_state='FAILED'):
    _reader_source(monkeypatch,template,mode,source_state)
    def forbidden(*a,**kw):raise AssertionError('No solver, converter or runtime probe in reader-only recovery')
    monkeypatch.setattr(impact,'selected_runtime',forbidden)
    monkeypatch.setattr(impact,'run_owned_command',forbidden)
    monkeypatch.setattr('caelab.impact_recovery.run_owned_command',forbidden)
    settings=json.loads((template/'input.json').read_text(encoding='utf-8'))
    workspace=tmp_path/'workspace';wb=Workbench(workspace,configuration={'workers':1})
    try:
        doc=wb.document_open(kind='simulation',draft={'backend':impact.domain.BACKEND,'settings':settings})
        reply=change(wb,doc,'simulation.evaluate');doc=reply['document'];source=wait(wb,reply['job'])
        assert source['state']==source_state,source
        old=canonical_hash(wb.document_result(doc['id'],source['id'],selection={'metadata_only':True}))
        source_run=deepcopy(doc['runs'][0])
        reply=change(wb,doc,'simulation.reprocess',{'source_job_id':source['id']})
        doc=reply['document'];job=wait(wb,reply['job']);assert job['state']=='FAILED',job
        requested=['impact.velocity.Z@1']+(['global_2'] if mode!='no_history' else [])
        result=wb.document_result(doc['id'],job['id'],selection={'responses':requested})
        assert result['source_execution_status']==source_state and result['execution_status']=='FAILED'
        assert result['solver_execution']=='NOT_PERFORMED'
        scope=result['diagnostics']['readback_scopes']
        assert scope['history']['status'] in ('PARTIAL','UNKNOWN','COMPLETE')
        response=result['responses']['impact.velocity.Z@1']
        assert response['value'] and set(response['value'])=={-100.}
        assert result['post_input']['format']=='pvd'
        new_run=doc['runs'][-1]
        assert (new_run['input_sha256'],new_run['input_revision'],new_run['input_generation'])==(
            source_run['input_sha256'],source_run['input_revision'],source_run['input_generation'])
        if mode in ('frame','combined','pin_damage','stale_frame_pin'):
            missing=scope['animation']['unavailable_frames'];assert len(missing)==1
            assert response['has_calculation_gaps'] and len(response['segments'])==2
            assert response['metadata']['unavailable_frames']==missing
            root=wb.root/'results'/job['id']/'calculation';outcome=result['diagnostics']['native_outcome']
            with pytest.raises(ValueError,match='원 프레임'):
                select_frame(outcome,root,index=missing[0]['frame_index'],quantity='velocity',component='Z',identity=1)
            assert select_frame(outcome,root,index=scope['animation']['expected_slots']-1,
                quantity='velocity',component='Z',identity=1)['value']==-100.
            if mode=='pin_damage':
                assert result['diagnostics']['artifact_copy_errors']
                assert not (root/'native/frame0001.vtk').exists()
            if mode=='stale_frame_pin':
                assert 'hash/size' in missing[0]['reason']
                assert (root/'native/frame0001.vtk').is_file()  # native_artifacts pin passed; original frame pin did not.
        if mode in ('tail','combined'):
            assert scope['history']['first_unverified_record']
            assert scope['history']['after_first_invalid']=='UNVERIFIED_NOT_SKIPPED'
            assert result['responses']['global_2']['axes'][0]['values'][-1]<settings['time']['end_s']
        if mode=='no_history':
            assert scope['history']['status']=='UNKNOWN' and not any(n.startswith('global_') for n in result['responses'])
        assert canonical_hash(wb.document_result(doc['id'],source['id'],selection={'metadata_only':True}))==old
        doc=change(wb,doc,'document.save')['document'];docid=doc['id'];jobid=job['id'];count=len(wb.manager.list())
        expected=deepcopy(response)
    finally:assert wb.shutdown()['joined']
    fresh=Workbench(workspace,configuration={'workers':1})
    try:
        fresh.document_open(kind='simulation',document_id=docid)
        reopened=fresh.document_result(docid,jobid,selection={'responses':requested})
        assert reopened['responses']['impact.velocity.Z@1']==expected
        assert reopened['execution_status']=='FAILED' and reopened['source_execution_status']==source_state
        assert len(fresh.manager.list())==count
        return reopened
    finally:assert fresh.shutdown()['joined']


@pytest.mark.parametrize('mode,source_state',[('missing','FAILED'),('tail','CANCELLED'),('frame','FAILED'),('no_history','CANCELLED'),('pin_damage','FAILED'),('stale_frame_pin','FAILED')])
def test_partial_reprocess_retains_scopes_selection_save_cold(tmp_path,monkeypatch,mode,source_state):
    install_boundary_double(monkeypatch);template=tmp_path/'template'
    assert run(impact.domain.BACKEND,definition(),output=template)['execution_status']=='SUCCEEDED'
    _exercise_owner(tmp_path,monkeypatch,template,mode,source_state)


def test_only_explicit_reader_is_partial_and_converter_failures_are_isolated(tmp_path,monkeypatch):
    from subprocess import CompletedProcess
    from caelab.execution_control import ExecutionCancelled,ExecutionCleanupFailed
    install_boundary_double(monkeypatch);output=tmp_path/'attempt'
    result=run(impact.domain.BACKEND,definition(),output=output)
    _,record,settings,model,physics,damage=context(result['diagnostics']['native_outcome'],output)
    titles=output/'native/impactT01_TITLES';title_bytes=titles.read_bytes();titles.unlink()
    with pytest.raises(ValueError,match='history'):
        impact.read_outputs(output,settings,model,physics,damage,{'responses':{},'diagnostics':{}},[],name='impact')
    titles.write_bytes(title_bytes)
    calls=[]
    def convert(argv,label):
        calls.append(label)
        if label=='history_convert':
            assert argv[0]=='TH';raise RuntimeError('UNIT bad TH converter artifact')
        assert argv[0]=='ANIM'
        if label=='animation_0001':raise ValueError('UNIT bad ANIM converter artifact')
        return CompletedProcess(argv,0,stdout=(output/f'native/frame{int(label[-4:]):04d}.vtk').read_bytes())
    # Existing Post is irrelevant to this new explicit reader output.
    shutil.rmtree(output/'post')
    partial={'responses':{},'diagnostics':{}}
    assert not impact.read_outputs(output,settings,model,physics,damage,partial,[],name='impact',
        command=convert,names={'anim_to_vtk':'ANIM','th_to_csv':'TH'},convert=True,partial=True,
        expected_frames=record['retained_native']['frames'])
    assert calls==['history_convert','animation_0000','animation_0001','animation_0002']
    assert partial['diagnostics']['readback_scopes']['animation']['available_frame_count']==2
    assert partial['post_artifacts'] and partial['responses']['global_2']['value']
    for failure in (ExecutionCancelled,ExecutionCleanupFailed):
        def interrupted(*a,**kw):raise failure('UNIT converter cancellation/cleanup')
        with pytest.raises(failure):
            impact.read_outputs(output,settings,model,physics,damage,{'responses':{},'diagnostics':{}},[],name='impact',
                command=interrupted,names={'anim_to_vtk':'ANIM','th_to_csv':'TH'},convert=True,partial=True)


@pytest.mark.parametrize('gap',[0,1])
def test_sampled_impulse_never_restarts_after_an_unavailable_frame(tmp_path,monkeypatch,gap):
    from caelab.impact_retained import FrameView,read_frame_selection
    install_boundary_double(monkeypatch);output=tmp_path/'attempt'
    result=run(impact.domain.BACKEND,definition(),output=output)
    _,record,_,model,physics,damage=context(result['diagnostics']['native_outcome'],output)
    frames=deepcopy(record['retained_native']['frames']);frames[gap].update(available=False,reason='UNIT unavailable frame')
    monkeypatch.setattr('caelab.impact_responses._sample',lambda *a:(100.,''))
    rows=[{'name':'impulse','quantity':'contact_impulse','component':'Z','identity':1}]
    response=read_frame_selection(FrameView(output,frames,model,physics),model,rows,damage)[0]['impulse']
    assert response['value']==([0.] if gap==1 else [])
    assert response['has_calculation_gaps'] and response['raw_samples']['calculation_valid'][-1] is False


def test_healthy_bounded_slice_keeps_original_frame_source_rows(tmp_path,monkeypatch):
    from caelab.impact_retained import FrameView,read_frame_selection
    install_boundary_double(monkeypatch);output=tmp_path/'attempt'
    result=run(impact.domain.BACKEND,definition(),output=output)
    _,record,_,model,physics,damage=context(result['diagnostics']['native_outcome'],output)
    frames=deepcopy(record['retained_native']['frames']);frames[1].update(available=False,reason='UNIT gap')
    rows=[{'name':'velocity','quantity':'velocity','component':'Z','identity':1}]
    view=FrameView(output,frames,model,physics)
    full,_=read_frame_selection(view,model,rows,damage)
    sliced,selected=read_frame_selection(view,model,rows,damage,start=2,stop=3)
    assert full['velocity']['source_rows']==[0,2]
    response=sliced['velocity']
    assert response['source_rows']==response['raw_samples']['source_rows']==[2]
    assert response['segments']==[{'source_rows':[2],'rows':[0,1]}]
    assert selected['velocity']['source_frame_indices']==[2]
    assert response['value']==[-100.]


def test_missing_raw_anim_sequence_is_an_unavailable_original_slot_without_receipt(tmp_path,monkeypatch):
    from subprocess import CompletedProcess
    from support import vtk
    install_boundary_double(monkeypatch);output=tmp_path/'attempt'
    result=run(impact.domain.BACKEND,definition(),output=output)
    _,_,settings,model,physics,damage=context(result['diagnostics']['native_outcome'],output)
    shutil.rmtree(output/'post')
    for path in (output/'native').glob('frame*.vtk'):path.unlink()
    (output/'native/impactA002').unlink()
    settings['responses']=[{'name':'impulse','quantity':'contact_impulse','component':'Z','identity':1}]
    monkeypatch.setattr('caelab.impact_responses._sample',lambda *a:(100.,''))
    calls=[]
    def converter(argv,label):
        calls.append(label)
        if label=='history_convert':return CompletedProcess(argv,0,stdout=b'')
        index=int(Path(argv[1]).name[7:])-1
        return CompletedProcess(argv,0,stdout=vtk((0.,.0005,.001)[index]).encode('ascii'))
    partial={'responses':{},'diagnostics':{}};frames=[]
    assert not impact.read_outputs(output,settings,model,physics,damage,partial,frames,name='impact',
        command=converter,names={'anim_to_vtk':'ANIM','th_to_csv':'TH'},convert=True,partial=True)
    assert calls==['history_convert','animation_0000','animation_0002']
    scope=partial['diagnostics']['readback_scopes']['animation']
    assert scope['available_frame_indices']==[0,2] and scope['expected_slots']==3
    assert scope['unavailable_frames'][0]['frame_index']==1 and scope['unavailable_frames'][0]['time_s'] is None
    assert frames[2]['artifact']['relative']=='native/frame0002.vtk'
    assert partial['responses']['impulse']['value']==[0.]
    assert partial['responses']['impulse']['has_calculation_gaps']


ACTUAL=Path(__file__).resolve().parents[2]/'_workspace/a-native-04/workbench/results/J57bcfff277394fb2ac71c0a5b5f13dd2/calculation'


@pytest.mark.skipif(not ACTUAL.is_dir(),reason='Existing Windows native04 retained files are not installed; no solver is launched')
def test_existing_native04_copy_missing_th_cut_csv_and_damaged_frame_save_cold(tmp_path,monkeypatch):
    before={p.relative_to(ACTUAL).as_posix():file_hash(p) for p in ACTUAL.rglob('*') if p.is_file()}
    result=_exercise_owner(tmp_path,monkeypatch,ACTUAL,'combined')
    assert result['diagnostics']['frame_count']==12
    assert len(result['responses']['global_2']['value'])==119
    assert {p.relative_to(ACTUAL).as_posix():file_hash(p) for p in ACTUAL.rglob('*') if p.is_file()}==before
