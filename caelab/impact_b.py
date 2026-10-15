"""B domain facade for the existing Impact adapter and Sol's native Qt editor."""
from copy import deepcopy
from . import impact_bulk, impact_bulk_deck, impact_interface, impact_bulk_results
from .storage import canonical_hash

KEYS={'bulk_damage','interface_controls','b_responses'}


def enabled(settings):
    return any(settings.get(k) for k in KEYS)


def validate(model,settings):
    impact_bulk.validate(model,settings.get('bulk_damage',[]))
    impact_interface.validate(model,settings)
    impact_bulk_results.validate(model,settings)
    if settings.get('b_readback') is not None:
        raise ValueError('원출력은 같은 Simulation의 보존 결과 다시 읽기 명령을 사용하세요. '
                         '계산 초안에 이전 b_readback 참조를 넣어 실행하지 않습니다.')


def model_identity(model):
    return canonical_hash({'nodes':sorted(model['nodes'].items()),
                           'elements':sorted(model['elements'].items()),
                           'assignment':sorted(model['assignment'].items())})


def compile(text,model,settings,cohesive):
    validate(model,settings)
    text,bulk=impact_bulk_deck.apply(text,model,settings.get('bulk_damage',[]))
    text,interface=impact_interface.apply(text,model,settings,cohesive)
    text,outputs=impact_bulk_deck.add_output_cards(text,bulk,settings,model)
    definition={'version':1,'model_identity':model_identity(model),'bulk':bulk,'cohesive':deepcopy(cohesive),
                'interface':interface,'outputs':outputs,'native_acceptance':'NOT_RUN'}
    verify(text,model,settings,definition)
    return text,definition


def verify(text,model,settings,definition):
    if model_identity(model)!=definition['model_identity']:
        raise ValueError('B native definition belongs to a different effective model')
    impact_bulk_deck.verify(text,model,settings.get('bulk_damage',[]),definition['bulk'])
    blocks=impact_bulk_deck.cards(text)
    for key,expected in {**definition['interface']['cards'],**definition['outputs']['generated_cards']}.items():
        if blocks.get(key)!=expected:
            raise ValueError('B interface/output card changed: '+key)
    for group in definition['outputs']['groups']:
        if group['kind']!='pair':continue
        index=group['contact_index'];members=group['members']
        if type(index) is not int or not 0<=index<len(settings['contacts']) or group['pair']!=settings['contacts'][index] or len(members)!=1:
            raise ValueError('B contact pair receipt differs from the original selected pair')
        contact=blocks.get('/INTER/TYPE24/'+str(members[0]))
        if not contact or contact[0].strip().upper()!='IMPACT'+str(index+1):
            raise ValueError('B contact pair member differs from the exact TYPE24 card')
    from .impact_damage import law_card
    for item in definition['cohesive']['elements'].values():
        mid=item['material_id'];name=item['material']
        law=next(v for v in settings['cohesive'] if v['material']==name)
        expected=impact_bulk_deck.cards(law_card(mid,name,model['materials'][name],law))
        if blocks.get('/MAT/LAW117/'+str(mid))!=expected['/MAT/LAW117/'+str(mid)]:
            raise ValueError('The retained LAW117 envelope was changed by a bulk/contact extension')


def readback(folder,model,settings,definition,frames,*,failed=False,runtime_identity=None):
    from pathlib import Path
    from .impact_bulk_history import read
    folder=Path(folder); path=folder/'native/impactT01';titles=folder/'native/impactT01_TITLES'
    history=read(path,titles=titles,failed=failed) if path.is_file() and titles.is_file() else None
    selected,record=impact_bulk_results.read_selected(history,frames,model,settings,definition,runtime_identity=runtime_identity)
    return selected,record,history


def append_readback(folder,model,settings,result,frames,*,partial=False):
    """Add B observations to the existing attempt/read job, without a second owner.

    An explicit partial read isolates TH and animation selections. The original
    execution verdict is evidence, never upgraded by a readable output prefix.
    """
    if not enabled(settings):return
    import json
    from pathlib import Path
    from collections.abc import Sequence
    from .dynamic_result_store import file_pin,verify_pin,admit_pin
    from .impact_native_io import read_bytes
    from .impact_bulk_history import read
    from .execution_control import ExecutionCancelled,ExecutionCleanupFailed
    from .storage import save_json
    root=Path(folder);diagnostics=result['diagnostics']
    scopes=diagnostics.setdefault('readback_scopes',{}) if partial else {}
    record={'selections':{},'events':{},'scopes':{},'qualification':'UNKNOWN',
            'bulk_damage_dissipation':'UNKNOWN_NOT_SYNTHESIZED',
            'native_initiation_evolution_states':'NOT_MAPPED_TO_A_VERIFIED_OUTPUT_CHANNEL',
            'source_execution_status':result.get('source_execution_status',result.get('execution_status','UNKNOWN')),
            'reader_operation':'READBACK_ONLY' if partial else 'ORIGINAL_OUTPUT_READ'}
    errors=(ValueError,KeyError,TypeError,OSError,RuntimeError,StopIteration,UnicodeError)
    def scope(name,status,**detail):
        item={'status':status,**detail};record['scopes'][name]=item
        if partial:scopes['b_'+name]=deepcopy(item)
    def reject(error):
        if isinstance(error,(ExecutionCancelled,ExecutionCleanupFailed)):raise error
        if not partial:raise error
    def pinned_json(pin):
        return json.loads(read_bytes(admit_pin(root,pin),expected=pin,maximum=64*1024*1024))
    retained=None;definition=None
    try:
        if partial:
            # Only the original receipt admits optional input. A loose file in
            # the result directory cannot become a new B definition after a run.
            original_pin=deepcopy(diagnostics['original_execution_record'])
            original_pin['relative']='original_execution.json'
            original=pinned_json(original_pin)
            retained=original['retained_native']
            pin=retained['input_artifacts'].get('b_definition.json')
        else:
            pin=file_pin(root,root/'b_definition.json') if (root/'b_definition.json').is_file() else None
        if pin is not None:
            if pin['relative']!='b_definition.json':raise ValueError('B definition artifact differs from its receipt')
            definition=pinned_json(pin)
            starter=root/'native/impact_0000.rad'
            starter_pin=(retained['native_artifacts']['native/impact_0000.rad'] if retained is not None
                         else file_pin(root,starter))
            text=read_bytes(admit_pin(root,starter_pin),expected=starter_pin,maximum=64*1024*1024).decode('ascii')
            verify(text,model,settings,definition)
            record['definition_pin']=deepcopy(pin)
    except errors as error:
        reject(error);scope('definition','UNKNOWN',reason=str(error));definition=None
    if definition is None:
        if 'definition' not in record['scopes']:
            scope('definition','UNKNOWN',reason='원 실행에 보존된 B 정의가 없습니다. B 수치를 생성하지 않았습니다.')
        record['requested_selections']=deepcopy(settings.get('b_responses',[]))
        diagnostics['b_observations']=record;save_json(root/'b_selected_responses.json',record)
        return
    validate(model,settings)

    class AvailableFrames(Sequence):
        def __init__(self):
            self.indices=[i for i,m in enumerate(frames.frames) if m.get('available',True)] if hasattr(frames,'frames') else list(range(len(frames)))
        def __len__(self):return len(self.indices)
        def __getitem__(self,index):
            if type(index) is not int or not 0<=index<len(self):raise IndexError(index)
            ordinal=self.indices[index];path,raw=frames[ordinal]
            return path,{**raw,'source_ordinal':ordinal}
    available=AvailableFrames()
    excluded=[{'frame_index':i,'time_s':m.get('time_s'),'reason':m.get('reason')}
              for i,m in enumerate(frames.frames) if not m.get('available',True)] if hasattr(frames,'frames') else []
    history=None;history_error=None
    needs_history=any(r['scope'] in ('bulk','pair') for r in settings.get('b_responses',[]))
    if needs_history:
        try:
            path=root/'native/impactT01';titles=root/'native/impactT01_TITLES'
            for relative in ('native/impactT01','native/impactT01_TITLES'):
                if retained is not None:verify_pin(root,retained['native_artifacts'][relative])
            history=read(path,titles=titles,failed=partial)
            for relative in ('native/impactT01','native/impactT01_TITLES'):
                if retained is not None:verify_pin(root,retained['native_artifacts'][relative])
            save_json(root/'b_native_history.json',history)
        except errors as error:
            reject(error);history_error=str(error)
    for kind in ('bulk','pair','interface'):
        rows=[r for r in settings.get('b_responses',[]) if r['scope']==kind]
        if not rows:continue
        try:
            if kind!='interface' and history_error:raise ValueError(history_error)
            chosen,observations=impact_bulk_results.read_selected(history if kind!='interface' else None,
                available,model,{**settings,'b_responses':rows},definition,excluded_frames=excluded,
                runtime_identity=diagnostics.get('runtime'))
            # A correctly read inactive element remains masked; deletion is not
            # a reader failure. Missing samples/channels and unproven pair force
            # semantics remain separate from that physical activation state.
            observed=any(item['times_s'] for item in observations['selections'].values())
            incomplete=bool(excluded) if kind=='interface' else bool(history and history['excluded'])
            readable=all(response['metadata'].get('status')!='UNKNOWN' for response in chosen.values())
            status='UNKNOWN' if not observed or kind=='pair' and not readable else 'PARTIAL' if incomplete else 'COMPLETE'
            scope(kind,status,selected_names=[r['name'] for r in rows],
                  excluded_tail=deepcopy(history['excluded']) if kind!='interface' and history else [],
                  unavailable_frames=deepcopy(excluded) if kind=='interface' else [])
            for response in chosen.values():
                response['metadata'].update(reader_operation=record['reader_operation'],
                    source_execution_status=record['source_execution_status'],definition_pin=deepcopy(record['definition_pin']))
            result.setdefault('responses',{}).update(chosen)
            for key in ('selections','events'):record[key].update(observations[key])
            record['interface_controls']=observations['interface_controls']
        except errors as error:
            reject(error);scope(kind,'UNKNOWN',reason=str(error),selected_names=[r['name'] for r in rows])
    diagnostics['b_observations']=record
    save_json(root/'b_selected_responses.json',record)


def editor_rows(settings):
    """Native Qt table data; hashes/internal JSON are not the primary display."""
    rows=[]
    for i,law in enumerate(settings.get('bulk_damage',[])):
        rows.append({'label':'벌크 '+law['material'],'law':'LAW36 + INIEVO',
                     'gf_n_mm':law['evolution']['gf_n_mm'],'length':'초기 체적의 세제곱근 (ILEN0)',
                     'integration':'HEPH 1 IP / FAILIP1','eta':deepcopy(law['initiation']['eta']),
                     'rates_s_inv':deepcopy(law['initiation']['rates_s_inv']),
                     'initiation_table':deepcopy(law['initiation']['plastic_strain']),
                     'calibration_source':law['calibration']['source'],
                     'temperature':'교정 적용조건만; native 온도 의존 아님','settings_index':i})
    return {'bulk':rows,'interfaces':deepcopy(settings.get('interface_controls',[])),
            'quantities':[{'id':key,'label':v[0],'unit':v[2]} for key,v in impact_bulk_results.BULK.items()],
            'readback_label':'보존 결과 다시 읽기',
            'pair_semantics':'정확한 접촉쌍의 누적 충격량·구간 평균 힘·평균 힘 표본 적분을 구분합니다. 고정 runtime 미확인은 UNKNOWN입니다.'}


def set_bulk_law(settings,material,law=None):
    draft=deepcopy(settings); laws=draft.setdefault('bulk_damage',[])
    index=next((i for i,v in enumerate(laws) if v['material']==material),None)
    value=deepcopy(law) if law is not None else impact_bulk.default_law(material)
    if value.get('material')!=material:
        raise ValueError('선택 재료와 손상 정의가 다릅니다')
    if index is None:laws.append(value)
    else:laws[index]=value
    # An incomplete draft is editable/savable; validate() is the run gate.
    return draft
