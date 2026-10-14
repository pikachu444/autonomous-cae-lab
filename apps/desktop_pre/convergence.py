"""Convergence editing belongs to the selected native Analysis/solver document.

TIME rows use FreeCAD's existing properties. FIELD and penalty LINE SEARCH have
no FreeCAD 1.1.4 property/writer counterpart: explicitly applied supplemental
cards live in the same native document metadata, not a second solver document.
"""
from copy import deepcopy
import json

from caelab.calculix_controls import default_draft, draft_errors, raise_errors, validate_step_controls
from .nonlinear_material import native_type

OPERATIONS = ('pre.fem.convergence_read', 'pre.fem.convergence_save', 'pre.fem.convergence_apply')
NATIVE = ('IterationsControlParameterTimeUse', 'IterationsControlParameterIter', 'IterationsControlParameterCutb')


def selection(fem, solver, analysis_id):
    analysis = fem.owner._object(analysis_id)
    if (native_type(analysis) != 'Fem::FemAnalysis' or native_type(solver) != 'Fem::SolverCcxTools'
            or analysis.Document is not fem.owner.doc or solver not in analysis.Group
            or getattr(solver, 'Suppressed', False)):
        raise ValueError('현재 해석의 활성 CalculiX 설정을 선택하세요.')
    return analysis


def signature(solver):
    # An old solver/double may omit disabled row properties. Do not manufacture
    # effective TIME values: use=False means no card, not FreeCAD custom defaults.
    enabled = getattr(solver, NATIVE[0], False)
    return {'time_use': enabled, 'iterations': getattr(solver, NATIVE[1], ''),
            'factors': getattr(solver, NATIVE[2], '')}


def _record(fem, analysis, solver):
    rows = [r for r in fem._metadata().get('convergence_drafts', [])
            if r.get('analysis_id') == analysis.Name and r.get('solver_id') == solver.Name]
    if len(rows) > 1:
        raise ValueError('선택한 solver의 수렴 초안이 중복됩니다.')
    return deepcopy(rows[0]) if rows else None


def _context(fem, analysis):
    data = fem._metadata()
    programs = [r for r in data.get('contact_programs', []) if r.get('analysis_id') == analysis.Name]
    if len(programs) > 1:
        raise ValueError('해석 단계 정의가 중복됩니다.')
    # ContactEditor stores the program as 'draft'; inspect rather than silently
    # assuming static when another procedure has been saved.
    procedure = programs[0]['draft'].get('procedure') if programs else 'static'
    pairs = [r for r in data.get('contacts', []) if r.get('analysis_id') == analysis.Name]
    penalty = False
    for pair in pairs:
        try:
            obj = fem.owner._object(pair['object_id'])
        except (KeyError, ValueError):
            continue
        if obj in analysis.Group and not getattr(obj,'Suppressed',False) and pair.get('draft',{}).get('normal_law') == 'linear':
            penalty = True
    return procedure, penalty


def _cards(draft):
    return {'controls': [draft['iterations'], draft['factors']] if draft['time_use'] else None,
            **({'field_controls': draft['field']} if draft['field_use'] else {}),
            **({'line_search_controls': draft['line_search']} if draft['line_search_use'] else {})}


def read(fem, solver, analysis_id):
    analysis = selection(fem, solver, analysis_id)
    record = _record(fem, analysis, solver)
    current = signature(solver)
    value = deepcopy(record['draft']) if record else {**default_draft(), **current}
    errors = draft_errors(value)
    if not errors:
        try:
            procedure, penalty = _context(fem, analysis)
            validate_step_controls(_cards(value), procedure=procedure, penalty=penalty)
        except (ValueError, KeyError, TypeError) as e:
            errors.append({'path': 'controls', 'message': str(e)})
    applied = bool(record and record.get('applied_draft') == value and record.get('applied_native') == current)
    if record and record.get('applied_draft') == value and record.get('applied_native') != current:
        errors.append({'path': 'native', 'message': 'FreeCAD 증분 제어가 변경됐습니다. 값을 확인한 뒤 명시 적용하세요.'})
    return {'analysis_id': analysis.Name, 'solver_id': solver.Name, 'draft': value,
            'native': current, 'applied': applied, 'errors': errors, 'executed': False,
            'source': 'saved_draft' if record else 'native_properties'}


def _store(fem, analysis, solver, record):
    data = fem._metadata()
    data['convergence_drafts'] = [r for r in data.get('convergence_drafts', [])
        if (r.get('analysis_id'), r.get('solver_id')) != (analysis.Name, solver.Name)] + [record]
    fem.owner.write_metadata(data)


def save(fem, solver, analysis_id, draft):
    analysis = selection(fem, solver, analysis_id)
    if not isinstance(draft, dict) or len(json.dumps(draft, allow_nan=False).encode('utf-8')) > 16384:
        raise ValueError('수렴 초안은 16 KiB 이하의 설정으로 저장하세요.')
    record = _record(fem, analysis, solver) or {'analysis_id': analysis.Name, 'solver_id': solver.Name}
    record['draft'] = deepcopy(draft)
    fem._transaction('수렴 초안 저장', lambda: _store(fem, analysis, solver, record))
    return read(fem, solver, analysis_id)


def apply(fem, solver, analysis_id, draft):
    analysis = selection(fem, solver, analysis_id)
    raise_errors(draft_errors(draft))
    procedure, penalty = _context(fem, analysis)
    validate_step_controls(_cards(draft), procedure=procedure, penalty=penalty)
    def change():
        # Existing FreeCAD properties only. Disabled strings are preserved too.
        for prop, key in zip(NATIVE, ('time_use', 'iterations', 'factors')):
            setattr(solver, prop, draft[key])
        record = {'analysis_id': analysis.Name, 'solver_id': solver.Name,
                  'draft': deepcopy(draft), 'applied_draft': deepcopy(draft), 'applied_native': signature(solver)}
        _store(fem, analysis, solver, record)
    fem._transaction('수렴 설정 적용', change)
    return read(fem, solver, analysis_id)


def effective(fem, analysis, solver):
    """Fail closed before writing/creating a run. Never substitute applied for draft."""
    record = _record(fem, analysis, solver)
    if record:
        info = read(fem, solver, analysis.Name)
        raise_errors(info['errors'])
        if not info['applied']:
            raise ValueError('저장한 수렴 초안을 적용한 뒤 입력을 준비하세요.')
        return _cards(record['applied_draft'])
    native = signature(solver)
    # Legacy projects do not acquire supplemental FIELD/LINE SEARCH implicitly.
    value = {**default_draft(), **native}
    raise_errors(draft_errors(value))
    return _cards(value)


def dispatch(fem, operation, args, target):
    fem.owner.assert_thread()
    expected = {'analysis_id'} if operation.endswith('_read') else {'analysis_id', 'draft'}
    if operation not in OPERATIONS or set(args) != expected:
        raise ValueError('해석과 수렴 설정을 명시하세요.')
    solver = fem._object(target)
    if operation.endswith('_read'):
        return read(fem, solver, args['analysis_id'])
    fem._assert_idle()
    return (save if operation.endswith('_save') else apply)(fem, solver, args['analysis_id'], args['draft'])
