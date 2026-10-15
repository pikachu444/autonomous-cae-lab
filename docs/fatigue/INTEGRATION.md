# Integration / ownership

Current integration note (Sol,2026-10-16): the recovered Pro payload was applied
as21 new paths and bounded hunks to `fatigue.py`, `fatigue_editor.py` and the
current `simulation_window.py`. The later impact result-read guards were kept.
Root applied the one-line `simulation_document.py` description separately.
Windows execution/Qt evidence and the GUI-only corrections are recorded at the
end of `DELIVERY_KO.md`; the original Pro baseline/evidence below is preserved.

Baseline: ce9ec3aefc6b7bc759b7b6bda23177595dbd3cd1.
Fixture pin: 3e48bf6138f495299f45b1af254bfb4aaff307b8.
Provided ZIP: 4,707,584 bytes, SHA256 e1d174da516110a965ba2607076bcc9a2a789d2e7e8879b1d87de85919dbb9a0.
All 716 supplied raw file bytes/SHA256/Git blob identities were checked before editing. WIP overlay: 0.

## Patch boundaries

`product.patch` contains new dedicated core, dialog/results viewer, tests, examples and documentation,
plus the owned `caelab/fatigue.py` compatibility dispatch. Full dedicated source files accompany it.
The legacy settings/result branch and vendored counter remain unchanged. Dispatch is conditional on the
explicit new `method` field; old saved results are not migrated or retroactively recomputed.

`integration.patch` contains only the `damage.rainflow` description in `caelab/simulation_document.py`.
The existing `research_execution.run_domain` already resolves this backend and requires no change.
No inherited owner, registry, schema file, general reader, Workbench, HTTP client/service, save protocol or
scheduler is changed. No new constitutive/FE/impact solver or server is introduced.

`gui-integration.patch` contains only the existing editor/result route and current-document guard in
`apps/research/fatigue_editor.py`, and the one backend caption/description in
`apps/research/simulation_window.py`. The old S–N editor and old S–N cycle viewer remain in place.
The advanced viewer returns a local checked selection to the existing host; subsequent update/save use
its normal CAS, generations, retention and recovery. Selection never calls evaluation.

Shared files are **not** copied in `source/`. Root/Sol apply the hunks to the then-current main.
In particular, f2b4a5c25f3260c7f76d62eea8ea2ce1e836c38c Data/Runner GUI and later parallel
Contact/S2/B13/C3B/finite-measure/Impact A/B changes were not overlaid or rewritten.
No change to `data_window.py`, `runner_window.py`, `impact_editor.py`, shared response pickers, or native runtimes.

From the target repository root, with a clean reviewable working tree:

    git apply --check /path/to/delivery/product.patch
    git apply --check /path/to/delivery/integration.patch
    git apply --check /path/to/delivery/gui-integration.patch
    git apply /path/to/delivery/product.patch
    git apply /path/to/delivery/integration.patch
    git apply /path/to/delivery/gui-integration.patch

The exact frozen baseline is used for the delivered apply check. A conflict on a newer main is not
permission to replace shared whole files. Transfer the bounded hunks after reviewing current changes.
`BASE_AND_FILES.json` lists owner, before/after SHA256 and size for every changed/new file.
`verification/PATCH_APPLY_CHECK.json` records application to a separate original baseline copy.

## Existing public integration points

`fatigue.validate_settings`, `fatigue.resolved_adapter`, `fatigue.analyze` keep their old signatures.
For advanced settings they delegate to `fatigue_strain`. `FatigueAdapter.run` remains the adapter used
by the existing backend/evaluator. New files are found by existing setuptools package globs; pyproject
and dependency pins do not change.

`fatigue_tensor.read_bundle(provider, source, method=..., mean_stress=...)` accepts the existing Workbench
or Client read API, uses `_resolve` before/after selected reads, and never accepts draft `resolved_response`.
`fatigue_strain.select_result` checks retained plane/cycle/row membership and returns a small selection
bound to the existing job and canonical result hash. It is a pure read operation, not another owner.

The dedicated GUI edits a detached draft. Its explicit synthetic example calls existing Data import/save
and does not run fatigue. The main host still performs explicit Simulation run and Save. Existing local
HTTP transport is reused for GUI; the CLI example uses Workbench directly and starts no HTTP server.

## Review ownership and acceptance

This archive is authored source and executed Linux evidence, not a remote commit or an independent review.
Astra's mathematical/source review and root/Sol's actual Windows Qt acceptance remain pending.
No assertion that another named reviewer ran tests is made. The existing native check/process ownership
policy remains applicable; no installation or paid call is needed for this implementation.
