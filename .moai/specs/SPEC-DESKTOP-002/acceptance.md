# User outcomes and focused verification

| ID | User outcome | Verification |
|---|---|---|
| AC-D02-01 | Double-click/default start opens the real desktop window, including a runtime that has not installed Qt yet. | Actual Windows startup; default browser dispatch absent; fresh-runtime installer/dispatch spy verifies ResearchUI prerequisites and ordering, with explicit extras preserved in suppression modes. |
| AC-D02-02 | Direct Numerical/Expert/Data/PDE and other supported tools open the selected document, while Runner opens the exact job. | Existing real launcher/desktop dispatch and targeted argument tests; no solver/provider. |
| AC-D02-03 | Another tool shares the same service/store and exact document/result without a duplicate controller. | Service context/dispatch checks and relevant existing navigation tests. |
| AC-D02-04 | NoBrowser starts/verifies the service with no UI; research PrepareOnly also returns the unchanged selected tool/document/job context; InstallOnly installs without starting service or UI. | Positive setup/receipt assertions plus no desktop/browser spawn or recursion; failures remain nonzero/stderr without QMessageBox for headless preparation. |
| AC-D02-05 | Existing live user work survives a source/store/process mismatch. | Preserve existing identity guards; controlled mismatch tests, no unrelated process termination. |
| AC-D02-06 | Unicode/space paths and bad selections are handled clearly. | Real argv routing and failure exit/diagnostics; ordinary file/store contracts retained. |

Qt startup tests use public synthetic records and an isolated local test store.
No unchanged solver benchmark or engineering release is a prerequisite for this
GUI/entry implementation. Native application availability is reported separately.

## Windows execution, 2026-10-13

Actual Pro source: `9d6d7807abd2ba6496b98a9758e6029cd3d48881` on
`codex/desktop-tools-20261013`; Codex integrated the authored commits locally.
The target was a private CPython 3.12.14 runtime with the project's PySide6 6.9.1
and matplotlib 3.10.8, a public test store with Korean/spaced paths, and port 18766.
No solver, provider, device, or engineering campaign ran.

- Python entry-point checks: 24 passed after the complete preparation-flag fix.
  Existing navigation checks: 24 passed at the first source checkpoint; their
  unchanged native/document routing was not repeatedly tested.
- Windows launcher cases: 11 passed at `0e08502`; the remaining module-location
  assertion was corrected to Windows PowerShell's actual manifest/script fields
  and passed. The new actual-installer native-argv regression also passed. These
  are focused runs across the stated checkpoints, not one whole final-suite run.
- The actual default CMD path under Windows PowerShell 5.1 opened a native
  `Runner — existing executions` window. A direct `-Tool data -DocumentId ...`
  opened `Data — 독립 자료` for the existing saved public document; the same
  service PID 17720 was retained. Window handles and exact process arguments
  were verified. The initial damaged readiness invocation is retained as a
  failed observation; Pro's corrected quoting was then tested on the same path.
- Root/research PrepareOnly returned the same service and exact selected Data
  ID without UI. A real source-mismatch request returned nonzero while its old
  owned test server remained alive; only that test server was subsequently
  explicitly stopped after process/listener ownership checks.
- All nine tool/typed-ID routes, one bootstrap/dispatch, fresh Qt install request,
  suppression-mode positive setup, no recursion, conflict refusal, Unicode paths,
  child exit codes, CMD stdin-open failures and caller-environment restoration
  were checked with the actual scripts and isolated service/installer/UI doubles.
  Installer readiness's actual source/function was also executed through WinPS
  5.1 and native Python, with fixture imports and exact `sys.orig_argv` comparison.
- Astra/xhigh independently reviewed the authored source and corrections;
  no source/contract findings remain in this unit. Pro's disconnected remote
  runtime remains NOT_RUN; Windows execution belongs to Codex.

Local raw checks and Qt renders are under ignored
`runs/product-development/20261013/`. Native window creation and Qt offscreen
rendering do not claim OS interaction/DPI, whole-product usability, actual
FreeCAD/ParaView operation, numerical qualification, or engineering release.
