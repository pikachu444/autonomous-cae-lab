"""Persist dynamic drafts in the existing FreeCAD Owner metadata/transactions."""
from copy import deepcopy
from caelab.storage import canonical_hash
from caelab.dynamic_model import (NAMESPACE, OPERATIONS, READ_ONLY, DynamicInputError,
    check_shape, default_draft, settings, attach, capability)
from . import dynamic_native as native


class DynamicEditor:
    def __init__(self, owner): self.owner = owner
    def _records(self): return self.owner.read_metadata().get(NAMESPACE, {})
    def _get(self, key):
        if key not in self._records(): raise DynamicInputError('analysis_id', '동해석 설정을 먼저 만드세요.')
        return deepcopy(self._records()[key])
    def _put(self, key, record):
        data = self.owner.read_metadata()
        data.setdefault(NAMESPACE, {})[key] = deepcopy(record)
        self.owner.write_metadata(data)
    def discover(self):
        from .fem_edit import _native_type
        return [{'id': a.Name, 'label': a.Label, 'solvers': [
            {'id': s.Name, 'label': s.Label} for s in a.Group if _native_type(s) == 'Fem::SolverCcxTools']}
            for a in self.owner.doc.Objects if _native_type(a) == 'Fem::FemAnalysis']
    def inspect(self, analysis_id=None):
        self.owner.assert_thread()
        result = {'analyses': self.discover(), 'models': deepcopy(self._records())}
        if analysis_id is None: return result
        r = self._get(analysis_id); d = r['draft']; errors = []; model = identity = None
        try:
            model, identity = native.base(self.owner, analysis_id, d['solver_id'])
            native.check_targets(self.owner, d, model, identity)
            preview = attach(model, d)
            native.admitted(self.owner, r, model, identity)
        except DynamicInputError as exc: errors.append(exc.record())
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            errors.append({'path': 'native', 'message': str(exc)})
        result.update(record=r, errors=errors, can_freeze=not errors,
            bodies=[] if model is None else [{'id': b['body_id'], 'mesh_id': b['mesh_id'],
                'native_node_ids': [n['native_node_id'] for n in model['nodes'] if n['body_id'] == b['body_id']]}
                for b in identity], capability=None if model is None else capability(model))
        return result
    def create(self, analysis_id, solver_id):
        if analysis_id in self._records(): raise DynamicInputError('analysis_id', '기존 동해석 설정을 편집하세요.')
        model, _ = native.base(self.owner, analysis_id, solver_id)
        from caelab.contact_steps import default_program
        p = [r['draft'] for r in self.owner.fem._metadata().get('contact_programs', []) if r['analysis_id'] == analysis_id]
        program = deepcopy(p[0]) if len(p) == 1 else default_program(model['step'], model['conditions'])
        densities = []
        for m in model['materials']:
            try: text = str(self.owner.App.Units.Quantity(m['native_values']['Density']).getValueAs('kg/m^3').Value)
            except (KeyError, ValueError, AttributeError): text = ''
            densities.append({'body_id': m['body_id'], 'material_id': m['object_id'], 'kg_m3': text})
        draft = default_draft(analysis_id, solver_id, program, densities)
        self.owner._transaction('동해석 설정 만들기', lambda: self._put(analysis_id, {'draft': draft}))
        return self.inspect(analysis_id)
    def save_draft(self, analysis_id, draft):
        check_shape(draft)
        record = self._get(analysis_id)
        if draft['analysis_id'] != analysis_id or draft['solver_id'] != record['draft']['solver_id']:
            raise DynamicInputError('analysis_id', '초안의 해석과 solver 대상을 바꿀 수 없습니다.')
        record['draft'] = deepcopy(draft)
        self.owner._transaction('동해석 초안 저장', lambda: self._put(analysis_id, record))
        return self.inspect(analysis_id)
    def apply(self, analysis_id, draft):
        record = self._get(analysis_id); check_shape(draft)
        if draft['analysis_id'] != analysis_id or draft['solver_id'] != record['draft']['solver_id']:
            raise DynamicInputError('analysis_id', '해석과 solver 대상을 확인하세요.')
        model, identity = native.base(self.owner, analysis_id, draft['solver_id'])
        native.check_targets(self.owner, draft, model, identity)
        values = settings(draft, model)
        attach(model, draft)  # Validate element/law/step combinations before any write.
        def change():
            for row in values['densities']:
                obj = self.owner._object(row['material_id'])
                obj.Material = dict(obj.Material, Density=f"{row['kg_m3']:.17g} kg/m^3")
            self.owner.doc.recompute()
            current, proof = native.base(self.owner, analysis_id, draft['solver_id'])
            native.check_targets(self.owner, draft, current, proof)
            record.update(draft=deepcopy(draft), applied_draft_hash=canonical_hash(draft),
                          source_stamp=native.source_stamp(current, proof))
            self._put(analysis_id, record)
        self.owner._transaction('동해석 설정 적용', change)
        return self.inspect(analysis_id)
    def dispatch(self, operation, args, target):
        if target: raise ValueError('동해석은 명시한 Analysis와 원 body 대상을 사용합니다.')
        allowed = {
            'pre.dynamic.inspect': {'analysis_id'}, 'pre.dynamic.create': {'analysis_id', 'solver_id'},
            'pre.dynamic.draft': {'analysis_id', 'draft'}, 'pre.dynamic.apply': {'analysis_id', 'draft'},
            'pre.dynamic.capture': {'analysis_id', 'body_id', 'native_node_ids', 'faces'},
            'pre.dynamic.freeze': {'analysis_id'},
            'pre.dynamic.restart': {'analysis_id', 'parent_attempt', 'checkpoint_step', 'steps'}}
        if operation not in allowed or (set(args) != allowed[operation] and not (operation == 'pre.dynamic.inspect' and not args)):
            raise ValueError('지원되지 않는 동해석 명령 인수입니다.')
        key = args.get('analysis_id')
        if operation == 'pre.dynamic.inspect': return self.inspect(key)
        if operation == 'pre.dynamic.create': return self.create(key, args['solver_id'])
        if operation == 'pre.dynamic.draft': return self.save_draft(key, args['draft'])
        if operation == 'pre.dynamic.apply': return self.apply(key, args['draft'])
        r = self._get(key)
        if operation == 'pre.dynamic.capture':
            model, identity = native.base(self.owner, key, r['draft']['solver_id'])
            return {'target': native.target(self.owner, model, identity, args['body_id'],
                native_node_ids=args['native_node_ids'], faces=args['faces'])}
        if operation == 'pre.dynamic.freeze': return native.freeze(self.owner, r)
        return native.restart(self.owner, r, args['parent_attempt'], args['checkpoint_step'], args['steps'])
