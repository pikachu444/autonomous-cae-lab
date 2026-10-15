"""Bounded variable semantics shared by Numerical's existing engines.

Only generation/evaluation calls ``resolve``. Retained assignment verification
uses frozen hashes and membership, NEVER evaluates dependent expressions. Units
in dependencies use dimensioned_expression's SI dimensions; labels do not scale
values. Integer/choice coordinates belong to samplers, not to model inputs.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import math
import re
from typing import Any

from . import dimensioned_expression as expression
from .contracts import CapabilityUnavailable
from .storage import canonical_hash

DOMAIN_SCHEMA = 'caelab.variable-domains.v1'
ASSIGNMENT_SCHEMA = 'caelab.variable-assignment.v1'
KINDS = ('continuous', 'integer', 'discrete', 'categorical')
MODES = ('free', 'fixed', 'dependent')
MAX_VARIABLES = 64
MAX_CHOICES = 256
MAX_EXACT_INTEGER = 2**53 - 1
_ALLOWED = {'id', 'parameter_id', 'unit', 'kind', 'mode', 'lower', 'upper',
            'lower_bound', 'upper_bound', 'value', 'initial', 'transform',
            'values', 'choices', 'expression'}


class DomainError(ValueError):
    """A location-bearing declaration/input error; no model was dispatched."""
    def __init__(self, code: str, message: str, *, path='variables', node=None):
        self.code, self.path = code, path
        self.line = getattr(node, 'lineno', None)
        self.column = getattr(node, 'col_offset', None)
        location = f' (line {self.line}, column {self.column + 1})' if self.line else ''
        super().__init__(f'{path}: {message}{location}')

    def diagnostic(self):
        return {'code': self.code, 'path': self.path, 'message': str(self),
                'line': self.line, 'column': self.column}


def _fail(code, message, path, node=None):
    raise DomainError(code, message, path=path, node=node)


def _plain_number(value, path):
    # Accept NumPy scalar callers without bool/int conflation. JSON stays typed.
    if type(value).__module__.startswith('numpy') and hasattr(value, 'item'):
        value = value.item()
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        _fail('NONFINITE_NUMBER', 'A finite number (not bool) is required', path)
    return value


def _integer(value, path, *, encoded=False):
    value = _plain_number(value, path)
    if (type(value) is not int and not (encoded and float(value).is_integer())):
        _fail('FRACTIONAL_INTEGER', 'An exact integer is required; values are never rounded', path)
    if abs(value) > MAX_EXACT_INTEGER:
        _fail('INTEGER_PRECISION', 'Integer exceeds the exact float64 sampler range', path)
    return int(value)


def kind(variable):
    return variable.get('kind', 'continuous')


def mode(variable):
    return variable.get('mode', 'free')


def typed(variables):
    return any(kind(v) != 'continuous' or mode(v) != 'free' for v in variables)


def validate_choices(choices, *, path='choices'):
    if not isinstance(choices, list) or not 1 <= len(choices) <= MAX_CHOICES:
        _fail('CHOICE_SET', f'Declare 1..{MAX_CHOICES} choices', path)
    ids, values, labels = set(), set(), set()
    result = []
    for i, row in enumerate(choices):
        p = f'{path}.{i}'
        if not isinstance(row, dict) or set(row) != {'id', 'label', 'value'}:
            _fail('CHOICE_DECLARATION', 'A choice requires id, label and actual string value', p)
        if any(not isinstance(row[k], str) or not row[k].strip() or len(row[k]) > 128
               for k in ('id', 'label', 'value')):
            _fail('AMBIGUOUS_ENUM', 'Category IDs, labels and values must be nonempty strings; numeric codes are not values', p)
        if row['id'] in ids or row['value'] in values or row['label'] in labels:
            _fail('DUPLICATE_CHOICE', 'Choice identity, value and displayed label must be distinct', p)
        ids.add(row['id']); values.add(row['value']); labels.add(row['label'])
        result.append(deepcopy(row))
    return result


def check_value(variable, value, *, path=None, calculated=False):
    """Validate physical membership. ``calculated`` permits exact integral AST results."""
    path = path or 'values.' + variable['id']
    k = kind(variable)
    if k == 'categorical':
        if type(value) is not str or value not in [c['value'] for c in variable['choices']]:
            _fail('ENUM_MEMBERSHIP', 'Use an advertised actual category value, not its label or index', path)
        return value
    if k == 'integer':
        value = _integer(value, path, encoded=calculated)
    elif k == 'continuous':
        value = float(_plain_number(value, path))
    else:
        value = _plain_number(value, path)
        if value not in variable['values']:
            _fail('DISCRETE_MEMBERSHIP', 'Value is outside the explicit numeric set', path)
        # Preserve the declaration's scalar type at generation, not by rounding.
        value = next(v for v in variable['values'] if v == value)
    if not variable['lower'] <= value <= variable['upper']:
        _fail('OUT_OF_BOUNDS', 'Value is outside declared bounds', path)
    return value


def _alias(row, primary, secondary, default, path):
    if primary in row and secondary in row:
        _fail('AMBIGUOUS_FIELD', f'Use {primary} or {secondary}, not both', path)
    return row.get(primary, row.get(secondary, default))


def normalize(variables):
    """Normalize declarations without evaluating a candidate or any dependency.

    Omitted kind/mode keep the old continuous/free normalized representation.
    Prefix units remain ordinary labels unless used in a dimensioned dependency.
    """
    if not isinstance(variables, list) or not 1 <= len(variables) <= MAX_VARIABLES:
        _fail('VARIABLE_COUNT', f'Declare 1..{MAX_VARIABLES} numerical variables', 'variables')
    result, names = [], set()
    for i, row in enumerate(variables):
        path = f'variables.{i}'
        if not isinstance(row, dict) or set(row) - _ALLOWED:
            _fail('VARIABLE_FIELDS', 'Unknown variable fields; executable paths are not inputs', path)
        name = _alias(row, 'id', 'parameter_id', None, path + '.id')
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            _fail('VARIABLE_ID', 'A nonempty bounded variable ID is required', path + '.id')
        if name in names:
            _fail('DUPLICATE_ID', 'Variable IDs must be distinct: ' + name, path + '.id')
        names.add(name)
        unit = row.get('unit')
        if not isinstance(unit, str) or not unit.strip() or len(unit) > 128:
            _fail('UNIT_REQUIRED', 'Declare the unit (1 for dimensionless values)', path + '.unit')
        k, m = row.get('kind', 'continuous'), row.get('mode', 'free')
        if k not in KINDS or m not in MODES:
            _fail('DOMAIN_KIND', 'Choose a supported kind and mode', path)
        if m == 'fixed' and not (set(row) & {'value', 'initial'}):
            _fail('FIXED_VALUE_REQUIRED', 'A fixed variable requires an explicit value', path + '.value')
        tr = row.get('transform', 'linear')
        if tr not in ('linear', 'log') or (tr == 'log' and (k != 'continuous' or m != 'free')):
            _fail('INVALID_LOG', 'Log sampling is only available for positive free continuous variables', path + '.transform')
        if m == 'dependent':
            if k not in ('continuous', 'integer'):
                _fail('DEPENDENT_KIND', 'Dependent expressions have numeric continuous/integer outputs', path)
            if 'value' in row or 'initial' in row:
                _fail('DEPENDENT_OVERRIDE', 'A dependent declaration cannot override its expression with a value', path + '.value')
            if not isinstance(row.get('expression'), str) or not row['expression'].strip():
                _fail('EXPRESSION_REQUIRED', 'A dependent variable requires an expression', path + '.expression')
        elif 'expression' in row:
            _fail('EXPRESSION_MODE', 'An expression requires mode=dependent', path + '.expression')
        v = {'id': name, 'unit': unit}
        if 'kind' in row or 'mode' in row or k != 'continuous' or m != 'free':
            v.update(kind=k, mode=m)
        if k == 'categorical':
            if unit != '1' or set(row) & {'values', 'lower', 'upper', 'lower_bound', 'upper_bound'}:
                _fail('ENUM_DECLARATION', 'Categories use unit 1 and choices, never numeric bounds', path)
            v['choices'] = validate_choices(row.get('choices'), path=path + '.choices')
            default = v['choices'][0]['value']
        elif k == 'discrete':
            if 'choices' in row:
                _fail('DISCRETE_DECLARATION', 'Numeric discrete variables use values, not categories', path)
            vals = row.get('values')
            if not isinstance(vals, list) or not 1 <= len(vals) <= MAX_CHOICES:
                _fail('DISCRETE_SET', f'Declare 1..{MAX_CHOICES} ordered numeric values', path + '.values')
            vals = [_plain_number(x, f'{path}.values.{j}') for j, x in enumerate(vals)]
            if any(a >= b for a, b in zip(vals, vals[1:])):
                _fail('DISCRETE_ORDER', 'Numeric values must be distinct and strictly increasing', path + '.values')
            v['values'] = vals
            default = vals[len(vals)//2]
        else:
            if set(row) & {'values', 'choices'}:
                _fail('NUMERIC_DECLARATION', 'Use bounds for continuous/integer variables', path)
            default = None
        if k != 'categorical':
            supplied = _alias(row, 'value', 'initial', default, path + '.value')
            low_default = v['values'][0] if k == 'discrete' else supplied if m == 'fixed' else None
            high_default = v['values'][-1] if k == 'discrete' else supplied if m == 'fixed' else None
            low = float(_plain_number(_alias(row, 'lower', 'lower_bound', low_default, path), path + '.lower'))
            high = float(_plain_number(_alias(row, 'upper', 'upper_bound', high_default, path), path + '.upper'))
            if (low > high or (low == high and k == 'continuous' and m == 'free')
                    or not math.isfinite(high-low) or not math.isfinite(high+low)):
                _fail('INVALID_BOUNDS', 'Requires increasing finite bounds (or an explicit fixed/finite singleton)', path)
            if k == 'integer':
                if max(abs(low), abs(high)) > MAX_EXACT_INTEGER:
                    _fail('INTEGER_PRECISION', 'Bounds exceed the exact integer sampler range', path)
                if math.ceil(low) > math.floor(high):
                    _fail('EMPTY_INTEGER_RANGE', 'No allowed integer lies in these bounds', path)
            if tr == 'log' and low <= 0:
                _fail('INVALID_LOG', 'Log sampling requires positive bounds', path + '.transform')
            v.update(lower=low, upper=high)
            if k == 'discrete' and any(not low <= x <= high for x in v['values']):
                _fail('DISCRETE_BOUNDS', 'Every declared discrete value must lie in the bounds', path)
            if default is None:
                default = (math.ceil(low)+math.floor(high))//2 if k == 'integer' else (low+high)/2
        if m != 'dependent':
            val = _alias(row, 'value', 'initial', default, path + '.value')
            v['value'] = check_value(v, val, path=path + '.value')
        else:
            v['expression'] = row['expression']
        v['transform'] = tr
        result.append(v)
    _dependencies(result)  # Only bounded parsing, topology and dimensions; no evaluation.
    return result


def _dependencies(variables):
    by_id = {v['id']: v for v in variables}
    indices = {v['id']: i for i, v in enumerate(variables)}
    deps, trees = {}, {}
    for variable in variables:
        if mode(variable) != 'dependent':
            continue
        name = variable['id']; path = f"variables.{indices[name]}.expression"
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) or name in expression.FUNCTIONS:
            _fail('DEPENDENT_ID', 'Expression output IDs must be ordinary, non-function names', path)
        source = variable['expression']
        if not isinstance(source, str) or len(source) > 2048:
            _fail('EXPRESSION_BOUND', 'Expressions are bounded to 2048 characters', path)
        try:
            tree = ast.parse(source, mode='eval').body
        except (SyntaxError, ValueError, RecursionError) as exc:
            _fail('EXPRESSION_SYNTAX', str(exc), path)
        nodes = list(ast.walk(tree))
        if len(nodes) > 256:
            _fail('EXPRESSION_BOUND', 'Expression exceeds 256 AST nodes', path)
        call_names = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
        refs = []
        for node in nodes:
            if not isinstance(node, ast.Name) or id(node) in call_names:
                continue
            if node.id == name:
                _fail('SELF_REFERENCE', 'Dependent value refers to itself', path, node)
            if node.id not in by_id:
                _fail('UNKNOWN_REFERENCE', 'Undefined variable: ' + node.id, path, node)
            if kind(by_id[node.id]) == 'categorical':
                _fail('CATEGORY_EXPRESSION', 'Categories cannot enter scalar arithmetic', path, node)
            if node.id not in refs:
                refs.append(node.id)
        symbols = {}
        try:
            for ref in refs:
                symbols[ref] = expression.Meaning(expression.unit_dimension(by_id[ref]['unit'], path=f'variables.{indices[ref]}.unit'))
            parsed, meaning = expression.parse(source, symbols, path=path)
            expected = expression.Meaning(expression.unit_dimension(variable['unit'], path=f'variables.{indices[name]}.unit'))
        except expression.ExpressionError as exc:
            error = DomainError('EXPRESSION_DIMENSION_OR_SYNTAX', str(exc), path=exc.path)
            error.line, error.column = exc.line, exc.column
            raise error from exc
        if meaning != expected:
            _fail('UNIT_MISMATCH', 'Expression dimensions differ from the declared output unit; no scaling is inferred', path, parsed)
        deps[name], trees[name] = refs, parsed
    order, visiting, visited = [], set(), set()
    def visit(name):
        if name in visiting:
            _fail('DEPENDENCY_CYCLE', 'Dependency cycle contains ' + name, f'variables.{indices[name]}.expression')
        if name in visited:
            return
        visiting.add(name)
        for ref in deps[name]:
            if ref in deps:
                visit(ref)
        visiting.remove(name); visited.add(name); order.append(name)
    for name in deps:
        visit(name)
    return order, trees


def value_key(values):
    """Exact JSON-typed assignments; no categorical-distance interpretation."""
    return canonical_hash(values)


def _seal(body):
    return {**body, 'sha256': canonical_hash(body)}


def _verify_seal(packet, schema, path):
    if not isinstance(packet, dict) or packet.get('schema') != schema:
        _fail('MISSING_RETAINED_ASSIGNMENT', 'A typed result needs its original frozen assignment', path)
    body = {k: v for k, v in packet.items() if k != 'sha256'}
    if packet.get('sha256') != canonical_hash(body):
        _fail('RETAINED_HASH', 'Retained variable/assignment identity changed', path)


class VariableDomains:
    """One small immutable-by-copy domain boundary, not an optimizer or store."""
    def __init__(self, variables):
        self.declarations = deepcopy(variables)
        self.variables = normalize(variables)
        self.by_id = {v['id']: v for v in self.variables}
        self.free = [v for v in self.variables if mode(v) == 'free']
        self.order, self._trees = _dependencies(self.variables)
        self.typed = typed(self.variables)
        self.snapshot = _seal({'schema': DOMAIN_SCHEMA, 'declarations': deepcopy(self.declarations),
            'variables': deepcopy(self.variables), 'free_order': [v['id'] for v in self.free],
            'dependent_order': self.order[:], 'unit_policy': 'SI dimensions; no inferred conversion'})

    def encoded(self):
        result = []
        for v in self.free:
            k = kind(v)
            if k in ('discrete', 'categorical'):
                low, high = 0, len(v['values'] if k == 'discrete' else v['choices'])-1
            elif k == 'integer':
                low, high = math.ceil(v['lower']), math.floor(v['upper'])
            else:
                low, high = (math.log(v['lower']), math.log(v['upper'])) if v['transform'] == 'log' else (v['lower'], v['upper'])
            result.append({'parameter_id': v['id'], 'target': 'numerical',
                'kind': 'continuous' if k == 'continuous' else 'integer', 'mode': 'free',
                'lower_bound': low, 'upper_bound': high})
        return result

    def free_values(self, values, *, path='candidate.values'):
        if not isinstance(values, dict):
            _fail('CANDIDATE_VALUES', 'Candidate values must be a mapping', path)
        extras = set(values)-{v['id'] for v in self.free}
        if any(name in self.by_id and mode(self.by_id[name]) == 'dependent' for name in extras):
            _fail('DEPENDENT_OVERRIDE', 'Candidate cannot override dependent expressions', path)
        if set(values) != {v['id'] for v in self.free}:
            _fail('FREE_ASSIGNMENTS', 'Every candidate must contain exactly the declared free variables', path)
        return {v['id']: check_value(v, values[v['id']], path=path+'.'+v['id']) for v in self.free}

    def encode(self, values=None):
        physical = self.free_values(values if values is not None else {v['id']: v['value'] for v in self.free})
        result = {}
        for v in self.free:
            name, k = v['id'], kind(v); value = physical[name]
            if k == 'categorical':
                result[name] = [c['value'] for c in v['choices']].index(value)
            elif k == 'discrete':
                result[name] = v['values'].index(value)
            else:
                result[name] = math.log(value) if v['transform'] == 'log' else value
        return result

    def decode_free(self, encoded):
        if not isinstance(encoded, dict) or set(encoded) != {v['id'] for v in self.free}:
            _fail('ENCODED_ASSIGNMENTS', 'Encoded coordinates must match free variable IDs', 'encoded')
        result = {}
        for v in self.free:
            name, k = v['id'], kind(v); value = encoded[name]
            if k == 'continuous':
                value = _plain_number(value, 'encoded.'+name)
                try:
                    if v['transform'] == 'log':
                        # Exact boundary inverses, not a tolerance or clipping:
                        # exp(log(bound)) need not round back to the same float.
                        endpoints = {math.log(v['lower']): v['lower'], math.log(v['upper']): v['upper']}
                        value = endpoints[value] if value in endpoints else math.exp(value)
                    else:
                        value = float(value)
                except OverflowError as exc:
                    raise DomainError('NONFINITE_NUMBER', 'Log coordinate overflow', path='encoded.'+name) from exc
                # No clipping/rounding of already proposed physical values.
            else:
                value = _integer(value, 'encoded.'+name, encoded=True)
                if k in ('categorical', 'discrete'):
                    choices = [c['value'] for c in v['choices']] if k == 'categorical' else v['values']
                    if not 0 <= value < len(choices):
                        _fail('CHOICE_INDEX', 'Sampler coordinate is outside its finite set', 'encoded.'+name)
                    value = choices[value]
            result[name] = check_value(v, value)
        return result

    def sample_free(self, cube):
        """LHS unit-cube inverse CDF: finite bins are uniform, with replacement.

        This is the public qmc integer sampler's floor(n*u) bin convention,
        applied per finite axis alongside continuous axes from the SAME LHS.
        """
        result = []
        for row in cube:
            if len(row) != len(self.free):
                _fail('SAMPLER_DIMENSION', 'Unit-cube dimension differs from free variables', 'sampling')
            values = {}
            for v, u in zip(self.free, row):
                u = float(u)
                if not 0 <= u < 1:
                    _fail('SAMPLER_RANGE', 'LHS coordinates must be in [0,1)', 'sampling')
                k = kind(v)
                if k == 'integer':
                    low, high = math.ceil(v['lower']), math.floor(v['upper'])
                    value = low + min(high-low, math.floor(u*(high-low+1)))
                elif k in ('discrete', 'categorical'):
                    choices = v['values'] if k == 'discrete' else [c['value'] for c in v['choices']]
                    value = choices[min(len(choices)-1, math.floor(u*len(choices)))]
                elif v['transform'] == 'log':
                    value = math.exp(math.log(v['lower']) + u*(math.log(v['upper'])-math.log(v['lower'])))
                else:
                    value = v['lower'] + u*(v['upper']-v['lower'])
                values[v['id']] = check_value(v, value)
            result.append(values)
        return result

    def resolve(self, free_values, *, tolerate=False):
        """Explicit new candidate resolution. State is fresh for EVERY candidate."""
        free = self.free_values(free_values)
        values = deepcopy(free)
        values.update({v['id']: deepcopy(v['value']) for v in self.variables if mode(v) == 'fixed'})
        error = None
        for name in self.order:
            variable = self.by_id[name]
            path = f"variables.{self.variables.index(variable)}.expression"
            try:
                try:
                    calculated = expression.evaluate(self._trees[name], values)
                except ZeroDivisionError as exc:
                    raise DomainError('DIVISION_BY_ZERO', 'Dependent expression divides by zero', path=path, node=self._trees[name]) from exc
                except (ArithmeticError, ValueError, TypeError) as exc:
                    raise DomainError('DEPENDENT_ARITHMETIC', str(exc), path=path, node=self._trees[name]) from exc
                values[name] = check_value(variable, calculated, path=path, calculated=True)
            except DomainError as exc:
                if not tolerate:
                    raise
                error = exc.diagnostic(); break
        return {'free_values': free, 'values': values, 'error': error}

    def decode(self, encoded):
        return self.resolve(self.decode_free(encoded))['values']

    def assignment(self, identifier, resolution):
        values = resolution['values']
        return _seal({'schema': ASSIGNMENT_SCHEMA, 'domain_sha256': self.snapshot['sha256'],
            'candidate_id': identifier, 'free_values': deepcopy(resolution['free_values']),
            'values': deepcopy(values), 'choice_ids': {v['id']: next(c['id'] for c in v['choices'] if c['value'] == values[v['id']])
                for v in self.variables if kind(v) == 'categorical' and v['id'] in values},
            'status': 'REJECTED' if resolution['error'] else 'RESOLVED',
            'error': deepcopy(resolution['error'])})

    def attach(self, row, resolution):
        if self.typed:
            row['domain_assignment'] = self.assignment(row['candidate_id'], resolution)
        return row

    def candidates(self, candidates):
        rows, names = [], set()
        for i, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                _fail('CANDIDATE_VALUES', 'Each candidate is a mapping', f'candidates.{i}')
            values = candidate.get('values', candidate)
            identifier = candidate.get('candidate_id', f'C{i:06d}') if 'values' in candidate else f'C{i:06d}'
            if not isinstance(identifier, str) or not identifier or identifier in names:
                _fail('CANDIDATE_ID', 'Candidate IDs must be nonempty and distinct', f'candidates.{i}')
            names.add(identifier)
            resolution = self.resolve(values, tolerate=True)
            row = {'candidate_id': identifier, 'values': resolution['values']}
            if resolution['error']:
                row['domain_error'] = resolution['error']
            self.attach(row, resolution)
            rows.append(row)
        if not rows:
            _fail('CANDIDATE_COUNT', 'At least one candidate is required', 'candidates')
        return rows

    def coverage(self, rows):
        size = 1
        for v in self.free:
            k = kind(v)
            if k == 'continuous':
                size = None; break
            size *= (math.floor(v['upper'])-math.ceil(v['lower'])+1 if k == 'integer'
                     else len(v['values'] if k == 'discrete' else v['choices']))
        keys = {value_key({v['id']: r['values'][v['id']] for v in self.free}) for r in rows}
        return {'requested_rows': len(rows), 'unique_free_assignments': len(keys),
                'repeat_rows': len(rows)-len(keys), 'finite_cartesian_size': size,
                'finite_cartesian_covered': size is not None and len(keys) == size,
                'cardinality_scope': 'free-variable Cartesian product before dependent/domain rejection'}


def verify_retained(snapshot, variables, row):
    """Check frozen identity/membership without executing a dependency.

    This is integrity checking of retained input, NOT a fresh numerical proof of
    a dependent expression. Owner result/input hashes are still authoritative.
    """
    _verify_seal(snapshot, DOMAIN_SCHEMA, 'domain_input')
    if normalize(snapshot['declarations']) != snapshot['variables'] or normalize(variables) != snapshot['variables']:
        _fail('DOMAIN_DECLARATION_CHANGED', 'Retained domains differ from the submitted declaration', 'domain_input.variables')
    checked = VariableDomains(snapshot['declarations'])
    if checked.snapshot != snapshot:
        _fail('DOMAIN_DECLARATION_CHANGED', 'Frozen declaration order or unit semantics changed', 'domain_input')
    packet = row.get('domain_assignment')
    _verify_seal(packet, ASSIGNMENT_SCHEMA, 'domain_assignment')
    if packet['domain_sha256'] != snapshot['sha256'] or packet['candidate_id'] != row.get('candidate_id'):
        _fail('ASSIGNMENT_IDENTITY', 'Assignment belongs to another declaration or candidate', 'domain_assignment')
    if canonical_hash(packet['values']) != canonical_hash(row.get('values')):
        _fail('ASSIGNMENT_VALUES', 'Candidate values differ from the frozen resolved assignment', 'values')
    vs = snapshot['variables']; by_id = {v['id']: v for v in vs}
    if set(packet['values']) - set(by_id):
        _fail('ASSIGNMENT_VALUES', 'Unknown resolved variable', 'values')
    expected_free = {v['id'] for v in vs if mode(v) == 'free'}
    if set(packet['free_values']) != expected_free or not expected_free <= set(packet['values']):
        _fail('FREE_ASSIGNMENTS', 'Frozen free values differ from declared free IDs', 'domain_assignment.free_values')
    for name, value in packet['values'].items():
        actual = check_value(by_id[name], value)
        if type(actual) is not type(value) or actual != value:
            _fail('ASSIGNMENT_TYPE', 'Retained physical value type changed', 'values.'+name)
        if name in expected_free and canonical_hash(value) != canonical_hash(packet['free_values'][name]):
            _fail('ASSIGNMENT_VALUES', 'Frozen free and full values differ', 'values.'+name)
        if mode(by_id[name]) == 'fixed' and canonical_hash(value) != canonical_hash(by_id[name]['value']):
            _fail('FIXED_OVERRIDE', 'Frozen fixed assignment differs from its declaration', 'values.'+name)
    expected_choices = {v['id']: next(c['id'] for c in v['choices'] if c['value'] == packet['values'][v['id']])
                        for v in vs if kind(v) == 'categorical' and v['id'] in packet['values']}
    if packet.get('choice_ids') != expected_choices:
        _fail('CHOICE_IDENTITY', 'Retained category identity/value pair changed', 'domain_assignment.choice_ids')
    if packet['status'] == 'RESOLVED':
        if set(packet['values']) != set(by_id) or packet.get('error') is not None:
            _fail('RESOLVED_ASSIGNMENTS', 'Resolved candidates require every assignment', 'domain_assignment')
    elif packet['status'] != 'REJECTED' or not isinstance(packet.get('error'), dict) or row.get('execution_status') == 'SUCCEEDED':
        _fail('ASSIGNMENT_STATUS', 'Unresolved inputs cannot be reported as evaluated success', 'domain_assignment')
    return deepcopy(packet['values'])


def reidentify_assignment(row, identifier):
    """Preserve values when the existing epsilon engine namespaces child IDs."""
    row['candidate_id'] = identifier
    if 'domain_assignment' in row:
        packet = {k: deepcopy(v) for k, v in row['domain_assignment'].items() if k != 'sha256'}
        packet['candidate_id'] = identifier
        row['domain_assignment'] = _seal(packet)


def capability(method, variables):
    vs = normalize(variables)
    is_typed = typed(vs)
    supported = method in {'doe', 'optimize', 'epsilon', 'batch_export', 'batch_import', 'analyze', 'statistics', 'pareto', 'read'} or not is_typed
    if method in {'sample_sensitivity', 'sensitivity'} and any(v['transform'] != 'linear' for v in vs):
        supported = False
    return {'method': method, 'available': supported,
            'reason': None if supported else 'This method requires independent continuous variables; mixed/fixed/dependent inputs remain available for DOE and DE.',
            'variable_kinds': [kind(v) for v in vs], 'variable_modes': [mode(v) for v in vs]}


def require_capability(method, variables):
    result = capability(method, variables)
    if not result['available']:
        raise CapabilityUnavailable(method + ': ' + result['reason'])
    return result


def variable_schema():
    """Closed field schema for the existing Plan/GUI; semantic errors use normalize."""
    string = {'type': 'string', 'minLength': 1, 'maxLength': 128}
    number = {'type': 'number'}
    return {'type': 'object', 'additionalProperties': False, 'required': ['id', 'unit'],
        'properties': {'id': string, 'unit': string, 'kind': {'enum': list(KINDS)},
            'mode': {'enum': list(MODES)}, 'lower': number, 'upper': number,
            'value': {'type': ['number', 'string']}, 'transform': {'enum': ['linear', 'log']},
            'values': {'type': 'array', 'items': number, 'minItems': 1, 'maxItems': MAX_CHOICES},
            'choices': {'type': 'array', 'minItems': 1, 'maxItems': MAX_CHOICES, 'items': {
                'type': 'object', 'additionalProperties': False, 'required': ['id', 'label', 'value'],
                'properties': {'id': string, 'label': string, 'value': string}}},
            'expression': {'type': 'string', 'minLength': 1, 'maxLength': 2048}}}


def rejected_evaluation(error):
    return {'execution_status': 'REJECTED', 'responses': {}, 'checks': [],
            'diagnostics': {'failure_reason': error['message'], 'domain_error': deepcopy(error),
                            'model_dispatched': False}}


def annotate_result(result, domains):
    if domains.typed:
        result['domain_input'] = deepcopy(domains.snapshot)
        result['domain_accounting'] = domains.coverage(result.get('candidates', []))
        result['domain_accounting']['dependency_rejections'] = sum(
            row.get('domain_assignment', {}).get('status') == 'REJECTED' for row in result.get('candidates', []))
        result['domain_accounting']['model_calls'] = result.get('timing', {}).get('model_calls')
    return result


def validate_retained_table(table):
    variables = normalize(table['variables'])
    rows = table.get('candidates')
    if not isinstance(rows, list):
        _fail('CANDIDATE_TABLE', 'Retained candidates must be a list', 'candidates')
    ids = set()
    for row in rows:
        identifier = row.get('candidate_id') if isinstance(row, dict) else None
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            _fail('CANDIDATE_ID', 'Retained IDs must be distinct', 'candidates')
        ids.add(identifier)
        if typed(variables):
            verify_retained(table.get('domain_input'), variables, row)
        else:
            values = row.get('values')
            if not isinstance(values, dict) or set(values) != {v['id'] for v in variables}:
                _fail('CANDIDATE_VALUES', 'Retained values differ from declarations', 'candidates')
            for v in variables:
                check_value(v, values[v['id']])
    return variables


def retained_candidates(snapshot, variables, candidates):
    """Copy a retained typed table for exchange or an explicitly NEW job.

    The original result owner supplies the capsule. No dependency evaluation,
    sampling, rounding or re-labelling is performed here.
    """
    validate_retained_table({'domain_input': snapshot, 'variables': variables, 'candidates': candidates})
    if not candidates:
        _fail('CANDIDATE_COUNT', 'At least one retained candidate is required', 'candidates')
    result = []
    for row in candidates:
        copied = {k: deepcopy(row[k]) for k in ('candidate_id', 'values', 'domain_assignment')}
        if row['domain_assignment']['status'] == 'REJECTED':
            copied['domain_error'] = deepcopy(row['domain_assignment']['error'])
        result.append(copied)
    return result
