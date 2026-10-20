"""Model-definition IC cards plus the existing static step/load writer."""
from copy import deepcopy
from ..initial_field_conditions import effective,static_program
from ..contact_deck import num


def program(model,definition):
    """Preserve authored steps; the Aster consumer admits only its actual scope."""
    value,steps=static_program(model)
    if [s['parameter'] for s in definition['states']]!=[s['end'] for s in steps]:
        raise ValueError('초기장 상태와 원 정적 단계의 실제 끝값이 다릅니다.')
    if definition['solver']=='codeaster':
        # This worker supports constant native supports and a shared force
        # multiplier, not arbitrary changing displacement/release curves.
        if (model['step']['automatic'] or model['step'].get('controls') is not None
                or model['step'].get('matrix_solver')!='default'
                or any(s['initial']!=s['duration'] or s['maximum']!=s['duration']
                       or s['output_frequency']!=1 for s in steps)):
            raise ValueError('Code_Aster 호환 초기 상태는 단계마다 고정 증분 한 번과 매 단계 출력을 지원합니다. 자동 증분·별도 수렴/행렬 설정을 묵시적으로 바꾸지 않습니다.')
        previous=definition['states'][0]['load_factor']
        boundary={(r['node_id'],r['component']):r['value_mm'] for r in model['boundary_dofs']}
        forces={(r['node_id'],r['component']):r['force_N'] for r in model['loads']}
        for step,state in zip(steps,definition['states']):
            expected_bc={k:[[0.,v],[step['duration'],v]] for k,v in boundary.items()}
            expected_force={k:[[0.,v*previous],[step['duration'],v*state['load_factor']]] for k,v in forces.items()}
            if step['boundary']!=expected_bc or step['loads']!=expected_force:
                raise ValueError('Code_Aster 호환 초기 상태는 불변 구속과 공통 외력 배율만 지원합니다. 원 정적 곡선을 바꾸지 않습니다.')
            previous=state['load_factor']
    return value


def decorate(model,text):
    definition=effective(model)
    if definition is None:return text
    if model.get('analysis_steps')!=program(model,definition):raise ValueError('초기장 첫 평형·후속 하중 단계가 보존한 상태 정의와 다릅니다.')
    # The Aster consumer preserves this original geometry/load baseline; it does
    # not execute it as a CCX surrogate for ETAT_INIT.
    if definition['solver']=='codeaster':return text+'** Compatible initial state is executed by Code_Aster ETAT_INIT only.\n'
    lines=text.splitlines();first=next(i for i,l in enumerate(lines) if l.upper().startswith('*STEP'))
    pre=['*ELSET,ELSET=INITIAL_BODY']
    ids=sorted(r['element_id'] for r in model['elements'])
    pre += [','.join(map(str,ids[i:i+12])) for i in range(0,len(ids),12)]
    if definition['kind']=='temperature':
        t=definition['temperature'];at=next(i for i,l in enumerate(lines) if l.startswith('*SOLID SECTION'))
        lines[at:at]=['*EXPANSION,ZERO='+num(t['reference_K']),num(t['expansion_per_K'])]
        first=next(i for i,l in enumerate(lines) if l.upper().startswith('*STEP'))
        pre+=['*INITIAL CONDITIONS,TYPE=TEMPERATURE']
        pre+=[str(r['node_id'])+','+num(t['reference_K']) for r in model['nodes']]
    else:
        pre+=['*INITIAL CONDITIONS,TYPE=STRESS']
        pre += [str(r['element_id'])+','+str(r['point'])+','+','.join(num(v) for v in r['values_MPa']) for r in definition['stress_rows']]
    lines[first:first]=pre
    index=0;output=[]
    for line in lines:
        if line=='*END STEP':
            if definition['kind']=='temperature':
                t=definition['temperature'];value=t['samples_K'][index+1][1];selected=set(definition['node_ids'])
                output+=['*TEMPERATURE']+[str(r['node_id'])+','+num(value if r['node_id'] in selected else t['reference_K']) for r in model['nodes']]
            output+=['*EL PRINT,ELSET=INITIAL_BODY,FREQUENCY=1','S,COORD']
            index+=1
        output.append(line)
    if index!=len(definition['states']):raise ValueError('초기장 native 입력과 원 정적 단계 수가 다릅니다.')
    return '\n'.join(output)+'\n'
