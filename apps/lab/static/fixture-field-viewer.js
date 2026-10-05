"use strict";

// CPS6 display only; no CAD schema, invented U, solver, or engineering verdict.
(function (root) {
  const controls = root.fixtureFieldControls ?? (typeof module !== "undefined" && module.exports ? require("./fixture-field-controls.js") : null);
  const label = component => component === "MAGNITUDE" ? "|U|" : component;
  const triangles = [[0, 3, 5], [3, 1, 4], [5, 4, 2], [3, 4, 5]];
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
  function createViewer(canvas, model, isCurrent, onProbe = () => {}) {
    controls.requireVerified(model);
    const ctx = canvas.getContext("2d"); if (!ctx) throw new Error("FEA 메시를 표시할 2D canvas를 사용할 수 없습니다.");
    const field = model.field, nodes = new Map(field.nodes.map(node => [node.node_id, node]));
    const boundaryIds = new Set(field.boundary_faces.flatMap(face => face.node_ids));
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    field.nodes.forEach(node => node.position_mm.forEach((value, i) => { lo[i] = Math.min(lo[i], value); hi[i] = Math.max(hi[i], value); }));
    const center = lo.map((value, i) => (value + hi[i]) / 2), extent = Math.max(...hi.map((value, i) => value - lo[i]));
    if (!Number.isFinite(extent) || extent <= 0 || center.some(value => !Number.isFinite(value))) throw new Error("표시할 원본 좌표 범위를 확인할 수 없습니다.");
    let component = "UZ", factor = 0, yaw = -.65, pitch = -.55, zoom = 1, selected = null, destroyed = false, projected = new Map(), start = null;
    const current = () => !destroyed && canvas.isConnected && isCurrent() === true;
    function project(point, width, height) {
      const [x, y, z] = point.map((value, i) => value - center[i]);
      const rx = Math.cos(yaw) * x - Math.sin(yaw) * y, ry = Math.sin(yaw) * x + Math.cos(yaw) * y;
      const qy = Math.cos(pitch) * ry - Math.sin(pitch) * z, qz = Math.sin(pitch) * ry + Math.cos(pitch) * z;
      const scale = Math.min(width, height) * .78 * zoom / extent;
      return { x: width / 2 + rx * scale, y: height / 2 - qy * scale, z: qz };
    }
    function color(value, min, max) {
      const t = max === min ? .5 : Math.max(0, Math.min(1, (value - min) / (max - min)));
      return `rgb(${Math.round(45 + 190 * t)},${Math.round(121 + 32 * (1 - Math.abs(t - .5) * 2))},${Math.round(190 - 144 * t)})`;
    }
    function dot(point, colorValue, radius, square = false) {
      ctx.fillStyle = colorValue; ctx.beginPath(); if (square) ctx.rect(point.x - radius, point.y - radius, radius * 2, radius * 2); else ctx.arc(point.x, point.y, radius, 0, 2 * Math.PI); ctx.fill();
    }
    function draw() {
      if (!current()) return false;
      const data = scene(model, component, factor), ratio = Math.max(1, Math.min(2, root.devicePixelRatio || 1));
      const width = Math.max(240, canvas.clientWidth || 800), height = Math.max(240, canvas.clientHeight || 480);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height); ctx.fillStyle = "#f3f7f9"; ctx.fillRect(0, 0, width, height);
      projected = new Map([...data.positions].map(([node, position]) => [node, project(position, width, height)]));
      const ordered = data.triangles.map(triangle => ({ ...triangle, points: triangle.node_ids.map(node => projected.get(node)) }))
        .sort((a, b) => a.points.reduce((sum, point) => sum + point.z, 0) - b.points.reduce((sum, point) => sum + point.z, 0));
      ctx.lineWidth = .35; ctx.strokeStyle = "rgba(34,59,70,.22)";
      for (const triangle of ordered) {
        ctx.beginPath(); triangle.points.forEach((point, i) => i ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)); ctx.closePath();
        ctx.fillStyle = color(triangle.node_ids.reduce((sum, node) => sum + data.values.get(node) / 3, 0), data.min, data.max); ctx.fill(); ctx.stroke();
      }
      field.fixed_node_ids.forEach(node => dot(projected.get(node), "#154991", 2, true));
      const maxForce = Math.max(...field.loads.map(load => Math.hypot(...load.force_N)));
      for (const load of field.loads) {
        const point = projected.get(load.node_id), position = data.positions.get(load.node_id);
        const end = project(position.map((value, i) => value + load.force_N[i] / maxForce * extent * .09), width, height);
        dot(point, "#9b3036", 2); const angle = Math.atan2(end.y - point.y, end.x - point.x);
        ctx.strokeStyle = "#9b3036"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(point.x, point.y); ctx.lineTo(end.x, end.y);
        for (const delta of [-.5, .5]) { ctx.moveTo(end.x, end.y); ctx.lineTo(end.x - 4 * Math.cos(angle + delta), end.y - 4 * Math.sin(angle + delta)); } ctx.stroke();
      }
      if (selected !== null) dot(projected.get(selected), "#fbcc42", 5);
      const origin = project(center, width, height);
      for (const [axis, name] of ["X", "Y", "Z"].entries()) {
        const target = project(center.map((value, i) => value + (i === axis ? extent * .08 / zoom : 0)), width, height);
        const x = 48 + target.x - origin.x, y = height - 48 + target.y - origin.y;
        ctx.strokeStyle = ["#9b3036", "#477245", "#154991"][axis]; ctx.beginPath(); ctx.moveTo(48, height - 48); ctx.lineTo(x, y); ctx.stroke();
        ctx.fillStyle = ctx.strokeStyle; ctx.font = "12px sans-serif"; ctx.fillText(name, x + 3, y - 3);
      }
      canvas.dataset.component = component; canvas.dataset.displayFactor = String(factor); canvas.dataset.nativeNodeCount = String(field.node_count);
      return true;
    }
    function set(componentValue, factorValue) {
      if (!current()) return false; scene(model, componentValue, factorValue); component = componentValue; factor = factorValue; return draw();
    }
    function probe(nodeId) {
      if (!current()) return false; if (!nodes.has(nodeId)) throw new Error("이 메시의 실제 절점 ID가 아닙니다."); selected = nodeId; draw(); onProbe(nodes.get(nodeId)); return true;
    }
    canvas.addEventListener("pointerdown", event => { if (!current()) return; start = { x: event.clientX, y: event.clientY, distance: 0 }; canvas.setPointerCapture?.(event.pointerId); });
    canvas.addEventListener("pointermove", event => {
      if (!current() || !start) return; const dx = event.clientX - start.x, dy = event.clientY - start.y;
      start.distance += Math.abs(dx) + Math.abs(dy); start.x = event.clientX; start.y = event.clientY;
      if (start.distance > 3) { yaw += dx * .008; pitch = Math.max(-1.5, Math.min(1.5, pitch + dy * .008)); draw(); }
    });
    canvas.addEventListener("pointerup", event => {
      if (!current() || !start) return; const dragged = start.distance > 3; start = null; if (dragged) return;
      const bounds = canvas.getBoundingClientRect(), x = event.clientX - bounds.left, y = event.clientY - bounds.top; let nearest = null, distance = 144;
      for (const node of boundaryIds) { const p = projected.get(node), d = (p.x - x) ** 2 + (p.y - y) ** 2;
        if (d < distance || (d === distance && nearest !== null && p.z > projected.get(nearest).z)) { nearest = node; distance = d; } }
      if (nearest !== null) probe(nearest);
    });
    canvas.addEventListener("pointercancel", () => { start = null; });
    canvas.addEventListener("wheel", event => { if (!current()) return; event.preventDefault(); zoom = Math.max(.5, Math.min(3, zoom * (event.deltaY < 0 ? 1.1 : .9))); draw(); }, { passive: false });
    const observer = typeof root.ResizeObserver === "function" ? new root.ResizeObserver(() => draw()) : null; observer?.observe(canvas);
    draw(); return { draw, set, probe, home: () => { if (!current()) return false; yaw = -.65; pitch = -.55; zoom = 1; return draw(); },
      destroy: () => { destroyed = true; observer?.disconnect(); }, snapshot: () => scene(model, component, factor) };
  }
  function mount(container, model, isCurrent) {
    controls.requireVerified(model); if (!container.isConnected || isCurrent() !== true) return null;
    const doc = container.ownerDocument || root.document, field = model.field, metadata = model.metadata;
    const node = (tag, text, className) => { const item = doc.createElement(tag); if (text !== undefined) item.textContent = String(text); if (className) item.className = className; return item; };
    const current = () => container.isConnected && isCurrent() === true;
    const button = (text, handler) => { const item = node("button", text, "button subtle compact"); item.type = "button"; item.addEventListener("click", () => { if (current()) handler(); }); return item; };
    const chooser = (caption, values) => { const item = node("select"), wrapper = node("label", caption); values.forEach(([value, text]) => { const option = node("option", text); option.value = value; item.append(option); }); wrapper.append(item); return { item, wrapper }; };
    container.replaceChildren();
    container.append(node("p", `메시 ${field.mesh_size_max_mm} mm · 전체 ${field.node_count}절점 · ${field.element_count} C3D10 · ${field.boundary_face_count} CPS6`, "fixture-field-summary"),
      node("p", "원본 좌표 mm · U mm · 하중 N · SOLVER_GLOBAL_CARTESIAN (전체 XYZ 축)", "hint"),
      node("p", `정적 step ${field.static.step} / increment ${field.static.increment} · load_parameter ${field.static.load_parameter} (시간 값 아님)`, "hint"),
      node("p", `UNKNOWN · ${metadata.decision} · 미확인 검사 ${metadata.unknownCount}개 · ${metadata.sensitivity === "NOT_ASSESSED" ? "선택 메시 민감도 미평가" : "메시 검사 판정은 위 원본 기록 참조"}`, "fixture-field-qualification"));
    const settings = node("div", undefined, "fixture-field-settings");
    const component = chooser("표시할 물리 변위 성분", controls.COMPONENTS.map(value => [value, `${label(value)} (mm)`])); component.item.value = "UZ";
    const mode = chooser("형상 표시", [["undeformed", "미변형 원본 메시"], ["deformed", "변형 표시 (보기 배율)"]]); mode.item.value = "undeformed";
    const scale = node("input"), scaleLabel = node("label", "변형 보기 배율 · display-only"); scale.type = "number"; scale.min = "0"; scale.max = String(controls.LIMITS.factor); scale.step = "any"; scale.value = "100"; scale.disabled = true; scaleLabel.append(scale);
    settings.append(component.wrapper, mode.wrapper, scaleLabel); container.append(settings);
    const deformationNote = node("p", undefined, "fixture-field-display-note"), error = node("p", "", "fixture-field-error"), legend = node("p", undefined, "fixture-field-legend"); error.hidden = true;
    const canvas = node("canvas", undefined, "fixture-field-canvas"); canvas.setAttribute("aria-label", "같은 해석 기록의 실제 CPS6 외곽 메시와 절점 변위. 드래그로 회전하고 절점을 선택하세요."); canvas.tabIndex = 0;
    container.append(deformationNote, error, canvas, legend, node("p", "드래그로 회전 · 휠로 확대 · 외곽 절점 클릭 또는 아래 ID 검색. 파란 사각형은 고정 XYZ, 붉은 화살표는 실제 saddle 하중입니다. 화살표 길이는 보기용이며 N 값은 절점 표를 따릅니다.", "hint separated"),
      node("p", "외곽 CPS6의 6절점을 네 삼각형으로 표시합니다. 면 색은 세 절점 성분의 평균 표시이며, 선택 절점 표는 저장된 원본 U입니다.", "hint"));
    const probeBox = node("div", undefined, "fixture-field-probe"), searchLabel = node("label", "실제 절점 ID로 찾기"), search = node("input"); search.type = "number"; search.min = "1"; search.step = "1"; search.placeholder = "빈칸이면 전체 절점"; searchLabel.append(search);
    const rows = node("div", undefined, "fixture-field-rows"), pager = node("div", undefined, "button-row separated"), pageCaption = node("span", undefined, "hint");
    container.append(searchLabel, probeBox, rows, pager);
    let page = 0, selectedRows = field.nodes, destroyed = false;
    const fixed = new Set(field.fixed_node_ids), loads = new Map(field.loads.map(load => [load.node_id, load.force_N]));
    function showProbe(value) {
      if (!current() || destroyed) return; search.value = String(value.node_id); selectedRows = [value]; page = 0;
      probeBox.textContent = `절점 ${value.node_id} · 원본 XYZ ${value.position_mm.join(" / ")} mm · U ${value.displacement_tokens.join(" / ")} mm · |U| ${Math.hypot(...value.displacement_mm)} mm${fixed.has(value.node_id) ? " · 고정 XYZ" : ""}${loads.has(value.node_id) ? ` · 하중 ${loads.get(value.node_id).join(" / ")} N` : ""}`;
      drawTable();
    }
    const viewer = createViewer(canvas, model, () => current() && !destroyed, showProbe);
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
    const tools = node("div", undefined, "button-row separated"); tools.append(button("기본 시점", () => viewer.home())); container.append(tools);
    function update() {
      if (!current() || destroyed) return false;
      try {
        if (!["undeformed", "deformed"].includes(mode.item.value)) throw new Error("형상 표시를 선택하세요.");
        scale.disabled = mode.item.value === "undeformed";
        if (!scale.disabled && !scale.value.trim()) throw new Error("변형 보기 배율을 입력하세요.");
        const factor = scale.disabled ? 0 : Number(scale.value), data = scene(model, component.item.value, factor);
        viewer.set(component.item.value, factor); canvas.hidden = false; error.hidden = true;
        legend.textContent = `${label(data.component)} · 전체 절점 물리값 ${data.min} ~ ${data.max} mm (배율 미적용)`;
        deformationNote.textContent = factor === 0 ? "미변형 원본 메시 · 원래 mm 좌표. 표와 색 범위는 실제 물리 변위입니다." : `보기 배율 ${factor}× · display-only: x + ${factor}U. 표시 변형은 실제 물리 변위가 아니며 표와 색 범위에는 배율을 곱하지 않습니다.`;
        return true;
      } catch (failure) { canvas.hidden = true; error.hidden = false; error.textContent = failure.message; return false; }
    }
    component.item.addEventListener("change", update); mode.item.addEventListener("change", update); scale.addEventListener("input", update);
    search.addEventListener("input", () => {
      if (!current() || destroyed) return; page = 0; const raw = search.value.trim(); selectedRows = raw ? field.nodes.filter(value => String(value.node_id) === raw) : field.nodes;
      probeBox.textContent = ""; if (selectedRows.length === 1) viewer.probe(selectedRows[0].node_id); else drawTable();
    });
    const fullRange = scene(model, "MAGNITUDE", 0);
    container.append(node("p", `전체 절점 최대 |U| ${fullRange.max} mm · 기존 max_displacement는 하중 안장의 |UZ| 통계 ${metadata.loadedMaximumUz ?? "미제공"} mm입니다. 두 값은 별도 범위이며 기존 metric을 바꾸지 않습니다.`, "fixture-field-statistic"));
    const provenance = node("details", undefined, "raw-detail fixture-field-source"); provenance.append(node("summary", "검증 상세 · 부모·개정·생산 버전·원본"),
      node("p", `실험 ${metadata.experimentId} · 부모 CAD ${metadata.parentId}`), node("p", `CAD revision ${metadata.revision}`, "mono"),
      node("p", `필드 adapter ${metadata.fieldProducer} · 결과 adapter ${metadata.resultProducer} · Core producer ${metadata.coreCommit ?? "미기록"}`, "mono"),
      node("p", `Pinned source ${metadata.upstreamCommit ?? "미기록"} · ${metadata.saddleGroup} · 총 하중 ${metadata.totalForceN} N`, "mono"),
      node("p", `필드 ${model.artifact.size_bytes} bytes · SHA-256 ${model.artifact.sha256}`, "mono"));
    Object.values(field.sources).forEach(source => provenance.append(node("p", `${source.path} · ${source.bytes} bytes · SHA-256 ${source.sha256}`, "mono"))); container.append(provenance);
    drawTable(); update(); return { viewer, update, refs: { component: component.item, mode: mode.item, scale, canvas, legend, error, search, rows, probeBox, pageCaption, previous, next, deformationNote, provenance },
      destroy: () => { destroyed = true; viewer.destroy(); } };
  }
  const api = { scene, createViewer, mount };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.fixtureFieldViewer = api;
})(globalThis);
