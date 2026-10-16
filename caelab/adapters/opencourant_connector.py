"""Connector capability on the existing pinned OpenCourant/owned evaluation path."""
from pathlib import Path
from copy import deepcopy
import sys
import shutil

from .. import connector_model as domain
from ..connector_deck import starter,engine,layout
from ..connector_results import parse,catalog
from ..storage import save_json,canonical_hash
from ..dynamic_result_store import file_pin,verify_pin
from ..execution_control import (run_owned_command,check_cancelled,ExecutionCancelled,ExecutionCleanupFailed)
from .opencourant_runtime import runtime as selected_runtime
from .impact import starter_admission
from . import inp2rad_worker,impact_admission
from .impact_timing import engine_termination


class ConnectorAdapter:
    backend,version=domain.BACKEND,'1'
    default_settings=staticmethod(domain.default_settings)
    @staticmethod
    def validate_settings(settings):
        if isinstance(settings,dict) and set(settings)=={'data_id'}:
            from ..storage import check_id
            check_id(settings['data_id']);return deepcopy(settings)
        if not isinstance(settings,dict) or set(settings)!={'connector'}:
            raise ValueError('등록된 입력 또는 연결요소 초안을 선택하세요. 서버 파일 경로는 입력할 수 없습니다.')
        domain.validate_settings(settings)
        return deepcopy(settings)
    input_source_files=[__file__,domain.__file__,*[Path(domain.__file__).with_name(name) for name in
        ('connector_deck.py','connector_results.py','connector_fe.py','connector_snapshot.py','connector_admission.py')],
        Path(inp2rad_worker.__file__),Path(impact_admission.__file__)]
    input_runtime_identity=staticmethod(lambda:{'runtime':'explicit_selected_opencourant','qualification':'UNKNOWN'})
    def describe_model(self,settings):
        self.validate_settings(settings)
        if 'data_id' in settings:return {'backend':self.backend,'model':{'data_id':settings['data_id']}}
        return {'backend':self.backend,'model':domain.model_from_settings(settings)}
    def describe_ports(self,settings):
        self.validate_settings(settings)
        return {'inputs':{},'outputs':{},'coordinate_frame':'NATIVE_CONNECTOR_LOCAL','clock':'physical_seconds','qualification':'UNKNOWN'}
    def describe_inputs(self,settings):
        if 'data_id' in settings:raise ValueError('연결요소 계수를 원 FreeCAD 문서에서 편집하고 새 입력을 준비하세요.')
        m=domain.model_from_settings(settings);rows=[]
        for key in ('k','c'):
            for i,mode in enumerate(domain.MODES):
                unit=settings['connector']['units'][('translation_' if i<3 else 'rotation_')+key]
                rows.append({'id':key+'_'+mode,'label':mode+' '+key,'unit':unit,
                    'value':domain.number(settings['connector'][key][i],key), 'lower':0.,'upper':1e30,
                    'settings_path':['connector',key,i],'declaration_paths':[['model','draft',key,i]]})
        return rows
    def bind_inputs(self,settings,values):
        from ..model_parameters import expected_settings
        bound=expected_settings(settings,self.describe_inputs(settings),values)
        domain.validate_settings(bound);return bound
    def run(self,settings,*,output,runtime=None):
        from ..connector_snapshot import resolve,validate_snapshot
        original_settings=deepcopy(settings)
        settings=resolve(settings)
        m=domain.model_from_settings(settings);out=Path(output);out.mkdir(parents=True,exist_ok=True)
        native=out/'native';native.mkdir(exist_ok=False)
        if runtime and set(runtime)-{'threads','memory_mb'}: raise ValueError('연산 자원은 기존 실행 관리자의 선언을 사용합니다.')
        threads=(runtime or {}).get('threads',1)
        if type(threads) is not int or not 1<=threads<=64: raise ValueError('스레드 수는 1~64의 정수여야 합니다.')
        save_json(out/'input.json',settings)
        if 'data_id' in original_settings:
            manifest,_,_,files=validate_snapshot(original_settings['snapshot_path'])
            bundle=out/'source_bundle';bundle.mkdir()
            for p in files:shutil.copyfile(p,bundle/p.name)
            save_json(out/'frozen_input.json',{'data_id':original_settings['data_id'],'manifest':manifest})
        mapping={'nodes':layout(m)[0],'attachments':layout(m)[1],'th_group':1,'native_run_name':'connector',
                  'spring_element':1,'property':1,'axes':m['axes'],'model_sha256':canonical_hash(m)}
        if m['fe'] is None:
            (native/'connector_0000.rad').write_text(starter(m),encoding='ascii',newline='\n')
            (native/'connector_0001.rad').write_text(engine(m),encoding='ascii',newline='\n')
        result={'execution_status':'FAILED','responses':{},'checks':[],
                'diagnostics':{'qualification':'UNKNOWN','decision':'NOT_RELEASED','native_execution_status':'NOT_STARTED'}}
        receipt={'backend':self.backend,'execution_status':'FAILED','runtime':None,'artifacts':[],
                 'model_sha256':canonical_hash(m),'qualification':'UNKNOWN'}
        phase='runtime'
        try:
            names,env,identity=selected_runtime();env={**env,'OMP_NUM_THREADS':str(threads)};receipt['runtime']=identity
            def command(argv,label):
                check_cancelled()
                p=run_owned_command([str(v) for v in argv],native,label,env=env,owned_tree=True)
                if p.returncode: raise RuntimeError(label+' 실행이 실패했습니다. 원 로그와 입력은 보존됩니다.')
                return p
            if m['fe'] is not None:
                phase='conversion'
                from .. import impact_model
                from .impact import converted_mesh
                from .impact_admission import (global_gravity,normalize_contact_friction,normalize_surfaces,
                    normalize_elastic_tetra4,validate_physics)
                from ..connector_fe import append
                s=deepcopy(m['fe']['settings'])
                s['time'].update(m['time']);s['time']['field_interval_s']=m['time']['end_s']
                base=impact_model.model_from_settings(s);text,initial=impact_model.render(s)
                (native/'impact.inp').write_text(text,encoding='ascii',newline='\n')
                command([sys.executable,Path(inp2rad_worker.__file__),native/'impact.inp'],'convert')
                converted_mesh(native/'impact_0000.rad',base,initial['nodes'])
                original=(native/'impact_0000.rad').read_text(encoding='ascii')
                gravity,gravity_receipt=global_gravity(original,s['gravity_mm_s2'])
                effective=normalize_contact_friction(gravity,s)
                effective,surface_receipt=normalize_surfaces(effective,base)
                effective,formulation=normalize_elastic_tetra4(effective,base,initial,s)
                physics=validate_physics(effective,base,initial,s)
                save_json(out/'fe_physical_admission.json',{'physics':physics,'gravity':gravity_receipt,
                    'surfaces':surface_receipt,'formulation':formulation})
                # Attachment coordinates must be the frozen reference geometry;
                # initial placement transforms would require a matching frame.
                if initial['nodes']!=base['nodes']:
                    raise ValueError('FE 초기 위치 이동은 부착 기준과 다릅니다. 원 모델에서 위치를 적용한 뒤 다시 가져오세요.')
                (out/'base_effective_0000.rad').write_text(effective,encoding='ascii',newline='\n')
                effective,overlay=append(effective,m,base,initial=initial)
                (native/'impact_0000.rad').write_text(effective,encoding='ascii',newline='\n')
                (native/'impact_0001.rad').write_text(impact_model.engine_deck(s,model=base,physics=physics),encoding='ascii',newline='\n')
                mapping.update(overlay,native_run_name='impact')
                mapping['nodes']=[*base['nodes'].items(),*[(r['connector_reference'],m['endpoints'][i]['reference_mm']) for i,r in enumerate(overlay['attachments'])],
                                  *[(r['native_cog_main'],m['endpoints'][i]['reference_mm']) for i,r in enumerate(overlay['attachments'])]]
            from ..connector_admission import expected_bodies
            mapping['expected_native_bodies']=expected_bodies(m,mapping,base if m['fe'] is not None else None)
            save_json(out/'connector_mapping.json',mapping)
            name=mapping['native_run_name']
            receipt['effective_deck_pins']=[file_pin(out,native/(name+'_'+tail+'.rad')) for tail in ('0000','0001')]
            phase='starter'
            command([names['starter'],'-i',name+'_0000.rad','-np','1','-nt',threads],'starter')
            for pin in receipt['effective_deck_pins']:verify_pin(out,pin)
            # Reuse the existing exact no-warning/unit gate. No solid formulation
            # is invented; this deck contains only the declared native connector.
            expected_nodes=dict(mapping['nodes'])
            admission=starter_admission(native/(name+'_0000.out'),{'nodes':expected_nodes,'elements':{}})
            receipt['starter_admission']=admission;result['checks'].append(admission)
            from ..connector_admission import read_bodies
            receipt['native_attachments']=read_bodies(native/(name+'_0000.out'),mapping,fe=m['fe'] is not None)
            result['checks'].append({'name':'native_rigid_attachments',**receipt['native_attachments']})
            phase='engine';result['diagnostics']['native_execution_status']='STARTED'
            p=command([names['engine'],'-i',name+'_0001.rad','-nt',threads],'engine')
            for pin in receipt['effective_deck_pins']:verify_pin(out,pin)
            termination=engine_termination(native/(name+'_0001.out'),p.stdout,m['time']['end_s'])
            receipt['native_termination']=termination
            if termination['status']!='NORMAL': raise ValueError('원 native Engine이 정상 종료되지 않았습니다.')
            if selected_runtime()[2]!=identity: raise ValueError('실행 중 고정 runtime이 변경됐습니다.')
            result['diagnostics']['native_execution_status']='SUCCEEDED';phase='readback'
            h=parse(out,settings);save_json(out/'connector_history.json',h)
            receipt['execution_status']=result['execution_status']='SUCCEEDED'
        except ExecutionCleanupFailed: raise
        except ExecutionCancelled as exc:
            receipt['execution_status']=result['execution_status']='CANCELLED';receipt['reason']=str(exc)
            if result['diagnostics']['native_execution_status']=='STARTED':result['diagnostics']['native_execution_status']='CANCELLED'
        except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
            receipt['reason']=str(exc)
            if result['diagnostics']['native_execution_status']=='STARTED':result['diagnostics']['native_execution_status']='FAILED'
        name=mapping['native_run_name']
        if result['execution_status']!='SUCCEEDED' and receipt.get('starter_admission') and all((native/(name+s)).is_file() for s in ('T01','T01_TITLES')):
            if result['execution_status']=='CANCELLED':
                receipt['prefix_read']='DEFERRED_CANCELLED_PREFIX'
            else:
                try:
                    h=parse(out,settings,failed=True)
                    if h['time_s']:
                        save_json(out/'connector_history.json',h)
                        receipt['prefix_read']='VERIFIED_FAILED_PREFIX'
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    receipt['prefix_read_error']=str(exc)
        receipt['last_phase']=phase
        receipt['artifacts']=[file_pin(out,p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='connector_execution.json']
        save_json(out/'connector_execution.json',receipt)
        result['diagnostics'].update(native_outcome=deepcopy(receipt),last_phase=phase,
            reason=receipt.get('reason'),native_termination=receipt.get('native_termination'),
            scope=('selected elastic FE patches rigidly attached; remaining FE stiffness/mass preserved' if m['fe'] else
                   'explicit selected CAD/mesh rigid representation; deformable stiffness/mass not inferred'),
            limitations=['TH local generalized moments are not endpoint reaction moments',
                         'TH IE includes viscous work; engineering release remains UNKNOWN'])
        if receipt.get('prefix_read'):
            try:
                if receipt['prefix_read']=='DEFERRED_CANCELLED_PREFIX':
                    from ..connector_results import deferred_catalog
                    result['native_channels']=deferred_catalog(receipt,out,settings)
                else:
                    from ..connector_results import _descriptors
                    result['native_channels']=_descriptors(receipt,settings,h,file_pin(out,out/'connector_history.json'))
                result['native_result']={'backend':self.backend,'directory':'.'}
            except (OSError,ValueError,KeyError,TypeError) as exc:
                result['diagnostics']['prefix_catalog_error']=str(exc)
        if result['execution_status']=='SUCCEEDED':
            from ..connector_results import _descriptors
            result['native_channels']=_descriptors(receipt,settings,h,file_pin(out,out/'connector_history.json'))
            result['native_result']={'backend':self.backend,'directory':'.'}
            for token,values in h['values'].items():
                from ..connector_results import units
                meta={'kind':'series','unit':units(token),'component':token,
                      'location':settings['connector']['label']+' / 실제 대상 A–B','reduction':'none',
                      'axes':[{'name':'time','unit':'s','values':h['time_s']}],
                      'metadata':{'qualification':'UNKNOWN','source_rows':h['source_rows'],'valid_mask':h['mask'][token]}}
                if all(h['mask'][token]):meta['value']=values
                else:
                    # A masked native channel is selected through the existing
                    # native reader; do not create a value-less ordinary series
                    # with a full axis, or invent finite values for its gaps.
                    continue
                result['responses']['connector.'+token]=meta
        return result
