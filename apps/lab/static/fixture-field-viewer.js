"use strict";

// CPS6 display only; no CAD schema, invented U, solver, or engineering verdict.
(function (root) {
  const controls = root.fixtureFieldControls ?? (typeof module !== "undefined" && module.exports ? require("./fixture-field-controls.js") : null);
  const label = component => component === "MAGNITUDE" ? "|U|" : component;
  const triangles = [[0, 3, 5], [3, 1, 4], [5, 4, 2], [3, 4, 5]];
  // Display geometry only: these bounds/tolerances are not native or engineering criteria.
  const DISPLAY = Object.freeze({ tilePx: 24, maxAxisTiles: 64, maxReferences: 262144, areaPx2: 1e-8, barycentric: 1e-7, relativeDepth: 1e-7, segmentPx: 2, maxSegmentSteps: 256 });
  function depthIndex(triangles, width, height, span) {
    if (![width, height, span].every(value => Number.isFinite(value) && value > 0)) throw new Error("표시 깊이 범위를 확인할 수 없습니다.");
    const columns = Math.min(DISPLAY.maxAxisTiles, Math.ceil(width / DISPLAY.tilePx)), rows = Math.min(DISPLAY.maxAxisTiles, Math.ceil(height / DISPLAY.tilePx));
    const cellX = width / columns, cellY = height / rows, buckets = Array.from({ length: columns * rows }, () => []); let references = 0;
    const inside = point => [point.x, point.y, point.z].every(Number.isFinite) && point.x >= 0 && point.x <= width && point.y >= 0 && point.y <= height;
    for (const triangle of triangles) {
      const points = triangle.points;
      if (!Array.isArray(points) || points.length !== 3 || !points.every(point => [point.x, point.y, point.z].every(Number.isFinite))) throw new Error("표시 삼각형이 유한하지 않습니다.");
      const [a, b, c] = points, denominator = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y);
      if (Math.abs(denominator) <= DISPLAY.areaPx2) continue;
      const lowX = Math.max(0, Math.floor(Math.min(...points.map(point => point.x)) / cellX)), highX = Math.min(columns - 1, Math.floor(Math.max(...points.map(point => point.x)) / cellX));
      const lowY = Math.max(0, Math.floor(Math.min(...points.map(point => point.y)) / cellY)), highY = Math.min(rows - 1, Math.floor(Math.max(...points.map(point => point.y)) / cellY));
      const item = { points, denominator };
      for (let y = lowY; y <= highY; y++) for (let x = lowX; x <= highX; x++) {
        if (++references > DISPLAY.maxReferences) throw new Error("보기 깊이 검색의 화면 자원 범위를 넘었습니다. 표시 맞추기로 범위를 줄여 주세요."); buckets[y * columns + x].push(item);
      }
    }
    function frontDepth(x, y) {
      if (!inside({ x, y, z: 0 })) return null; let front = null;
      const items = buckets[Math.min(rows - 1, Math.floor(y / cellY)) * columns + Math.min(columns - 1, Math.floor(x / cellX))];
      for (const { points: [a, b, c], denominator } of items) {
        const wa = ((b.y - c.y) * (x - c.x) + (c.x - b.x) * (y - c.y)) / denominator;
        const wb = ((c.y - a.y) * (x - c.x) + (a.x - c.x) * (y - c.y)) / denominator, wc = 1 - wa - wb;
        if (Math.min(wa, wb, wc) >= -DISPLAY.barycentric) { const depth = wa * a.z + wb * b.z + wc * c.z; if (front === null || depth > front) front = depth; }
      }
      return front;
    }
    const depthTolerance = span * DISPLAY.relativeDepth;
    function visible(point) {
      if (!inside(point)) return false; const front = frontDepth(point.x, point.y);
      return front !== null && point.z >= front - Math.max(depthTolerance, 64 * Number.EPSILON * Math.max(1, Math.abs(front), Math.abs(point.z)));
    }
    function unoccluded(point) {
      if (!inside(point)) return false; const front = frontDepth(point.x, point.y);
      return front === null || point.z >= front - Math.max(depthTolerance, 64 * Number.EPSILON * Math.max(1, Math.abs(front), Math.abs(point.z)));
    }
    function pick(candidates, x, y, mode = "visible") {
      if (!["visible", "xray"].includes(mode)) throw new Error("표시 가림 정책을 선택하세요."); let nearest = null, distance = 144;
      for (const point of candidates) {
        if (!(mode === "xray" ? inside(point) : visible(point))) continue;
        const value = (point.x - x) ** 2 + (point.y - y) ** 2;
        if (value < distance || (value === distance && nearest !== null && point.z > nearest.z)) { nearest = point; distance = value; }
      }
      return nearest?.node_id ?? null;
    }
    function segments(a, b, mode = "visible") {
      if (!["visible", "xray"].includes(mode)) throw new Error("표시 가림 정책을 선택하세요.");
      const steps = Math.max(1, Math.min(DISPLAY.maxSegmentSteps, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / DISPLAY.segmentPx))), output = [];
      const point = t => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, z: a.z + (b.z - a.z) * t });
      const shown = mode === "xray" ? inside : unoccluded;
      for (let i = 0; i < steps; i++) { const start = point(i / steps), end = point((i + 1) / steps); if (shown(start) && shown(point((i + .5) / steps)) && shown(end)) output.push([start, end]); }
      return output;
    }
    return { frontDepth, visible, unoccluded, inside, pick, segments, depthTolerance, references, tiles: buckets.length };
  }
  function scene(model, component = "UZ", factor = 0) {
    controls.requireVerified(model);
    const field = model.field, positions = new Map(), values = new Map(); let min = Infinity, max = -Infinity;
    for (const node of field.nodes) {
      const value = controls.scalar(node, component); positions.set(node.node_id, controls.displayPosition(node, factor)); values.set(node.node_id, value);
      min = Math.min(min, value); max = Math.max(max, value);
    }
    return { component, factor, positions, values, min, max, triangles: field.boundary_faces.flatMap(face =>
      triangles.map(slots => ({ node_ids: slots.map(slot => face.node_ids[slot]), group: face.group, face_id: face.element_id }))) };
  }
  function createViewer(canvas, model, isCurrent, onProbe = () => {}, onDisplay = () => {}) {
    controls.requireVerified(model);
    const field = model.field, nodes = new Map(field.nodes.map(node => [node.node_id, node]));
    const boundaryIds = new Set(field.boundary_faces.flatMap(face => face.node_ids));
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    field.nodes.forEach(node => node.position_mm.forEach((value, i) => { lo[i] = Math.min(lo[i], value); hi[i] = Math.max(hi[i], value); }));
    const extent = Math.max(...hi.map((value, i) => value - lo[i])), maxForce = Math.max(...field.loads.map(load => Math.hypot(...load.force_N)));
    let requested = { component: "UZ", factor: 0, yaw: -.65, pitch: -.55, zoom: 1, center: lo.map((value, i) => (value + hi[i]) / 2), selected: null, mode: "visible", layers: { edges: true, fixed: true, loads: true } };
    let frame = null, context = null, destroyed = false, start = null, lastFailure = "", pendingConfiguration = null;
    const current = () => !destroyed && canvas.isConnected && isCurrent() === true;
    const size = () => ({ width: Math.max(240, canvas.clientWidth || 800), height: Math.max(240, canvas.clientHeight || 480) });
    const tailPosition = (position, load) => position.map((value, i) => value - load.force_N[i] / maxForce * extent * .09);
    function project(point, view, width, height) {
      const [x, y, z] = point.map((value, i) => value - view.center[i]);
      const rx = Math.cos(view.yaw) * x - Math.sin(view.yaw) * y, ry = Math.sin(view.yaw) * x + Math.cos(view.yaw) * y;
      const qy = Math.cos(view.pitch) * ry - Math.sin(view.pitch) * z, qz = Math.sin(view.pitch) * ry + Math.cos(view.pitch) * z;
      const scale = Math.min(width, height) * .78 * view.zoom / extent;
      return { x: width / 2 + rx * scale, y: height / 2 - qy * scale, z: qz };
    }
    function fitCamera(view) {
      const data = scene(model, view.component, view.factor), points = [...data.positions.values()];
      if (view.layers.loads) field.loads.forEach(load => points.push(tailPosition(data.positions.get(load.node_id), load)));
      const low = [Infinity, Infinity, Infinity], high = [-Infinity, -Infinity, -Infinity]; points.forEach(point => point.forEach((value, i) => { low[i] = Math.min(low[i], value); high[i] = Math.max(high[i], value); }));
      view.center = low.map((value, i) => (value + high[i]) / 2); view.zoom = 1; const { width, height } = size(), projectedPoints = points.map(point => project(point, view, width, height));
      const bounds = projectedPoints.reduce((value, point) => [Math.min(value[0], point.x), Math.max(value[1], point.x), Math.min(value[2], point.y), Math.max(value[3], point.y)], [Infinity, -Infinity, Infinity, -Infinity]);
      const baseScale = Math.min(width, height) * .78 / extent, rx = ((bounds[0] + bounds[1]) / 2 - width / 2) / baseScale, qy = -((bounds[2] + bounds[3]) / 2 - height / 2) / baseScale;
      const ry = Math.cos(view.pitch) * qy, dz = -Math.sin(view.pitch) * qy;
      view.center = view.center.map((value, i) => value + [Math.cos(view.yaw) * rx + Math.sin(view.yaw) * ry, -Math.sin(view.yaw) * rx + Math.cos(view.yaw) * ry, dz][i]);
      view.zoom = .84 * Math.min(width / Math.max(1, bounds[1] - bounds[0]), height / Math.max(1, bounds[3] - bounds[2]));
    }
    // Every frame-derived value is local until prepare and paint both succeed.
    function prepare(view) {
      if (!Number.isFinite(extent) || extent <= 0 || view.center.some(value => !Number.isFinite(value))) throw new Error("표시할 원본 좌표 범위를 확인할 수 없습니다.");
      const data = scene(model, view.component, view.factor), { width, height } = size();
      const projected = new Map([...data.positions].map(([node, position]) => [node, project(position, view, width, height)]));
      const ordered = data.triangles.map(triangle => ({ ...triangle, points: triangle.node_ids.map(node => projected.get(node)) }))
        .sort((a, b) => a.points.reduce((sum, point) => sum + point.z, 0) - b.points.reduce((sum, point) => sum + point.z, 0));
      const bounds = [...data.positions.values()].reduce((result, point) => { point.forEach((value, i) => { result[i] = Math.min(result[i], value); result[i + 3] = Math.max(result[i + 3], value); }); return result; }, [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity]);
      const index = depthIndex(ordered, width, height, Math.max(...bounds.slice(0, 3).map((value, i) => bounds[i + 3] - value)));
      const eligible = point => view.mode === "xray" ? index.inside(point) : index.visible(point);
      const fixed = view.layers.fixed ? field.fixed_node_ids.map(node => projected.get(node)).filter(eligible) : [], loads = [];
      if (view.layers.loads) for (const load of field.loads) {
        const point = projected.get(load.node_id); if (!eligible(point)) continue;
        const tail = project(tailPosition(data.positions.get(load.node_id), load), view, width, height), angle = Math.atan2(point.y - tail.y, point.x - tail.x);
        const pieces = index.segments(tail, point, view.mode);
        for (const delta of [-.5, .5]) pieces.push(...index.segments({ x: point.x - 4 * Math.cos(angle + delta), y: point.y - 4 * Math.sin(angle + delta), z: point.z }, point, view.mode));
        loads.push({ point, pieces });
      }
      let selected = null;
      if (view.selected !== null) {
        const point = projected.get(view.selected), kind = !boundaryIds.has(view.selected) ? "INTERIOR" : !index.inside(point) ? "OFFSCREEN" : index.visible(point) ? "VISIBLE_SURFACE" : "HIDDEN_SURFACE";
        selected = { node_id: view.selected, kind, onscreen: index.inside(point), cueShown: index.inside(point) && (view.mode === "xray" || kind === "VISIBLE_SURFACE"), mode: view.mode };
      }
      const origin = project(view.center, view, width, height), axes = ["X", "Y", "Z"].map((name, axis) => { const target = project(view.center.map((value, i) => value + (i === axis ? extent * .08 / view.zoom : 0)), view, width, height);
        return { name, color: ["#9b3036", "#477245", "#154991"][axis], x: 48 + target.x - origin.x, y: height - 48 + target.y - origin.y }; });
      const status = { ok: true, component: view.component, factor: view.factor, min: data.min, max: data.max, mode: view.mode, layers: { ...view.layers },
        fixed: { drawn: fixed.length, total: field.fixed_node_ids.length, visible: field.fixed_node_ids.filter(node => index.visible(projected.get(node))).length },
        loads: { drawn: loads.length, total: field.loads.length, visible: field.loads.filter(load => index.visible(projected.get(load.node_id))).length }, selected,
        displayDepthTolerance: index.depthTolerance, tileReferences: index.references, tiles: index.tiles };
      return { data, width, height, projected, ordered, index, fixed, loads, selected, axes, status, view };
    }
    function paint(candidate) {
      context ??= canvas.getContext("2d"); if (!context) throw new Error("FEA 메시를 표시할 2D canvas를 사용할 수 없습니다.");
      const ctx = context, { data, width, height, view } = candidate, ratio = Math.max(1, Math.min(2, root.devicePixelRatio || 1));
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height); ctx.fillStyle = "#f3f7f9"; ctx.fillRect(0, 0, width, height); ctx.lineWidth = .35; ctx.strokeStyle = "rgba(34,59,70,.22)";
      for (const triangle of candidate.ordered) {
        ctx.beginPath(); triangle.points.forEach((point, i) => i ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)); ctx.closePath();
        const value = triangle.node_ids.reduce((sum, node) => sum + data.values.get(node) / 3, 0), t = data.max === data.min ? .5 : Math.max(0, Math.min(1, (value - data.min) / (data.max - data.min)));
        ctx.fillStyle = `rgb(${Math.round(45 + 190 * t)},${Math.round(121 + 32 * (1 - Math.abs(t - .5) * 2))},${Math.round(190 - 144 * t)})`; ctx.fill(); if (view.layers.edges) ctx.stroke();
      }
      function dot(point, color, radius, square = false) { ctx.fillStyle = color; ctx.beginPath(); if (square) ctx.rect(point.x - radius, point.y - radius, radius * 2, radius * 2); else ctx.arc(point.x, point.y, radius, 0, 2 * Math.PI); ctx.fill(); }
      candidate.fixed.forEach(point => dot(point, "#154991", 2, true));
      for (const load of candidate.loads) { dot(load.point, "#9b3036", 2); ctx.strokeStyle = "#9b3036"; ctx.lineWidth = 1; if (load.pieces.length) { ctx.beginPath(); load.pieces.forEach(([a, b]) => { ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); }); ctx.stroke(); } }
      if (candidate.selected?.cueShown) dot(candidate.projected.get(view.selected), "#fbcc42", 5);
      for (const axis of candidate.axes) { ctx.strokeStyle = axis.color; ctx.beginPath(); ctx.moveTo(48, height - 48); ctx.lineTo(axis.x, axis.y); ctx.stroke(); ctx.fillStyle = axis.color; ctx.font = "12px sans-serif"; ctx.fillText(axis.name, axis.x + 3, axis.y - 3); }
    }
    function render(action = () => {}, notifyProbe = false) {
      if (!current()) return false;
      const next = { ...requested, center: [...requested.center], layers: { ...requested.layers } };
      try {
        action(next); requested = next; frame = null;
        if (pendingConfiguration?.refusal) throw new Error(pendingConfiguration.refusal);
        const candidate = prepare(next); if (!current()) return false;
        paint(candidate); if (!current()) return false;
        frame = candidate; lastFailure = ""; canvas.hidden = false; canvas.setAttribute("aria-hidden", "false"); canvas.dataset.renderStatus = "READY"; canvas.dataset.pickingEnabled = "true"; delete canvas.dataset.renderError;
        canvas.dataset.component = next.component; canvas.dataset.displayFactor = String(next.factor); canvas.dataset.nativeNodeCount = String(field.node_count);
        canvas.dataset.visibilityMode = next.mode; canvas.dataset.fixedDrawn = String(candidate.fixed.length); canvas.dataset.loadsDrawn = String(candidate.loads.length);
        onDisplay(candidate.status); if (notifyProbe && next.selected !== null && current()) onProbe(nodes.get(next.selected), candidate.selected); return true;
      } catch (failure) {
        if (!current()) return false; requested = next; frame = null; lastFailure = pendingConfiguration?.refusal || failure?.message || String(failure);
        // Failure publication cannot depend on a working drawing context.
        // CSS visibility retains the real viewport; [hidden] would collapse it to zero.
        canvas.hidden = false; canvas.setAttribute("aria-hidden", "true"); canvas.dataset.renderStatus = "UNAVAILABLE"; canvas.dataset.pickingEnabled = "false"; canvas.dataset.renderError = lastFailure;
        for (const key of ["component", "displayFactor", "visibilityMode", "fixedDrawn", "loadsDrawn"]) delete canvas.dataset[key];
        const selected = nodes.has(next.selected) ? { node_id: next.selected, kind: "UNAVAILABLE", onscreen: null, cueShown: false, mode: next.mode } : null;
        try { onDisplay({ ok: false, message: lastFailure, configurationRefused: Boolean(pendingConfiguration?.refusal), mode: next.mode, layers: { ...next.layers }, selected }); if (notifyProbe && selected && current()) onProbe(nodes.get(next.selected), selected); } catch { /* The frame remains invalid if its owning DOM cannot report. */ }
        return false;
      }
    }
    const set = (component, factor) => render(view => { view.component = component; view.factor = factor; });
    const fit = (component = requested.component, factor = requested.factor) => render(view => { view.component = component; view.factor = factor; fitCamera(view); });
    const home = () => render(view => { view.yaw = -.65; view.pitch = -.55; fitCamera(view); });
    const probe = nodeId => render(view => { if (!nodes.has(nodeId)) throw new Error("이 메시의 실제 절점 ID가 아닙니다."); view.selected = nodeId; }, true);
    const clearProbe = () => render(view => { view.selected = null; });
    const overlay = (value, policy) => render(view => {
      if (!value || Object.keys(value).sort().join(",") !== "edges,fixed,loads" || !Object.values(value).every(item => typeof item === "boolean") || !["visible", "xray"].includes(policy)) throw new Error("표시 레이어·가림 정책을 선택하세요.");
      view.layers = { ...value }; view.mode = policy;
    });
    function configure(options) {
      return render(view => {
        // Capture the complete raw request before validation; partial actions cannot discard it.
        pendingConfiguration = { component: options?.component, deformationMode: options?.deformationMode, scaleText: options?.scaleText, refusal: null };
        try {
          if (!["undeformed", "deformed"].includes(pendingConfiguration.deformationMode)) throw new Error("형상 표시를 선택하세요.");
          if (typeof pendingConfiguration.scaleText !== "string" || (pendingConfiguration.deformationMode === "deformed" && !pendingConfiguration.scaleText.trim())) throw new Error("변형 보기 배율을 입력하세요.");
          if (!controls.COMPONENTS.includes(pendingConfiguration.component)) throw new Error("지원하는 U 성분을 선택하세요.");
          const factor = pendingConfiguration.deformationMode === "undeformed" ? 0 : Number(pendingConfiguration.scaleText);
          if (!Number.isFinite(factor) || factor < 0 || factor > controls.LIMITS.factor) throw new Error(`보기 배율은 0~${controls.LIMITS.factor}의 유한한 수치여야 합니다.`);
          view.component = pendingConfiguration.component; view.factor = factor;
        } catch (failure) { pendingConfiguration.refusal = failure?.message || String(failure); throw failure; }
        if (options.home) { view.yaw = -.65; view.pitch = -.55; } if (options.fit || options.home) fitCamera(view);
      });
    }
    function pickAt(coordinates) {
      let chosen = false;
      const rendered = render(view => {
        if (!frame) throw new Error(lastFailure || "현재 표시가 확인되지 않아 canvas 선택을 할 수 없습니다. 표시 맞추기를 사용하세요.");
        const { x, y } = coordinates();
        const node = frame.index.pick([...boundaryIds].map(node_id => ({ ...frame.projected.get(node_id), node_id })), x, y, frame.view.mode);
        if (node !== null) { view.selected = node; chosen = true; }
      }, true);
      return rendered && chosen;
    }
    const pick = (x, y) => pickAt(() => ({ x, y }));
    canvas.addEventListener("pointerdown", event => { if (!current()) return; render(() => { start = { x: event.clientX, y: event.clientY, distance: 0 }; canvas.setPointerCapture?.(event.pointerId); }); });
    canvas.addEventListener("pointermove", event => {
      if (!current() || !start) return;
      render(view => { const dx = event.clientX - start.x, dy = event.clientY - start.y; start.distance += Math.abs(dx) + Math.abs(dy); start.x = event.clientX; start.y = event.clientY;
        if (start.distance > 3) { view.yaw += dx * .008; view.pitch = Math.max(-1.5, Math.min(1.5, view.pitch + dy * .008)); } });
    });
    canvas.addEventListener("pointerup", event => {
      if (!current() || !start) return; const dragged = start.distance > 3; start = null; if (dragged) return;
      pickAt(() => { const bounds = canvas.getBoundingClientRect(); return { x: event.clientX - bounds.left, y: event.clientY - bounds.top }; });
    });
    canvas.addEventListener("pointercancel", () => { if (current()) render(() => { start = null; }); });
    canvas.addEventListener("wheel", event => { if (!current()) return; render(view => { event.preventDefault(); view.zoom = Math.max(.02, Math.min(20, view.zoom * (event.deltaY < 0 ? 1.1 : .9))); }); }, { passive: false });
    let observer = null;
    render(view => { if (typeof root.ResizeObserver === "function") { observer = new root.ResizeObserver(() => current() && frame !== null ? render() : false); observer.observe(canvas); } fitCamera(view); });
    return { draw: () => render(), set, configure, probe, clearProbe, overlay, pick, fit, home,
      destroy: () => { destroyed = true; frame = null; try { observer?.disconnect(); } catch { /* No current owner remains. */ } }, snapshot: () => scene(model, requested.component, requested.factor) };
  }
  function mount(container, model, isCurrent) {
    controls.requireVerified(model); if (!container.isConnected || isCurrent() !== true) return null;
    const doc = container.ownerDocument || root.document, field = model.field, metadata = model.metadata;
    const node = (tag, text, className) => { const item = doc.createElement(tag); if (text !== undefined) item.textContent = String(text); if (className) item.className = className; return item; };
    const current = () => container.isConnected && isCurrent() === true;
    const button = (text, handler) => { const item = node("button", text, "button subtle compact"); item.type = "button"; item.addEventListener("click", () => { if (current()) handler(); }); return item; };
    const chooser = (caption, values) => { const item = node("select"), wrapper = node("label", caption); values.forEach(([value, text]) => { const option = node("option", text); option.value = value; item.append(option); }); wrapper.append(item); return { item, wrapper }; };
    container.replaceChildren();
    const workspace = node("div", undefined, "fixture-field-workspace"), viewport = node("div", undefined, "fixture-field-viewport"), properties = node("aside", undefined, "fixture-field-properties");
    properties.setAttribute("aria-label", "같은 해석의 필드 표시와 절점 정보"); workspace.append(viewport, properties);
    container.append(node("p", `메시 ${field.mesh_size_max_mm} mm · 전체 ${field.node_count}절점 · ${field.element_count} C3D10 · ${field.boundary_face_count} CPS6`, "fixture-field-summary"), workspace);
    properties.append(node("p", "원본 좌표 mm · U mm · 하중 N · SOLVER_GLOBAL_CARTESIAN (전체 XYZ 축)", "hint"),
      node("p", `정적 step ${field.static.step} / increment ${field.static.increment} · load_parameter ${field.static.load_parameter} (시간 값 아님)`, "hint"),
      node("p", `UNKNOWN · ${metadata.decision} · 미확인 검사 ${metadata.unknownCount}개 · ${metadata.sensitivity === "NOT_ASSESSED" ? "선택 메시 민감도 미평가" : "메시 검사 판정은 위 원본 기록 참조"}`, "fixture-field-qualification"));
    const settings = node("div", undefined, "fixture-field-settings");
    const component = chooser("표시할 물리 변위 성분", controls.COMPONENTS.map(value => [value, `${label(value)} (mm)`])); component.item.value = "UZ";
    const mode = chooser("형상 표시", [["undeformed", "미변형 원본 메시"], ["deformed", "변형 표시 (보기 배율)"]]); mode.item.value = "undeformed";
    const scale = node("input"), scaleLabel = node("label", "변형 보기 배율 · display-only"); scale.type = "number"; scale.min = "0"; scale.max = String(controls.LIMITS.factor); scale.step = "any"; scale.value = "100"; scale.disabled = true; scaleLabel.append(scale);
    settings.append(component.wrapper, mode.wrapper, scaleLabel); properties.append(settings);
    const layers = node("div", undefined, "fixture-field-layers"), checks = {};
    for (const [key, text] of [["edges", "메시 선"], ["fixed", "고정 XYZ"], ["loads", "saddle 하중"]]) {
      const wrapper = node("label", text), input = node("input"); input.type = "checkbox"; input.checked = true; wrapper.append(input); layers.append(wrapper); checks[key] = input;
    }
    const visibility = chooser("표시·클릭 가림 정책", [["visible", "보이는 외곽면만 (기본)"], ["xray", "X-ray 투과 검사 (숨은 외곽절점 포함)"]]); visibility.item.value = "visible"; layers.append(visibility.wrapper);
    const policy = node("p", undefined, "fixture-field-visibility"); policy.setAttribute("aria-live", "polite"); properties.append(layers, policy);
    const deformationNote = node("p", undefined, "fixture-field-display-note"), error = node("p", "", "fixture-field-error"), legend = node("p", undefined, "fixture-field-legend"); error.hidden = true;
    const canvas = node("canvas", undefined, "fixture-field-canvas"); canvas.setAttribute("aria-label", "같은 해석 기록의 실제 CPS6 외곽 메시와 절점 변위. 드래그로 회전하고 절점을 선택하세요."); canvas.tabIndex = 0;
    const tools = node("div", undefined, "button-row fixture-field-view-actions"), fitButton = button("현재 표시 맞추기", () => update(true)), homeButton = button("기본 시점", () => update(true, true)); tools.append(fitButton, homeButton);
    viewport.append(error, tools, canvas, legend, node("p", "드래그로 회전 · 휠로 확대 · 외곽 절점을 클릭해 원본 값을 확인합니다.", "hint")); properties.append(deformationNote);
    const probeBox = node("div", undefined, "fixture-field-probe"), searchLabel = node("label", "실제 절점 ID로 찾기"), search = node("input"); search.type = "number"; search.min = "1"; search.step = "1"; search.placeholder = "빈칸이면 전체 절점"; searchLabel.append(search);
    const rows = node("div", undefined, "fixture-field-rows"), pager = node("div", undefined, "button-row separated"), pageCaption = node("span", undefined, "hint");
    properties.append(searchLabel, probeBox); container.append(rows, pager);
    let page = 0, selectedRows = field.nodes, destroyed = false;
    const fixed = new Set(field.fixed_node_ids), loads = new Map(field.loads.map(load => [load.node_id, load.force_N]));
    let selectedNode = null;
    function probeText(value, selection) {
      const kind = { VISIBLE_SURFACE: "보이는 외곽 절점", HIDDEN_SURFACE: "앞면에 가려진 뒤쪽 외곽 절점", INTERIOR: "내부 절점", OFFSCREEN: "화면 밖 외곽 절점", UNAVAILABLE: "현재 위치 표시를 확인할 수 없음" }[selection.kind];
      const cue = selection.cueShown ? selection.mode === "xray" ? "X-ray 투과 위치 표시" : "보이는 위치 표시" : "원본 표로 확인 · canvas 위치 표시 안 함";
      probeBox.textContent = `절점 ${value.node_id} · ${kind} · ${cue}${selection.onscreen === false ? " · 현재 화면 밖" : ""} · 원본 XYZ ${value.position_mm.join(" / ")} mm · U ${value.displacement_tokens.join(" / ")} mm · |U| ${Math.hypot(...value.displacement_mm)} mm${fixed.has(value.node_id) ? " · 고정 XYZ" : ""}${loads.has(value.node_id) ? ` · 하중 ${loads.get(value.node_id).join(" / ")} N` : ""}`;
    }
    function showProbe(value, selection) {
      if (!current() || destroyed) return; selectedNode = value; search.value = String(value.node_id); selectedRows = [value]; page = 0; probeText(value, selection);
      drawTable();
    }
    function showPolicy(status) {
      if (!current() || destroyed) return;
      if (!status.ok) {
        error.hidden = false; error.textContent = `표시 불가: ${status.message} 원본 절점 표는 계속 조회할 수 있습니다. ${status.configurationRefused ? "표시 설정을 올바르게 입력한 뒤 다시 확인하세요." : "현재 표시 맞추기로 다시 확인하세요."}`;
        legend.textContent = "현재 canvas 범례·위치 표시는 확인되지 않았습니다. 원본 물리값은 절점 표와 기록을 따릅니다.";
        deformationNote.textContent = "현재 변형 위치 표시 없음 · 원본 mm 좌표와 U는 표에 보존됩니다.";
        policy.className = "fixture-field-visibility unavailable";
        policy.textContent = `표시 불가 · canvas 클릭 비활성 · 현재 표시 개수 미확인 · 고정 원본 ${field.fixed_node_ids.length} / 하중 원본 ${field.loads.length}. 저장된 BC·하중·절점 수치가 없어진 것은 아닙니다.`;
        if (selectedNode) probeText(selectedNode, { node_id: selectedNode.node_id, kind: "UNAVAILABLE", onscreen: null, cueShown: false, mode: status.mode });
        return;
      }
      error.hidden = true; error.textContent = "";
      legend.textContent = `${label(status.component)} · 전체 절점 물리값 ${status.min} ~ ${status.max} mm (배율 미적용)`;
      deformationNote.textContent = status.factor === 0 ? "미변형 원본 메시 · 원래 mm 좌표. 표와 색 범위는 실제 물리 변위입니다." : `보기 배율 ${status.factor}× · display-only: x + ${status.factor}U. 표시 변형은 실제 물리 변위가 아니며 표와 색 범위에는 배율을 곱하지 않습니다.`;
      policy.className = `fixture-field-visibility${status.mode === "xray" ? " xray" : ""}`;
      policy.textContent = `${status.mode === "xray" ? "X-ray 투과 검사: 뒤쪽 외곽 절점도 표시·클릭 후보입니다. 내부 절점은 ID 검색으로 확인합니다." : "보이는 외곽면만 표시·클릭합니다. 뒤쪽 및 내부 절점은 숨기며 ID 검색으로 원본을 확인할 수 있습니다."} 고정 표시 ${status.fixed.drawn} / 원본 ${status.fixed.total} (현재 보이는 ${status.fixed.visible}) · 하중 표시 ${status.loads.drawn} / 원본 ${status.loads.total} (현재 보이는 ${status.loads.visible}). 가려진 화살표 구간은 기본 보기에서 숨깁니다. 표시 개수는 전체 원본 개수가 아닙니다.`;
      if (selectedNode && status.selected?.node_id === selectedNode.node_id) probeText(selectedNode, status.selected);
      else if (selectedNode && status.selected === null) { selectedNode = null; probeBox.textContent = ""; }
    }
    const viewer = createViewer(canvas, model, () => current() && !destroyed, showProbe, showPolicy);
    function drawTable() {
      if (!current() || destroyed) return; const table = node("table"), head = node("tr");
      ["절점", "원본 X / Y / Z (mm)", "UX (mm)", "UY (mm)", "UZ (mm)", "|U| (mm)", "고정 XYZ", "실제 Fx / Fy / Fz (N)"].forEach(text => { const cell = node("th", text); cell.scope = "col"; head.append(cell); });
      const thead = node("thead"); thead.append(head); const body = node("tbody"), start = page * 50, visible = selectedRows.slice(start, start + 50);
      visible.forEach(value => { const row = node("tr"); row.dataset.nodeId = String(value.node_id);
        [String(value.node_id), value.position_mm.join(" / "), ...value.displacement_tokens, String(Math.hypot(...value.displacement_mm)), fixed.has(value.node_id) ? "XYZ 고정" : "—", loads.get(value.node_id)?.join(" / ") ?? "—"].forEach(text => row.append(node("td", text))); body.append(row); });
      table.append(thead, body); const scroll = node("div", undefined, "table-scroll"); scroll.append(table); rows.replaceChildren(scroll);
      pageCaption.textContent = selectedRows.length ? `${start + 1}–${start + visible.length} / ${selectedRows.length}절점 (전체 원본 ${field.node_count}개)` : "이 메시의 절점 ID가 아닙니다.";
      previous.disabled = page === 0; next.disabled = start + 50 >= selectedRows.length;
    }
    const previous = button("이전 50개", () => { if (page > 0) { page--; drawTable(); } }), next = button("다음 50개", () => { if ((page + 1) * 50 < selectedRows.length) { page++; drawTable(); } });
    pager.append(previous, next, pageCaption);
    function update(fitView = false, homeView = false) {
      if (!current() || destroyed) return false;
      scale.disabled = mode.item.value === "undeformed";
      return viewer.configure({ component: component.item.value, deformationMode: mode.item.value, scaleText: scale.value, fit: fitView === true, home: homeView === true });
    }
    component.item.addEventListener("change", update); mode.item.addEventListener("change", update); scale.addEventListener("input", update);
    function updateOverlay() {
      if (!current() || destroyed) return false;
      return viewer.overlay(Object.fromEntries(Object.entries(checks).map(([key, input]) => [key, input.checked])), visibility.item.value);
    }
    Object.values(checks).forEach(input => input.addEventListener("change", updateOverlay)); visibility.item.addEventListener("change", updateOverlay);
    search.addEventListener("input", () => {
      if (!current() || destroyed) return; page = 0; const raw = search.value.trim(); selectedRows = raw ? field.nodes.filter(value => String(value.node_id) === raw) : field.nodes;
      selectedNode = null; probeBox.textContent = ""; if (selectedRows.length === 1) viewer.probe(selectedRows[0].node_id); else { viewer.clearProbe(); drawTable(); }
    });
    const fullRange = scene(model, "MAGNITUDE", 0);
    container.append(node("p", `전체 절점 최대 |U| ${fullRange.max} mm · 기존 max_displacement는 하중 안장의 |UZ| 통계 ${metadata.loadedMaximumUz ?? "미제공"} mm입니다. 두 값은 별도 범위이며 기존 metric을 바꾸지 않습니다.`, "fixture-field-statistic"));
    const provenance = node("details", undefined, "raw-detail fixture-field-source"); provenance.append(node("summary", "검증 상세 · 부모·개정·생산 버전·원본"),
      node("p", "파란 사각형은 고정 XYZ, 붉은 화살표는 실제 saddle 하중입니다. 화살표는 실제 하중 방향으로 절점에 도달하며 길이는 보기용입니다. N 값은 절점 표를 따릅니다."),
      node("p", "외곽 CPS6의 6절점을 네 삼각형으로 표시합니다. 면 색은 세 절점 성분의 평균 표시이며, 선택 절점 표는 저장된 원본 U입니다."),
      node("p", `실험 ${metadata.experimentId} · 부모 CAD ${metadata.parentId}`), node("p", `CAD revision ${metadata.revision}`, "mono"),
      node("p", `필드 adapter ${metadata.fieldProducer} · 결과 adapter ${metadata.resultProducer} · Core producer ${metadata.coreCommit ?? "미기록"}`, "mono"),
      node("p", `Pinned source ${metadata.upstreamCommit ?? "미기록"} · ${metadata.saddleGroup} · 총 하중 ${metadata.totalForceN} N`, "mono"),
      node("p", `필드 ${model.artifact.size_bytes} bytes · SHA-256 ${model.artifact.sha256}`, "mono"));
    Object.values(field.sources).forEach(source => provenance.append(node("p", `${source.path} · ${source.bytes} bytes · SHA-256 ${source.sha256}`, "mono"))); container.append(provenance);
    drawTable(); return { viewer, update, updateOverlay, refs: { component: component.item, mode: mode.item, scale, canvas, legend, error, search, rows, probeBox, pageCaption, previous, next, deformationNote, provenance, checks, visibility: visibility.item, policy, fit: fitButton, home: homeButton },
      destroy: () => { destroyed = true; viewer.destroy(); } };
  }
  const api = { scene, createViewer, mount, depthIndex, DISPLAY };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.fixtureFieldViewer = api;
})(globalThis);
