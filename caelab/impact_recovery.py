"""Explicit impact output re-read on existing Simulation and JobManager owners.

The native attempt is immutable. A new READBACK_ONLY job may use the pinned
ANIM/TH converters only after an explicit convert_raw request. Starter and Engine
are never callable from this module. C2 generic file pins protect the transfer.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil

from .dynamic_result_store import file_pin,verify_pin
from .storage import check_id,save_json,canonical_hash,load_json
from .execution_control import check_cancelled,run_owned_command,ExecutionCancelled,ExecutionCleanupFailed
from .impact_retained import BACKEND,context,reference,artifact_receipt,catalog

OPERATION='impact.reprocess'
COMMAND='simulation.reprocess'


def _source(owner,document,source_job_id):
    source_job_id=check_id(source_job_id)
    run=next((r for r in document['runs'] if r['job_id']==source_job_id),None)
    if run is None or run['operation']!='simulation.run' or run['draft']['backend']!=BACKEND:
        raise ValueError('같은 Simulation의 원 충격 실행을 선택하세요. 파생 읽기를 원 실행으로 바꾸지 않습니다')
    retained=run.get('retained_result')
    if retained:
        revision=retained['revision'];owner._verify_revision(document['id'],revision)
        folder=owner._folder(document['id'])/'revisions'/revision
        job=load_json(folder/'jobs'/(source_job_id+'.json'))
        result_folder=folder/'results'/source_job_id
    else:
        job=owner.manager.status(source_job_id);result_folder=owner.manager.root/'results'/source_job_id
    if job['state'] not in {'SUCCEEDED','FAILED','CANCELLED','PARTIAL_FAILURE','INTERRUPTED'} or job.get('cleanup_unconfirmed'):
        raise ValueError('원 실행이 종료되지 않았거나 owned 프로세스 정리가 미확인입니다')
    if job['arguments']!=run['arguments'] or job['operation']!=run['operation']:
        raise ValueError('원 실행과 문서의 고정 입력이 다릅니다')
    from .evaluation import read_result
    result=read_result(result_folder,selection={'metadata_only':True})
    outcome=result['diagnostics']['native_outcome']
    root=result_folder/'calculation'
    _,record,settings,_,_,_=context(outcome,root)
    if record['diagnostics'].get('cleanup_unconfirmed'):raise ValueError('원 owned 프로세스 정리가 미확인입니다')
    if canonical_hash({'backend':BACKEND,'settings':settings})!=run['input_sha256']:
        raise ValueError('보존 결과가 같은 Simulation 원 입력에 속하지 않습니다')
    return root,record,run,job,outcome


def document_request(owner,document,arguments):
    if not isinstance(arguments,dict) or set(arguments)-{'source_job_id','convert_raw'} or 'source_job_id' not in arguments:
        raise ValueError('원 실행과 ANIM/TH 재변환 여부만 지정하세요')
    convert=arguments.get('convert_raw',False)
    if type(convert) is not bool:raise ValueError('원 ANIM/TH 재변환 여부를 명시하세요')
    _,_,run,_,outcome=_source(owner,document,arguments['source_job_id'])
    request={'document_id':document['id'],'source_job_id':run['job_id'],'source_record':outcome['impact_record'],
             'source_input_sha256':run['input_sha256'],'convert_raw':convert}
    return deepcopy(run['draft']),OPERATION,request


def source_input_context(document,arguments,snapshot):
    """Bind a read job to the original run, while the editable draft stays current."""
    run=next((r for r in document['runs'] if r['job_id']==arguments.get('source_job_id')),None)
    if (run is None or run.get('operation')!='simulation.run'
            or run.get('input_sha256')!=arguments.get('source_input_sha256')
            or canonical_hash(snapshot)!=run.get('input_sha256')
            or run.get('draft')!=snapshot):
        raise ValueError('원 읽기 입력과 고정된 실행 snapshot이 다릅니다')
    generation,revision=run.get('input_generation'),run.get('input_revision')
    if type(generation) is not int or generation<0 or not isinstance(revision,str) or not revision.startswith('I'):
        raise ValueError('원 실행의 input generation/revision이 없어 읽기 결과를 연결할 수 없습니다')
    check_id(revision)
    return {'input_generation':generation,'input_revision':revision}


def prepare(workbench,arguments):
    if not isinstance(arguments,dict) or set(arguments)!={'document_id','source_job_id','source_record','source_input_sha256','convert_raw'}:
        raise ValueError('Impact re-read requires the exact original document/job/input/record')
    identifier=check_id(arguments['document_id']);owner=workbench.simulation_documents
    document=owner.read(identifier)
    _,_,run,_,outcome=_source(owner,document,arguments['source_job_id'])
    if (arguments['source_record']!=outcome['impact_record'] or arguments['source_input_sha256']!=run['input_sha256']
            or type(arguments['convert_raw']) is not bool):
        raise ValueError('원 입력/실행 기록이 준비한 읽기 요청과 다릅니다')
    return deepcopy(arguments)


def execute(workbench,arguments,identifier):
    arguments=prepare(workbench,arguments);identifier=check_id(identifier)
    job=workbench.manager.status(identifier)
    if job['operation']!=OPERATION or job['arguments']!=arguments:raise ValueError('Owned 읽기 Job이 준비한 요청과 다릅니다')
    owner=workbench.simulation_documents;doc=owner.read(arguments['document_id'])
    source,original,run,original_job,outcome=_source(owner,doc,arguments['source_job_id'])
    _,_,s,model,physics,damage=context(outcome,source)
    output=workbench.root/'results'/identifier;target=output/'calculation';target.mkdir(parents=True)
    attempt={'execution_status':original['execution_status'],'readback_status':'FAILED','responses':{},'checks':[],
        'post_artifacts':[],'solver_execution':'NOT_PERFORMED','source_job_id':run['job_id'],
        'source_execution_status':original['execution_status'],'original_job_state':original_job['state'],
        'diagnostics':{'source_sha256':canonical_hash(s['source']),
            'native_execution_status':original['diagnostics'].get('native_execution_status','UNKNOWN'),
            'qualification':'UNKNOWN','decision':'NOT_RELEASED','readback_only':True,
            'original_execution_record':deepcopy(outcome['impact_record']),
            'source_input_sha256':run['input_sha256'],
            'runtime':deepcopy(original['diagnostics'].get('runtime'))}}
    frames=[]
    try:
        for pin in original['retained_native']['input_artifacts'].values():
            check_cancelled();src=verify_pin(source,pin);dst=target/pin['relative']
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst)
            verify_pin(source,pin);verify_pin(target,pin)
        # Input admission remains strict. An unavailable result artifact cannot
        # conceal unrelated healthy fields, but its pin failure is never blessed
        # as a new valid payload or omitted from the readback scope.
        copy_errors=[]
        for pin in original['retained_native']['native_artifacts'].values():
            check_cancelled();dst=None
            try:
                src=verify_pin(source,pin);dst=target/src.relative_to(source)
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,dst);verify_pin(source,pin);verify_pin(target,pin)
            except (ValueError,OSError) as error:
                if dst is not None and dst.is_file():dst.unlink()
                copy_errors.append({'artifact':deepcopy(pin),'reason':str(error)})
        if copy_errors:attempt['diagnostics']['artifact_copy_errors']=copy_errors
        # Pin and retain the source execution record as evidence, never overwrite it.
        src=verify_pin(source,outcome['impact_record']);shutil.copyfile(src,target/'original_execution.json')
        if file_pin(target,target/'original_execution.json')['sha256']!=outcome['impact_record']['sha256']:
            raise ValueError('복사된 원 실행 기록이 다릅니다')
        if s['source']['format']=='RAD':name=Path(s['source']['bundle']['starter']).name[:-9]
        else:name='impact'
        command=None;names=None;identity=None
        if arguments['convert_raw']:
            from .adapters.opencourant_runtime import runtime
            names,env,identity=runtime()
            if identity!=original['diagnostics'].get('runtime'):
                raise ValueError('원 실행과 동일한 pinned ANIM/TH converter identity가 필요합니다')
            allowed={str(names['anim_to_vtk']),str(names['th_to_csv'])}
            def command(argv,label):
                check_cancelled()
                if str(argv[0]) not in allowed:raise ValueError('읽기 작업은 Starter/Engine를 실행할 수 없습니다')
                process=run_owned_command([str(x) for x in argv],target/'native','readback_'+label,env=env,owned_tree=True)
                if process.returncode:raise ValueError('원 결과 변환 실패; readback 로그와 원 실행 상태를 별도 보존합니다')
                return process
        from .adapters.impact import read_outputs
        complete=read_outputs(target,s,model,physics,damage,attempt,frames,name=name,command=command,names=names,
                     convert=arguments['convert_raw'],partial=True,expected_frames=original['retained_native']['frames'])
        if identity is not None and runtime()[2]!=identity:raise ValueError('읽기 중 converter identity가 바뀌었습니다')
        attempt['readback_status']='SUCCEEDED' if complete else 'FAILED'
        if not complete:attempt['diagnostics']['readback_error']='일부 보존 결과만 읽었습니다. 누락·손상 구간은 readback_scopes에서 확인하세요. 원 해석 상태는 변경하지 않았습니다.'
    except ExecutionCleanupFailed:
        attempt['diagnostics']['cleanup_unconfirmed']=True
        save_json(target/'impact_execution.json',attempt)
        raise
    except ExecutionCancelled as error:
        attempt['readback_status']='CANCELLED';attempt['diagnostics']['readback_error']=str(error)
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as error:
        attempt['diagnostics']['readback_error']=str(error)
    finally:
        # No process is adopted or left running: run_owned_command owns/finalizes
        # every converter. Any unconfirmed cleanup propagates to JobManager.
        verify_pin(source,arguments['source_record'])
    attempt['retained_native']=artifact_receipt(target,frames)
    save_json(target/'impact_execution.json',attempt)
    result=deepcopy(attempt);result['execution_status']=attempt['readback_status']
    result.update(operation=OPERATION,operation_kind='READBACK_ONLY',settings=deepcopy(s),backend=BACKEND)
    result['diagnostics']['native_outcome']=reference(target)
    if frames:
        result['native_channels']=catalog(BACKEND,result['diagnostics']['native_outcome'],target)
        result['native_result']={'backend':BACKEND,'directory':'calculation'}
    from .research_execution import publish_fields
    try:publish_fields(workbench,result,output)
    except (ValueError,KeyError,TypeError,OSError) as error:
        result['post_registration']={'status':'FAILED','message':str(error)};result['execution_status']='FAILED'
    from .evaluation import save_evaluation
    save_evaluation(result,output,existing=True)
    return result
