# First product unit and author scope

1. Reuse the existing start-windows service/bootstrap and start_cae_research/desktop
   tool entry. Preserve service-only calls from native Pre/Post launchers.
2. Replace default web startup with real desktop dispatch; keep explicit tool,
   selected document/job and installation flags meaningful. A default Runner
   window is acceptable, without requiring all research to begin there.
   Default/explicit research UI requests enable the existing ResearchUI install
   extra before dispatch, including a fresh runtime. Service/install-only calls
   retain explicitly requested extras instead of enabling UI unconditionally.
   Use one bootstrap before dispatch. NoBrowser still starts/verifies service
   but suppresses all UI; research PrepareOnly returns its original selection
   receipt; InstallOnly suppresses both service and UI. Headless preparation
   failures report on stderr with a nonzero exit, without a Qt message box.
3. Pro writes source and relevant argument/lifecycle tests. Source-first GitHub
   publication remains available when Pro's remote Qt runtime is disconnected.
4. Codex runs targeted Windows checks; Astra independently reviews independent
   use plus the connected system. Correct concrete failures before integration.
5. Update affected usage docs and commit reviewed code. Continue to the next
   Numerical/Expert feature unit using the existing feature/task map.

Reference request: `PRO-IMPL-DESKTOP-20261013-01`. Source inventory is recorded
locally under `runs/product-development/20261013/`. No new queue is created here.

## Native project integration

Use [the corrected Pro design](../../../docs/native-project/DESIGN_KO.md), existing
native owners and the original portable transaction. This is a Plan–Run handoff,
not a second current-status queue. CURRENT_STATE and MoAI card t25 hold execution.

| Bundle | Writer-owned scope | User outcome |
| --- | --- | --- |
| N0 | native_project_contract/inputs, portable_project_native | Exact registration, portable copy, open ticket, first Save and current head |
| N1 | desktop_pre/portable_project, Pre examples/usage | Editable FreeCAD/XLink copy, selection, Undo and Save without original paths |
| N2 | native_post_dependencies, desktop_post portable/restore | Reader/history restoration, partial recovery and resaved analysis copy |
| N3 | native-project-research example/test/usage | Data/Study/Report and selected native evidence survive two copies together |
| N4 | research/native_project_actions and usage | Existing native menus and connected GUI/HTTP/CLI/MCP use the same operations |

The lead applies common Workbench, command, transport, launcher and reference
patches sequentially. Writers coordinate shared contracts directly. Native-only
and mixed copies reuse one writer and verification implementation. Pro owns the
substantial design, Astra the independent design/integration review. User work,
original source/result bytes and historical failures remain preserved. Do not
make unchanged solver campaigns a prerequisite for desktop integration.
