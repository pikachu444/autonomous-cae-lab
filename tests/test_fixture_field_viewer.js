"use strict";

// TEST_ONLY native-shaped arrays. Tests paint an inert canvas/DOM, never a browser or solver.
const { test } = require("node:test"), assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm");
const controls = require("../apps/lab/static/fixture-field-controls.js"), viewer = require("../apps/lab/static/fixture-field-viewer.js");
const { fixture, clone, verify } = require("./test_fixture_field_controls.js");
class TinyNode {
  constructor(tag, doc) {
    this.tagName = tag.toUpperCase(); this.ownerDocument = doc; this.children = []; this.listeners = new Map(); this.attributes = {}; this.dataset = {};
    this.className = ""; this._text = ""; this._connected = true; this.value = ""; this.hidden = false; this.disabled = false; this.open = false;
    this.clientWidth = 800; this.clientHeight = 480; this.paint = [];
    this.context = Object.fromEntries(["setTransform", "clearRect", "fillRect", "beginPath", "moveTo", "lineTo", "closePath", "fill", "stroke", "rect", "arc", "fillText"].map(name => [name, (...args) => this.paint.push([name, ...args])]));
    this.classList = { add: (...names) => this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...names])].join(" "), toggle: () => {} };
  }
  get isConnected() { return this._connected && (!this.parentNode || this.parentNode.isConnected); }
  set isConnected(value) { this._connected = value; }
  set textContent(value) { this.replaceChildren(); this._text = String(value ?? ""); }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set innerHTML(_value) { throw new Error("Field content must remain inert text"); }
  append(...items) { items.forEach(child => { child.parentNode = this; child._connected = true; this.children.push(child); }); }
  replaceChildren(...items) { this.children.forEach(child => { child._connected = false; }); this.children = []; this._text = ""; this.append(...items); }
  addEventListener(name, callback) { if (!this.listeners.has(name)) this.listeners.set(name, []); this.listeners.get(name).push(callback); }
  emit(name, values = {}) { return (this.listeners.get(name) ?? []).map(callback => callback({ preventDefault() {}, clientX: 0, clientY: 0, pointerId: 1, deltaY: 1, ...values })); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  querySelector(selector) { return walk(this).slice(1).find(item => selector.startsWith(".") ? item.className.split(/\s+/).includes(selector.slice(1)) : item.tagName === selector.toUpperCase()) ?? null; }
  getContext(kind) { assert.equal(kind, "2d"); return this.context; }
  getBoundingClientRect() { return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight }; }
  setPointerCapture() {}
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function documentFixture() { const ids = new Map(), doc = { createElement: tag => new TinyNode(tag, doc), getElementById: id => { if (!ids.has(id)) ids.set(id, new TinyNode("div", doc)); return ids.get(id); } }; return doc; }
function mountFixture(isCurrent = () => true) { const data = fixture(), model = verify(data), doc = documentFixture(), container = doc.createElement("article"), mounted = viewer.mount(container, model, isCurrent); return { data, model, container, mounted }; }
test("native mechanics selector and first canvas both start at whole vector magnitude with partial DOF labels", () => {
  const data=require("./test_native_structural_field.js").nativeFixture(),
    model=require("../apps/lab/static/fixture-field-controls.js").verifyField(data.field,data.inspection,data.path),
    doc=documentFixture(),container=doc.createElement("article"), mounted=viewer.mount(container,model,()=>true);
  assert.equal(mounted.refs.component.value,"MAGNITUDE"); assert.equal(mounted.refs.canvas.dataset.component,"MAGNITUDE");
  assert.match(mounted.refs.legend.textContent,/\|U\|/); assert.match(container.textContent,/CAD_DOCUMENT_GLOBAL/);
  assert.match(tableRows(mounted)[0].textContent,/UX=0 mm/); assert.doesNotMatch(tableRows(mounted)[0].textContent,/XYZ 고정/);
});
function tableRows(mounted) { return walk(mounted.refs.rows).filter(item => item.tagName === "TR" && item.dataset.nodeId); }
test("field comparison callback carries only exact original identity, without displayed positions or amplified U", () => {
  const data = fixture(), before = JSON.stringify(data), model = verify(data), doc = documentFixture(), container = doc.createElement("article"), selected = [];
  const mounted = viewer.mount(container, model, () => true, value => selected.push(value));
  assert.equal(mounted.refs.compare.disabled, true);
  mounted.refs.search.value = "43"; mounted.refs.search.emit("input");
  mounted.refs.mode.value = "deformed"; mounted.refs.scale.value = "100"; mounted.update();
  mounted.refs.component.value = "UY"; mounted.update(); mounted.refs.compare.emit("click");
  assert.deepEqual(selected, [{ artifact: data.path, sha256: model.artifact.sha256, cad_revision: model.metadata.revision, node_id: 43, component: "UY" }]);
  assert.equal(JSON.stringify(data), before); assert.equal(Object.isFrozen(selected[0]), true);
  mounted.refs.component.value = "MAGNITUDE"; mounted.update(); mounted.refs.compare.emit("click");
  assert.equal(selected[1].component, "MAGNITUDE");
  mounted.refs.search.value = "210"; mounted.refs.search.emit("input"); mounted.refs.compare.emit("click");
  assert.equal(mounted.refs.compare.disabled, true); assert.equal(selected.length, 2);
});
test("retired or detached field comparisons cannot reach the observation callback", () => {
  const data = fixture(), model = verify(data), doc = documentFixture(), container = doc.createElement("article"), selected = []; let current = true;
  const mounted = viewer.mount(container, model, () => current, value => selected.push(value));
  mounted.refs.search.value = "43"; mounted.refs.search.emit("input"); current = false; mounted.refs.compare.emit("click");
  current = true; container.isConnected = false; mounted.refs.compare.emit("click");
  container.isConnected = true; mounted.destroy(); mounted.refs.compare.emit("click");
  assert.deepEqual(selected, []); assert.equal(mounted.refs.compare.disabled, true);
  assert.throws(() => controls.responseSelection(JSON.parse(JSON.stringify(model)), 43, "UZ"));
  assert.throws(() => controls.responseSelection(model, 210, "UZ"));
});
async function spin(predicate) {
  // WebCrypto completion comes from the worker pool. Event-loop turn counts
  // can expire before its callback under CI load; wait for the actual predicate.
  const deadline = performance.now() + 5000;
  while (!predicate() && performance.now() < deadline) await new Promise(resolve => setTimeout(resolve, 1));
  assert(predicate(), "bounded TEST_ONLY async condition");
}

test("only a complete verified native field is rendered; CAD and unbranded lookalikes refuse", () => {
  const data = fixture(), model = verify(data), scene = viewer.scene(model); assert.equal(scene.positions.size, 10);
  assert.throws(() => viewer.scene({ field: data.field })); assert.throws(() => viewer.scene({ bounds: [[0, 0, 0], [2, 2, 2]], faces: [] }));
  assert.throws(() => viewer.scene(clone(model)));
});
test("display deformation is exactly x+sU and never scales physical components, ranges, tokens or saved arrays", () => {
  const data = fixture(), before = JSON.stringify(data), model = verify(data), base = viewer.scene(model, "UZ", 0);
  for (const factor of [1, 100]) { const display = viewer.scene(model, "UZ", factor); assert.equal(display.min, base.min); assert.equal(display.max, base.max);
    for (const node of model.field.nodes) { assert.deepEqual(display.positions.get(node.node_id), node.position_mm.map((value, i) => value + factor * node.displacement_mm[i])); assert.equal(display.values.get(node.node_id), node.displacement_mm[2]); } }
  assert.equal(base.min, -.09); assert.equal(model.metadata.loadedMaximumUz, .05); assert.equal(JSON.stringify(data), before);
});
test("every CPS6 midside node participates in four display triangles without changing native face identity", () => {
  const model = verify(fixture()), scene = viewer.scene(model); assert.equal(scene.triangles.length, 16);
  for (const face of model.field.boundary_faces) { const triangles = scene.triangles.filter(item => item.face_id === face.element_id); assert.equal(triangles.length, 4);
    assert.deepEqual(new Set(triangles.flatMap(item => item.node_ids)), new Set(face.node_ids)); assert(triangles.every(item => item.group === face.group && item.node_ids.length === 3)); }
  for (const component of controls.COMPONENTS) { const values = model.field.nodes.map(node => controls.scalar(node, component)), display = viewer.scene(model, component);
    assert.equal(display.min, Math.min(...values)); assert.equal(display.max, Math.max(...values)); }
});
test("bad components or nonfinite/out-of-budget display scales cannot repaint an old mismatched view", () => {
  const { mounted, model } = mountFixture(), before = mounted.refs.canvas.paint.length;
  for (const factor of [NaN, Infinity, -1, controls.LIMITS.factor + 1]) assert.throws(() => viewer.scene(model, "UZ", factor));
  assert.equal(mounted.viewer.set("STRESS", 0), false); assert.equal(mounted.refs.canvas.paint.length, before); assert.equal(mounted.refs.canvas.dataset.pickingEnabled, "false");
  mounted.refs.mode.value = "deformed"; mounted.refs.scale.value = ""; assert.equal(mounted.update(), false); assert.equal(mounted.refs.canvas.hidden, false); assert.equal(mounted.refs.canvas.dataset.renderStatus, "UNAVAILABLE"); assert.match(mounted.refs.error.textContent, /배율/);
  mounted.refs.scale.value = "100"; assert.equal(mounted.update(), true); assert.equal(mounted.refs.canvas.hidden, false);
});
test("user controls retain unscaled raw values, UNKNOWN, native units and explicit display-only qualification", () => {
  const { container, mounted, data } = mountFixture(), before = JSON.stringify(data), rows = tableRows(mounted), legend = mounted.refs.legend.textContent;
  assert.equal(rows.length, 10); assert.equal(mounted.refs.provenance.open, false); assert.equal(walk(container).filter(item => item.tagName === "DETAILS").length, 1);
  assert.match(container.textContent, /SOLVER_GLOBAL_CARTESIAN/); assert.match(container.textContent, /step 1.*increment 1.*load_parameter 1 \(시간 값 아님\)/);
  assert.match(container.textContent, /UNKNOWN.*NOT_RELEASED.*미확인 검사 7개.*민감도 미평가/); assert.match(container.textContent, /파란 사각형.*고정 XYZ.*실제 saddle 하중/);
  assert.match(container.textContent, /전체 절점 최대 \|U\|.*기존 max_displacement.*0.05 mm/);
  const rawRow = rows.find(row => row.dataset.nodeId === "43").textContent; assert.match(rawRow, /-1.00000E-02.*2.00000E-02.*-3.00000E-02/);
  mounted.refs.mode.value = "deformed"; mounted.refs.mode.emit("change"); assert.equal(mounted.refs.canvas.dataset.displayFactor, "100");
  assert.equal(mounted.refs.legend.textContent, legend); assert.equal(tableRows(mounted).find(row => row.dataset.nodeId === "43").textContent, rawRow);
  assert.match(mounted.refs.deformationNote.textContent, /display-only.*x \+ 100U.*표와 색 범위에는 배율을 곱하지 않습니다/);
  mounted.refs.component.value = "MAGNITUDE"; mounted.refs.component.emit("change"); assert.match(mounted.refs.legend.textContent, /\|U\|.*배율 미적용/); assert.equal(JSON.stringify(data), before);
});
test("native ID probe includes nonloaded extrema and raw vector precision, and refuses fabricated IDs", () => {
  const { mounted } = mountFixture(); mounted.refs.search.value = "209"; mounted.refs.search.emit("input"); assert.equal(tableRows(mounted).length, 1);
  assert.match(mounted.refs.probeBox.textContent, /절점 209.*1.00000E-03.*1.00000E-02.*-9.00000E-02/); assert.doesNotMatch(mounted.refs.probeBox.textContent, /하중/);
  assert.equal(mounted.viewer.probe(210), false); mounted.refs.search.value = "210"; mounted.refs.search.emit("input"); assert.equal(tableRows(mounted).length, 0); assert.match(mounted.refs.pageCaption.textContent, /절점 ID가 아닙니다/);
  mounted.refs.search.value = "7"; mounted.refs.search.emit("input"); assert.match(mounted.refs.probeBox.textContent, /고정 XYZ/);
  mounted.refs.search.value = "145"; mounted.refs.search.emit("input"); assert.match(mounted.refs.probeBox.textContent, /하중 0 \/ 0 \/ -3 N/);
});
for (const invalidate of ["lease", "detach", "destroy"]) test(`component/deformation/probe/rotate callbacks cannot mutate a ${invalidate} view`, () => {
  let current = true; const { container, mounted } = mountFixture(() => current), oldText = container.textContent, paints = mounted.refs.canvas.paint.length;
  if (invalidate === "lease") current = false; else if (invalidate === "detach") container.isConnected = false; else mounted.destroy();
  mounted.refs.component.value = "UX"; mounted.refs.component.emit("change"); mounted.refs.mode.value = "deformed"; mounted.refs.mode.emit("change"); mounted.refs.scale.value = "10"; mounted.refs.scale.emit("input");
  mounted.refs.search.value = "209"; mounted.refs.search.emit("input"); mounted.refs.next.emit("click"); mounted.refs.canvas.emit("pointerdown"); mounted.refs.canvas.emit("pointermove", { clientX: 30 }); mounted.refs.canvas.emit("pointerup"); mounted.refs.canvas.emit("wheel");
  assert.equal(mounted.viewer.probe(43), false); assert.equal(mounted.viewer.home(), false); assert.equal(mounted.refs.canvas.paint.length, paints); assert.equal(container.textContent, oldText);
});

const appSource = fs.readFileSync(require.resolve("../apps/lab/static/app.js"), "utf8"), bootBoundary = appSource.indexOf('$("jobCancelBtn").addEventListener("click", async () => {');
const switchStart = appSource.indexOf("async function switchStore("), switchEnd = appSource.indexOf("\n// Exact Core keyword arguments", switchStart);
function appHarness(data = fixture()) {
  const doc = documentFixture(), requests = [], nativeLists = [], sandbox = { document: doc, Node: TinyNode, window: { fixtureFieldControls: controls, fixtureFieldViewer: viewer },
    location: { hash: "#results" }, URL, URLSearchParams, Intl, Uint8Array, console, setTimeout: () => { throw new Error("No app timers or live jobs permitted"); }, clearTimeout() {},
    fetch: (path, options) => {
      if (path === "/api/native-imports") {
        nativeLists.push({ path, options });
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ imports: [] }) });
      }
      return new Promise((resolve, reject) => requests.push({ path, options, resolve, reject }));
    } };
  vm.createContext(sandbox); vm.runInContext(appSource.slice(0, bootBoundary) + "\n" + appSource.slice(switchStart, switchEnd)
    // Field lifecycle harness does not mount the application's execution forms.
    + "\nupdateControls=()=>{};renderResearchAnswers=()=>{};invalidateModelDiscovery=()=>{};renderDiscovery=()=>{};renderOverview=()=>{};renderStudy=()=>{};renderRegistry=()=>{};globalThis.fieldApp={state,renderFixtureFields,switchStore};", sandbox);
  const app = sandbox.fieldApp; app.state.overview = { active_store: "TEST_ONLY-local", stores: [{ id: "TEST_ONLY-local", writable: true }] }; app.state.selectedExperiment = data.inspection;
  return { app, requests, nativeLists, data, root: doc.createElement("main"), doc };
}
function response(bytes) { return { ok: true, status: 200, headers: { get: () => String(bytes.length) }, arrayBuffer: async () => Uint8Array.from(bytes).buffer }; }
test("actual result renderer fetches only the same manifested child field and keeps all source links in closed verification detail", async () => {
  const h = appHarness(), before = JSON.stringify(h.data.inspection), pending = h.app.renderFixtureFields(h.root, h.data.inspection);
  assert.equal(h.requests.length, 1); assert.equal(h.requests[0].path, "/api/artifacts/E-TEST_ONLY-field?path=simulation%2Fsupport_0%2Ffea_field.json");
  h.requests[0].resolve(response(h.data.bytes)); assert.equal(await pending, true); const mounted = h.app.state.fixtureViewer; assert(mounted);
  assert.equal(mounted.refs.canvas.dataset.nativeNodeCount, "10"); const links = walk(mounted.refs.provenance).filter(item => item.tagName === "A"); assert.equal(links.length, 6);
  assert(links.every(item => item.href.startsWith("/api/artifacts/E-TEST_ONLY-field?path=simulation%2Fsupport_0%2F"))); assert.equal(mounted.refs.provenance.open, false); assert.equal(JSON.stringify(h.data.inspection), before);
});
for (const invalidate of ["selection", "epoch", "store", "switching", "detach"]) for (const fail of [false, true]) test(`actual app late ${fail ? "error" : "success"} is inert after ${invalidate}`, async () => {
  const h = appHarness(), pending = h.app.renderFixtureFields(h.root, h.data.inspection), before = h.root.textContent;
  if (invalidate === "selection") h.app.state.selectedExperiment = clone(h.data.inspection);
  else if (invalidate === "epoch") h.app.state.experimentRequest++;
  else if (invalidate === "store") h.app.state.overview.active_store = "TEST_ONLY-other";
  else if (invalidate === "switching") h.app.state.storeSwitching = true;
  else h.root.isConnected = false;
  if (fail) h.requests[0].reject(new Error("TEST_ONLY stale error")); else h.requests[0].resolve(response(h.data.bytes));
  assert.equal(await pending, false); assert.equal(h.app.state.fixtureViewer, null); assert.equal(h.root.textContent, before); assert.equal(h.root.querySelector("canvas"), null);
});
for (const fail of [false, true]) test(`late previously selected mesh ${fail ? "error" : "success"} cannot replace the newly selected mesh`, async () => {
  const h = appHarness(fixture({ legacy: true })), pending = h.app.renderFixtureFields(h.root, h.data.inspection), select = walk(h.root).find(item => item.tagName === "SELECT");
  assert.match(h.requests[0].path, /support_1/); select.value = "0"; select.emit("change"); assert.equal(h.requests.length, 2);
  h.requests[1].resolve(response(h.data.bytes)); await spin(() => h.app.state.fixtureViewer !== null); const latest = h.app.state.fixtureViewer, before = h.root.textContent;
  if (fail) h.requests[0].reject(new Error("TEST_ONLY late prior mesh")); else h.requests[0].resolve(response(h.data.byPath.get("simulation/support_1/fea_field.json")));
  assert.equal(await pending, false); assert.equal(h.app.state.fixtureViewer, latest); assert.equal(h.root.textContent, before); assert.match(before, /메시 4 mm/);
});
test("mounted actual result controls stop painting when its selection epoch changes", async () => {
  const h = appHarness(), pending = h.app.renderFixtureFields(h.root, h.data.inspection); h.requests[0].resolve(response(h.data.bytes)); await pending;
  const mounted = h.app.state.fixtureViewer, before = h.root.textContent, paints = mounted.refs.canvas.paint.length; h.app.state.experimentRequest++;
  mounted.refs.component.value = "UX"; mounted.refs.component.emit("change"); mounted.refs.mode.value = "deformed"; mounted.refs.mode.emit("change"); mounted.refs.search.value = "43"; mounted.refs.search.emit("input");
  assert.equal(h.root.textContent, before); assert.equal(mounted.refs.canvas.paint.length, paints);
});
test("raw changed field bytes and streaming overrun refuse a current display before any canvas is mounted", async () => {
  for (const stream of [false, true]) { const h = appHarness(), pending = h.app.renderFixtureFields(h.root, h.data.inspection); let cancelled = 0, released = 0;
    if (stream) h.requests[0].resolve({ ok: true, status: 200, headers: { get: () => null }, body: { getReader: () => ({ read: async () => ({ done: false, value: new Uint8Array(h.data.bytes.length + 1) }), cancel: async () => { cancelled++; }, releaseLock: () => { released++; } }) } });
    else { const bytes = Uint8Array.from(h.data.bytes); bytes[30] ^= 1; h.requests[0].resolve(response(bytes)); }
    assert.equal(await pending, false); assert.equal(h.root.querySelector("canvas"), null); assert.equal(h.app.state.fixtureViewer, null);
    assert.match(h.root.textContent, stream ? /바이트 범위/ : /SHA-256/); if (stream) { assert.equal(cancelled, 1); assert.equal(released, 1); }
  }
});
test("the real store POST invalidates mounted controls and pending field reads before the store response", async () => {
  const h = appHarness(), first = h.app.renderFixtureFields(h.root, h.data.inspection); h.requests[0].resolve(response(h.data.bytes)); await first;
  const mounted = h.app.state.fixtureViewer, paints = mounted.refs.canvas.paint.length, second = h.app.renderFixtureFields(h.root, h.data.inspection);
  const switchPending = h.app.switchStore("TEST_ONLY-other"); assert.equal(h.app.state.storeSwitching, true); assert.equal(h.app.state.fixtureViewer, null);
  mounted.refs.component.value = "UX"; mounted.refs.component.emit("change"); assert.equal(mounted.refs.canvas.paint.length, paints);
  assert.equal(h.requests[2].path, "/api/store"); assert.equal(h.requests[2].options.method, "POST"); h.requests[1].reject(new Error("TEST_ONLY old field while store POST is pending")); assert.equal(await second, false);
  h.requests[2].resolve({ ok: true, status: 200, json: async () => ({ active_store: "TEST_ONLY-other", stores: [] }) }); await switchPending;
  assert.equal(h.nativeLists.length, 1); assert.equal(h.nativeLists[0].path, "/api/native-imports");
  assert.equal(h.app.state.storeSwitching, false);
  assert.equal(h.app.state.overview.active_store, "TEST_ONLY-other"); assert.equal(h.app.state.selectedExperiment, null); assert.equal(h.app.state.fixtureViewer, null);
});

// TEST_ONLY projected display frames, independent of native data/solver qualification.
function overlapFrame({ rotate = false, rearShift = 0 } = {}) {
  const project = (x, y, z) => ({ x: rotate ? 100 - x : x, y, z: rotate ? -z : z });
  const front = [[10, 10, 8], [90, 10, 8], [10, 90, 8]].map(([x, y, z]) => project(x, y, z));
  const rear = [[10, 10, 1 + rearShift], [90, 10, 1 + rearShift], [10, 90, 1 + rearShift]].map(([x, y, z]) => project(x, y, z));
  return { index: viewer.depthIndex([{ points: rear }, { points: front }], 100, 100, 10 + rearShift),
    front: { ...project(30, 30, 8), node_id: 101 }, rear: { ...project(31, 31, 1 + rearShift), node_id: 202 } };
}
test("front/back overlapping triangles exclude rear cues and the closer hidden node from normal picking", () => {
  const frame = overlapFrame(); assert.equal(frame.index.frontDepth(31, 31), 8); assert.equal(frame.index.visible(frame.front), true); assert.equal(frame.index.visible(frame.rear), false);
  assert.equal(frame.index.pick([frame.rear, frame.front], 31, 31), 101); assert.equal(frame.index.pick([frame.rear, frame.front], 31, 31, "xray"), 202);
  const behind = frame.index.segments({ x: 30, y: 30, z: 1 }, { x: 40, y: 30, z: 1 }); assert.equal(behind.length, 0);
  assert(frame.index.segments({ x: 30, y: 30, z: 1 }, { x: 40, y: 30, z: 1 }, "xray").length > 0);
});
test("rotated and display-deformed front/back frames recompute the same visibility/picking policy", () => {
  for (const frame of [overlapFrame({ rotate: true }), overlapFrame({ rearShift: 10 })]) {
    assert.equal(frame.index.visible(frame.front), false); assert.equal(frame.index.visible(frame.rear), true);
    assert.equal(frame.index.pick([frame.front, frame.rear], frame.front.x, frame.front.y), 202);
  }
  const original = overlapFrame(); assert.equal(original.index.pick([original.front, original.rear], 31, 31), 101);
});
test("airborne external force tail remains visible while its rear/interior segment is depth clipped", () => {
  const frame = overlapFrame(), tail = { x: 30, y: 0, z: 10 }, head = { x: 30, y: 30, z: 8 }, behind = { x: 30, y: 40, z: 1 };
  assert.equal(frame.index.frontDepth(tail.x, tail.y), null); assert.equal(frame.index.unoccluded(tail), true); assert.equal(frame.index.visible(tail), false);
  const outside = frame.index.segments(tail, head); assert(outside.length > 0); assert(outside.some(([start]) => start.y < 10));
  const clipped = frame.index.segments(head, behind); assert.equal(clipped.length, 0); assert(frame.index.segments(head, behind, "xray").length > 0);
});
test("depth tolerances and finite spatial index are display resources, separate from scientific/loader criteria", () => {
  const frame = overlapFrame(), near = { ...frame.front, z: 8 - frame.index.depthTolerance / 2 }, far = { ...frame.front, z: 8 - frame.index.depthTolerance * 2 };
  assert(frame.index.visible(near)); assert.equal(frame.index.visible(far), false); assert(frame.index.tiles <= 4096); assert(frame.index.references <= 262144);
  assert.equal(viewer.DISPLAY.relativeDepth, 1e-7); assert.equal(controls.LIMITS.bytes, 32 * 1024 * 1024); assert.equal(controls.LIMITS.nodes, 40000); assert.equal(controls.LIMITS.elements, 25000); assert.equal(controls.LIMITS.faces, 8000);
  assert.throws(() => viewer.depthIndex([{ points: [{ x: NaN, y: 0, z: 0 }, { x: 10, y: 0, z: 1 }, { x: 0, y: 10, z: 2 }] }], 100, 100, 10), /유한/);
  const huge = { points: [{ x: 0, y: 0, z: 1 }, { x: 2048, y: 0, z: 1 }, { x: 0, y: 2048, z: 1 }] };
  assert.throws(() => viewer.depthIndex(Array(65).fill(huge), 2048, 2048, 10), /화면 자원/);
  assert.throws(() => frame.index.pick([frame.front], 30, 30, "unlabeled-through-solid"));
});
test("mesh-edge off preserves colored exterior; fixed/load toggles retain complete counts and scientific arrays", () => {
  const { data, mounted } = mountFixture(), before = JSON.stringify(data), scalar = mounted.refs.legend.textContent, rows = mounted.refs.rows.textContent, canvas = mounted.refs.canvas;
  mounted.refs.checks.fixed.checked = false; mounted.refs.checks.loads.checked = false; let start = canvas.paint.length; mounted.updateOverlay(); const edges = canvas.paint.slice(start);
  mounted.refs.checks.edges.checked = false; start = canvas.paint.length; mounted.updateOverlay(); const smooth = canvas.paint.slice(start);
  assert.equal(edges.filter(item => item[0] === "fill").length, 16); assert.equal(smooth.filter(item => item[0] === "fill").length, 16);
  assert.equal(edges.filter(item => item[0] === "stroke").length - smooth.filter(item => item[0] === "stroke").length, 16);
  assert.equal(canvas.dataset.fixedDrawn, "0"); assert.equal(canvas.dataset.loadsDrawn, "0"); assert.match(mounted.refs.policy.textContent, /고정 표시 0 \/ 원본 6.*하중 표시 0 \/ 원본 3/);
  mounted.refs.checks.fixed.checked = true; mounted.refs.checks.fixed.emit("change"); assert.equal(canvas.dataset.loadsDrawn, "0"); assert.match(mounted.refs.policy.textContent, /원본 6.*원본 3/);
  mounted.refs.checks.loads.checked = true; mounted.refs.checks.loads.emit("change"); assert.equal(mounted.refs.legend.textContent, scalar); assert.equal(mounted.refs.rows.textContent, rows); assert.equal(JSON.stringify(data), before);
});
test("X-ray is opt-in, persistently labels hidden picking and full-versus-displayed counts", () => {
  const { mounted } = mountFixture(), before = mounted.refs.legend.textContent;
  assert.equal(mounted.refs.visibility.value, "visible"); assert.equal(mounted.refs.canvas.dataset.visibilityMode, "visible"); assert.doesNotMatch(mounted.refs.policy.className, /xray/);
  mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change"); assert.equal(mounted.refs.canvas.dataset.visibilityMode, "xray"); assert.match(mounted.refs.policy.className, /xray/);
  assert.match(mounted.refs.policy.textContent, /X-ray 투과 검사.*뒤쪽 외곽 절점도 표시·클릭 후보.*표시 개수는 전체 원본 개수가 아닙니다/);
  assert.equal(mounted.refs.canvas.dataset.fixedDrawn, "6"); assert.equal(mounted.refs.canvas.dataset.loadsDrawn, "3"); assert.equal(mounted.refs.legend.textContent, before);
  mounted.refs.visibility.value = "visible"; mounted.refs.visibility.emit("change"); assert.match(mounted.refs.policy.textContent, /보이는 외곽면만 표시·클릭/);
});
test("hidden exact-ID probe keeps all raw components but suppresses an unexplained through-solid marker", () => {
  const { mounted, model } = mountFixture(); const hidden = model.field.nodes.find(node => { mounted.viewer.probe(node.node_id); return /앞면에 가려진/.test(mounted.refs.probeBox.textContent); });
  assert(hidden, "TEST_ONLY tetrahedron has a hidden boundary node"); mounted.viewer.clearProbe(); const start = mounted.refs.canvas.paint.length; mounted.viewer.probe(hidden.node_id);
  assert.match(mounted.refs.probeBox.textContent, /앞면에 가려진.*canvas 위치 표시 안 함/); assert(hidden.displacement_tokens.every(token => mounted.refs.probeBox.textContent.includes(token)));
  assert.equal(mounted.refs.canvas.paint.slice(start).filter(item => item[0] === "arc" && item[3] === 5).length, 0);
  mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change"); assert.match(mounted.refs.probeBox.textContent, /앞면에 가려진.*X-ray 투과 위치 표시/);
  mounted.refs.visibility.value = "visible"; mounted.refs.visibility.emit("change"); assert.match(mounted.refs.probeBox.textContent, /canvas 위치 표시 안 함/);
});
function interiorFixture() {
  const data = fixture(), point = { 7: [0, 0, 0], 11: [2, 0, 0], 21: [0, 2, 0], 43: [0, 0, 2] }, center = [.5, .5, .5];
  data.field.nodes.push({ node_id: 300, position_mm: center, displacement_mm: [.005, .003, -.007], displacement_tokens: ["5.00000E-03", "3.00000E-03", "-7.00000E-03"] });
  [7, 11, 21, 43].forEach((id, i) => data.field.nodes.push({ node_id: 301 + i, position_mm: point[id].map((value, axis) => (value + center[axis]) / 2), displacement_mm: [0, 0, 0], displacement_tokens: ["0.00000E+00", "0.00000E+00", "0.00000E+00"] }));
  data.field.node_count = 15; data.field.elements = [
    [7, 11, 21, 300, 54, 67, 81, 301, 302, 303], [7, 43, 11, 300, 102, 145, 54, 301, 304, 302],
    [11, 43, 21, 300, 145, 209, 67, 302, 304, 303], [21, 43, 7, 300, 209, 102, 81, 303, 304, 301]
  ].map((node_ids, i) => ({ element_id: 31 + i, type: "C3D10", node_ids })); data.field.element_count = 4; return data;
}
test("interior exact-ID probe is explicit and table-only by default; X-ray opt-in marks its stored position", () => {
  const data = interiorFixture(), before = JSON.stringify(data), model = verify(data), doc = documentFixture(), container = doc.createElement("article"), mounted = viewer.mount(container, model, () => true);
  mounted.refs.search.value = "300"; mounted.refs.search.emit("input"); assert.equal(tableRows(mounted).length, 1); assert.match(mounted.refs.probeBox.textContent, /내부 절점.*canvas 위치 표시 안 함.*5.00000E-03.*3.00000E-03.*-7.00000E-03/);
  mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change"); assert.match(mounted.refs.probeBox.textContent, /내부 절점.*X-ray 투과 위치 표시/); assert.match(mounted.refs.policy.textContent, /내부 절점은 ID 검색/);
  mounted.refs.search.value = ""; mounted.refs.search.emit("input"); assert.equal(mounted.refs.probeBox.textContent, ""); assert.equal(tableRows(mounted).length, 15); assert.equal(JSON.stringify(data), before);
});
test("camera rotation, x+sU changes and fit recompute overlay policy while keeping raw probe/physical range", () => {
  const { data, mounted } = mountFixture(), before = JSON.stringify(data), legend = mounted.refs.legend.textContent; mounted.viewer.probe(7); const initial = mounted.refs.probeBox.textContent;
  mounted.refs.canvas.emit("pointerdown", { clientX: 200, clientY: 100 }); mounted.refs.canvas.emit("pointermove", { clientX: 350, clientY: 250 }); mounted.refs.canvas.emit("pointerup", { clientX: 350, clientY: 250 });
  assert.notEqual(mounted.refs.probeBox.textContent, initial, "TEST_ONLY camera turn changes selected node visibility");
  mounted.refs.mode.value = "deformed"; mounted.refs.scale.value = "100"; mounted.refs.mode.emit("change"); mounted.refs.fit.emit("click");
  assert.equal(mounted.refs.canvas.dataset.displayFactor, "100"); assert.equal(mounted.refs.legend.textContent, legend); assert.match(mounted.refs.probeBox.textContent, /절점 7.*원본 XYZ 0 \/ 0 \/ 0/);
  mounted.viewer.home(); assert.match(mounted.refs.policy.textContent, /고정 표시.*원본 6.*하중 표시.*원본 3/); assert.equal(JSON.stringify(data), before);
});
for (const invalidate of ["lease", "detach", "destroy"]) test(`new overlay/policy/fit/pick callbacks are inert after ${invalidate}`, () => {
  let current = true; const { container, mounted } = mountFixture(() => current), text = container.textContent, paints = mounted.refs.canvas.paint.length, dataset = JSON.stringify(mounted.refs.canvas.dataset);
  if (invalidate === "lease") current = false; else if (invalidate === "detach") container.isConnected = false; else mounted.destroy();
  for (const input of Object.values(mounted.refs.checks)) { input.checked = false; input.emit("change"); } mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change"); mounted.refs.fit.emit("click");
  assert.equal(mounted.viewer.overlay({ edges: false, fixed: false, loads: false }, "xray"), false); assert.equal(mounted.viewer.pick(30, 30), false); assert.equal(mounted.viewer.fit(), false); assert.equal(mounted.viewer.clearProbe(), false);
  assert.equal(mounted.refs.canvas.paint.length, paints); assert.equal(JSON.stringify(mounted.refs.canvas.dataset), dataset); assert.equal(container.textContent, text);
});
test("actual same-record mounted overlay callbacks stop before the store POST completes", async () => {
  const h = appHarness(), pending = h.app.renderFixtureFields(h.root, h.data.inspection); h.requests[0].resolve(response(h.data.bytes)); await pending;
  const mounted = h.app.state.fixtureViewer, paints = mounted.refs.canvas.paint.length, policy = mounted.refs.policy.textContent, switching = h.app.switchStore("TEST_ONLY-other");
  mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change"); mounted.refs.checks.fixed.checked = false; mounted.refs.checks.fixed.emit("change"); mounted.refs.fit.emit("click");
  assert.equal(mounted.refs.canvas.paint.length, paints); assert.equal(mounted.refs.policy.textContent, policy);
  h.requests[1].resolve({ ok: true, status: 200, json: async () => ({ active_store: "TEST_ONLY-other", stores: [] }) }); await switching;
  assert.equal(h.nativeLists.length, 1); assert.equal(h.app.state.storeSwitching, false);
});

// TEST_ONLY mounted lifecycle controls. No real browser, HTTP, retained fields, or native run.
function assertUnavailable(mounted, message) {
  const { canvas, error, policy, legend, deformationNote } = mounted.refs;
  assert.equal(canvas.hidden, false, "unavailable canvas keeps its real layout dimensions"); assert.equal(canvas.attributes["aria-hidden"], "true"); assert.equal(canvas.dataset.renderStatus, "UNAVAILABLE"); assert.equal(canvas.dataset.pickingEnabled, "false");
  assert.equal(error.hidden, false); assert.match(error.textContent, message); assert.match(error.textContent, /원본 절점 표.*(?:현재 표시 맞추기|표시 설정을 올바르게 입력)/);
  for (const key of ["component", "displayFactor", "visibilityMode", "fixedDrawn", "loadsDrawn"]) assert.equal(canvas.dataset[key], undefined, `no old current-frame claim: ${key}`);
  assert.match(policy.textContent, /canvas 클릭 비활성.*현재 표시 개수 미확인.*고정 원본.*하중 원본/); assert.match(policy.className, /unavailable/);
  assert.doesNotMatch(policy.textContent, /고정 표시 \d|하중 표시 \d|현재 보이는 \d/);
  assert.match(legend.textContent, /현재 canvas 범례·위치 표시는 확인되지/); assert.match(deformationNote.textContent, /현재 변형 위치 표시 없음/);
}
function assertReady(mounted) {
  const { canvas, error, policy } = mounted.refs;
  assert.equal(canvas.hidden, false); assert.equal(canvas.attributes["aria-hidden"], "false"); assert.equal(canvas.dataset.renderStatus, "READY"); assert.equal(canvas.dataset.pickingEnabled, "true");
  assert.equal(canvas.dataset.renderError, undefined); assert.equal(error.hidden, true); assert.equal(error.textContent, "");
  assert.match(policy.textContent, /고정 표시 \d+ \/ 원본.*하중 표시 \d+ \/ 원본/); assert.doesNotMatch(policy.className, /unavailable/);
}
function withResizeObserver(run) {
  const present = Object.hasOwn(globalThis, "ResizeObserver"), previous = globalThis.ResizeObserver, observers = [];
  globalThis.ResizeObserver = class {
    constructor(callback) { this.callback = callback; this.disconnected = false; observers.push(this); }
    observe(canvas) { this.canvas = canvas; }
    disconnect() { this.disconnected = true; }
    emit() { return this.callback(); }
  };
  try { return run(observers); } finally { if (present) globalThis.ResizeObserver = previous; else delete globalThis.ResizeObserver; }
}
function selectedPixel(mounted, id = 7) {
  assert.equal(mounted.viewer.probe(id), true);
  const point = mounted.refs.canvas.paint.findLast(item => item[0] === "arc" && item[3] === 5);
  assert(point, "TEST_ONLY selected native point has an explicit current cue"); return { x: point[1], y: point[2] };
}

test("initial mounted drawing refusal preserves raw table and fit publishes the first accepted frame", () => {
  const data = fixture(), before = JSON.stringify(data), model = verify(data), doc = documentFixture(), originalCreate = doc.createElement;
  doc.createElement = tag => { const item = originalCreate(tag); if (tag === "canvas") item.getContext = () => null; return item; };
  const container = doc.createElement("article"), mounted = viewer.mount(container, model, () => true);
  assertUnavailable(mounted, /2D canvas/); assert.equal(tableRows(mounted).length, 10);
  mounted.refs.search.value = "145"; assert.doesNotThrow(() => mounted.refs.search.emit("input"));
  assert.equal(tableRows(mounted).length, 1); assert.match(mounted.refs.probeBox.textContent, /절점 145.*현재 위치 표시를 확인할 수 없음.*canvas 위치 표시 안 함.*-5.00000E-02.*하중 0 \/ 0 \/ -3 N/);
  assert.doesNotMatch(mounted.refs.probeBox.textContent, /현재 화면 밖|보이는 위치 표시|X-ray 투과 위치 표시/);
  mounted.refs.canvas.getContext = () => mounted.refs.canvas.context;
  assert.equal(mounted.update(true), true); assertReady(mounted); assert.equal(JSON.stringify(data), before);
});

const lifecycleActions = {
  update: mounted => { mounted.refs.component.value = "UX"; mounted.refs.component.emit("change"); },
  overlay: mounted => { mounted.refs.checks.edges.checked = false; mounted.refs.checks.edges.emit("change"); },
  fit: mounted => mounted.refs.fit.emit("click"),
  home: mounted => mounted.refs.home.emit("click"),
  probe: mounted => mounted.viewer.probe(145),
  clearProbe: mounted => mounted.viewer.clearProbe(),
  search: mounted => { mounted.refs.search.value = "145"; mounted.refs.search.emit("input"); },
  rotation: mounted => mounted.refs.canvas.emit("pointermove", { clientX: 410, clientY: 270 }),
  wheel: mounted => mounted.refs.canvas.emit("wheel", { deltaY: -1 }),
  resize: (_mounted, observer) => observer.emit(),
};
for (const [name, action] of Object.entries(lifecycleActions)) test(`${name} uses the same mounted refusal boundary and fit clears the error`, () => withResizeObserver(observers => {
  const { data, mounted } = mountFixture(), before = JSON.stringify(data), canvas = mounted.refs.canvas;
  mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change"); const oldPixel = selectedPixel(mounted);
  if (name === "rotation") canvas.emit("pointerdown", { clientX: 150, clientY: 150 });
  const originalFill = canvas.context.fill; canvas.context.fill = () => { throw new Error(`TEST_ONLY ${name} paint refusal`); };
  assert.doesNotThrow(() => action(mounted, observers[0])); assertUnavailable(mounted, /TEST_ONLY.*paint refusal/);
  if (!["clearProbe", "search"].includes(name)) assert.match(mounted.refs.probeBox.textContent, /현재 위치 표시를 확인할 수 없음.*canvas 위치 표시 안 함/);
  canvas.context.fill = originalFill; const paints = canvas.paint.length, rawProbe = mounted.refs.probeBox.textContent;
  assert.equal(mounted.viewer.pick(oldPixel.x, oldPixel.y), false, "previous projection/index cannot select after any failed frame");
  assert.equal(canvas.paint.length, paints); assert.equal(mounted.refs.probeBox.textContent, rawProbe); assertUnavailable(mounted, /TEST_ONLY.*paint refusal/);
  if (["probe", "search"].includes(name)) assert.match(mounted.refs.probeBox.textContent, /절점 145.*-5.00000E-02.*하중 0 \/ 0 \/ -3 N/);
  assert.equal(mounted.update(true), true); assertReady(mounted);
  const pixel = selectedPixel(mounted); assert.equal(mounted.viewer.pick(pixel.x, pixel.y), true); assert.match(mounted.refs.probeBox.textContent, /^절점 7 /);
  assert.equal(JSON.stringify(data), before);
}));

function coincidentDisplayFixture(copies) {
  // Deliberately overlapping disconnected TEST_ONLY TET10s trigger display allocation;
  // this is a renderer control, not a native mesh or a geometry/engineering qualification.
  const data = fixture(), base = clone(data.field), field = data.field;
  field.nodes = []; field.elements = []; field.boundary_faces = []; field.fixed_node_ids = []; field.loads = [];
  for (let copy = 0; copy < copies; copy++) {
    const node = id => id + copy * 1000;
    field.nodes.push(...base.nodes.map(value => ({ ...clone(value), node_id: node(value.node_id) })));
    field.elements.push(...base.elements.map(value => ({ ...value, element_id: 100000 + copy, node_ids: value.node_ids.map(node) })));
    field.boundary_faces.push(...base.boundary_faces.map((value, i) => ({ ...value, element_id: copy * 4 + i + 1, node_ids: value.node_ids.map(node) })));
    field.fixed_node_ids.push(...base.fixed_node_ids.map(node)); field.loads.push(...base.loads.map(value => ({ ...clone(value), node_id: node(value.node_id) })));
  }
  field.node_count = field.nodes.length; field.element_count = field.elements.length; field.boundary_face_count = field.boundary_faces.length;
  data.inspection.proposal.execution.load.force_per_support_N = 6 * copies;
  const details = data.inspection.result.provenance.adapter_details; details.force_per_support_N = 6 * copies; details.per_mesh_displacement.studies[0].loaded_node_count = 3 * copies;
  return data;
}

test("actual mounted depth-allocation refusal never clears/publishes a mixed frame and fit recovers without raising the cap", () => withResizeObserver(observers => {
  const data = coincidentDisplayFixture(64), before = JSON.stringify(data), model = verify(data), doc = documentFixture(), mounted = viewer.mount(doc.createElement("article"), model, () => true), canvas = mounted.refs.canvas;
  assertReady(mounted); mounted.refs.checks.fixed.checked = false; mounted.refs.checks.loads.checked = false; mounted.updateOverlay();
  mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change"); const oldPixel = selectedPixel(mounted, 43);
  // Growing the projected viewport/zoom, not native arrays or any cap, causes the refusal.
  canvas.clientWidth = 2048; canvas.clientHeight = 2048; let beforeAttempt = canvas.paint.length;
  assert.doesNotThrow(() => observers[0].emit());
  for (let step = 0; canvas.dataset.renderStatus === "READY" && step < 60; step++) { beforeAttempt = canvas.paint.length; assert.doesNotThrow(() => canvas.emit("wheel", { deltaY: -1 })); }
  assertUnavailable(mounted, /화면 자원/); assert.equal(canvas.paint.length, beforeAttempt, "resource refusal precedes canvas clear/paint");
  assert.match(mounted.refs.probeBox.textContent, /절점 43.*현재 위치 표시를 확인할 수 없음.*-3.00000E-02.*하중 0 \/ 0 \/ -1 N/);
  assert.equal(mounted.viewer.pick(oldPixel.x, oldPixel.y), false); assert.equal(canvas.paint.length, beforeAttempt);
  assert.equal(tableRows(mounted).length, 1); mounted.refs.search.value = "145"; assert.doesNotThrow(() => mounted.refs.search.emit("input"));
  assertUnavailable(mounted, /화면 자원/); assert.match(mounted.refs.probeBox.textContent, /절점 145.*-5.00000E-02.*하중 0 \/ 0 \/ -3 N/);
  canvas.clientWidth = 800; canvas.clientHeight = 480; mounted.refs.fit.emit("click"); assertReady(mounted);
  assert.equal(viewer.DISPLAY.maxReferences, 262144); assert.equal(model.field.node_count, 640); assert.equal(model.field.boundary_face_count, 256); assert.equal(JSON.stringify(data), before);
}));

for (const invalidate of ["lease", "detach", "destroy"]) test(`render failure callbacks and ResizeObserver remain inert after ${invalidate}`, () => withResizeObserver(observers => {
  let current = true; const { data, container, mounted } = mountFixture(() => current), before = JSON.stringify(data), canvas = mounted.refs.canvas;
  canvas.emit("pointerdown", { clientX: 150, clientY: 150 });
  const text = container.textContent, paints = canvas.paint.length, dataset = JSON.stringify(canvas.dataset); let attemptedPaints = 0;
  canvas.context.fill = () => { attemptedPaints++; throw new Error("TEST_ONLY obsolete display refusal"); };
  if (invalidate === "lease") current = false; else if (invalidate === "detach") container.isConnected = false; else mounted.destroy();
  for (const action of Object.values(lifecycleActions)) assert.doesNotThrow(() => action(mounted, observers[0]));
  assert.equal(mounted.viewer.draw(), false); assert.equal(mounted.viewer.pick(400, 240), false); assert.equal(attemptedPaints, 0);
  assert.equal(canvas.paint.length, paints); assert.equal(JSON.stringify(canvas.dataset), dataset); assert.equal(container.textContent, text); assert.equal(JSON.stringify(data), before);
  assert.equal(observers[0].disconnected, invalidate === "destroy");
}));

test("loss of current ownership during a drawing exception cannot publish success or error", () => {
  let current = true; const { container, mounted } = mountFixture(() => current), canvas = mounted.refs.canvas, text = container.textContent, dataset = JSON.stringify(canvas.dataset);
  canvas.context.fill = () => { current = false; throw new Error("TEST_ONLY detached during paint"); };
  assert.equal(mounted.viewer.set("UX", 100), false); assert.equal(container.textContent, text); assert.equal(JSON.stringify(canvas.dataset), dataset);
  const paints = canvas.paint.length; assert.equal(mounted.viewer.pick(400, 240), false); assert.equal(mounted.viewer.fit(), false); assert.equal(canvas.paint.length, paints);
});

test("unavailable layout never collapses or retries a fallback READY; explicit fit uses the actual resized viewport beside the canvas", () => withResizeObserver(observers => {
  const data = fixture(), before = JSON.stringify(data), model = verify(data), doc = documentFixture(), create = doc.createElement; let width = 1110, height = 520;
  doc.createElement = tag => {
    const item = create(tag); if (tag === "canvas") {
      // TEST_ONLY model of actual [hidden]{display:none}: client dimensions collapse to0.
      Object.defineProperties(item, { clientWidth: { get: () => item.hidden ? 0 : width }, clientHeight: { get: () => item.hidden ? 0 : height } });
      item.hidden = true; assert.equal(item.clientWidth, 0); assert.equal(item.clientHeight, 0); item.hidden = false;
    } return item;
  };
  const container = doc.createElement("article"), mounted = viewer.mount(container, model, () => true), canvas = mounted.refs.canvas;
  assertReady(mounted); assert.equal(canvas.width, width); assert.equal(canvas.height, height);
  const css = fs.readFileSync(require.resolve("../apps/lab/static/style.css"), "utf8"), declaration = css.match(/\.fixture-field-canvas\[data-render-status="UNAVAILABLE"\]\{([^}]+)\}/)?.[1];
  assert(declaration); assert.match(declaration, /visibility:hidden/); assert.match(declaration, /pointer-events:none/); assert.doesNotMatch(declaration, /display:none/);
  const fill = canvas.context.fill; canvas.context.fill = () => { throw new Error("TEST_ONLY stable viewport paint refusal"); };
  assert.equal(mounted.viewer.set("UY", 100), false); assertUnavailable(mounted, /stable viewport/); assert.equal(canvas.clientWidth, width); assert.equal(canvas.clientHeight, height);
  canvas.context.fill = fill; const paints = canvas.paint.length, status = JSON.stringify(canvas.dataset), error = mounted.refs.error.textContent;
  for (let retry = 0; retry < 3; retry++) assert.equal(observers[0].emit(), false);
  assert.equal(canvas.paint.length, paints); assert.equal(JSON.stringify(canvas.dataset), status); assert.equal(mounted.refs.error.textContent, error); assertUnavailable(mounted, /stable viewport/);
  width = 430; height = 400; assert.equal(observers[0].emit(), false); assert.equal(canvas.clientWidth, 430); assert.equal(canvas.clientHeight, 400);
  assert.equal(canvas.paint.length, paints); assertUnavailable(mounted, /stable viewport/); assert.equal(tableRows(mounted).length, 10);
  assert.equal(mounted.viewer.fit(), true); assertReady(mounted); assert.equal(canvas.width, 430); assert.equal(canvas.height, 400); assert.equal(canvas.dataset.component, "UY"); assert.equal(canvas.dataset.displayFactor, "100");
  const viewport = canvas.parentNode, fitIndex = viewport.children.findIndex(item => walk(item).includes(mounted.refs.fit)), canvasIndex = viewport.children.indexOf(canvas);
  const workspaceIndex = container.children.findIndex(item => walk(item).includes(canvas)), rowsIndex = container.children.indexOf(mounted.refs.rows);
  assert(fitIndex >= 0 && fitIndex < canvasIndex && workspaceIndex >= 0 && workspaceIndex < rowsIndex); assert.equal(mounted.refs.fit.parentNode, mounted.refs.home.parentNode);
  assert.equal(observers[0].emit(), true, "normal automatic resize resumes only after an accepted frame"); assert.equal(JSON.stringify(data), before);
}));

test("blank pending factor survives raw loaded-ID queries and unrelated rendering actions until a complete finite update", () => withResizeObserver(observers => {
  const { data, mounted } = mountFixture(), before = JSON.stringify(data), canvas = mounted.refs.canvas;
  mounted.refs.mode.value = "deformed"; mounted.refs.scale.value = "100"; assert.equal(mounted.update(), true); assertReady(mounted); const legend = mounted.refs.legend.textContent;
  mounted.refs.scale.value = ""; mounted.refs.scale.emit("input"); assertUnavailable(mounted, /변형 보기 배율을 입력/); const paints = canvas.paint.length;
  const stillBlocked = () => { assertUnavailable(mounted, /변형 보기 배율을 입력/); assert.equal(mounted.refs.scale.value, ""); assert.equal(canvas.paint.length, paints); };
  mounted.refs.search.value = "145"; mounted.refs.search.emit("input"); stillBlocked(); assert.equal(tableRows(mounted).length, 1);
  assert.match(mounted.refs.probeBox.textContent, /절점 145.*현재 위치 표시를 확인할 수 없음.*canvas 위치 표시 안 함.*-5.00000E-02.*하중 0 \/ 0 \/ -3 N/);
  const row = tableRows(mounted)[0].textContent;
  for (const input of Object.values(mounted.refs.checks)) { input.checked = false; input.emit("change"); stillBlocked(); }
  mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change"); stillBlocked();
  for (const action of [() => mounted.viewer.draw(), () => mounted.viewer.probe(145), () => mounted.viewer.fit(), () => mounted.viewer.home(), () => mounted.viewer.set("UY", 10), () => mounted.viewer.pick(400, 240)]) { assert.equal(action(), false); stillBlocked(); }
  canvas.emit("pointerdown", { clientX: 100, clientY: 100 }); canvas.emit("pointermove", { clientX: 200, clientY: 200 }); canvas.emit("pointerup", { clientX: 200, clientY: 200 }); canvas.emit("wheel"); stillBlocked();
  for (let repeat = 0; repeat < 3; repeat++) { assert.equal(observers[0].emit(), false); stillBlocked(); }
  assert.equal(tableRows(mounted)[0].textContent, row); assert.equal(JSON.stringify(data), before);
  mounted.refs.scale.value = "25"; mounted.refs.scale.emit("input"); assertReady(mounted); assert.equal(canvas.dataset.component, "UZ"); assert.equal(canvas.dataset.displayFactor, "25");
  assert.equal(mounted.refs.legend.textContent, legend); assert.equal(tableRows(mounted)[0].textContent, row); assert.equal(JSON.stringify(data), before);
}));

test("an explicit undeformed mounted update clears blank-factor refusal without coercing the deformed request", () => {
  const { data, mounted } = mountFixture(), before = JSON.stringify(data), canvas = mounted.refs.canvas;
  mounted.refs.mode.value = "deformed"; mounted.refs.scale.value = "100"; assert.equal(mounted.update(), true);
  mounted.refs.scale.value = ""; assert.equal(mounted.update(), false); const paints = canvas.paint.length;
  mounted.refs.search.value = "43"; mounted.refs.search.emit("input"); assertUnavailable(mounted, /배율을 입력/); assert.equal(canvas.paint.length, paints);
  mounted.refs.fit.emit("click"); mounted.refs.home.emit("click"); assertUnavailable(mounted, /배율을 입력/); assert.equal(canvas.paint.length, paints); assert.equal(mounted.refs.scale.value, "");
  mounted.refs.mode.value = "undeformed"; mounted.refs.mode.emit("change"); assertReady(mounted); assert.equal(canvas.dataset.displayFactor, "0"); assert.equal(mounted.refs.scale.value, ""); assert.equal(mounted.refs.scale.disabled, true);
  assert.match(mounted.refs.deformationNote.textContent, /미변형 원본 메시/); assert.match(mounted.refs.probeBox.textContent, /절점 43.*-3.00000E-02.*하중 0 \/ 0 \/ -1 N/); assert.equal(JSON.stringify(data), before);
});

test("unsupported or incomplete configuration refusals persist through partial actions and recover only through complete mounted input", () => {
  for (const invalid of ["mode", "component", "incomplete"]) {
    const { data, mounted } = mountFixture(), before = JSON.stringify(data), canvas = mounted.refs.canvas;
    if (invalid === "mode") mounted.refs.mode.value = "unsupported"; else if (invalid === "component") mounted.refs.component.value = "STRESS";
    assert.equal(invalid === "incomplete" ? mounted.viewer.configure({ component: "UZ", deformationMode: "undeformed" }) : mounted.update(), false);
    const message = invalid === "mode" ? /형상 표시/ : invalid === "component" ? /U 성분/ : /배율/, paints = canvas.paint.length;
    mounted.refs.search.value = "145"; mounted.refs.search.emit("input"); mounted.refs.visibility.value = "xray"; mounted.refs.visibility.emit("change");
    assert.equal(mounted.viewer.set("UX", 0), false); assert.equal(mounted.viewer.draw(), false); assertUnavailable(mounted, message); assert.equal(canvas.paint.length, paints);
    assert.match(mounted.refs.probeBox.textContent, /절점 145.*현재 위치 표시를 확인할 수 없음.*-5.00000E-02.*하중 0 \/ 0 \/ -3 N/);
    mounted.refs.mode.value = "undeformed"; mounted.refs.component.value = "UX"; assert.equal(mounted.update(), true); assertReady(mounted); assert.equal(canvas.dataset.component, "UX"); assert.equal(canvas.dataset.displayFactor, "0"); assert.equal(JSON.stringify(data), before);
  }
});
