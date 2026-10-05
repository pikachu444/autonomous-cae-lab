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
function tableRows(mounted) { return walk(mounted.refs.rows).filter(item => item.tagName === "TR" && item.dataset.nodeId); }
async function spin(predicate) { for (let tick = 0; tick < 150 && !predicate(); tick++) await new Promise(resolve => setImmediate(resolve)); assert(predicate(), "bounded TEST_ONLY async condition"); }

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
  assert.throws(() => mounted.viewer.set("STRESS", 0)); assert.equal(mounted.refs.canvas.paint.length, before);
  mounted.refs.mode.value = "deformed"; mounted.refs.scale.value = ""; assert.equal(mounted.update(), false); assert.equal(mounted.refs.canvas.hidden, true); assert.match(mounted.refs.error.textContent, /배율/);
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
  assert.throws(() => mounted.viewer.probe(210)); mounted.refs.search.value = "210"; mounted.refs.search.emit("input"); assert.equal(tableRows(mounted).length, 0); assert.match(mounted.refs.pageCaption.textContent, /절점 ID가 아닙니다/);
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
  const doc = documentFixture(), requests = [], sandbox = { document: doc, Node: TinyNode, window: { fixtureFieldControls: controls, fixtureFieldViewer: viewer },
    location: { hash: "#results" }, URL, URLSearchParams, Intl, Uint8Array, console, setTimeout: () => { throw new Error("No app timers or live jobs permitted"); }, clearTimeout() {},
    fetch: (path, options) => new Promise((resolve, reject) => requests.push({ path, options, resolve, reject })) };
  vm.createContext(sandbox); vm.runInContext(appSource.slice(0, bootBoundary) + "\n" + appSource.slice(switchStart, switchEnd)
    + "\nrenderResearchAnswers=()=>{};invalidateModelDiscovery=()=>{};renderDiscovery=()=>{};renderOverview=()=>{};renderStudy=()=>{};renderRegistry=()=>{};globalThis.fieldApp={state,renderFixtureFields,switchStore};", sandbox);
  const app = sandbox.fieldApp; app.state.overview = { active_store: "TEST_ONLY-local", stores: [{ id: "TEST_ONLY-local", writable: true }] }; app.state.selectedExperiment = data.inspection;
  return { app, requests, data, root: doc.createElement("main"), doc };
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
  assert.equal(h.app.state.overview.active_store, "TEST_ONLY-other"); assert.equal(h.app.state.selectedExperiment, null); assert.equal(h.app.state.fixtureViewer, null);
});
