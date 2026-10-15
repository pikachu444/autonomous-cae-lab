"""Real root _Budget + trusted allocations; no provider or solver calls."""
from copy import deepcopy
import time
import pytest
from caelab.assist.experts import _Budget, RuntimeConfig
from caelab.assist.research_team import (BudgetSlice, bind_allocation, plan_action,
    TeamWaiting, service_slice)


def tasks():
    initial = [{'id': 'T'+str(i), 'actor_id': 'r'+str(i), 'kind': 'INITIAL_RESEARCH',
        'status': 'PENDING', 'priority': i, 'depends_on': []} for i in range(3)]
    return initial + [{'id': 'Tq', 'actor_id': 'r2', 'kind': 'QUESTION', 'priority': 100,
        'status': 'PENDING', 'depends_on': [r['id'] for r in initial]},
        {'id': 'Ta', 'actor_id': 'r0', 'kind': 'ANSWER', 'priority': 101,
         'status': 'PENDING', 'depends_on': ['Tq']}]


def allocated(rows, limit=4, checkpoint=None):
    root = _Budget(RuntimeConfig(max_model_calls=8), {'model_calls': limit, 'tool_calls': 8, 'seconds': 120})
    events = []
    plan = plan_action({'turn_limit': 8}, rows, limits={'action_id': 'Dtest',
        'model_calls': limit, 'tool_calls': 8, 'deadline': root.deadline}, pending=[])
    bind_allocation(root, plan, checkpoint=checkpoint or (lambda *args: events.append(args)), control_status=lambda: {})
    return root, plan, events


@pytest.mark.parametrize('limit,expected',[(4,['T0','T1']),(8,['T0','T1','T2','Tq'])])
def test_actual_reserve_finite_schedule_keeps_peers_and_default(limit,expected):
    rows=tasks();root,plan,events=allocated(rows,limit)
    assert [ticket['task_id'] for ticket in plan['tickets']]==expected
    used=[]
    for ticket in plan['tickets'][:]:
        budget=BudgetSlice(root,ticket)
        used.append(budget.reserve_provider_steps())
        for _ in range(ticket['tool_calls']):budget.consume('tool')
        with pytest.raises(TeamWaiting):budget.reserve_provider_steps()
        ticket['status']='FINISHED';budget.active=False
    assert used==([2,2] if limit==4 else [2,2,2,1])
    assert root.used_models==sum(used) and root.used_tools==(2 if limit==4 else 3)
    assert root.used_model_host_invocations==len(expected) and root._team_observed_hosts==0
    assert len([e for e in events if e[0].startswith('reserve')])==len(expected)


def test_three_explicit_default_actions_complete_without_recalling_finished_roles():
    rows=tasks();trace=[]
    for expected in [('T0','T1'),('T2','Tq'),('Ta',)]:
        root,plan,_=allocated(rows)
        assert tuple(t['task_id'] for t in plan['tickets'])==expected
        for ticket in plan['tickets']:
            budget=BudgetSlice(root,ticket);budget.reserve_provider_steps();trace.append(ticket['task_id'])
            next(row for row in rows if row['id']==ticket['task_id'])['status']='COMPLETED'
    assert trace==['T0','T1','T2','Tq','Ta']


def test_budget_one_defers_evidence_and_allows_explicit_toolfree_framing():
    root,plan,_=allocated(tasks(),1);assert not plan['tickets']
    row={**tasks()[0],'kind':'PROBLEM_DEFINITION'}
    root,plan,_=allocated([row],1);slice_=BudgetSlice(root,plan['tickets'][0])
    assert slice_.reserve_provider_steps()==1 and slice_.tool_calls==0
    with pytest.raises(TeamWaiting):slice_.consume('tool')


def test_repair_cannot_steal_peer_steps_no_refund_and_checkpoint_before_host():
    def failed(*args):raise OSError('CONTROLLED checkpoint publication failure')
    root,plan,_=allocated(tasks(),checkpoint=failed);budget=BudgetSlice(root,plan['tickets'][0])
    with pytest.raises(TeamWaiting):budget.reserve_provider_steps(correction=True)
    assert root.used_models==0
    with pytest.raises(OSError):budget.reserve_provider_steps()
    assert root.used_models==2 and root._team_observed_hosts==0
    with pytest.raises(TeamWaiting):budget.reserve_provider_steps()


def test_deadline_pause_and_foreign_ticket_change_no_counter():
    root,plan,_=allocated(tasks());ticket=plan['tickets'][0]
    with pytest.raises(PermissionError):BudgetSlice(root,deepcopy(ticket))
    budget=BudgetSlice(root,ticket);root.deadline=time.monotonic()+4
    with pytest.raises(TeamWaiting,match='시간'):budget.reserve_provider_steps()
    assert root.used_models==0
    root.deadline=time.monotonic()+120;root._team_control=lambda:{'paused':True}
    with pytest.raises(TeamWaiting):budget.consume('tool')
    assert root.used_tools==0


def test_shared_evaluations_and_explicit_service_reservation():
    root,plan,_=allocated([tasks()[0]])
    role=BudgetSlice(root,plan['tickets'][0]);role.reserve_provider_steps();plan['tickets'][0]['status']='FINISHED'
    service=service_slice(root,plan,'MAP_SERVICE','r0')
    role.used_evaluations=7;assert service.used_evaluations==7
    assert service.reserve_provider_steps(correction=True)==1
    assert service.reserve_provider_steps(correction=True)==1
    with pytest.raises(TeamWaiting):service.reserve_provider_steps(correction=True)
    assert root.used_models==4


def test_legacy_reservation_formula_is_unchanged():
    root=_Budget(RuntimeConfig(max_model_calls=8),{'model_calls':4})
    assert root.reserve_provider_steps()==3
    assert root.reserve_provider_steps(correction=True)==1
