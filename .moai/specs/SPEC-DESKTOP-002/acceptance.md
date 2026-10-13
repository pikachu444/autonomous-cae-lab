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
