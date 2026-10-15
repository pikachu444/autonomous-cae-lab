"""Small analytic/exhaustive reference. This is not a replacement domain adapter."""
from copy import deepcopy
from itertools import product
from caelab.evaluation import PreparedEvaluation


def variables(*, finite=False):
    return [
        {'id': 'count', 'unit': '1', 'kind': 'integer', 'lower': 1, 'upper': 3, 'value': 1},
        {'id': 'level', 'unit': '1', 'kind': 'discrete', 'values': [1, 3, 4], 'value': 1},
        {'id': 'x', 'unit': '1', 'lower': 0., 'upper': 1., 'value': .25 if finite else .5,
         **({'mode': 'fixed'} if finite else {})},
        {'id': 'branch', 'unit': '1', 'kind': 'categorical', 'choices': [
            {'id': 'left', 'label': 'Left branch', 'value': 'left'},
            {'id': 'right', 'label': 'Right branch', 'value': 'right'}]},
        {'id': 'capacity', 'unit': '1', 'kind': 'integer', 'mode': 'dependent',
         'lower': 1, 'upper': 10, 'expression': 'count * level'}]


def scalar(value):
    return {'kind': 'scalar', 'value': value, 'unit': '1', 'component': 'scalar',
            'location': 'model', 'reduction': 'none'}


def evaluate(values, settings=None):
    assert type(values['count']) is int and type(values['level']) is int
    assert type(values['capacity']) is int
    assert values['branch'] in ('left', 'right')
    assert values['capacity'] == values['count'] * values['level']
    assert values['capacity'] <= 10  # Domain-rejected points must never arrive.
    if values['count'] == 1 and values['branch'] == 'right':
        return {'execution_status': 'FAILED', 'responses': {},
                'diagnostics': {'failure_reason': 'Declared synthetic physical failure', 'actual_values': deepcopy(values)}}
    cost = ((values['count'] - 2)**2 + (values['level'] - 4)**2 + (values['x'] - .25)**2
            + (2 if values['branch'] == 'right' else 0))
    return {'execution_status': 'SUCCEEDED', 'responses': {'cost': scalar(cost),
            'capacity': scalar(values['capacity']), 'coordinate': scalar(values['x'])},
            'diagnostics': {'actual_values': deepcopy(values)}}


class BatchFactory:
    def prepare(self, settings=None, *, runtime=None):
        return PreparedEvaluation(lambda values: evaluate(values, settings), settings or {},
            batch=lambda rows: [evaluate(values, settings) for values in rows])


def exhaustive(*, finite=False):
    return [{'candidate_id': f'C{count}-{level}-{branch}', 'values':
             {'count': count, 'level': level, 'branch': branch, **({} if finite else {'x': .25})}}
            for count, level, branch in product((1, 2, 3), (1, 3, 4), ('left', 'right'))]


OBJECTIVE = {'response': 'cost', 'unit': '1', 'direction': 'minimize'}
CONSTRAINT = {'response': 'capacity', 'unit': '1', 'operator': '<=', 'limit': 8., 'scale': 1.}
# Independent analytic minimum: each squared term is >=0, right adds 2;
# count=2, level=4, left and x=1/4 yields 0 and capacity=8 is feasible.
EXACT_OPTIMUM = {'objective': 0., 'count': 2, 'level': 4, 'branch': 'left', 'x': .25}
