# Implementation plan

1. Inspect existing analysis.py, workspace.py, external.py, measurements.py and
   post_window.py. Retain existing scalar comparison and native resampling rather
   than building a parallel engine. Use the FN-28 original definition and WELSIM
   interaction findings in docs/PREPOST_REUSE.md as input.
2. Actual Pro designs and implements the conversion chain, comparison controls,
   native execution, persistence and associated tests/examples/usage documentation.
   Select sources and quantities first; show conversion choices when needed, with
   an actual A/B/converted/difference table or view. Avoid a wall of metadata fields.
3. Astra independently reviews physical meaning, interpolation support and user
   recovery. Codex integrates and performs only changed-path basic/unit checks and
   a small native post example using public or manufactured fields, no solver run.
4. Publish the verified implementation and update CURRENT_STATE, MoAI and usage links.

Pro owns analysis/workspace/external/measurement and Qt comparison changes, tests
and its feature usage document. Sol separately owns native_controls.py for File→Exit;
coordinate bridge.py before touching it. Codex owns common integration and current
state. No concurrent shared-file changes. No extra provider/subscription charges.

An independent review may refine implementation choices without shrinking FN-28.
No full historical benchmark or unchanged solver campaign is required for this work.
