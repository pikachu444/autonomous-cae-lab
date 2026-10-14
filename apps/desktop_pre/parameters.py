"""Live research bindings using the pinned CAD worker's existing primitives.

The worker's discovery, datum reading/writing and geometry-effect thresholds
are reused on the exact open document. Its saved-file dispatch is never called.
Native formulas are inspected, never evaluated by Core or this adapter.
"""
from copy import deepcopy
import math
import re
import uuid

from caelab.adapters import freecad_parameters as selectors
from caelab.storage import canonical_hash

OPERATIONS = ('pre.parameters.discover', 'pre.parameters.probe', 'pre.parameters.register',
              'pre.parameters.update', 'pre.parameters.rebind', 'pre.parameters.remove', 'pre.parameters.preflight')


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + ' must be a finite number')
    return float(value)


class Parameters:
    def __init__(self, owner, worker=None):
        self.owner, self._worker = owner, worker
        self.proofs = {}

    @property
    def worker(self):
        if self._worker is None:
            from caelab.adapters.freecad_parameter_worker import _upstream_worker
            try:
                self._worker = _upstream_worker()
            except (FileNotFoundError, ImportError) as error:
                raise ValueError('PARAMETER_WORKER_UNAVAILABLE: install the pinned fixture submodule; native CAD remains editable') from error
        return self._worker

    def registry(self):
        # The upstream _registry creates a configuration object on read. Keep
        # inspection read-only and create it only in an explicit registration.
        import json
        obj = self.owner.doc.getObject('FixtureConfiguration')
        if obj is None:
            return {'parameters': [], 'final': None}
        value = json.loads(obj.Definition)
        if not isinstance(value, dict) or not isinstance(value.get('parameters'), list):
            raise ValueError('Invalid native parameter registry; preserve and repair the draft')
        return value

    def _current(self):
        worker, owner = self.worker, self.owner
        registry = self.registry()
        targets = worker._targets(owner.doc)
        # Inspection keeps broken drafts editable. The shared selector stays
        # strict for export/execution; no failed binding is guessed here.
        selectors.unique_paths(targets)
        entries, resolved, failures = registry['parameters'], [], {}
        if any(not isinstance(entry, dict) for entry in entries):
            raise ValueError('Invalid native parameter definition; preserve and repair the draft')
        def identity(entry):
            return (entry.get('object'), entry.get('kind'),
                    entry.get('property') if entry.get('kind') == 'property' else entry.get('constraint'))
        for index, entry in enumerate(entries):
            try:
                result = selectors.registered_targets(owner.doc, {'parameters': [entry]}, targets, worker._datum)[0]
                if any(other != index and (entries[other].get('name') == entry.get('name')
                       or entries[other].get('key') == entry.get('key')
                       or identity(entries[other]) == identity(entry)) for other in range(len(entries))):
                    raise ValueError('NATIVE_DUPLICATE_IDENTITY: Duplicate registered parameter name, key or target')
                resolved.append(result)
            except ValueError as error:
                failures[index] = str(error)
        stamp = canonical_hash({'document_id': owner.document_id, 'session_id': owner.session_id,
            'generation': owner.generation, 'targets': targets, 'registry': registry})
        return registry, targets, resolved, stamp, failures

    def _occupied(self, actual, registry):
        obj = self.owner._object(actual['object'])
        dimension = (actual['dimension'] if actual['kind'] == 'property'
                     else obj.Constraints[selectors.raw_constraint_index(actual)].Name)
        return any(entry.get('object') == actual['object'] and entry.get('kind') == actual['kind']
                   and entry.get('property' if actual['kind'] == 'property' else 'constraint') == dimension
                   for entry in registry['parameters'])

    def _writable(self, actual, entry=None):
        obj = self.owner._object(actual['object'])
        kind = actual['kind']
        if kind == 'property':
            datum = actual['dimension']
            if {'ReadOnly', 'Hidden'}.intersection(obj.getEditorMode(datum)):
                raise ValueError('Read-only/hidden property cannot be a writable research variable')
            paths = {datum}
        else:
            datum = selectors.raw_constraint_index(actual)
            if not obj.getDriving(datum):
                raise ValueError('A reference constraint cannot drive a research variable')
            name = obj.Constraints[datum].Name
            if name and sum(c.Name == name for c in obj.Constraints) != 1:
                raise ValueError('Ambiguous Sketcher constraint name; repair its native names first')
            paths = {'Constraints[' + str(datum) + ']', 'Constraints.' + name}
        if any(path in paths for path, _ in getattr(obj, 'ExpressionEngine', [])):
            raise ValueError('Expression-driven target: edit its native expression, not a numerical replacement')
        return obj, datum

    def discover(self):
        registry, targets, resolved, stamp, failures = self._current()
        candidates = selectors.discovery_candidates(targets, resolved, stamp)
        candidates = [item for item in candidates if not self._occupied(
            selectors.resolve_selection(item['key'], stamp, stamp, targets, resolved)[0], registry)]
        for item in candidates:
            actual, _ = selectors.resolve_selection(item['key'], stamp, stamp, targets, resolved)
            try:
                self._writable(actual)
                item['writable'], item['diagnostic'] = True, None
            except ValueError as error:
                item['writable'], item['diagnostic'] = False, str(error)
        metadata = self.owner.read_metadata().get('parameters', {})
        registered = []
        by_entry = {id(entry): target for entry, target in resolved}
        for index, entry in enumerate(registry['parameters']):
            row = {**deepcopy(entry), **deepcopy(metadata.get(entry['name'], {})),
                   'current_value': None, 'resolved': index not in failures}
            if index in failures:
                row.update(writable=False, diagnostic=failures[index])
                registered.append(row)
                continue
            target = by_entry[id(entry)]
            row['current_value'] = self.worker._read(self.owner.doc, entry)
            try:
                self._writable(target, entry)
                row['writable'], row['diagnostic'] = True, None
            except ValueError as error:
                row['writable'], row['diagnostic'] = False, str(error)
            registered.append(row)
        solids = [{'object_id': obj.Name, 'label': obj.Label}
                  for obj in self.owner.doc.Objects if hasattr(obj, 'Shape')
                  and len(obj.Shape.Solids) == 1 and not obj.Shape.isNull()]
        return {'source_stamp': stamp, 'candidates': candidates, 'parameters': registered,
                'effect_objects': solids, 'units': 'mm', 'supported_types': ['continuous length'],
                'native_document': self.owner.doc.Name, 'generation': self.owner.generation}

    def probe(self, args):
        if set(args) != {'selector', 'source_stamp', 'effect_object_id', 'trial_value', 'unit'}:
            raise ValueError('Probe requires selector/source_stamp, effect_object_id, trial_value and unit')
        if args['unit'] != 'mm':
            raise ValueError('The pinned length-variable worker takes explicit mm values')
        trial = _finite(args['trial_value'], 'Trial value')
        registry, targets, resolved, stamp, _ = self._current()
        actual, registered = selectors.resolve_selection(args['selector'], stamp, args['source_stamp'], targets, resolved)
        self._writable(actual, registered)
        entry = deepcopy(registered or actual)
        if entry['kind'] == 'property' and not registered:
            entry['property'] = actual['dimension']
        if entry['kind'] == 'constraint' and not registered:
            entry['constraint_index'] = selectors.raw_constraint_index(actual)
        final = self.owner._object(args['effect_object_id'])
        if not hasattr(final, 'Shape') or len(final.Shape.Solids) != 1 or not final.Shape.isValid():
            raise ValueError('Select one valid solid for the existing geometry-effect check')
        old = self.worker._read(self.owner.doc, entry)
        if trial == old:
            raise ValueError('Choose a trial value different from the current value')
        before = list(self.worker._signature(final.Shape))
        after, failure = None, None
        owner, doc = self.owner, self.owner.doc
        # Abort, not Undo: a diagnostic probe must not become a user edit.
        # The exact original datum is also restored before abort, and verified.
        try:
            with owner.preview_changes():
                doc.openTransaction('CAE Lab temporary parameter effect')
                try:
                    self.worker._assign(doc, entry, trial)
                    doc.recompute()
                    if 'Invalid' in final.State or 'Error' in final.State or not final.Shape.isValid():
                        raise ValueError('Trial value produced an invalid native feature')
                    after = list(self.worker._signature(final.Shape))
                except Exception as error:
                    failure = str(error)
                finally:
                    try:
                        self.worker._assign(doc, entry, old)
                        doc.recompute()
                    finally:
                        doc.abortTransaction()
                restored = (self.worker._read(doc, entry) == old
                            and not self.worker._changes_shape(before, self.worker._signature(final.Shape)))
        except Exception as error:
            # A failed restoration/abort must not leave a usable success proof
            # or let the preview pose reach saving, meshing or a solver input.
            owner.recovery_error = ('PARAMETER_RESTORE_FAILED: inspect the native feature and restore '
                                    'the original datum before save/run; ' + str(error))
            raise ValueError(owner.recovery_error) from error
        if not restored:
            owner.recovery_error = 'PARAMETER_RESTORE_FAILED: inspect the native feature and restore the original datum before save/run'
            raise ValueError(owner.recovery_error)
        proof = {'proof_id': 'E' + uuid.uuid4().hex, 'selector': args['selector'],
                 'source_stamp': stamp, 'effect_object_id': final.Name, 'original_value': old,
                 'trial_value': trial, 'unit': 'mm', 'before': before, 'after': after,
                 'restored': True, 'changed': bool(after is not None and self.worker._changes_shape(before, after)),
                 'error': failure, 'method': 'pinned upstream _signature/_changes_shape'}
        self.proofs[proof['proof_id']] = deepcopy(proof)
        return proof

    def register(self, args):
        required = {'selector', 'source_stamp', 'proof_id', 'parameter_id', 'label', 'lower', 'upper', 'mode'}
        if set(args) != required:
            raise ValueError('Registration requires an explicit effect proof, name, bounds and fixed/free mode')
        name = args['parameter_id']
        if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9_]{0,47}', name):
            raise ValueError('Use a unique lower-case research parameter ID')
        if not isinstance(args['label'], str) or not args['label'].strip() or len(args['label']) > 160:
            raise ValueError('A readable parameter label of at most 160 characters is required')
        lower, upper = _finite(args['lower'], 'Lower bound'), _finite(args['upper'], 'Upper bound')
        if lower >= upper or args['mode'] not in {'fixed', 'free'}:
            raise ValueError('Increasing bounds and fixed/free mode are required')
        registry, targets, resolved, stamp, _ = self._current()
        actual, registered = selectors.resolve_selection(args['selector'], stamp, args['source_stamp'], targets, resolved)
        if registered or self._occupied(actual, registry) or any(row['name'] == name for row in registry['parameters']):
            raise ValueError('This target or research ID is already registered')
        obj, datum = self._writable(actual)
        proof = self.proofs.get(args['proof_id'])
        if (not proof or proof['source_stamp'] != stamp or proof['selector'] != args['selector']
                or not proof['changed'] or proof['error'] or not proof['restored']):
            raise ValueError('EFFECT_PROOF_STALE_OR_FAILED: probe this current live target before registration')
        value = float(actual['value'])
        if not lower <= value <= upper or not lower <= proof['trial_value'] <= upper:
            raise ValueError('Current and probed values must lie inside the explicit bounds')
        entry = {key: deepcopy(actual[key]) for key in ('object', 'kind')}
        entry.update(name=name, label=args['label'].strip(), min=lower, max=upper,
                     unit='mm', key=args['selector'])
        if actual['kind'] == 'property':
            entry['property'] = actual['dimension']
        else:
            if any(c.Name == name for i, c in enumerate(obj.Constraints) if i != datum):
                raise ValueError('The requested stable Sketcher name already exists')
            entry['constraint'] = name
        metadata = self.owner.read_metadata()
        metadata.setdefault('parameters', {})[name] = {'parameter_id': name, 'mode': args['mode'],
            'type': 'continuous', 'default_value': value, 'effect': deepcopy(proof), 'source': 'explicit live native registration'}
        registry['parameters'].append(entry)
        def apply():
            if actual['kind'] == 'constraint':
                obj.renameConstraint(datum, name)
            self.worker._save_registry(self.owner.doc, registry)
            self.owner.write_metadata(metadata)
        self.owner._transaction('Register research variable ' + name, apply)
        return self.discover()

    def update(self, args):
        if set(args) - {'parameter_id', 'value', 'unit', 'lower', 'upper', 'mode', 'label'} or 'parameter_id' not in args:
            raise ValueError('Update only a named registered variable value/bounds/mode/label')
        registry, targets, resolved, _, _ = self._current()
        match = next(((e, t) for e, t in resolved if e['name'] == args['parameter_id']), None)
        if not match:
            raise ValueError('Select an existing research parameter ID')
        entry, actual = match
        self._writable(actual, entry)
        lower = _finite(args.get('lower', entry['min']), 'Lower bound')
        upper = _finite(args.get('upper', entry['max']), 'Upper bound')
        value = _finite(args.get('value', self.worker._read(self.owner.doc, entry)), 'Value')
        if ('value' in args and args.get('unit') != 'mm') or lower >= upper or not lower <= value <= upper:
            raise ValueError('Explicit mm value and increasing bounds containing the value are required')
        metadata = self.owner.read_metadata()
        info = metadata.setdefault('parameters', {}).setdefault(entry['name'], {})
        if args.get('mode', info.get('mode', 'fixed')) not in {'fixed', 'free'}:
            raise ValueError('Use fixed or free research mode')
        info['mode'] = args.get('mode', info.get('mode', 'fixed'))
        entry.update(min=lower, max=upper)
        if 'label' in args:
            if not isinstance(args['label'], str) or not 0 < len(args['label'].strip()) <= 160:
                raise ValueError('Enter a nonempty short label')
            entry['label'] = args['label'].strip()
        def apply():
            if 'value' in args:
                self.worker._assign(self.owner.doc, entry, value)
            self.worker._save_registry(self.owner.doc, registry)
            self.owner.write_metadata(metadata)
        self.owner._transaction('Edit research variable ' + entry['name'], apply)
        return self.discover()

    def rebind(self, args):
        if set(args) != {'parameter_id', 'selector', 'source_stamp', 'proof_id'}:
            raise ValueError('Repair requires the registered variable, current replacement and effect proof')
        registry, targets, resolved, stamp, failures = self._current()
        matches = [(i, entry) for i, entry in enumerate(registry['parameters'])
                   if entry['name'] == args['parameter_id']]
        if len(matches) != 1 or matches[0][0] not in failures:
            raise ValueError('Select one unresolved registered variable; duplicate IDs require native registry repair')
        index, old = matches[0]
        # Even an exact registered key cannot bypass a stale repair request.
        if args['source_stamp'] != stamp:
            raise ValueError('NATIVE_SELECTOR_STALE: rediscover before repairing this variable')
        actual, registered = selectors.resolve_selection(args['selector'], stamp, args['source_stamp'], targets, resolved)
        if registered or self._occupied(actual, registry):
            raise ValueError('The replacement target is already registered')
        obj, datum = self._writable(actual)
        proof = self.proofs.get(args['proof_id'])
        if (not proof or proof['source_stamp'] != stamp or proof['selector'] != args['selector']
                or not proof['changed'] or proof['error'] or not proof['restored']):
            raise ValueError('EFFECT_PROOF_STALE_OR_FAILED: check this replacement before applying repair')
        if old.get('unit') != 'mm' or actual.get('unit') != 'mm' or proof['unit'] != 'mm':
            raise ValueError('The replacement must use the registered mm length unit')
        lower, upper = _finite(old['min'], 'Lower bound'), _finite(old['max'], 'Upper bound')
        if lower >= upper or not lower <= actual['value'] <= upper or not lower <= proof['trial_value'] <= upper:
            raise ValueError('Replacement and probed values must lie inside the existing bounds')
        entry = deepcopy(old)
        for key in ('property', 'constraint', 'constraint_index'):
            entry.pop(key, None)
        entry.update(object=actual['object'], kind=actual['kind'], key=args['selector'])
        if actual['kind'] == 'property':
            entry['property'] = actual['dimension']
        else:
            if any(c.Name == old['name'] for i, c in enumerate(obj.Constraints) if i != datum):
                raise ValueError('The stable Sketcher name already exists; repair native names first')
            entry['constraint'] = old['name']
        registry['parameters'][index] = entry
        metadata = self.owner.read_metadata()
        metadata.setdefault('parameters', {}).setdefault(old['name'], {})['effect'] = deepcopy(proof)
        def apply():
            if actual['kind'] == 'constraint':
                obj.renameConstraint(datum, old['name'])
            self.worker._save_registry(self.owner.doc, registry)
            self.owner.write_metadata(metadata)
            selectors.registered_targets(self.owner.doc, {'parameters': [entry]},
                                         self.worker._targets(self.owner.doc), self.worker._datum)
        self.owner._transaction('Repair research variable ' + old['name'], apply)
        self.proofs.clear()
        return self.discover()

    def dispatch(self, operation, args, target):
        if target:
            raise ValueError('Research variable commands use explicit selector/parameter IDs in arguments')
        if operation == 'pre.parameters.discover':
            if args:
                raise ValueError('Discover takes no arguments')
            return self.discover()
        if operation == 'pre.parameters.probe':
            return self.probe(args)
        if operation == 'pre.parameters.register':
            return self.register(args)
        if operation == 'pre.parameters.update':
            return self.update(args)
        if operation == 'pre.parameters.rebind':
            return self.rebind(args)
        if operation == 'pre.parameters.remove':
            if set(args) != {'parameter_id'}:
                raise ValueError('Select an exact registered variable')
            registry = self.registry()
            if sum(e['name'] == args['parameter_id'] for e in registry['parameters']) != 1:
                raise ValueError('Select one unique registered variable; duplicate IDs require native registry repair')
            registry['parameters'] = [e for e in registry['parameters'] if e['name'] != args['parameter_id']]
            metadata = self.owner.read_metadata()
            metadata.setdefault('parameters', {}).pop(args['parameter_id'], None)
            def remove():
                self.worker._save_registry(self.owner.doc, registry)
                self.owner.write_metadata(metadata)
            self.owner._transaction('Remove research registration', remove)
            return self.discover()
        if operation == 'pre.parameters.preflight':
            if args:
                raise ValueError('Preflight takes no arguments')
            result = self.discover()
            result['diagnostics'] = [{'parameter_id': row['name'], 'message': row['diagnostic']}
                                     for row in result['parameters'] if row['diagnostic']]
            result['engineering_release'] = 'UNKNOWN'
            return result
        raise ValueError('Unsupported parameter operation')
