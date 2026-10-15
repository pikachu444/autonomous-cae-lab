"""Small public/synthetic host using the real owner, JobManager and fit engine.

Workbench's full native desktop imports are intentionally not substituted here.
The execute callback is the same narrow original-fit/detail dispatch boundary.
"""
from copy import deepcopy
from pathlib import Path
import time
import uuid

from caelab import numerical
from caelab.evaluation import evaluate
from caelab.jobs import JobManager, TERMINAL
from caelab.numerical_document import NumericalDocuments, request_draft
from caelab.numerical_candidate_detail import (
    COMMAND, OPERATION, plain, freeze_fit_input, read_candidate_detail,
    evaluate_candidate_detail, validate_detail_arguments,
)


def response(values, *, unit='MPa'):
    return dict(kind='series', value=list(values), unit=unit, component='xx',
        location='material_point', reduction='none', measure='first_Piola', frame='reference',
        axes=[dict(name='time', unit='s', values=[0., 1., 2., 3.])])


def synthetic(values, settings):
    """Public algebra fixture, not a substitute FELUPE implementation."""
    x = values['x']
    if x < 0 or settings.get('fail_trial'):
        return dict(execution_status='FAILED', responses={}, diagnostics={
            'failure_reason':'Synthetic declared negative-parameter/trial rejection',
            'input_values':deepcopy(values), 'protocol':deepcopy(settings)})
    prediction = response([settings['factor'] * x * t for t in (0., 1., 2., 3.)])
    return dict(execution_status='SUCCEEDED', responses={'stress':prediction},
                diagnostics={'protocol':deepcopy(settings), 'input_values':deepcopy(values)})


def synthetic_inputs(*, retain=32, holdout=True):
    experiments = []
    for i, factor in enumerate([1., 2., 3.] if holdout else [1., 2.]):
        obs = response([factor * 1.25 * t for t in (0., 1., 2., 3.)])
        # Preserve finite excluded values too: observation mask != fit mask.
        obs.update(source_rows=[i*10 + n for n in (1, 3, 5, 7)],
                   source_column_identity=2, mask=[True, True, False, True])
        experiments.append(dict(id=f'T{i}', role='holdout' if i==2 else 'fit',
            response='stress', observations=obs, weight=2.+i, scale=3.,
            mask=[True, False, True, True], observation_source={'source_sha256':'a'*64},
            settings={'factor':factor,'time':[0.,1.,2.,3.],'time_unit':'s',
                'deformation_gradient': [[[1 + .01*t*factor,0.,0.],[0.,1.,0.],[0.,0.,1.]] for t in range(4)]}))
    return dict(backend='test.candidate-detail.synthetic',
        variables=[dict(id='x',unit='MPa',value=1.,lower=-2.,upper=3.,transform='linear')],
        experiments=experiments, method='de',
        options=dict(seed=7,max_generations=1,population_size=6,
            detail_retention={'candidate_limit':retain,'byte_limit':8*1024*1024 if retain else 0}),
        execution=dict(mode='serial',workers=1,on_failure='continue',max_evaluations=128))


class DetailHost:
    """Real local document/job storage, including cold owner replacement."""
    def __init__(self, root, evaluator=synthetic, *, cold=False):
        self.root = Path(root)
        self.evaluator = evaluator
        self.dispatched = []
        self.manager = JobManager(root, self._execute, workers=1, cpu_budget=2)
        self.owner = NumericalDocuments(root, 'S'+uuid.uuid4().hex, self._submit, self.manager,
            resolve_document=lambda identifier: self.owner.read(identifier),
            resolve_result=lambda identifier, job: self.owner.result(identifier, job),
            prepare_request=lambda request: deepcopy(request['inputs']))

    def _submit(self, operation, arguments, **kwargs):
        if operation == OPERATION:
            validate_detail_arguments(self.owner, arguments)
        return self.manager.submit(operation, arguments, **kwargs)

    def _execute(self, operation, arguments, identifier):
        self.dispatched.append((operation, identifier))
        args = deepcopy(arguments)
        if operation == 'fit':
            backend = args.pop('backend')
            packet = args.pop('fit_inclusion', None)
            snapshot = freeze_fit_input(backend, args, arguments, inclusion_packet=packet)
            result = numerical.fit_model(self.evaluator, **args)
            result['fit_input_snapshot'] = snapshot
            return result
        if operation == OPERATION:
            validate_detail_arguments(self.owner, arguments, allow_active=True)
            args.pop('backend')
            return evaluate_candidate_detail(self.evaluator, **args)
        raise ValueError('Unexpected test operation '+operation)

    def wait(self, job_id):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status = self.manager.status(job_id)
            if status['state'] in TERMINAL:
                return status
            time.sleep(.005)
        raise AssertionError('Nonterminal job: '+repr(status))

    def create_fit(self, inputs=None):
        inputs = deepcopy(inputs if inputs is not None else synthetic_inputs())
        draft = request_draft({'purpose':'Public frozen multi-trial candidate detail test',
            'operation':'fit','inputs':inputs,'budget':{'evaluations':128}})
        document = self.owner.open(title='다중 시험 후보', draft=draft)
        assert document['diagnostics'] == [], document['diagnostics']
        answer = self.command(document['id'], 'numerical.run', {})
        status = self.wait(answer['job']['id'])
        assert status['result_refs'], status
        return document['id'], answer['job']['id']

    def command(self, document_id, operation, arguments, **kwargs):
        document = self.owner.read(document_id)
        return self.owner.command(document_id, operation, arguments,
            session_id=document['session_id'], expected_generation=document['generation'], **kwargs)

    def view(self, document_id, job_id, candidate_id, **kwargs):
        return read_candidate_detail(self.owner, document_id, job_id, candidate_id, **kwargs)

    def detail(self, view, **kwargs):
        args = dict(source=view['source'],candidate_id=view['candidate']['candidate_id'],
                    base_attempt_job_id=view['attempt_job_id'])
        return self.command(view['source']['document_id'], COMMAND, args, **kwargs)

    def close(self):
        result = self.manager.shutdown()
        assert result['joined'], result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def intermediate(host, document_id, job_id, status='SUCCEEDED'):
    result = host.owner.result(document_id, job_id)
    final_id = (result.get('final_candidate_detail') or {}).get('candidate_id')
    return next(r['candidate_id'] for r in result['candidates']
                if r['execution_status']==status and r['candidate_id'] != final_id)
