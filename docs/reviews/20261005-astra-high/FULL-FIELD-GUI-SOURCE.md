# Independent frozen full-U GUI source review

Verdict: **BOUNDED_SOURCE_REVIEW_PASS — 0 open P1, 0 open P2**.

The seven frozen GUI source/test files are suitable for Root's exact-byte integration and subsequent actual same-record browser gate. This verdict covers source inspection and read-only input-identity/display calculations. It does not qualify unseen pixels, browser performance, a new native run, selected Research, S3 recovery, U1, all 52 requirements, or engineering release.

## Scope and identity

Reviewer: independent Astra/high. Root owns design, shared interfaces, integration, Git and final acceptance. Research remains the approved `openai-codex/gpt-5.6-sol` / ChatGPT route; this review changes no model, authentication or runtime configuration.

Reviewed packet: `artifacts/development-cae-usability-audit-20261005-01/fixture-full-field-gui-source-01/`. Frozen source baseline is `ce120378ee8da570a779f985cfc745bf0340c6ce`, with candidate changes in exactly seven files. The working candidate is not described as already committed in that baseline. The separate Main metadata and selected Research profile/guard/schema8 work are outside this review.

- FREEZE SHA-256: `23c1bf8d210355fd1ec8b34c7f0f35160f167499bcde3d3975d396a95d719c1c`.
- MANIFEST SHA-256: `781f810d0d2a77f97f5df3b8944c85668651b14c98aea188ade8f6879e4d3d42`.
- Source RECEIPT SHA-256: `54afccaa272173266b14712b0025a1a32c66cfcfc8096b5138d624312616f7d8`.
- Reused independent native-review receipt: `bc9bd7039a2a460acf3d35fc692339e8a6a56ee738215e091bf5e80f729ce7bc`.
- Reused authoritative native MANIFEST-FINAL-02: `dc9053ba241853ecd6f2f5ddade8c36ef20c6248a1d1741be481bf065843d047`.

All 41 source-manifest entries and the seven corresponding writer-worktree files match their declared bytes/hashes. Frozen and writer-source identities are independently checked. `INPUT-PINS-BEFORE.json` and `INPUT-PINS-AFTER.json` record 62 protected inputs, including packet pins, selected field/result/proposal/thread, parent result and all five native sources. All 62 are unchanged across the recorded review interval. Before-pin capture follows initial read-only source orientation; it is not claimed to precede the first file read.

Recovery used AGENTS, the continuing R01–R52 ledger, current HANDOFF/CURRENT_STATE headers and relevant historical context, ARCHITECTURE, all ADR decision sections through ADR0036, OpenScience contract, the current CAE execution plan and applicable acceptance evidence. Large historical bulk output was truncated; targeted ledger/decision/current-state reads recovered the relevant scope. No unavailable chat or old cloud process is assumed available. The original assembly and broader Phase1–7 remain separate unfinished work. ADR0035/user steering means purpose-specific checks and optional justified sensitivity, with no mandatory whole-model sweep added by this GUI.

Per delegated restrictions, there were no Git calls or fresh CI/network queries. Saved worktree status/head/upstream records identify baseline ce12037 and fixture pin `3e48bf6138f495299f45b1af254bfb4aaff307b8`. The exact ce source CI record is run37281737051, not a new GUI-candidate CI pass; retained documentation reports 7 SUCCESS / 3 FAIL. Root must bind later integration/CI to the actual integrated source. This review does not infer whole CI success.

## Findings and inspected boundaries

No concrete P1/P2 source defect was identified within this frozen unit.

1. **Record admission and raw identity.** `fixture-field-controls.js:33–75` requires VERIFIED inspection and joins child, parent, revision, proposal, thread, execution settings and adapter producer. It requires exact manifested `simulation/support_N/fea_field.json` entries and selected/legacy mesh-policy consistency. `:193–202` copies the raw bytes, checks size and SHA-256, uses fatal UTF-8, rejects duplicate decoded JSON keys through `:173–190`, then verifies field structure. Production integration calls this raw loader. `verifyField` is a pure test/source helper; production does not bypass the raw loader through it.

2. **Native field semantics.** `fixture-field-controls.js:85–171` preserves versions5/6 limits, static step1/increment1/load_parameter1, mm/mm/N and SOLVER_GLOBAL_CARTESIAN. It checks ALL_MESH_NODES with finite three-component U and native tokens, safe ascending original IDs, complete C3D10 connectivity, shared midside associations, manifold faces and the complete CPS6 exterior. The five native metadata pins join the same revision/result manifest. The fixed set covers the recorded bottom plane with XYZ dofs; loads retain actual native IDs, direction, force tokens, saddle association and same-mesh DAT provenance. This is a defensive field reader over the separately verified native artifact, not an independent native solver or scientific validator. No CAD tessellation/partial-U substitute is present.

3. **Display and physical values remain distinct.** `fixture-field-controls.js:208–211` and `fixture-field-viewer.js:8–16` calculate positions as x+sU while scalar values remain the original UX/UY/UZ or full-vector magnitude. Factor0–1000 is a UI bound. Four triangles use all six CPS6 nodes. Face colors average the three drawn nodal scalar values and the text explicitly describes that approximation (`viewer:121–122`); no integration-point stress or interpolated missing U is fabricated. Whole-field maximum |U| and the existing loaded-saddle |UZ| metric are separately labeled (`:165–166`).

4. **User-facing evidence limits.** The mounted source exposes mm/N/frame, static step versus physical time, UNKNOWN/NOT_RELEASED and selected-mesh sensitivity unassessed (`viewer:110–113`). Raw probe/table values and force vectors are unscaled. Verification details start closed; five source pins and six download links are inside them. The table constructs at most50 data rows, with paging and exact native-ID search. This is source evidence of those controls, not a claim that their actual browser layout has been seen. Existing parent-CAD caption, result validation names, diagnostic-invalid stress and historical metrics remain in the unchanged result presentation path. No engineering threshold changes appear in the seven-file diff.

5. **Ownership and stale work.** `app.js:946–1003` captures result epoch, store, exact inspection object, connected card/detail and mesh-selection sequence. The guards are checked after fetch/chunk/hash awaits and before mount/success/error updates. Switching mesh destroys the owned old viewer; stale completion cannot replace the latest selection. `app.js:828–840,855–856,1519` invalidates/destroys the fixture view on inspection/render/store transitions, including before the store POST resolves. Viewer draw, component/deformation, search/probe, camera and table callbacks check current ownership/detachment/destruction. Current invalid factors hide the canvas; the frozen stylesheet's existing `[hidden]{display:none!important}` keeps that refusal effective. Source controls include late success and late error, lease/detach/destroy, mesh-switch and store-POST branches.

6. **Resources and rendering limits.** The raw field limit is32MiB; node/C3D10/CPS6 counts are bounded at40,000/25,000/8,000. Streaming reads refuse/cancel overruns and release their reader. These GUI bounds are distinct from native64MiB/source-file limits and from numerical acceptance. The renderer uses a canvas painter with explicit display approximations; this review does not certify image quality, occlusion/probe ergonomics, animation responsiveness or maximum-envelope performance. Historical2mm geometry counts inform the envelope only. No2mm full-U body or7body full-field support was tested or claimed.

## Evidence independently cross-checked

The small standard-library `audit.py` reads files and writes only this private review folder. It imports no product modules and runs no Node/Python product tests. It strictly decodes/parses the actual saved field, verifies input pins against the sealed manifest and cross-checks identities and small display calculations. The already-qualified native parser/whole-raw numerical audit is reused rather than rerun.

Actual data are `runs/fixture-selected-mesh-core-20261005-01`, child `E-selected-solve100`, parent `E-selected-cad32`, revision `676bd750044c0c0a20d33780bae993a384cee99ad93cbf1c50deef19a05f429b`. Both field/result are adapter6, produced by ce12037. Proposal execution equals recorded execution settings. The field is3,962,210bytes, SHA-256 `b32cfaecf38e0040d01c2b4b1843a23f1b0b044c4000040dbc9734e06c95adf7`. The five native raw source bytes match field pins, result manifest and sealed Root manifest.

- Counts:7,715nodes /23,145U components /4,422C3D10 /1,840CPS6 /1,057fixed nodes /123loaded nodes.
- Whole-field maximum |U|:0.006169333909086347mm at native node314.
- Preserved loaded-saddle max absolute UZ:0.00564208mm, a different statistic.
- Probe314: XYZ `[4.15,0,26]`mm; U `[-0.0024955,0.00000969048,-0.00564208]`mm. Its100× display location calculates to `[3.90045,0.000969048,25.435792]`mm.
- Invalid peak stress, invalid/null selected-mesh change ratio, seven blocking UNKNOWNs and NOT_RELEASED remain in the saved result.

The writer's sealed source evidence reports122PASS/0FAIL/0SKIP, comprising75new and47existing controls. Their source and receipt were inspected; this reviewer did not execute them. Tiny inert DOM/canvas controls and one writer filesystem loader/scene check do not constitute real HTTP/Core/browser verification. This review adds an independent filesystem cross-check; it does not revise the writer's separate one-body-read receipt.

Two read-command failures occurred before successful corrected reads: a PowerShell-incompatible brace path caused a parse error without executing the read; a document-summary print encountered console cp949 Unicode encoding and was repeated using explicit UTF-8. Neither changed protected files, product state or evidence. No data or source check failed.

## Next acceptance boundary

Root can integrate these exact frozen bytes and run the actual same-retained-field human GUI gate: inspect the rendered mesh, fixed/load cues, component legend, probe314, display scaling and real late-store success/error behavior with the same child/parent/revision. Check legibility and interaction/performance in the actual target browser; source inspection does not establish them. No new CAD, remesh, native solve, global convergence sweep or provider call is needed for this viewer gate.

This review performs no native/mesh/provider/auth/HTTP/GUI/runtime/Goal/automation/Git action and spawns no agent. It edits no source, test, tracked documentation or historical experiment. Private review artifacts remain local-only. General Research/S3/U1/all52/engineering completion is OPEN; UNKNOWN/NOT_RELEASED and prior canonical thresholds/failures are preserved.
