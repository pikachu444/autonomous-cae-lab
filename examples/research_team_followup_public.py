"""Controlled research reply → real Plan/analyze → follow-up draft → Study cold read.

Manufactured source/role response only; actual existing owners, JobManager and
numerical.analyze perform the calculation. No provider, solver or network call.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import time

from caelab.discussion_document import default_draft
from caelab.discussion_research_team import empty_state
from caelab.research_team_followup import (claim_rows, plan_link, proposal_origin,
    result_review_draft, study_proposal)
from caelab.storage import canonical_hash, save_json
from caelab.workbench import Workbench


CONFIG = {'workers': 1, 'runtime': {'external_model': False}, 'experts': [{'id': 'public-role', 'instructions': 'Controlled public fixture only',
                                   'collections': [], 'tools': ['calculations.plan']}]}


def command(wb, document, operation, arguments=None):
    return wb.document_command(document['id'], operation, arguments or {}, session_id=document['session_id'],
                               expected_generation=document['generation'])


def finished(wb, job):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        row = wb.manager.status(job['id'])
        if row['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED'}:
            if row['state'] != 'SUCCEEDED':
                raise ValueError('Public calculation failed: ' + str(row.get('error')))
            return
        time.sleep(.005)
    raise TimeoutError('Bounded public JobManager wait expired')


def run_public(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Use a new public example directory')
    wb = Workbench(output, configuration=CONFIG)
    import caelab.workbench as module
    original_evaluate = module.evaluate
    try:
        manufactured = {'kind': 'manufactured_table', 'execution_status': 'SUCCEEDED',
            'variables': [{'id': 'x', 'unit': '1', 'value': 0, 'lower': 0, 'upper': 10}],
            'candidates': [{'candidate_id': 'C' + str(i), 'values': {'x': i},
                'execution_status': 'SUCCEEDED' if i < 8 else 'FAILED',
                'responses': {'force': {'kind': 'scalar', 'unit': 'N', 'value': 2. * i + 1.,
                    'component': 'scalar', 'location': 'manufactured observation', 'reduction': 'none'}} if i < 8 else {},
                'failure_reason': None if i < 8 else 'Manufactured missing observation'} for i in range(9)]}
        # Control only this source producer; it is explicitly not a material/solver result.
        module.evaluate = lambda *a, **k: deepcopy(manufactured)
        source = wb.document_open(kind='material', title='Public manufactured source (not physics)')
        submitted = command(wb, source, 'material.evaluate')
        finished(wb, submitted['job'])
        module.evaluate = original_evaluate
        source = command(wb, wb.document_read(source['id']), 'document.save')['document']
        source_ref = wb.document_result_reference(source['id'], submitted['job']['id'])
        request = {'purpose': 'Analyze the public manufactured observations', 'operation': 'analyze',
            'inputs': {'result_refs': {'table': source_ref}, 'responses': [
                {'response': 'force', 'unit': 'N', 'reduction': 'none', 'direction': 'minimize'}]},
            'budget': {'evaluations': 1}}
        runtime = wb.assistance().experts
        proposal = runtime.plan(request)
        raw = {'status': 'ANSWERED', 'expert_id': 'public-role', 'answer': 'CONTROLLED: inspect the actual observations.',
            'sources': [], 'assumptions': [], 'tool_events': [], 'proposed_actions': [proposal],
            'research_reply': {'kind': 'hypothesis', 'claims': [{'text': 'The manufactured response may increase with x.',
                'basis': 'hypothesized', 'conditions': ['Manufactured example only'], 'source_refs': [], 'missing_evidence': []}],
                'questions': [], 'revisions': [], 'unknowns': []}}
        original_ask = runtime.ask
        runtime.ask = lambda *a, **k: deepcopy(raw)
        try:
            draft = default_draft(); draft['participants'] = ['public-role']; draft['composer']['text'] = 'Review the public observations'
            discussion = wb.document_open(kind='expert', title='Controlled public research reply', draft=draft)
            asked = command(wb, discussion, 'expert.ask')
            finished(wb, asked['job'])
            discussion = wb.document_read(discussion['id'])
        finally:
            runtime.ask = original_ask
        # Owner provenance is a labelled controlled boundary, not an actual AI research claim.
        owner = wb.discussion_documents
        internal = owner._documents[discussion['id']]
        turn = next(t for t in internal['discussion']['turns'] if t.get('job_id') == asked['job']['id'])
        raw = deepcopy(turn['response'])  # Keep the actual owner-added format/time fields too.
        response_id = 'RpublicControlled'; turn['research_response_id'] = response_id
        team = empty_state()
        from caelab.evaluation import file_hash
        raw_path = owner._folder(internal['id']) / 'research-team' / 'Dpublic' / 'assets' / 'Rpublic.json'
        save_json(raw_path, raw)
        raw_ref = {'path': raw_path.relative_to(owner._folder(internal['id'])).as_posix(), 'sha256': file_hash(raw_path)}
        team['assets']['Rpublic'] = raw_ref
        team['dependencies']['DpublicAuthored'] = {'id': 'DpublicAuthored', 'kind': 'authored',
            'parent_ids': [], 'exact_ref': {'kind': 'authored_question'},
            'content_digest': canonical_hash('CONTROLLED public authored input')}
        team['manifests']['MpublicControlled'] = {'id': 'MpublicControlled', 'coverage': 'COMPLETE_SUPPLIED_INPUT',
                                                'status': 'COMPLETED'}
        team['responses'][response_id] = {'id': response_id, 'task_id': 'Tpublic', 'phase_id': 'Ppublic',
            'dependency_ids': ['DpublicAuthored'], 'input_manifest_ids': ['MpublicControlled'],
            'raw_response_ref': raw_ref,
            'claim_refs': [{'id': 'C' + canonical_hash({'response': response_id, 'index': 0})[:32],
                            'response_id': response_id, 'index': 0}]}
        internal['discussion']['research_team'] = team
        internal['draft']['context']['research_team'] = {'version': 2, 'phase_id': 'Ppublic', 'parent_phase_id': None,
            'objective': 'Review manufactured observations', 'assignments': [{'expert_id': 'public-role',
                'question': 'Review the actual values', 'source_refs': [], 'result_refs': []}]}
        discussion = command(wb, owner.read(discussion['id']), 'document.save')['document']
        origin = proposal_origin(discussion, turn['id'], 0)
        opened = wb.desktop.discussion_plan(discussion['id'], turn['id'], 0, session_id=wb.session_id, command_id='CpublicPlan')
        plan = opened['document']; link = plan_link(origin, plan)
        calculated = command(wb, plan, 'numerical.run')
        finished(wb, calculated['job'])
        plan = command(wb, wb.document_read(plan['id']), 'document.save')['document']
        actual = wb.document_result(plan['id'], calculated['job']['id'])
        assert actual['statistics'][0]['count'] == 8 and actual['statistics'][0]['max'] == 15
        assert {'id': 'C8', 'reason': 'ROW_UNUSABLE'} in actual['exclusions']
        result_ref = wb.document_result_reference(plan['id'], calculated['job']['id'])
        # Statistics are a Numerical owner result, not an invented native field.
        selector = {'metadata_only': True, 'channels': []}
        count = len(wb.manager.list())
        followup = wb.research_team_transfer(discussion['id'], 'result_review', {
            'turn_id': turn['id'], 'proposal_index': 0, 'plan_document_id': plan['id'],
            'job_id': result_ref['job_id'], 'selector': selector, 'actor_ids': ['public-role']},
            session_id=wb.session_id, expected_generation=discussion['generation'], command_id='CpublicReview')
        assert followup['new_ask'] is False and len(wb.manager.list()) == count
        proposal = study_proposal(discussion, [claim_rows(discussion)[0]['id']])
        study = wb.research_team_transfer(discussion['id'], 'study', {'claim_ids': [claim_rows(discussion)[0]['id']]},
            session_id=wb.session_id, expected_generation=discussion['generation'], command_id='CpublicStudy')['document']
        study = command(wb, study, 'document.save')['document']
        assert study['draft']['engineering_release'] == 'NOT_RELEASED'
        # A report-service boundary is controlled here; the existing Report
        # owner, full B sharing gate, immutable capture and retry are real.
        report_body = {'text': 'CONTROLLED report: inspect the actual calculated statistics.',
                       'references': [], 'status': 'INCOMPLETE_CITATIONS'}
        report_path = owner._folder(internal['id']) / 'research-team' / 'Dpublic' / 'assets' / 'Fpublic.json'
        save_json(report_path, report_body)
        report_ref = {'path': report_path.relative_to(owner._folder(internal['id'])).as_posix(), 'sha256': file_hash(report_path)}
        current = owner._documents[discussion['id']]
        current_team = current['discussion']['research_team']
        current_team['assets']['Fpublic'] = report_ref
        current_team['actions']['DpublicReport'] = {'id': 'DpublicReport', 'phase_id': 'Ppublic', 'report': {
            'status': 'APPLIED', 'body_ref': report_ref, 'dependency_ids': ['DpublicAuthored'],
            'input_manifest_ids': ['MpublicControlled']}}
        current['discussion']['turns'].append({'id': 'FDpublicReport', 'research_action_id': 'DpublicReport',
            'response': {'answer': report_body['text'], 'costorm': {'report': report_body}},
            'dependency_ids': ['DpublicAuthored'], 'input_manifest_ids': ['MpublicControlled']})
        owner._persist_draft(current)
        report = wb.research_team_transfer(discussion['id'], 'report', {'action_id': 'DpublicReport'},
            session_id=wb.session_id, expected_generation=discussion['generation'], command_id='CpublicReport')['document']
        assert report['draft']['sections'][0]['text'] == report_body['text']
        assert report['draft']['sections'][0]['asset']['reference']['kind'] == 'expert_turn'
        report = command(wb, report, 'document.save')['document']
        retry = wb.research_team_transfer(discussion['id'], 'report', {'action_id': 'DpublicReport'},
            session_id=wb.session_id, expected_generation=discussion['generation'], command_id='CpublicReport')
        assert retry['document']['id'] == report['id']
        save_json(output / 'followup-draft.json', followup)
        save_json(output / 'study-proposal.json', proposal)
        identity = {'discussion_id': discussion['id'], 'plan_id': plan['id'], 'result_reference': result_ref,
                    'study_id': study['id'], 'study_draft': study['draft'], 'report_id': report['id'],
                    'report_draft': report['draft'], 'source_turn_id': turn['id'], 'job_count': count,
                    'actual_math': 'existing numerical.analyze', 'provider': 'NOT_RUN', 'solver': 'NOT_RUN',
                    'role_reply': 'CONTROLLED_FIXTURE', 'team_authority': 'CONTROLLED_FIXTURE_NOT_A_RUNTIME_ACCEPTANCE'}
    finally:
        module.evaluate = original_evaluate
        assert wb.shutdown()['joined']
    cold = Workbench(output, configuration=CONFIG)
    try:
        reopened = cold.document_read(identity['study_id'])
        assert reopened['draft'] == identity['study_draft']
        assert cold.document_result(identity['plan_id'], identity['result_reference']['job_id'])['statistics'][0]['max'] == 15
        assert cold.document_read(identity['report_id'])['draft'] == identity['report_draft']
        assert len(cold.manager.list()) == identity['job_count']
        identity['cold_read'] = 'PASSED_NO_NEW_JOB'
    finally:
        assert cold.shutdown()['joined']
    save_json(output / 'receipt.json', identity)
    return identity


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_public(args.output), ensure_ascii=False, indent=2))
