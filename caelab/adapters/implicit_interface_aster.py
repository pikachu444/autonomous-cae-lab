"""Pinned native joint writer/worker; consumes user meshes and authored curves.

Only solve imports Code_Aster. The existing owned SIF execution path is reused
by the adapter integration; no specimen generator or constitutive solver lives
here. One STATIC stage may contain opening/unloading/compression/reopening.
"""
from pathlib import Path
import hashlib
import json
import math
from copy import deepcopy
from importlib.util import find_spec

if __package__:
    from .contact_aster_worker import capture_import
    from .codeaster_worker import _runtime_versions, _save
else:
    from contact_aster_worker import capture_import
    from codeaster_worker import _runtime_versions, _save

BACKEND = 'structure.codeaster.implicit_interface'
SOURCE = '50ebc13c70ee9df62faf93ddcb746a3757b3042a'
VERSION = '17.4.0'


def command_text():
    return "import sys\nsys.path.insert(0, '/work')\nfrom implicit_interface_aster import solve\nsolve('/work/solver/input.json')\n"


def mesh_text(model):
    from ..implicit_interface import build_joints
    from .contact_aster_worker import mesh_text as bulk_mesh
    if model.get('contacts'):
        raise ValueError('같은 계면에 접촉을 중복 적용하지 마세요. 현재 연결은 joint 자체의 압축 지지를 사용합니다.')
    joints = build_joints(model,model['interfaces'])
    if len(model['elements'])+len(joints) > 500000:
        raise ValueError('계면을 포함한 요소 수가 기존 Aster 입력 한도를 넘습니다. 메시를 자동 축소하지 않습니다.')
    text,labels,catalog = bulk_mesh(model)
    if not text.endswith('FIN\n'):
        raise ValueError('원 고체 메시의 native 종료 구문이 다릅니다.')
    lines = [text[:-4], 'HEXA8']
    groups = {}
    for joint in joints:
        cell = 'J'+str(joint['element_id'])
        connectivity = [labels[n] for n in joint['node_ids']]
        lines += [cell+' '+' '.join(connectivity[:5]),' '.join(connectivity[5:])]
        catalog['cells'][cell] = dict(type='HEXA8',nodes=connectivity,
            element_id=joint['element_id'],interface_id=joint['interface_id'],joint=True)
        groups.setdefault(joint['interface_id'],[]).append(cell)
    lines.append('FINSF')
    catalog['groups']['INTERFACES'] = [cell for cells in groups.values() for cell in cells]
    catalog['interfaces'] = {}
    for i,(identifier,cells) in enumerate(groups.items(),1):
        group = 'I'+str(i)
        catalog['groups'][group] = cells
        records = [j for j in joints if j['interface_id'] == identifier]
        catalog['interfaces'][identifier] = dict(group=group,material=records[0]['material'],joints=records)
    for group in ('INTERFACES',*[r['group'] for r in catalog['interfaces'].values()]):
        lines += ['GROUP_MA',group,*catalog['groups'][group],'FINSF']
    lines += ['FIN','']
    return '\n'.join(lines),labels,catalog


def loading(model):
    from ..contact_steps import default_program,compile_program,validate_contributions
    if (model['step']['geometry'] != 'linear' or model['step']['matrix_solver'] != 'default'
            or any(model.get(key) for key in ('dynamic','restart','periodic_constraints','pretension_sections','initial_fields'))):
        raise ValueError('현재 계면 연결은 작은 변형 STATIC과 기본 Aster 해법을 지원합니다.')
    if any(m.get('law') != 'isotropic_linear_elastic' or m.get('plasticity') for m in model['materials']):
        raise ValueError('현재 계면 연결의 두 고체에는 등방 선형 탄성 재료를 사용하세요.')
    if any(model['step'].get(key) for key in ('controls','field_controls','line_search_controls')):
        raise ValueError('CalculiX 전용 수렴 제어를 Aster에서 같은 의미로 사용하지 않습니다.')
    validate_contributions(model)
    program = model.get('analysis_steps') or default_program(model['step'],model['conditions'])
    stages = compile_program(program,model['conditions'])
    if len(stages) != 1 or stages[0]['procedure'] != 'static':
        raise ValueError('현재 계면 연결은 하나의 STATIC 단계 안에서 작성한 하중 이력을 지원합니다. 다단계 상태 연속은 별도 연결입니다.')
    stage = stages[0]
    groups = {}
    for category in ('boundary','loads'):
        for (node,component),points in stage[category].items():
            key = category,tuple(tuple(p) for p in points)
            groups.setdefault(key,[]).append([node,component])
    excitations = [dict(category=category,points=[list(p) for p in points],dofs=dofs)
                   for (category,points),dofs in groups.items()]
    count = max(1,math.ceil(stage['duration']/min(stage['initial'],stage['maximum'])))
    values = {min(stage['initial']*i,stage['duration']) for i in range(count+1)}
    values.update(t for group in excitations for t,_ in group['points'])
    if len(values)-1 > stage['increments']:
        raise ValueError('작성한 이력의 절점과 증분을 포함하면 최대 증분 수를 넘습니다. 해석 단계를 수정하세요.')
    return dict(stage={k:stage[k] for k in ('id','label','duration','initial','minimum','maximum','increments','output_frequency')},
                excitations=excitations,requested_parameters=sorted(values),
                automatic=model['step']['automatic'])


def validate_model(model):
    from ..contact_deck import validate_model as common
    from ..implicit_interface import profile,build_joints
    from .contact_aster_model import mesh_quality
    profile(model)
    nodes,elements,bodies = common(model,_profile='aster_interface')
    build_joints(model,model['interfaces'])
    loading(model)
    return nodes,elements,bodies,mesh_quality(model)


def validate_snapshot(path):
    from .frozen_fem import _read
    from ..storage import check_id
    path = Path(path)
    if not path.is_absolute() or path.name != 'snapshot.json':
        raise ValueError('등록한 계면 입력을 선택하세요.')
    data = _read(path,8*1024**2)
    manifest = json.loads(data)
    if (manifest.get('kind') != 'freecad-contact-frozen' or manifest.get('schema_version') != '1'
            or manifest.get('backend') != BACKEND or manifest.get('input_file') != 'model.comm'):
        raise ValueError('완료된 비선형 정적 계면 입력이 아닙니다.')
    check_id(manifest['id'])
    expected = {'mesh.json','mesh.mail','model.comm','editable.FCStd'}
    if manifest.get('editable_project') == 'editable.caepre':
        expected.add('editable.caepre')
    elif manifest.get('editable_project') is not None:
        raise ValueError('편집 가능한 원 프로젝트 형식이 지원 범위와 다릅니다.')
    entries = manifest.get('files',[])
    if len(entries) != len(expected) or {r['relative'] for r in entries} != expected:
        raise ValueError('계면 입력 파일 목록이 불완전합니다.')
    pins = {'snapshot.json':dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())}
    for row in entries:
        raw = _read(path.parent/row['relative'])
        if (type(row['bytes']) is not int or row['bytes'] <= 0 or len(raw) != row['bytes']
                or hashlib.sha256(raw).hexdigest() != row['sha256']):
            raise ValueError('계면 입력이 보존본과 다릅니다: '+row['relative'])
        pins[row['relative']] = dict(bytes=row['bytes'],sha256=row['sha256'])
    model = json.loads(_read(path.parent/'mesh.json'))
    _,_,_,quality = validate_model(model)
    mail,_,_ = mesh_text(model)
    if (_read(path.parent/'mesh.mail') != mail.encode('ascii')
            or _read(path.parent/'model.comm') != command_text().encode('ascii')):
        raise ValueError('원 메시·계면 정의와 native 입력이 일치하지 않습니다.')
    if manifest['bodies'] != model['source_bodies']:
        raise ValueError('원 고체의 메시·형상 증명이 다릅니다.')
    return manifest,model,pins,quality


def solve(input_path):
    from code_aster.Commands import (DEBUT,FIN,LIRE_MAILLAGE,AFFE_MODELE,DEFI_MATERIAU,
        AFFE_MATERIAU,AFFE_CHAR_MECA,DEFI_FONCTION,DEFI_LIST_REEL,DEFI_LIST_INST,
        STAT_NON_LINE,CALC_CHAMP,CREA_TABLE,IMPR_RESU)
    from code_aster.Cata.Syntax import _F
    path = Path(input_path)
    root = path.parent
    config = json.loads(path.read_text(encoding='utf-8'))
    mesh_record = root/'mesh.json'
    if hashlib.sha256(mesh_record.read_bytes()).hexdigest() != config['mesh_record_sha256']:
        raise ValueError('Prepared interface model changed')
    source = json.loads(mesh_record.read_text(encoding='utf-8'))
    if hashlib.sha256(Path('fort.20').read_bytes()).hexdigest() != config['mail_sha256']:
        raise ValueError('Native linked interface mesh changed')
    DEBUT()
    versions,runtime = _runtime_versions()
    if versions.get('code_aster') != VERSION:
        raise ValueError('Configured Code_Aster17.4.0 required')
    mesh = LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)
    guard = capture_import(mesh,config['catalog'])
    guard['native_joint_cells'] = {
        i:dict(element_id=config['catalog']['cells'][cell]['element_id'],
               interface_id=config['catalog']['cells'][cell]['interface_id'])
        for i,cell in enumerate(guard['cell_names_in_native_order'],1)
        if config['catalog']['cells'][cell].get('joint')}
    _save(root/'native_mesh_checks.json',guard)
    model = AFFE_MODELE(MAILLAGE=mesh,AFFE=(
        _F(GROUP_MA='BODY',PHENOMENE='MECANIQUE',MODELISATION='3D'),
        _F(GROUP_MA='INTERFACES',PHENOMENE='MECANIQUE',MODELISATION='3D_JOINT')))
    materials = []
    for i,body in enumerate(sorted(source['body_maps']),1):
        row = next(m for m in source['materials'] if m['body_id'] == body)
        materials.append(_F(GROUP_MA='B'+str(i),MATER=DEFI_MATERIAU(
            ELAS=_F(E=row['young_modulus_MPa'],NU=row['poisson_ratio']))))
    for interface in config['catalog']['interfaces'].values():
        materials.append(_F(GROUP_MA=interface['group'],MATER=DEFI_MATERIAU(
            RUPT_FRAG=_F(**interface['material']))))
    assigned = AFFE_MATERIAU(MAILLAGE=mesh,AFFE=tuple(materials))
    excitations = []
    for group in config['loading']['excitations']:
        curve = DEFI_FONCTION(NOM_PARA='INST',ABSCISSE=[p[0] for p in group['points']],
            ORDONNEE=[p[1] for p in group['points']],INTERPOL='LIN',PROL_GAUCHE='EXCLU',PROL_DROITE='EXCLU')
        boundary = group['category'] == 'boundary'
        names = ('DX','DY','DZ') if boundary else ('FX','FY','FZ')
        rows = tuple(_F(NOEUD='N'+str(n),**{names[d-1]:1.}) for n,d in group['dofs'])
        charge = AFFE_CHAR_MECA(MODELE=model,**{'DDL_IMPO' if boundary else 'FORCE_NODALE':rows})
        excitations.append(_F(CHARGE=charge,FONC_MULT=curve))
    policy = config['loading']
    listing = DEFI_LIST_REEL(VALE=policy['requested_parameters'])
    increments = DEFI_LIST_INST(DEFI_LIST=_F(LIST_INST=listing),ECHEC=_F(
        EVENEMENT='ERREUR',ACTION='DECOUPE',SUBD_METHODE='MANUEL',SUBD_PAS=2,
        SUBD_PAS_MINI=policy['stage']['minimum'])) if policy['automatic'] else listing
    result = STAT_NON_LINE(MODELE=model,CHAM_MATER=assigned,EXCIT=tuple(excitations),
        COMPORTEMENT=(
            _F(GROUP_MA='BODY',RELATION='ELAS',DEFORMATION='PETIT'),
            _F(GROUP_MA='INTERFACES',RELATION='CZM_LIN_REG',DEFORMATION='PETIT',ALGO_INTE='ANALYTIQUE')),
        INCREMENT=_F(LIST_INST=increments),NEWTON=_F(MATRICE='TANGENTE',REAC_ITER=1),
        SOLVEUR=_F(METHODE='MUMPS'),ARCHIVAGE=_F(PAS_ARCH=policy['stage']['output_frequency']))
    result = CALC_CHAMP(reuse=result,RESULTAT=result,FORCE='REAC_NODA')
    orders = list(result.getIndexes())
    states = []
    for order in orders:
        tables = {}
        for field,components in (('DEPL',('DX','DY','DZ')),('REAC_NODA',('DX','DY','DZ')),
            ('SIEF_ELGA',('SIGN','SITX','SITY')),('VARI_ELGA',tuple('V'+str(i) for i in range(1,10)))):
            selection = dict(GROUP_MA='INTERFACES') if field in ('SIEF_ELGA','VARI_ELGA') else dict(TOUT='OUI')
            table = CREA_TABLE(RESU=_F(RESULTAT=result,NOM_CHAM=field,NUME_ORDRE=order,NOM_CMP=components,**selection))
            tables[field] = table.EXTR_TABLE().values()
            _save(root/('order_'+str(order)+'_'+field+'.json'),tables[field])
        states.append(dict(order=order,tables=tables))
    IMPR_RESU(FORMAT='MED',UNITE=80,RESU=_F(RESULTAT=result,
        NOM_CHAM=('DEPL','REAC_NODA','SIEF_ELGA','VARI_ELGA'),TOUT_ORDRE='OUI'))
    _save(root/'worker_result.json',dict(solver_status='COMPLETED',converged=True,
        versions=versions,code_aster_runtime=runtime,source_commit=SOURCE,
        native_mesh_checks=guard,available_orders=orders,access_parameters=result.getAccessParameters(),states=states,
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),mail_sha256=config['mail_sha256']))
    FIN()


class ImplicitInterfaceCodeAsterAdapter:
    """One evaluation on the existing configured runtime and JobManager path."""
    backend,version=BACKEND,'1'
    input_source_files = ([__file__,find_spec('caelab.implicit_interface').origin,find_spec('caelab.contact_steps').origin,
        *[find_spec(__package__+'.'+name).origin for name in
          ('contact_aster_worker','implicit_interface_results','codeaster_worker','codeaster_execution','codeaster_frozen')]]
        if __package__ else [])
    @staticmethod
    def default_settings():return {'data_id':None}
    @staticmethod
    def validate_settings(settings):
        from ..storage import check_id
        if not isinstance(settings,dict) or set(settings)!={'data_id'}:
            raise ValueError('등록된 Aster 계면 입력을 선택하세요. 서버 파일 경로는 입력할 수 없습니다.')
        check_id(settings['data_id']);return deepcopy(settings)
    def describe_model(self,settings):
        self.validate_settings(settings);return {'backend':BACKEND,'model':deepcopy(settings)}
    def describe_ports(self,settings):
        self.validate_settings(settings)
        return dict(inputs={},outputs={},coordinate_frame='FREECAD_DOCUMENT_GLOBAL',clock='STATIC_LOAD_PARAMETER',qualification='UNKNOWN')
    def run(self,settings,*,output,runtime=None):
        import json,os
        from . import implicit_interface_aster as worker
        from . import implicit_interface_results as reader
        from .codeaster_frozen import execute_native, _source_check
        from .codeaster_execution import process_budgets
        from .codeaster_contact import _IMAGE_SHA
        from .frozen_fem import _read,_sha
        from ..storage import check_id,save_json
        from ..execution_control import check_cancelled,ExecutionCancelled,ExecutionCleanupFailed
        if not isinstance(settings,dict) or set(settings)!={'data_id','snapshot_path'} or not isinstance(settings['snapshot_path'],str):
            raise ValueError('실행 단계에서 확인한 등록 계면 입력이 필요합니다.')
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
            from . import contact_aster_worker as contact_worker
            for p in (Path(worker.__file__),Path(common_worker.__file__),Path(contact_worker.__file__)):
                (out/p.name).write_bytes(_read(p));sources[p.name]=_sha(p)
            config=dict(catalog=catalog,node_labels=labels,mail_sha256=_sha(solver/'mesh.mail'),
                mesh_record_sha256=_sha(solver/'mesh.json'),worker_sources=sources,loading=worker.loading(model))
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
            parsed=reader.parse(raw,model,catalog);save_json(out/'interface_fields.json',parsed)
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
        result['limitations']=['두 HEXA8 고체·명시한 영두께 3D_JOINT·CZM_LIN_REG·작은 변형과 단일 STATIC 하중 이력입니다.',
            '원 내부변수의 상태·에너지 offset을 보존합니다. V3/V4를 연속 손상으로 바꾸지 않습니다.',
            '정적 하중 진행값은 물리 시간이 아닙니다. 압축 rc의 양수 admission은 전체 tangent의 양정치나 공학적 승인이 아닙니다.',
            '고정 SIF와 upstream binary 동등성·공학적 적합성은 UNKNOWN입니다.']
        result['artifacts']=[dict(relative=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=_sha(p))
            for p in sorted(out.rglob('*')) if p.is_file() and not p.is_symlink()]
        save_json(out/'interface_execution.json',result)
        if result['execution_status']=='SUCCEEDED':
            result['native_channels']=reader.catalog(result,out)
            save_json(out/'interface_execution.json',result)
        return result
