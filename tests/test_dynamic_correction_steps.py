"""Public generator and GUI default semantics through the real compiler.

The fixture is a small frozen model, not a native FreeCAD execution.
"""
from copy import deepcopy
import pytest
from caelab.contact_steps import compile_program
from caelab.contact_deck import render
from caelab.dynamic_model import attach, continuation_step
from examples.dynamic.generate_freecad import CASES, configure_draft
from test_dynamic_support import base_model, draft_for


def example(case):
    model = base_model()
    model['step'].update(initial=1e-5, period=.004, minimum=1e-8,
                         maximum=1e-5, increments=5000)
    if case == 'initial-velocity':
        model['conditions'] = model['conditions'][:1]
        model['loads'] = []
    source = draft_for(model)
    draft = configure_draft(source, case=case,
        initial_target={'body_id':'Solid', 'native_node_ids':[51]})
    return model, source, draft


@pytest.mark.parametrize('case', CASES)
def test_public_generator_uses_compilable_exact_case_definition(case):
    model, source, draft = example(case)
    before = deepcopy(draft)
    steps = compile_program(draft['program'], model['conditions'])
    actual = attach(model, draft)
    deck = render(actual)
    assert draft == before and source == draft_for(model)
    assert deck.count('*DYNAMIC') == 2
    assert '*RESTART,WRITE,FREQUENCY=1' in deck
    if case == 'initial-velocity':
        assert len(steps) == 2 and '*STATIC' not in deck
        assert '*INITIAL CONDITIONS,TYPE=VELOCITY\n4,3,100' in deck
        assert all(not s['loads'] for s in steps)
    else:
        assert len(steps) == 3 and deck.index('*STATIC') < deck.index('*DYNAMIC')
        modes = [s['curves'][0]['mode'] for s in draft['program']['steps']]
        assert modes == ['curve', *(['release']*2 if case.endswith('release') else ['hold']*2)]
        expected = 0. if case.endswith('release') else -5.
        for step in steps[1:]:
            assert list(step['loads'].values()) == [[[0., expected], [.002, expected]]]


def test_old_generator_and_gui_release_to_hold_remains_rejected():
    model, _, draft = example('preload-release')
    draft['program']['steps'][-1]['curves'][0]['mode'] = 'hold'
    with pytest.raises(ValueError, match='해제된 변위/하중'):
        compile_program(draft['program'], model['conditions'])
    with pytest.raises(ValueError, match='해제된 변위/하중'):
        attach(model, draft)


@pytest.mark.parametrize('mode', ['release','hold','curve','INVALID'])
def test_continuation_is_deep_copy_and_does_not_repair_invalid_input(mode):
    _, _, draft = example('preload-release')
    row = draft['program']['steps'][-1]
    row['curves'][0]['mode'] = mode
    row['curves'][0]['points'] = [['0','1e'],['.002','']]
    before = deepcopy(row)
    new = continuation_step(row, identifier='Next', label='다음 단계')
    assert row == before and new['id'] == 'Next' and new['label'] == '다음 단계'
    assert new['curves'][0]['mode'] == ('hold' if mode in ('curve','hold') else mode)
    assert new['curves'][0]['points'] == before['curves'][0]['points']
    new['curves'][0]['points'][0][1] = 'changed'
    assert row == before


def test_displacement_release_stays_free_in_following_dynamic_step():
    model, _, draft = example('preload-release')
    model['conditions'].append({'object_id':'Driven', 'label':'지정 변위',
        'type':'Fem::ConstraintDisplacement', 'body_id':'Solid',
        'components_mm':{'1':.01}, 'boundary_dofs':[{'node_id':4,'component':1,'value_mm':.01}]})
    stages = draft['program']['steps']
    for i, stage in enumerate(stages[:2]):
        stage['curves'].append({'condition_id':'Driven','component':1,'unit':'mm',
            'mode':'curve' if i==0 else 'release', 'points':[[0,0],[1,.01]]})
    stages[2] = continuation_step(stages[1], identifier='Dynamic2')
    compiled = compile_program(draft['program'], model['conditions'])
    assert (4,1) in compiled[0]['boundary']
    assert all((4,1) not in s['boundary'] for s in compiled[1:])
    stages[2]['curves'][-1]['mode'] = 'hold'
    with pytest.raises(ValueError, match='해제된 변위/하중'):
        compile_program(draft['program'], model['conditions'])
