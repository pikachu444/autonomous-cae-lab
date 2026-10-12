"""Risk-focused neo-Hooke planning lifecycle checks. No Qt, fits or solvers."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from state_model import ConflictError, DraftSession, PendingBufferError, PlanningStore, load_samples, reference


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        (self.folder / 'tensile_A.csv').write_text('time_s,force_N,extension_mm,temperature_C\n1,10,1.25,20\n2,11,-60,20\n3,12,2,20\n', encoding='utf-8')
        (self.folder / 'tensile_B.csv').write_text('extension_um,temperature_K,load_kN,time_ms\n1250,293.15,.01,1000\n2000,293.15,.012,3000\n', encoding='utf-8')
        self.samples, self.raw = load_samples(self.folder)
        imports = {s['source']: s['source_sha256'] for s in self.samples}
        self.store = PlanningStore(self.folder / 'planning.json', imports)
        self.session = DraftSession(self.store)
        self.session.samples = self.samples

    def edit(self, owner, field, text):
        self.session.begin_buffer(owner, field, text)
        self.session.commit_buffer()

    def reopened(self):
        result = DraftSession(PlanningStore(self.store.path))
        result.samples = self.samples
        return result

    def test_initial_story_and_owner_generation_start_current_separation(self):
        self.assertEqual(self.session.saved['Material']['revision'], 17)
        self.assertEqual(self.session.saved['Plan']['revision'], 8)
        self.assertEqual(self.session.draft['Material']['mu_MPa'], .85)
        self.assertEqual(self.session.draft['Material']['lmbda_MPa'], 12)
        self.assertEqual(self.session.inspect_candidate('c009')['mu_MPa'], .401)
        self.assertEqual(self.session.inspect_candidate('c009')['status'], 'FAILED_INCOMPLETE_REQUIRED_RESPONSE')
        self.assertEqual(self.session.inspect_candidate('c009')['detail'], 'PARTIAL_FIXTURE_ONLY')
        self.assertEqual(self.session.inspect_candidate('c009')['train_objective'], 'INVALID')
        self.assertEqual(self.session.inspect_candidate('c021')['mu_MPa'], .878)
        self.assertEqual(self.session.inspect_candidate('c014')['train_objective'], '0.07908 (SIMULATED)')
        self.edit('Plan', 'mu_max_MPa', '1.2')
        self.assertEqual(self.session.generations['Plan'], 22)
        self.assertEqual(self.session.draft['Material']['mu_MPa'], .85)
        self.assertEqual(self.session.draft['Plan']['mu_start_MPa'], .85)
        with self.assertRaises(KeyError):
            self.session.begin_buffer('Material', 'lmbda_MPa', '9')

    def test_buffer_cancel_invalid_owner_draft_save_and_run_gate(self):
        self.session.begin_buffer('Material', 'mu_MPa', '1e')
        self.assertFalse(self.session.dirty('Material'))
        with self.assertRaises(PendingBufferError):
            self.session.save('Material')
        self.session.discard_buffer()
        self.assertEqual(self.session.draft['Material']['mu_MPa'], .85)
        self.edit('Plan', 'mu_start_MPa', '1e')
        self.assertEqual(self.session.draft['Plan']['mu_start_MPa'], '1e')
        self.assertTrue(self.session.diagnostics('Plan'))
        self.assertIn('INVALID_DRAFT', self.session.save('Plan'))
        self.assertEqual(self.reopened().draft['Plan']['mu_start_MPa'], '1e')
        with self.assertRaises(ValueError):
            self.session.simulate_run()
        self.assertEqual(self.store.read()['runs'], [])

    def test_stale_revision_rejects_save_and_retains_local_mu(self):
        self.edit('Material', 'mu_MPa', '.87')
        self.store.inject_external_change()
        with self.assertRaises(ConflictError):
            self.session.save('Material')
        self.assertEqual(self.session.draft['Material']['mu_MPa'], .87)
        self.assertEqual(self.store.read()['domains']['Material']['value']['mu_MPa'], .90)
        self.assertTrue(self.session.dirty('Material'))

    def test_source_refresh_cancel_then_explicit_apply_save_and_frozen_run(self):
        original = copy.deepcopy(self.session.draft['Plan'])
        self.edit('Material', 'mu_MPa', '.90')
        with self.assertRaisesRegex(ConflictError, 'current draft/input hash'):
            self.session.simulate_run()  # saved Material/Plan refs still match r17; current input is dirty .90.
        self.assertEqual(self.store.read()['runs'], [])
        self.session.save('Material')
        self.assertEqual(self.session.draft['Plan'], original)
        with self.assertRaises(ConflictError):
            self.session.simulate_run()
        preview = self.session.preview_source_refresh()
        self.assertEqual(preview['proposed']['source_refs']['Material']['revision'], 18)
        self.session.cancel_source_refresh()
        self.assertEqual(self.session.draft['Plan'], original)
        self.session.preview_source_refresh()
        self.session.apply_source_refresh()
        self.assertEqual(self.session.draft['Plan']['mu_start_MPa'], .9)
        self.assertEqual(self.session.draft['Plan']['mu_max_MPa'], 1.4)
        with self.assertRaises(ValueError):
            self.session.simulate_run()  # Plan draft is not yet saved.
        self.session.save('Plan')
        run = self.session.simulate_run()
        self.assertEqual(run['plan']['source_refs']['Material']['revision'], 18)
        self.assertEqual(run['plan']['mu_start_MPa'], .9)
        self.assertEqual(run['observations']['B']['role'], 'holdout')
        self.assertIn('NOT IMPLEMENTED', run['actual_capability'])
        self.assertEqual(run['status'], 'PROPOSED_FUTURE_SIMULATED_NO_COMPUTATION')
        self.edit('Material', 'mu_MPa', '1.0')
        self.assertEqual(self.store.read()['runs'][0]['plan']['mu_start_MPa'], .9)

    def test_refresh_preview_rejects_changed_source_or_changed_local_plan(self):
        self.session.preview_source_refresh()
        self.store.inject_external_change()
        with self.assertRaises(ConflictError):
            self.session.apply_source_refresh()
        self.assertEqual(self.session.draft['Plan']['source_refs']['Material']['revision'], 17)
        self.session.preview_source_refresh()
        self.edit('Plan', 'mu_max_MPa', '1.2')
        with self.assertRaises(ConflictError):
            self.session.apply_source_refresh()
        self.assertEqual(self.session.draft['Plan']['mu_max_MPa'], 1.2)

    def test_selection_reopen_no_evaluation_and_explicit_sidecar_retains_original_status(self):
        before = copy.deepcopy(self.store.read())
        for candidate_id in ('c017', 'c014', 'c009', 'c021'):
            self.session.inspect_candidate(candidate_id)
            self.reopened().inspect_candidate(candidate_id)
        self.assertEqual(self.store.read(), before)
        with self.assertRaises(ValueError):
            self.session.preview_adoption('c014')
        detail_id = self.session.simulate_detail_evaluation('c014')
        self.assertTrue(detail_id.startswith('SIM-EVAL-'))
        original = self.session.inspect_candidate('c014')
        self.assertEqual(original['detail'], 'NOT_RETAINED')
        self.assertEqual(original['holdout'], 'NOT_EVALUATED')
        self.assertIsNone(original['evaluation_id'])
        retained = self.reopened().store.read()['evaluations'][detail_id]
        self.assertEqual(retained['candidate_id'], 'c014')
        self.assertEqual(retained['frozen_plan']['value']['source_refs']['Material']['revision'], 17)
        proposal = self.session.preview_adoption('c014')
        self.assertEqual(proposal['candidate_id'], 'c014')
        self.session.resolve_adoption('cancel')
        with self.assertRaises(ValueError):
            self.session.simulate_detail_evaluation('c009')
        self.assertEqual(len(self.store.read()['evaluations']), 2)

    def test_adoption_conflict_apply_draft_then_explicit_save_revision19(self):
        self.store.inject_external_change()
        proposal = self.session.preview_adoption('c017')
        mu = proposal['differences'][0]
        self.assertEqual((mu['base'], mu['current'], mu['proposed']), (.85, .90, .862))
        self.assertEqual(proposal['phase'], 'CONFLICT_REVIEW')
        self.assertEqual(self.store.read()['domains']['Material']['value']['mu_MPa'], .90)
        with self.assertRaises(ConflictError):
            self.session.resolve_adoption('apply')
        self.session.resolve_adoption('new_proposal')
        self.assertEqual(self.store.read()['domains']['Material']['revision'], 18)
        before_apply = copy.deepcopy(self.store.read())
        frozen_plan = copy.deepcopy(self.session.draft['Plan'])
        receipt = self.session.resolve_adoption('apply')
        self.assertEqual(self.store.read(), before_apply)
        self.assertEqual(receipt['status'], 'SIMULATED_ACKNOWLEDGED_DIRTY_ADOPTION_DRAFT')
        self.assertNotIn('destination_ref', receipt)
        self.assertEqual(receipt['candidate_base_ref']['revision'], 17)
        self.assertEqual(receipt['current_ref']['revision'], 18)
        self.assertEqual(self.store.read()['domains']['Material']['revision'], 18)
        self.assertEqual(self.store.read()['domains']['Material']['value']['mu_MPa'], .90)
        self.assertEqual(self.store.read()['adoption_receipts'], [])
        self.assertEqual(self.session.saved['Material']['revision'], 18)
        self.assertTrue(self.session.dirty('Material'))
        self.assertEqual(self.session.draft['Material']['mu_MPa'], .862)
        self.assertEqual(self.session.draft['Material']['protocol'], self.store.read()['domains']['Material']['value']['protocol'])
        self.assertEqual(self.session.draft['Plan']['mu_start_MPa'], .85)
        self.assertEqual(self.session.draft['Plan']['source_refs']['Material']['revision'], 17)
        self.assertEqual(self.session.draft['Plan'], frozen_plan)
        self.assertEqual(self.reopened().draft['Material']['mu_MPa'], .90)
        self.assertEqual(self.session.save('Material'), 'saved')
        saved_receipt = self.store.read()['adoption_receipts'][-1]
        self.assertEqual(saved_receipt['destination_ref']['revision'], 19)
        self.assertEqual(saved_receipt['candidate_base_ref']['revision'], 17)
        self.assertEqual(saved_receipt['current_ref']['revision'], 18)
        self.assertFalse(saved_receipt['proposal_modified_before_save'])
        self.assertIsNone(self.session.pending_adoption_receipt)
        self.assertFalse(self.session.dirty('Material'))
        self.assertEqual(self.session.draft['Plan']['source_refs']['Material']['revision'], 17)
        self.assertEqual(self.session.draft['Plan'], frozen_plan)
        self.assertEqual(self.store.read()['domains']['Plan'], before_apply['domains']['Plan'])
        self.assertEqual(self.reopened().draft['Material']['mu_MPa'], .862)

    def test_acknowledged_adoption_recovery_then_stale_save_never_publishes_receipt(self):
        self.store.inject_external_change()
        self.session.preview_adoption('c017')
        self.session.resolve_adoption('new_proposal')
        self.session.resolve_adoption('apply')
        self.session.preserve_recovery()
        self.store.inject_external_change()
        before = copy.deepcopy(self.store.read())
        restored = self.reopened()
        restored.restore_recovery()
        self.assertEqual(restored.saved['Material']['revision'], 18)
        self.assertEqual(restored.draft['Material']['mu_MPa'], .862)
        self.assertIsNotNone(restored.pending_adoption_receipt)
        with self.assertRaises(ConflictError):
            restored.save('Material')
        self.assertEqual(self.store.read(), before)
        self.assertEqual(self.store.read()['adoption_receipts'], [])
        self.assertTrue(restored.dirty('Material'))
        self.assertEqual(restored.draft['Plan']['source_refs']['Material']['revision'], 17)
        restored.reload_domain('Material', discard_confirmed=True)
        self.assertIsNone(restored.pending_adoption_receipt)

    def test_adoption_branch_cancel_and_freshness_no_overwrite(self):
        self.store.inject_external_change()
        before = copy.deepcopy(self.store.read()['domains'])
        self.session.preview_adoption('c017')
        self.session.resolve_adoption('cancel')
        self.assertEqual(self.store.read()['domains'], before)
        self.session.preview_adoption('c017')
        branch = self.session.resolve_adoption('branch')
        self.assertEqual(branch['proposed_value']['mu_MPa'], .862)
        self.assertEqual(self.store.read()['domains'], before)
        self.session.preview_adoption('c017')
        self.session.resolve_adoption('new_proposal')
        self.store.inject_external_change()
        with self.assertRaises(ConflictError):
            self.session.resolve_adoption('apply')
        self.assertEqual(self.store.read()['domains']['Material']['value']['mu_MPa'], .9)

    def test_partial_save_recovery_restores_buffer_drafts_and_bases_without_revision_publish(self):
        self.edit('Material', 'mu_MPa', '.88')
        self.edit('Plan', 'mu_max_MPa', '1.2')
        self.session.begin_buffer('Plan', 'mu_start_MPa', '1e')
        outcome = self.session.save_all(simulate_plan_failure=True)
        self.assertEqual(outcome['Material'], 'saved')
        self.assertIn('failure', outcome['Plan'])
        self.assertEqual(self.store.read()['domains']['Material']['revision'], 18)
        self.assertEqual(self.store.read()['domains']['Plan']['revision'], 8)
        self.store.inject_external_change()  # Another saved revision after partial success.
        before = copy.deepcopy(self.store.read())
        path = self.session.preserve_recovery()
        self.assertEqual(self.store.read(), before)
        capsule = json.loads(path.read_text())
        self.assertIn('NOT_SAVED_REVISION', capsule['kind'])
        reopened = self.reopened()
        self.assertEqual(reopened.draft['Material']['mu_MPa'], .9)
        reopened.restore_recovery()
        self.assertEqual(reopened.buffer['text'], '1e')
        self.assertEqual(reopened.draft['Plan']['mu_max_MPa'], 1.2)
        self.assertEqual(reopened.saved['Material']['revision'], 18)
        self.assertEqual(self.store.read()['domains']['Material']['revision'], 19)
        self.assertEqual(reopened.last_save_outcomes, outcome)
        self.assertEqual(self.store.read(), before)
        reopened.commit_buffer()
        self.assertEqual(reopened.draft['Plan']['mu_start_MPa'], '1e')

    def test_mask_intersection_display_independence_undo_and_reimport_identity_guard(self):
        original = self.session.frozen_mask(self.session.draft['Data'], self.session.draft['Plan'])
        a0, a2 = self.samples[0]['id'], self.samples[2]['id']
        self.assertEqual(original['A']['sample_ids'], [a0, a2])  # negative-stretch row excluded by operation validity.
        saved_input = reference('Data', self.session.saved['Data'])
        data_generation = self.session.generations['Data']
        self.session.toggle_mask(a0, 'View', 'display_hidden')
        self.assertEqual(self.session.generations['Data'], data_generation)
        self.assertFalse(self.session.dirty('Data'))
        self.assertEqual(reference('Data', self.session.saved['Data']), saved_input)
        self.assertEqual(self.session.frozen_mask(self.session.draft['Data'], self.session.draft['Plan']), original)
        self.session.toggle_mask(a0)
        self.assertEqual(self.session.frozen_mask(self.session.draft['Data'], self.session.draft['Plan'])['A']['sample_ids'], [a2])
        self.session.toggle_mask(a2, 'Plan', 'inclusion_excluded')
        with self.assertRaises(ValueError):
            self.session.frozen_mask(self.session.draft['Data'], self.session.draft['Plan'])
        self.assertEqual(self.session.undo_mask('Plan'), 'Plan.inclusion_excluded')
        self.assertEqual(self.session.draft['Data']['quality_excluded'], [a0])
        self.session.save('Data')
        self.assertEqual(self.reopened().draft['Data']['quality_excluded'], [a0])
        source = self.folder / 'tensile_A.csv'
        source.write_text(source.read_text().replace('1,10,1.25,20', '1,10,1.26,20'))
        changed, _ = load_samples(self.folder)
        self.assertNotEqual(changed[0]['id'], a0)
        self.session.samples = changed
        with self.assertRaises(ValueError):
            self.session.frozen_mask(self.session.draft['Data'], self.session.draft['Plan'])

    def test_unit_geometry_mapping_retains_time_raw_values_and_source_hash(self):
        a, b = self.samples[0], self.samples[3]
        for field in ('time_s', 'force_N', 'extension_mm', 'temperature_K', 'e11', 'P11_MPa'):
            self.assertAlmostEqual(a[field], b[field])
        self.assertAlmostEqual(b['extension_mm'], 1.25)
        self.assertAlmostEqual(b['e11'], .025)
        self.assertAlmostEqual(b['axial_stretch'], 1.025)
        self.assertAlmostEqual(b['P11_MPa'], .5)
        self.assertEqual(b['time_s'], 1)
        self.assertEqual(self.raw['B'][0]['extension_um'], '1250')
        self.assertEqual(len(b['source_sha256']), 64)

    def test_focused_owner_undo_interleaved_coefficients_never_pops_other_owner(self):
        self.edit('Material', 'mu_MPa', '.90')
        self.edit('Plan', 'mu_max_MPa', '1.2')
        self.edit('Material', 'mu_MPa', '.95')
        self.edit('Plan', 'mu_min_MPa', '.5')
        plan = copy.deepcopy(self.session.draft['Plan'])
        plan_generation = self.session.generations['Plan']
        self.session.begin_buffer('Plan', 'mu_start_MPa', '1e')
        self.assertEqual(self.session.undo_label('Material'), 'Material.mu_MPa')
        self.assertEqual(self.session.undo('Material'), 'Material.mu_MPa')
        self.assertEqual(self.session.draft['Material']['mu_MPa'], .90)
        self.assertEqual(self.session.draft['Plan'], plan)
        self.assertEqual(self.session.generations['Plan'], plan_generation)
        self.assertEqual(self.session.buffer['text'], '1e')
        self.assertEqual(self.session.undo('Material'), 'Material.mu_MPa')
        self.assertEqual(self.session.draft['Material']['mu_MPa'], .85)
        self.assertEqual(self.session.undo('Material'), 'none')
        self.assertEqual(self.session.undo_label('Plan'), 'Plan.mu_min_MPa')
        self.assertEqual(self.session.undo('Plan'), 'Plan.mu_min_MPa')
        self.assertEqual(self.session.draft['Plan']['mu_min_MPa'], .4)
        self.assertEqual(self.session.draft['Plan']['mu_max_MPa'], 1.2)
        self.assertEqual(self.session.undo('Plan'), 'Plan.mu_max_MPa')
        self.assertEqual(self.session.draft['Plan']['mu_max_MPa'], 1.4)
        self.assertEqual(self.store.read()['domains']['Material']['revision'], 17)

    def test_focused_owner_mask_undo_preserves_other_masks_and_view_history(self):
        a0, a2, b0 = self.samples[0]['id'], self.samples[2]['id'], self.samples[3]['id']
        self.session.toggle_mask(a0, 'Data', 'quality_excluded')
        self.session.toggle_mask(b0, 'Plan', 'inclusion_excluded')
        self.session.toggle_mask(a2, 'Data', 'quality_excluded')
        self.session.toggle_mask(b0, 'View', 'display_hidden')
        self.assertEqual(self.session.undo('Plan'), 'Plan.inclusion_excluded')
        self.assertEqual(self.session.draft['Plan']['inclusion_excluded'], [])
        self.assertEqual(self.session.draft['Data']['quality_excluded'], [a0, a2])
        self.assertEqual(self.session.view_hidden, [b0])
        self.assertEqual(self.session.undo('Data'), 'Data.quality_excluded')
        self.assertEqual(self.session.draft['Data']['quality_excluded'], [a0])
        self.assertEqual(self.session.undo('Data'), 'Data.quality_excluded')
        self.assertEqual(self.session.draft['Data']['quality_excluded'], [])
        self.assertEqual(self.session.undo('Data'), 'none')
        self.assertEqual(self.session.view_hidden, [b0])
        generations = copy.deepcopy(self.session.generations)
        self.assertEqual(self.session.undo('View'), 'View.display_hidden')
        self.assertEqual(self.session.view_hidden, [])
        self.assertEqual(self.session.generations, generations)


if __name__ == '__main__':
    unittest.main(verbosity=2)
