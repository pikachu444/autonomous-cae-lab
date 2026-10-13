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
