"""User-body hard-contact input; native syntax is owned by the 17.4 worker.

The existing separate-body contact validator owns mesh/set/load identity. This
profile changes the admitted native law and element family, never their values.
"""
from __future__ import annotations
import math
from copy import deepcopy
from pathlib import Path
from importlib.util import find_spec

BACKEND = 'structure.codeaster.contact'
SOURCE = '50ebc13c70ee9df62faf93ddcb746a3757b3042a'
VERSION = '17.4.0'
SLOTS = {'C3D10': (1,0,2,3,4,6,5,8,7,9), 'C3D8': (5,6,7,4,1,2,3,0)}
FACES = {
    'C3D10': {1:(0,2,1,6,5,4),2:(0,1,3,4,8,7),3:(1,2,3,5,9,8),4:(2,0,3,6,7,9)},
    'C3D8': {1:(0,3,2,1),2:(4,5,6,7),3:(0,1,5,4),4:(1,2,6,5),5:(2,3,7,6),6:(3,0,4,7)}}

def element_slots(row):
    return SLOTS[row['type']]

def face_slots(row):
    return FACES[row['type']]

def law_errors(draft):
    from ..contact import number, CONTACT_FIELDS
    errors=[]
    def fail(key,message):
        errors.append(dict(path=key,message=message,severity='error',blocks_evaluation=True))
    if not isinstance(draft,dict) or set(draft) != set(CONTACT_FIELDS):
        fail('normal_law','접촉 정의의 필드가 맞지 않습니다. 접촉 창에서 다시 적용하세요.');return errors
    required={'normal_law':'hard','gap_policy':'geometry','normal':'outward_solid',
              'sliding':'small','step':'Step1','activation':'whole_step'}
    for key,value in required.items():
        if draft.get(key)!=value:
            fail(key,{'normal_law':'Aster 비관통 접촉을 선택하세요.',
                'gap_policy':'원 형상의 실제 간극을 사용하세요.',
                'normal':'고체 바깥쪽 법선을 사용하세요.',
                'sliding':'이번 경로는 작은 미끄럼 접촉입니다. 큰 미끄럼은 별도 지원 범위입니다.',
                'step':'전체 정적 단계를 선택하세요.',
                'activation':'전체 단계에서 접촉을 유지하세요.'}[key])
    if draft.get('tangential_law') not in ('frictionless','coulomb'):
        fail('tangential_law','마찰 없음 또는 쿨롱 마찰을 선택하세요.')
    for key in ('normal_stiffness_MPa_per_mm','stick_stiffness_MPa_per_mm','nominal_gap_mm','tie_tolerance_mm'):
        if draft.get(key) not in ('',None):
            fail(key,'비관통 경로에서 사용하지 않는 값입니다. 값을 비운 뒤 다시 적용하세요.')
    try:
        if number(draft.get('adjustment_mm'))!=0:raise ValueError()
    except (ValueError,TypeError):fail('adjustment_mm','원 절점 위치를 유지하려면 조정값 0을 입력하세요.')
    if draft.get('tie_adjust') is not False:fail('tie_adjust','절점 자동 맞춤을 해제하세요.')
    try:
        if draft['tangential_law']=='coulomb':
            if number(draft['friction_coefficient'])<0:raise ValueError()
        elif draft.get('friction_coefficient') not in ('',None,0,0.):raise ValueError()
    except (ValueError,TypeError):fail('friction_coefficient','쿨롱 계수는 0 이상의 유한 수입니다. 마찰 없음에서는 값을 비우세요.')
    return errors

def profile(model):
    """Finite first support; no CCX controls are silently reinterpreted."""
    from ..contact import number
    if model.get('backend')!=BACKEND or model.get('analysis_scope') is not None:
        raise ValueError('두 독립 고체의 Aster 접촉 입력을 선택하세요.')
    if len(model['body_maps'])!=2:
        raise ValueError('이번 비관통 접촉 경로는 독립적인 두 고체를 지원합니다.')
    if len({p['draft']['tangential_law'] for p in model['contacts']})!=1:
        raise ValueError('하나의 접촉 해석에서 마찰 없음 또는 쿨롱 formulation을 일관되게 선택하세요.')
    if any(m.get('law')!='isotropic_linear_elastic' or m.get('plasticity') is not None for m in model['materials']):
        raise ValueError('이번 접촉 경로는 등방 선형 탄성 재료입니다. 소성 재료는 별도 입력 경로를 사용하세요.')
    if any(key in model for key in ('analysis_steps','dynamic','restart','pretension_sections','periodic_constraints')):
        raise ValueError('단계 전환·동해석·재시작·체결·주기 조건을 이 접촉 입력에서 생략할 수 없습니다.')
    step=model['step']
    if step['geometry']!='linear' or step['matrix_solver']!='default':
        raise ValueError('작은 변형과 기본 선형 해법을 선택하세요. Aster의 실제 MUMPS 해법은 입력에 보존됩니다.')
    if any(step.get(key) not in (None,[],{}) for key in ('controls','field_controls','line_search_controls')):
        raise ValueError('CalculiX 전용 수렴 제어는 Aster로 자동 변환하지 않습니다. 사용자 제어를 해제하세요.')
    if not math.isfinite(number(step['period'])):raise ValueError('유한 하중 구간을 지정하세요.')

def validate_model(model):
    from ..contact_deck import validate_model as common
    nodes,elements,bodies=common(model,_profile='aster_hard')
    quality=mesh_quality(model)
    slave=set()
    for pair in model['contacts']:
        current=surface_nodes(model,pair['a'])
        if slave & current:
            raise ValueError('A 면의 접촉 절점이 다른 접촉쌍과 겹칩니다. 접촉 영역을 분리하세요.')
        if current & {row['node_id'] for row in model['boundary_dofs']}:
            raise ValueError('현재 Code_Aster 연결은 A면의 변위 구속과 방향별 접촉 제외를 함께 지원하지 않습니다. 원 구속은 자동으로 제거하지 않습니다.')
        slave |= current
    return nodes,elements,bodies,quality

def surface_nodes(model,surface):
    elements={r['element_id']:r for r in model['elements']}
    return {elements[e]['node_ids'][i] for e,f in surface['element_faces'] for i in face_slots(elements[e])[f]}

def assemble(bodies, *, minimum_bodies=2):
    """Same body-local -> effective map as contact.separate_meshes; no welding."""
    from ..contact import number
    if len(bodies)!=2 or minimum_bodies!=2:raise ValueError('독립적인 두 body 메시를 선택하세요.')
    nodes,elements,maps=[],[],{}
    for body in bodies:
        name=body['body_id']
        if name in maps:raise ValueError('서로 다른 body를 선택하세요.')
        nm,em={},{}
        for row in body['nodes']:
            n=row['node_id']
            if type(n)is not int or n<=0 or n in nm:raise ValueError('원 절점 번호가 중복됐습니다.')
            nm[n]=len(nodes)+1
            nodes.append(dict(node_id=nm[n],body_id=name,native_node_id=n,position_mm=[number(v) for v in row['position_mm']]))
        for row in body['elements']:
            e=row['element_id'];ids=row['native_node_ids'];slots=element_slots(row)
            if type(e)is not int or e<=0 or e in em or len(ids)!=len(slots) or len(set(ids))!=len(ids):
                raise ValueError('TETRA10 또는 HEXA8 원 연결 번호를 확인하세요.')
            em[e]=len(elements)+1
            elements.append(dict(element_id=em[e],body_id=name,native_element_id=e,type=row['type'],
                native_node_ids=list(ids),node_ids=[nm[ids[i]] for i in slots]))
        maps[name]=dict(nodes=nm,elements=em)
    return dict(nodes=nodes,elements=elements,body_maps=maps,native_to_deck_slots={k:list(v) for k,v in SLOTS.items()},interface_policy='independent_body_dofs')

def surface_union(body_id,face_rows,mappings):
    result,rows=set(),[]
    for row in face_rows:
        local=[]
        for e,f in row['element_faces']:
            if e not in mappings[body_id]['elements'] or type(f)is not int or f not in range(1,7):
                raise ValueError('선택 면의 원 요소·면 번호를 확인하세요.')
            value=[mappings[body_id]['elements'][e],f];local.append(value);result.add(tuple(value))
        if not local:raise ValueError('선택한 CAD 면에 연결된 메시 면이 없습니다.')
        rows.append(dict(face=row['face'],element_faces=local))
    return dict(body_id=body_id,element_faces=[list(v) for v in sorted(result)],cad_faces=rows)

def mesh_quality(model):
    """Reuse existing TETRA10 gates; HEXA8 uses native 2x2x2 Jacobian samples."""
    from .frozen_fem import _jacobian_gates
    from apps.desktop_pre.fem_edit import _det, ABSOLUTE_JACOBIAN_FLOOR_MM3, NORMALIZED_JACOBIAN_FLOOR
    nodes={r['node_id']:r['position_mm'] for r in model['nodes']}
    tet={r['element_id']:r['node_ids'] for r in model['elements'] if r['type']=='C3D10'}
    result={'tetra10':_jacobian_gates(nodes,tet) if tet else None,'hexa8':[]}
    signs=((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
    for row in model['elements']:
        if row['type']!='C3D8':continue
        p=[nodes[n] for n in row['node_ids']]
        scale=max(max(v[a] for v in p)-min(v[a] for v in p) for a in range(3))
        if scale<=0:raise ValueError('퇴화한 HEXA8 요소를 다시 메시하세요.')
        p=[[(v[a]-p[0][a])/scale for a in range(3)] for v in p]
        determinants=[]
        for x,y,z in signs:
            x,y,z=(v/math.sqrt(3) for v in (x,y,z))
            d=[(sx*(1+sy*y)*(1+sz*z)/8,sy*(1+sx*x)*(1+sz*z)/8,sz*(1+sx*x)*(1+sy*y)/8) for sx,sy,sz in signs]
            determinants.append(_det([[math.fsum(v[a]*w[b] for v,w in zip(p,d)) for b in range(3)] for a in range(3)]))
        low=min(determinants);absolute=low*scale**3
        if low<=NORMALIZED_JACOBIAN_FLOOR or absolute<=ABSOLUTE_JACOBIAN_FLOOR_MM3 or not math.isfinite(absolute):
            raise ValueError('HEXA8 Jacobian 품질 기준을 만족하지 않습니다. 원 메시를 수정하세요.')
        result['hexa8'].append(dict(element_id=row['element_id'],minimum_sampled_jacobian_mm3=absolute,minimum_scaled_sampled_jacobian=low))
    return result

def validate_snapshot(path):
    import json, hashlib
    from .frozen_fem import _read
    path=Path(path)
    if not path.is_absolute() or path.name!='snapshot.json':raise ValueError('등록된 접촉 입력을 선택하세요.')
    data=_read(path,8*1024**2);manifest=json.loads(data)
    if manifest.get('kind')!='freecad-contact-frozen' or manifest.get('schema_version')!='1' or manifest.get('backend')!=BACKEND or manifest.get('input_file')!='model.comm':
        raise ValueError('완료된 Aster 접촉 입력이 아닙니다.')
    from ..storage import check_id
    check_id(manifest['id'])
    expected={'mesh.json','mesh.mail','model.comm','editable.FCStd'}
    if manifest.get('editable_project')=='editable.caepre':expected.add('editable.caepre')
    elif manifest.get('editable_project') is not None:
        raise ValueError('편집 가능한 원 프로젝트 형식이 지원 범위와 다릅니다.')
    entries=manifest.get('files',[])
    if len(entries)!=len(expected) or {r['relative'] for r in entries}!=expected:raise ValueError('접촉 입력 파일 목록이 불완전합니다.')
    pins={'snapshot.json':dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())}
    for row in entries:
        name=row['relative'];raw=_read(path.parent/name)
        if type(row['bytes'])is not int or row['bytes']<=0 or len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('접촉 입력이 보존본과 다릅니다: '+name)
        pins[name]=dict(bytes=row['bytes'],sha256=row['sha256'])
    model=json.loads(_read(path.parent/'mesh.json'));_,_,_,quality=validate_model(model)
    from .contact_aster_worker import mesh_text, command_text
    mail,_,_=mesh_text(model)
    if _read(path.parent/'mesh.mail')!=mail.encode('ascii') or _read(path.parent/'model.comm')!=command_text().encode('ascii'):
        raise ValueError('원 메시·접촉 정의와 native 입력이 일치하지 않습니다.')
    if manifest['bodies']!=model['source_bodies']:raise ValueError('원 body의 메시·형상 증명이 다릅니다.')
    return manifest,model,pins,quality


class ContactCodeAsterAdapter:
    """One evaluation on the existing configured runtime and JobManager path."""
    backend,version=BACKEND,'1'
    input_source_files=[__file__,*[find_spec(__package__+'.'+name).origin for name in
        ('contact_aster_worker','contact_aster_results','codeaster_worker','codeaster_execution','codeaster_frozen')]]
    @staticmethod
    def default_settings():return {'data_id':None}
    @staticmethod
    def validate_settings(settings):
        from ..storage import check_id
        if not isinstance(settings,dict) or set(settings)!={'data_id'}:
            raise ValueError('등록된 Aster 접촉 입력을 선택하세요. 서버 파일 경로는 입력할 수 없습니다.')
        check_id(settings['data_id']);return deepcopy(settings)
    def describe_model(self,settings):
        self.validate_settings(settings);return {'backend':BACKEND,'model':deepcopy(settings)}
    def describe_ports(self,settings):
        self.validate_settings(settings)
        return dict(inputs={},outputs={},coordinate_frame='FREECAD_DOCUMENT_GLOBAL',clock='STATIC_LOAD_PARAMETER',qualification='UNKNOWN')
    def run(self,settings,*,output,runtime=None):
        import json,os
        from . import contact_aster_worker as worker
        from . import contact_aster_results as reader
        from .codeaster_frozen import execute_native, _source_check
        from .codeaster_execution import process_budgets
        from .codeaster_contact import _IMAGE_SHA
        from .frozen_fem import _read,_sha
        from ..storage import check_id,save_json
        from ..execution_control import check_cancelled,ExecutionCancelled,ExecutionCleanupFailed
        if not isinstance(settings,dict) or set(settings)!={'data_id','snapshot_path'} or not isinstance(settings['snapshot_path'],str):
            raise ValueError('실행 단계에서 확인한 등록 접촉 입력이 필요합니다.')
        check_id(settings['data_id'])
        if runtime and (set(runtime)-{'threads','memory_mb'} or runtime.get('threads')!=2):
            raise ValueError('기존 Aster 실행 환경의 2 thread 예약을 사용하세요.')
        out=Path(output).absolute()
        if any(p.is_symlink() for p in (out,*out.parents)):raise ValueError('일반 결과 폴더를 선택하세요.')
        out.mkdir(parents=True,exist_ok=True)
        if any(out.iterdir()):raise ValueError('새 실행 폴더를 사용하세요. 기존 원 결과는 덮지 않습니다.')
        result=dict(execution_status='REJECTED',solver_status='NOT_RUN',responses={},checks=[],diagnostics={},
            qualification='UNKNOWN',decision='NOT_RELEASED',engineering_valid=False)
        phase='INPUT'
        try:
            source=Path(settings['snapshot_path']);manifest,model,pins,quality=validate_snapshot(source)
            retained=out/'frozen_input';retained.mkdir()
            for relative in pins:(retained/relative).write_bytes(_read(source.parent/relative))
            _source_check(source,retained,pins);validate_snapshot(retained/'snapshot.json')
            solver=out/'solver';solver.mkdir()
            mail,labels,catalog=worker.mesh_text(model)
            (solver/'mesh.mail').write_text(mail,encoding='ascii',newline='\n')
            save_json(solver/'mesh.json',model)
            sources={}
            from . import codeaster_worker as common_worker
            for p in (Path(worker.__file__),Path(common_worker.__file__)):
                (out/p.name).write_bytes(_read(p));sources[p.name]=_sha(p)
            config=dict(catalog=catalog,node_labels=labels,mail_sha256=_sha(solver/'mesh.mail'),
                mesh_record_sha256=_sha(solver/'mesh.json'),worker_sources=sources)
            save_json(solver/'input.json',config)
            (solver/'model.comm').write_text(worker.command_text(),encoding='ascii',newline='\n')
            budgets=process_budgets();save_json(out/'process_budgets.json',budgets)
            (solver/'model.export').write_text(
                f"P actions make_etude\nP memory_limit {budgets['solver_memory_mb']}\nP time_limit {budgets['solver_time_seconds']}\nP mpi_nbcpu 1\nP ncpus 1\n"
                'F comm /work/solver/model.comm D 1\nF mail /work/solver/mesh.mail D 20\n'
                'F rmed /work/solver/results.med R 80\nF mess /work/solver/aster.mess R 6\nF resu /work/solver/aster.resu R 8\n',encoding='ascii',newline='\n')
            prepared={p.relative_to(out).as_posix():_sha(p) for p in solver.iterdir() if p.is_file()}
            result.update(snapshot_id=manifest['id'],data_id=settings['data_id'],input_pins=pins,
                checks=[dict(name='frozen_body_mesh_identity',status='PASS',quality=quality)])
            phase='RUNTIME';check_cancelled()
            if os.environ.get('CAELAB_CODEASTER_IMAGE_SHA256')!=_IMAGE_SHA:
                raise RuntimeError('기존 검증 대상 Code_Aster 17.4 SIF와 Linux worker를 선택하세요. 입력은 보존됐으며 계산은 시작하지 않았습니다.')
            result['execution_status']='FAILED';result['runtime']=execute_native(out,budgets)
            phase='NATIVE_READ';check_cancelled();_source_check(source,retained,pins)
            for name,digest in {**prepared,**sources}.items():
                if _sha(out/name)!=digest:raise ValueError('실행 중 준비된 Aster 입력·worker가 바뀌었습니다.')
            raw=json.loads(_read(solver/'worker_result.json'))
            if (raw['input_sha256']!=_sha(solver/'input.json') or raw['mail_sha256']!=config['mail_sha256'] or
                json.loads(_read(solver/'native_mesh_checks.json'))!=raw['native_mesh_checks']):
                raise ValueError('실제 native 결과의 입력·메시 증명이 다릅니다.')
            if not (solver/'results.med').is_file() or not (solver/'results.med').stat().st_size:raise ValueError('실제 native MED 결과가 없습니다.')
            parsed=reader.parse(raw,model,catalog);save_json(out/'contact_fields.json',parsed)
            phase='POST';primary,secondary=reader.write_post(out,model,parsed)
            result.update(execution_status='SUCCEEDED',solver_status='COMPLETED',post_artifact=primary,
                additional_post_artifacts=secondary,native_result=dict(backend=BACKEND,directory='.'),
                native_version=raw['versions'],static=parsed['steps'][-1]['load_parameter'])
        except ExecutionCleanupFailed:raise
        except ExecutionCancelled as exc:result.update(execution_status='CANCELLED',diagnostics=dict(reason=str(exc),phase=phase))
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,OSError,RuntimeError,OverflowError) as exc:
            result['diagnostics']=dict(reason=str(exc),type=type(exc).__name__,phase=phase)
        execution=out/'solver/solver.execution.json'
        if execution.is_file():
            state=json.loads(_read(execution));result['native_execution']=state
            result['solver_status']='COMPLETED' if state['status']=='COMPLETED' else 'CANCELLED' if state['status']=='CANCELLED' else 'FAILED' if state.get('pid') else 'NOT_RUN'
        result['limitations']=['작은 변형·초기 형상 고정의 비관통 접촉. 큰 미끄럼·소성·동해석은 별도 지원 범위입니다.',
            '정적 하중 진행값은 물리 시간이 아닙니다. native 힘은 N, 압력 승수는 MPa입니다.',
            'SIF의 MPI 호환 패치와 upstream 원문의 binary 동등성·공학적 적합성은 UNKNOWN입니다.']
        result['artifacts']=[dict(relative=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=_sha(p))
            for p in sorted(out.rglob('*')) if p.is_file() and not p.is_symlink()]
        save_json(out/'contact_execution.json',result)
        if result['execution_status']=='SUCCEEDED':
            result['native_channels']=reader.catalog(result,out)
            save_json(out/'contact_execution.json',result)
        return result
