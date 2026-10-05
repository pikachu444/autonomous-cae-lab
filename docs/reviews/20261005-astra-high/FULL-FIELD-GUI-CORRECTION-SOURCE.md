# Current bounded source disposition — Root2026-10-05

The two Astra/high findings below are retained history, not a current overall-system PASS. Review02 additionally identified empty-factor→native-ID/overlay→old100x READY bypass (report SHA dbedcfc88cd4875e19ffbe19fe3797135d22699e83011877d8d1ef15d59203b1; receipt c0022dbc7530da11ff70c3531430d954a9a2be43ad4c43f46ca1044c64d1d105). Its earlier render-failure/layout finding was source-verified corrected.

Root read the exact02→03 delta and adopted final58 impacted controls (55existing+3regressions); prior152 full controls were not rerun. Complete raw display configuration/refusal persists across partial actions; raw U/N/ID queries remain available, and explicit complete valid input restores READY. No limits or scientific arrays/criteria changed. Root checked final frozen2, protectedCSS/4, payload20/371534B and prior seals. No third Astra micro-review was requested: the user clarified that Astra must assess the whole system and Root delivery process. Actual corrected browser/pixel gate remains OPEN.

Current record: `../../../benchmarks/records/20261005-fixture-field-pixel-correction-source-r03.json`. The existing complete-system audit and improvement plan remain separate and assess prototype usability, lifecycle, assembly mechanics and remaining Phase1–7 scope.

---

## Historical independent source review01
# 전체 변위 화면 교정의 독립 source 감수

아래 packet01은 역사이며 SOURCE_CORRECTION_REQUIRED/0P1/1P2입니다. 최초 actual pixel P2와 추가 render-refusal source P2를 구분합니다. Root가 source finding을 채택하여 같은3파일 소유자에게 additive packet02 교정을 맡겼습니다. source135PASS는 실제 픽셀 PASS가 아닙니다.

원문 SHA 7b62a1626f61af2e1e9c79fcf7a8294eced55e92949ed1f9c7aba5442ad887ab; receipt SHA a19d1c5d4345ce5fb6fbe23cf8135537b7e96e59dadfb0c908c63be4520b828b. 공개 사본은 LF만 정리하며 raw private packet은 보존합니다.

---

# Independent pixel-correction source review, packet01

**Verdict: SOURCE_CORRECTION_REQUIRED — 0 P1 / 1 P2 in this correction source.**

The three-file correction implements the intended visibility/picking and explicit X-ray design, but its new render-resource refusal can escape interaction callbacks and leave a blank canvas with stale frame state. Complete that bounded failure-handling correction before source acceptance. The original actual-pixel P2 remains separately OPEN until Root captures the corrected clean-source browser view;135 source passes cannot close it.

## Exact input and review scope

Reviewed private packet: `fixture-full-field-gui-pixel-correction-01`, actual seal filename `FREEZE.json` (the tentative `SOURCE-FREEZE-01.json` name does not exist). Only viewer.js/style.css/test_fixture_field_viewer.js are owned changes. All three current Primary files match frozen3; their before snapshots match the prior source67 bytes. All four unowned GUI/loader/app files match the protected hashes.

- FREEZE SHA-256 `681ced83605bfe251c911395cdd57a192c862af3cbb3a41ec606cb3c316f84a5`.
- MANIFEST SHA-256 `9b8d0b006fb193e4eadbbedce68e417588dda00a935b7dfde7918de926115c0c`.
- RECEIPT SHA-256 `e91a5786a3d3875636af56f44c7ee6b31f54480c343942c810b748506d086ca2`.
- Corrected viewer SHA-256 `b64ad45f5d1914fbbe41a99423febb56da1cceadd6a7199704f0b7eeea9d0d96`.
- Corrected stylesheet SHA-256 `3dd826d1ad3d9f7203a7e9800b95e3208556c473f400e8b7b1cb2df4fc5172af`.
- Corrected viewer-test SHA-256 `f493b04c6f1c10cdd3f2343da2433eaabf8711b8d7d7e19ed6cb1c839b237d81`.

I verified every26manifest entry, current three/protected four source files and prior source/pixel seals, with40protected input files retained unchanged between this review's hash manifests. Initial source orientation occurred before the before-pin capture. No test/product import, browser/HTTP/runtime/native/provider/mesh/Git/Goal/automation operation was run. No source, test, tracked document or historical packet was edited. The first attempted read of the tentative freeze filename failed; reading the discovered actual FREEZE.json succeeded. This was a filename lookup, not a seal/source failure.

Current doc-only HEAD `e5000f119d2eb6e82cfc4f8089eacb06028510bc`, UI baseline67caf04 and clean native producerce12037 are distinct. Their identities/status are taken from Root and saved packet records; no fresh Git/CI query is claimed. Continuing52/Phase1–7/ADR0035 purpose-specific scope, approved5.6Sol research and engineering UNKNOWN/NOT_RELEASED remain as previously recovered. This is an incremental correction review, not a duplicate native audit or architecture reset.

## P2: Interaction redraw failures bypass the visible refusal/recovery path

**File:** `apps/lab/static/fixture-field-viewer.js`, primary **lines184–192**; relevant state mutation **lines128–134**, other callers **171,179,257,280**, existing catches **258–275**.

`depthIndex()` deliberately throws for maxReferences overflow or an invalid projected span. `draw()` first resizes/clears the canvas and assigns a newly projected node map, then evaluates the potentially throwing depthIndex call. If that call fails, assignment to `index` does not complete, so a previous index/status may survive alongside the new projected map.

The mounted `update()` and `updateOverlay()` have catches, but pointermove, wheel and ResizeObserver call draw directly without that error boundary. Exact-ID probing/search and home can also reach draw/fit outside those catches. A cap/invalid-span refusal on those paths escapes as an event callback exception: the canvas has already been cleared, the promised readable display-resource error is not set, counts/probe state can still describe the previous frame, and picking remains enabled against the old index plus new projected points. The source therefore does not implement its report's advertised readable refusal and safe fit recovery for all interaction paths.

This is a concrete conditional control-flow defect in the new refusal path. It is **not** a claim that the retained7,715-node/4mm field exceeded the cap, that a browser exception has been observed, or that the full GUI envelope has been tested. The direct `depthIndex` assert.throws in `test_fixture_field_viewer.js:175–182` proves the helper throws; it does not establish how a mounted viewer responds to that throw. Root independently identified and accepted this same source finding during the review.

**Required correction:** use a single current-owner-guarded rendering success/error boundary for initial rendering, component/deformation/overlay changes, rotation, wheel, resize, probe/clear and fit/home. Prepare the candidate projected map/index/status before publishing an accepted frame. On failure, invalidate picking and any current-frame-derived counts/probe visibility, hide or unmistakably invalidate the canvas, and deliver the existing readable error through the owning mounted view. Keep exact raw node data and the validated model available. A later successful fit must clear the error, restore the canvas and publish a coherent new projected/index/status tuple. Stale or destroyed owners must remain inert on both success and failure. Do not increase caps or relax display/scientific thresholds to avoid the failure path.

## Other reviewed correction semantics

No additional P1/P2 source finding was identified in this bounded inspection.

- The same `depthIndex.visible` governs ordinary BC/load anchors, selected exterior cues and pick candidates. Barycentric front depth uses larger projectedZ as nearer, consistent with the viewer projection/draw ordering. A closer screen-distance rear candidate is excluded before nearest-node selection. Rotation/deformation rebuild projected geometry. X-ray is an explicit alternative, not a silent fallback.
- Edge/fixed/load toggles operate independently and retain all native arrays. Default visible mode and the persistent adjacent X-ray notice name the policy, visible counts and drawn/original counts. Interior nodes remain exact-ID inspections; hidden/interior/offscreen probe text distinguishes the state. Blank/invalid search clears the old selection marker.
- Conventional load arrows end at the actual displayed loaded node. `tailPosition = displayedPosition − normalizedForce × displayLength`, so tail→head follows the stored global force direction. Both shaft and head wings go through depth-aware segment sampling; air can remain visible. Sampling and2D head wings are display glyph approximations, not a physical force interpolation or a pixel-perfect subpixel guarantee.
- Fit uses current x+sU positions and enabled load-tail extents, keeps camera direction, and adds margin. The inverse projection recentering is consistent with the forward yaw/pitch transform. Component/overlay changes do not automatically reset the camera. Fit/display updates remain subject to the P2 failure-boundary correction above.
- New tolerances/caps are localized to projected display geometry. Native reader/32MiB raw-field and40k/25k/8k GUI admission, all U/N values, raw tokens/source joins, physical scalar ranges, whole-field |U| versus loaded-saddle |UZ|, invalid stress and UNKNOWN/NOT_RELEASED are unchanged. No engineering or canonical benchmark threshold is modified.
- Existing current/detached/destroy guards cover ordinary new callbacks. The actual-app source harness also exercises store POST invalidation before its response. These inert controls establish source behavior only, not actual browser/network state or fresh human usability.

The sealed worker evidence reports135PASS/0FAIL/0SKIP (old122 + new13) and one retained failed atomic patch attempt. I read the controls/source evidence and did not rerun it. The13new controls cover front/back visibility/picking, display rotation/deformation, external/occluded segments, resource-helper refusal, layer independence, X-ray captions/counts, interior/hidden probes and ownership. The missing mounted refusal/recovery path is the specific new acceptance need.

## Closure conditions

1. Preserve this frozen packet01/135PASS history and this review; use a new additive correction packet for the same bounded file owner. Root owns integration/Git.
2. Add a focused mounted-control case that causes a deterministic render/depth failure through interaction callbacks rather than only calling depthIndex directly. Cover pointer/wheel/resize paths and the shared route for probe/home. Assert readable error, invalid canvas/frame state, disabled picking and no old counts/probe visibility masquerading as the failed frame. Verify that a subsequent fitting/successful render clears the error and restores coherent state; keep thresholds/caps unchanged.
3. Retain old raw/scalar/layer/displayfactor/source/ownership controls, including stale/destroyed failure callbacks and pending store POST. Publish exact corrected source identities and test receipts for incremental read-only review. No native solve/remesh/provider/global-sweep gate is required for this display correction.
4. After source closure, Root captures actual clean-source same-field pixels and interactions: clean UZ view, rotated bottom restraints, saddle loads alone, explicit X-ray/count notice, native probe314 and a visible click, and0/100x/component invariants. Actual pixel P2 remains OPEN until that evidence demonstrates useful, unambiguous cues. No new or maximum-envelope performance assertion is inferred from the stills or source tests.

General Research/S3/U1/all52,2mm/full-envelope/7body support and engineering release remain OPEN/UNKNOWN/NOT_RELEASED. This review's outputs are private LOCAL_ONLY; prior source/native/pixel seals remain unchanged.
