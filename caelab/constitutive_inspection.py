"""Selected constitutive evidence through existing verified result/native readers."""
from copy import deepcopy
from .storage import canonical_hash, revision_read_scope
from .research_workflows import result_folder
from .evaluation import read_result


def native_steps(backend,raw):
    # Producer-owned schemas: SVK publishes the integrated history at root.
    return raw['steps'] if backend=='material.mfront.hyperelastic' else raw['mgis']['steps']



CARTESIAN9=[a+b for a in 'xyz' for b in 'xyz']
SYMMETRIC6=['xx','yy','zz','xy','xz','yz']
NATIVE_FRAME='Tridimensional model component basis; sensor/world alignment UNKNOWN'


def quantity(name,measure,values,components,unit,frame,*,origin='retained'):
    if values is None:return None
    if isinstance(values,list) and values and isinstance(values[0],list):
        if len(values)!=3 or any(len(row)!=3 for row in values):
            raise ValueError('보존된 텐서의 크기가 3×3과 다릅니다.')
        values=[v for row in values for v in row];components=CARTESIAN9
    if not isinstance(values,list) or len(values)!=len(components):
        raise ValueError('보존된 물리량과 성분 순서가 다릅니다.')
    return {'name':name,'measure':measure,'values':deepcopy(values),'components':list(components),
            'unit':unit,'frame':frame,'origin':origin}


def physical_quantities(backend,settings,result,step,frame):
    """Exact saved values only; no symmetry completion, Kelvin conversion or new evaluation."""
    rows=[]
    def add(*args,**kwargs):
        row=quantity(*args,**kwargs)
        if row is not None:rows.append(row)
    if backend=='material.felupe':
        index=step['index'];snapshots=result.get('diagnostics',{}).get('constitutive_increments',[])
        saved=next((r for r in snapshots if r['increment']==index),None)
        measure='infinitesimal_Cauchy' if settings['model']=='linear_elastic' else 'first_Piola'
        add('변형구배 F','deformation_gradient',settings['deformation_gradient'][index],CARTESIAN9,'1',frame,origin='frozen_input')
        if saved:
            if (saved['deformation_gradient']!=settings['deformation_gradient'][index] or
                saved['stress_measure']!=measure or saved['stress_unit']!=settings['stress_unit'] or saved['frame']!=frame):
                raise ValueError('응력 snapshot과 보존 입력의 물리 선언이 다릅니다.')
            values=saved['stress']
        else:
            values=[result['responses'].get('stress_'+name,{}).get('value',[None]*len(settings['time']))[index]
                    for name in CARTESIAN9]
        add('응력',measure,values,CARTESIAN9,settings['stress_unit'],frame)
    elif backend=='material.mfront.hyperelastic':
        from .adapters.mfront_hyperelastic_worker import F_COMPONENTS
        add('변형구배 F','deformation_gradient',step.get('deformation_gradient'),F_COMPONENTS,'1',frame)
        add('제1 Piola 응력','first_Piola',step.get('pk1_stress_mpa'),F_COMPONENTS,'MPa',frame)
        add('Cauchy 응력','Cauchy = PK1 Fᵀ/det(F)',step.get('cauchy_stress_mpa'),SYMMETRIC6,'MPa',frame,origin='retained_derived')
    elif backend=='material.mfront.user':
        add('변형률','Kelvin strain (sqrt(2) shear)',step.get('strain_kelvin'),SYMMETRIC6,'1',frame)
        add('응력','Kelvin Cauchy stress (sqrt(2) shear)',step.get('stress_kelvin'),SYMMETRIC6,'Pa',frame)
    else:
        add('변형률','physical tensor strain (not engineering shear)',step.get('strain_physical'),SYMMETRIC6,'1',frame)
        add('응력','physical infinitesimal Cauchy stress',step.get('stress_physical_mpa'),SYMMETRIC6,'MPa',frame)
        add('변형률','Kelvin strain (sqrt(2) shear)',step.get('gradients_kelvin'),SYMMETRIC6,'1',frame)
        add('응력','Kelvin Cauchy stress (sqrt(2) shear)',step.get('stress_kelvin_mpa'),SYMMETRIC6,'MPa',frame)
    return rows


@revision_read_scope()
def inspect_constitutive(wb,document_id,job_id,increment=0):
    if wb._document_owner(document_id) is not wb.material_documents:
        raise ValueError('재료 문서의 계산 결과를 선택하세요.')
    folder,run=result_folder(wb,document_id,job_id)
    if canonical_hash(run['draft'])!=run['input_sha256']: raise ValueError('보존 입력이 일치하지 않습니다.')
    result=read_result(folder,verify='all')
    backend=run['draft'].get('backend')
    view={'document_id':document_id,'job_id':job_id,'backend':backend,
          'source':wb.document_result_reference(document_id,job_id) if run.get('retention_complete') and run.get('retained_result') else None,
          'retained':bool(run.get('retention_complete')),'draft':deepcopy(run['draft']),
          'execution_status':result['execution_status'],'residual':None,'substeps':None,
          'state_initial':None,'state_trial':None,'state_committed':None,'finite_differences':[],'quantities':[],
          'unavailable':[]}
    if type(increment) is not int or increment<0: raise ValueError('증분을 선택하세요.')
    if backend=='material.felupe':
        settings=run['draft']['settings'];times=settings['time']
        if increment>=len(times): raise ValueError('보존 이력에 없는 증분입니다.')
        tangent=result.get('responses',{}).get('tangent',{}).get('value')
        if tangent is None: raise ValueError('이 실행에 접선 결과가 없습니다.')
        import numpy as np
        matrix=np.asarray(tangent,dtype=float)[increment].reshape(9,9).tolist()
        names=[a+b for a in 'xyz' for b in 'xyz']
        stress={name:row['value'][increment] for name,row in result['responses'].items() if name.startswith('stress_')}
        view.update(increments=[{'index':i,'time':t,'unit':settings['time_unit']} for i,t in enumerate(times)],
                    increment=increment,time=times[increment],time_unit=settings['time_unit'],
                    stress=stress,strain=deepcopy(settings['deformation_gradient'][increment]),
                    tangent=matrix,components=names,tangent_unit=settings['stress_unit'],
                    pair='dσᵢⱼ/dFₖₗ (미소변형 Cauchy)' if settings['model']=='linear_elastic' else 'dPᵢⱼ/dFₖₗ (제1 Piola)',
                    frame='material_cartesian',state_initial={'declaration':'ZERO_ELASTIC_STATE'},
                    finite_differences=deepcopy(result.get('diagnostics',{}).get('tangent_probes',[])))
        view['quantities']=physical_quantities(backend,settings,result,{'index':increment},view['frame'])
        if any(v is None for q in view['quantities'] for v in q['values']):
            view['unavailable'].append('과거 실행에 없는 응력 성분은 미보존으로 표시합니다.')
        view['unavailable']+=['내부 상태 없음: 탄성 법칙','trial/committed 상태·반복 잔차·substep은 FELUPE 출력에 없음']
    elif backend in ('material.mfront','material.mfront.hyperelastic','material.mfront.viscoelastic'):
        from .adapters import retained_law_responses as reader
        from .workbench import contained
        native=result.get('native_result',{})
        location=contained(folder,native.get('directory','calculation/simulation'))
        outcome=result.get('diagnostics',{}).get('native_outcome',{})
        catalog=reader.catalog(backend,outcome,location)
        if not catalog:
            raise ValueError('완료된 증분 없음. 실패한 native 원기록은 실행 작업에서 확인하세요.')
        frames={row['coordinate_frame'] for row in catalog.values()}
        if len(frames)!=1:raise ValueError('선택 native 자료의 성분 기준계가 서로 다릅니다.')
        frame=next(iter(frames))
        raw=reader._load(location,'native_raw.json');steps=native_steps(backend,raw)
        if increment>=len(steps): raise ValueError('보존 이력에 없는 증분입니다.')
        step=deepcopy(steps[increment])
        is_finite=backend=='material.mfront.hyperelastic'
        tangent_key='pk1_tangent_mpa' if is_finite else 'tangent_kelvin_mpa'
        tangent=step.get(tangent_key)
        if tangent is None:
            # Different producer spelling is never guessed into a physical pair.
            view['unavailable'].append('이 생산자의 접선 성분은 지원 reader에 선언되지 않음')
        components=['xx','yy','zz','xy','xz','yz']
        if is_finite:
            from .adapters.mfront_hyperelastic_worker import F_COMPONENTS
            components=list(F_COMPONENTS)
        view.update(increments=[{'index':i,'time':r['time_s'],'unit':'s'} for i,r in enumerate(steps)],
                    increment=increment,time=step['time_s'],time_unit='s',
                    stress={k:v for k,v in step.items() if k in ('stress_physical_mpa','pk1_stress_mpa','cauchy_stress_mpa')},
                    strain=step.get('strain_physical',step.get('deformation_gradient')),
                    tangent=tangent,components=components,tangent_unit='MPa',
                    pair='dPK1/dF native 9×9' if is_finite else 'dσKelvin/dεKelvin, xx yy zz √2xy √2xz √2yz',
                    frame=frame,state_initial=step.get('initial_state',step.get('initial_manager')),
                    state_trial=step.get('nominal_before_probes'),state_committed=step.get('nominal_after_update'),
                    finite_differences=step.get('finite_differences',[]),integration_return=step.get('integration_return'))
        view['quantities']=physical_quantities(backend,run['draft']['settings'],result,step,frame)
        mtest=raw.get('mtest',{}).get('states',raw.get('mtest',{}).get('steps',[]))
        actual=next((r for r in mtest if r.get('time_s')==step['time_s']),None)
        if actual: view['substeps']={k:v for k,v in actual.items() if k in ('iterations','subSteps','substeps','iterations_increment')}
        view['unavailable'].append('구성 적분 잔차는 native 기록에 없음')
    elif backend=='material.mfront.user':
        history=result.get('diagnostics',{}).get('constitutive',{})
        steps=history.get('steps',[])
        view['build']=deepcopy(result.get('diagnostics',{}).get('build'))
        if not steps and view['build']:
            view.update(increments=[],increment=None,tangent=None,components=[],stress={},
                pair='generic MGIS / 보존 빌드 선언',tangent_unit='Pa',frame=NATIVE_FRAME,
                unavailable=[result.get('diagnostics',{}).get('reason') or '빌드 완료 · 적분 미실행'])
            return view
        if increment>=len(steps): raise ValueError('보존된 사용자 법칙 증분이 없습니다.')
        step=deepcopy(steps[increment])
        view.update(increments=[{'index':i,'time':r['time_s'],'unit':'s'} for i,r in enumerate(steps)],
                    increment=increment,time=step['time_s'],time_unit='s',stress=step.get('stress_kelvin'),
                    strain=step.get('strain_kelvin'),tangent=step.get('tangent'),components=['xx','yy','zz','xy','xz','yz'],
                    tangent_unit='Pa',pair='dσKelvin/dεKelvin',frame=NATIVE_FRAME,
                    state_initial=step.get('initial_state'),state_trial=step.get('trial_state'),
                    state_committed=step.get('committed_state'),finite_differences=step.get('finite_differences',[]))
        view['quantities']=physical_quantities(backend,run['draft']['settings'],result,step,NATIVE_FRAME)
        view['unavailable']=['MGIS 잔차/substep 미보고','응력과 변형률 전단은 Kelvin 성분']
    else: raise ValueError('이 구성식의 증분 reader는 아직 등록되지 않았습니다.')
    return view
