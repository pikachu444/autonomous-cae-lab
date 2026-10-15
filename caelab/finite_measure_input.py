"""Pure UI/import/recipe compilation over existing Data documents and owners."""
from copy import deepcopy
from .finite_measure import (make_definition, operation, evaluate_row, active_roles, F_COMPONENTS, STRAIN_MEASURES)
from .material_test import TIME

NAMES = {'load': 'fm_load', 'deformation': 'fm_deformation', 'area': 'fm_area', 'J': 'fm_J',
         **{'F'+c:'fm_F'+c for c in F_COMPONENTS}}
RESULT_NAMES = {'first_Piola':'finite_P', 'finite_Cauchy':'finite_sigma',
                'engineering_strain':'finite_e', 'stretch':'finite_lambda', 'log_strain':'finite_log'}


def default_config():
    return {'version':1, 'axis':'x', 'scope_confirmed':False, 'time_column':None, 'time_unit':'',
        'columns': {'load': {'column':None, 'unit':'', 'measure':'axial_force'},
                    'deformation': {'column':None, 'unit':'', 'measure':'gauge_extension'}},
        'geometry': {'A0': {'value':'', 'unit':'mm2', 'evidence':''},
                     'L0': {'value':'', 'unit':'mm', 'evidence':''}},
        'measurement':'', 'basis':'none', 'stress_unit':'MPa', 'assumptions':{},
        'outputs':['first_Piola','engineering_strain','stretch','log_strain']}


def mapping(config, *, delimiter=',', skip_header=1):
    """Raw columns are not relabelled as transformed stress/strain.

    Parsing numbers is a dialog concern. Invalid raw text remains in its config
    and invalid mappings remain saveable through the ordinary Data owner.
    """
    axis = {'column':config.get('time_column'), 'name':'time', 'unit':'s',
            'scale':TIME.get(config.get('time_unit'), config.get('time_unit'))}
    columns = {}
    for role, entry in config.get('columns', {}).items():
        name = NAMES[role]
        component = role[1:] if role.startswith('F') else 'J' if role == 'J' else config.get('axis','')*2
        columns[name] = {'column':entry.get('column'), 'unit':entry.get('unit',''),
            'measure':entry.get('measure',''), 'component':component,
            'location':'material_point', 'frame':'material_cartesian', 'reduction':'none',
            'axis':deepcopy(axis), 'row_selection':{'display_hidden_rows':[]}}
    return dict(delimiter=delimiter,skip_header=skip_header,columns=columns)


def definitions(config):
    selected = config.get('outputs', [])
    if not isinstance(selected, list) or not selected or len(set(selected)) != len(selected) or set(selected)-set(RESULT_NAMES):
        raise ValueError('계산할 유한 응력/변형 측도를 선택하세요.')
    defs = []
    load = config.get('columns', {}).get('load', {}).get('measure')
    for target in selected:
        basis = config.get('basis', 'none')
        if target in STRAIN_MEASURES or target == load or target=='first_Piola' and load=='axial_force':
            basis='none'
        definition = make_definition(output=target,axis=config.get('axis'),unit=config.get('stress_unit'),basis=basis,
            channels={role:NAMES[role] for role in config.get('columns', {})},
            geometry=config.get('geometry'),measurement=config.get('measurement'),assumptions=config.get('assumptions'))
        if config.get('scope_confirmed') is not True:
            definition['scope']='UNCONFIRMED'
        defs.append(definition)
    return defs


def recipe(config, existing=None):
    """Replace only this feature's reserved operations; leave all other DAG work."""
    result = deepcopy(existing or {'version':1,'operations':[]})
    additions = [operation('Ofinite'+str(index+1), definition, RESULT_NAMES[definition['output']])
                 for index,definition in enumerate(definitions(config))]
    result['operations'] = [op for op in result['operations'] if not (
        op.get('operation')=='finite_observation' and op.get('id','').startswith('Ofinite'))]
    existing_outputs = {op['output'] for op in result['operations']}
    if any(op['output'] in existing_outputs for op in additions):
        raise ValueError('같은 출력명이 기존 처리에 사용 중입니다. 기존 처리를 덮어쓰지 않습니다.')
    # Finite observation inputs are raw channels; put them before their existing
    # downstream operations (smooth/resample/etc.) instead of creating a cycle.
    result['operations'] = additions + result['operations']
    return result


def verify_import(config, result, *, delimiter=',', skip_header=1):
    expected = mapping(config,delimiter=delimiter,skip_header=skip_header)['columns']
    for name, spec in expected.items():
        actual=result.get('responses',{}).get(name)
        if actual is None or actual.get('mapping') != spec:
            raise ValueError('열/단위 설정과 선택한 보존 import가 다릅니다. 현재 설정을 적용하고 명시적으로 다시 가져오세요: '+name)


def local_preview(config, rows):
    """Unsealed UI calculation only; never an import identity or Plan source."""
    mapped = mapping(config)['columns']; defs = definitions(config); result=[]
    for index,row in enumerate(rows):
        record={'preview_row':index+1,'raw':deepcopy(row),'values':{},'errors':{}}
        for definition in defs:
            target=definition['output']
            try:
                operands={}
                for role in active_roles(definition):
                    name=definition['channels'][role];spec=mapped[name]
                    column=spec['column']
                    if type(column) is not int or not 0<=column<len(row):
                        raise ValueError(role+': 원본 열을 선택하세요.')
                    raw=row[column]
                    if isinstance(raw,bool):raise ValueError('boolean은 측정값이 아닙니다.')
                    value=float(raw)
                    operands[role]={'value':value,'metadata':{k:spec[k] for k in
                        ('unit','measure','component','location','frame','reduction')}}
                record['values'][target]=evaluate_row(definition,operands)[0]
            except (ValueError,TypeError,KeyError,IndexError,OverflowError,ZeroDivisionError) as error:
                record['values'][target]=None;record['errors'][target]=str(error)
        result.append(record)
    return result


def verify_processing_specification(draft, imported):
    """Never execute an old finite recipe beneath newly edited geometry/units.

    Only the GUI-owned Ofinite operations are tied to its raw form. Hand-authored
    finite operations without a GUI config continue using their own definition.
    Past immutable processing revisions are never passed through this current-
    draft check: frozen Plan evidence remains independently readable.
    """
    config=draft.get('finite_measure')
    operations=(draft.get('processing') or {}).get('recipe',{}).get('operations',[])
    owned=[op for op in operations if op.get('operation')=='finite_observation' and op.get('id','').startswith('Ofinite')]
    if config is None or not owned:return
    expected=recipe(config)['operations']
    if owned!=expected:
        raise ValueError('현재 치수/측도 초안과 처리 정의가 다릅니다. 유한변환 단계를 다시 연결하고 검토하세요. 과거 보존 결과는 변경하지 않습니다.')
    verify_import(config,imported)
