"use strict";

// A retained-record reader. Domain/Core verdicts and native values are never recomputed.
(function (root) {
  const JSON_LIMIT = 32 * 1024 * 1024, NODE_LIMIT = 200000, CELL_LIMIT = 400000, ENTRY_LIMIT = 2048;
  const SHA = /^[0-9a-f]{64}$/, SIDES = ["xmin", "xmax", "ymin", "ymax"];
  const kinds = { "pde.fenicsx.rectangle": "rectangle", "pde.fenicsx.transient": "transient",
    "pde.fenicsx.vector": "vector", "pde.fenicsx.coupled": "coupled", "pde.fenicsx.imported": "imported" };
  const catalogs = new WeakMap();
  const object = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
  const finite = (x) => typeof x === "number" && Number.isFinite(x);
  const integer = (x) => Number.isSafeInteger(x) && x >= 0;
  const positive = (x) => integer(x) && x > 0;
  class Refusal extends Error {
    constructor(status, reason) { super(reason); this.status = status; }
  }
  const demand = (condition, reason) => { if (!condition) throw new Refusal("error", reason); };
  function clone(x) {
    if (Array.isArray(x)) return x.map(clone);
    if (object(x)) return Object.fromEntries(Object.entries(x).map(([key, value]) => [key, clone(value)]));
    return x;
  }
  function freeze(x) {
    if (x && typeof x === "object" && !Object.isFrozen(x)) { Object.values(x).forEach(freeze); Object.freeze(x); }
    return x;
  }
  function equal(a, b) {
    if (Object.is(a, b)) return true;
    if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((v, i) => equal(v, b[i]));
    return object(a) && object(b) && Object.keys(a).length === Object.keys(b).length &&
      Object.keys(a).every((key) => Object.hasOwn(b, key) && equal(a[key], b[key]));
  }
  function keys(x, expected, label) {
    demand(object(x) && equal(Object.keys(x).sort(), [...expected].sort()), `${label}: keys differ`);
  }
  function pathCheck(path) {
    demand(typeof path === "string" && path.length > 0 && !/[\\\x00-\x1f:#?%]/.test(path) &&
      path.split("/").every((part) => part && part !== "." && part !== ".."), "Unsafe artifact path");
    return path;
  }
  function current(ctx) {
    if (typeof ctx.isCurrent !== "function" || ctx.isCurrent() !== true) throw new Refusal("error", "Selection changed; trusted field cleared");
  }
  async function hash(ctx, bytes) {
    current(ctx);
    const crypto = root.crypto || (typeof module !== "undefined" && module.exports ? require("node:crypto").webcrypto : null);
    if (!crypto?.subtle) throw new Refusal("unavailable", "WebCrypto SHA-256 unavailable");
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    current(ctx);
    return Array.from(new Uint8Array(digest), (v) => v.toString(16).padStart(2, "0")).join("");
  }

  // Record top-level array spans without converting Python float lexemes to JS JSON.
  // The same scan refuses duplicate keys, excessive depth and non-JSON tokens.
  function spans(text) {
    let at = 0;
    const top = Object.create(null), space = () => { while (/\s/.test(text[at] || "") && at < text.length) at++; };
    function string() {
      const start = at++;
      while (at < text.length) {
        const c = text[at++];
        if (c === "\\") at++;
        else if (c === '"') return JSON.parse(text.slice(start, at));
      }
      throw new Refusal("error", "Malformed JSON string");
    }
    function value(depth) {
      demand(depth <= 64, "JSON nesting exceeds reader limit"); space();
      if (text[at] === "{") {
        at++; space(); const seen = new Set();
        if (text[at] === "}") { at++; return; }
        while (true) {
          demand(text[at] === '"', "Malformed JSON object"); const key = string();
          demand(!seen.has(key), "Duplicate JSON key"); seen.add(key); space(); demand(text[at++] === ":", "Malformed JSON key");
          space(); const start = at; value(depth + 1); if (depth === 0) top[key] = text.slice(start, at);
          space(); const c = text[at++]; if (c === "}") return; demand(c === ",", "Malformed JSON object separator"); space();
        }
      }
      if (text[at] === "[") {
        at++; space(); if (text[at] === "]") { at++; return; }
        while (true) { value(depth + 1); space(); const c = text[at++]; if (c === "]") return; demand(c === ",", "Malformed JSON array separator"); }
      }
      if (text[at] === '"') { string(); return; }
      const match = /^(?:-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)/.exec(text.slice(at));
      demand(!!match, "Malformed JSON value"); at += match[0].length;
    }
    value(0); space(); demand(at === text.length, "Trailing JSON data"); return top;
  }
  function json(bytes) {
    let text, data, raw;
    try { text = new TextDecoder("utf-8", { fatal: true }).decode(bytes); data = JSON.parse(text); raw = spans(text); }
    catch (error) { if (error instanceof Refusal) throw error; throw new Refusal("error", "Malformed UTF-8 JSON artifact"); }
    demand(object(data), "JSON artifact must be an object");
    return { data, raw };
  }
  async function read(ctx, path) {
    current(ctx); const artifact = ctx.manifest.get(pathCheck(path));
    demand(!!artifact, `Artifact is not manifested: ${path}`);
    if (artifact.size_bytes > JSON_LIMIT) throw new Refusal("unavailable", `JSON exceeds 32 MiB reader limit: ${path}`);
    let original;
    try { original = await ctx.fetchBytes(path); }
    catch (error) { current(ctx); throw new Refusal("partial", `Manifested artifact unavailable: ${path}`); }
    current(ctx);
    demand(original instanceof Uint8Array, "fetchBytes must return Uint8Array");
    const bytes = Uint8Array.from(original); // Freeze the bytes consumed across the hash await.
    demand(bytes.byteLength === artifact.size_bytes, `Artifact byte length differs: ${path}`);
    demand(await hash(ctx, bytes) === artifact.sha256, `Artifact SHA-256 differs: ${path}`);
    current(ctx); return json(bytes);
  }
  function fail(error, metadata = null, downloads = [], catalog = false) {
    return freeze({ status: error instanceof Refusal ? error.status : "error",
      reason: error instanceof Refusal ? error.message : "Malformed retained field record", metadata, downloads,
      ...(catalog ? { entries: [] } : { selection: null, components: [], nodes: [], cells: [], boundaries: null, interface: null, mapping: null, binding: null }) });
  }
  function context(inspection, fetchBytes, isCurrent) {
    const saved = clone(inspection); demand(saved?.integrity === "VERIFIED", "Inspection integrity must be VERIFIED");
    const result = saved.result, proposal = saved.proposal;
    demand(object(result) && object(proposal) && typeof result.experiment_id === "string" && result.experiment_id &&
      result.experiment_id === proposal.id && SHA.test(result.model_revision) && result.model_revision === proposal.model_revision &&
      SHA.test(result.proposal_revision) && result.provenance?.proposal_sha256 === result.proposal_revision &&
      typeof result.provenance.adapter === "string" && result.provenance.adapter === proposal.physics?.backend &&
      equal(result.provenance.execution_settings, proposal.execution), "Core proposal/result identity differs");
    demand(result.study?.id === proposal.study_id && saved.thread?.experiment === result.experiment_id &&
      saved.thread?.study === proposal.study_id && saved.thread?.model_revision === result.model_revision &&
      saved.ledger?.experiment_id === result.experiment_id, "Inspection thread/study/ledger identity differs");
    demand(typeof fetchBytes === "function" && typeof isCurrent === "function", "Reader callbacks required");
    demand(Array.isArray(result.artifacts) && object(result.metrics) && Array.isArray(result.validations) && Array.isArray(result.evidence), "Incomplete Core result");
    const manifest = new Map(), paths = new Set();
    for (const artifact of result.artifacts) {
      demand(object(artifact) && SHA.test(artifact.sha256) && integer(artifact.size_bytes) && artifact.revision === result.proposal_revision, "Artifact hash/size/proposal revision differs");
      const path = pathCheck(artifact.path), key = path.toLowerCase(); demand(!paths.has(key), "Duplicate artifact path"); paths.add(key); manifest.set(path, freeze(artifact));
    }
    if (saved.hashes?.artifacts) demand(equal(saved.hashes.artifacts, result.artifacts), "Inspection manifest copies differ");
    freeze(saved);
    const metadata = freeze({ experimentId: result.experiment_id, backend: result.provenance.adapter,
      modelRevision: result.model_revision, proposalRevision: result.proposal_revision, status: result.status,
      assessment: { decision: result.decision, solverStatus: result.solver_status, converged: result.converged,
        validations: result.validations, evidence: result.evidence }, metrics: result.metrics, provenance: result.provenance });
    const downloads = freeze([...manifest.values()].map((row) => ({ path: row.path, sha256: row.sha256,
      sizeBytes: row.size_bytes, mimeType: row.mime_type || "application/octet-stream", revision: row.revision })));
    return { saved, manifest, metadata, downloads, fetchBytes, isCurrent, kind: kinds[metadata.backend], entryData: new Map() };
  }
  function fileRefs(ctx, row, used) {
    const names = ["field", "field_data", "form_source", "dofs"];
    if (ctx.kind === "transient") names.push("time_binding");
    if (["vector", "coupled", "imported"].includes(ctx.kind)) names.push("binding");
    if (ctx.kind === "imported") names.push("original", "dense", "mapping");
    keys(row.files, names, "Study file references"); keys(row.artifact_sha256, names, "Study artifact hashes");
    const files = {};
    for (const key of names) {
      const path = pathCheck(`pde/${pathCheck(row.files[key])}`), artifact = ctx.manifest.get(path);
      demand(artifact && SHA.test(row.artifact_sha256[key]) && artifact.sha256 === row.artifact_sha256[key], "Study file/manifest identity differs");
      demand(!used.has(path), "Study/step file reference reused"); used.add(path); files[key] = path;
    }
    return files;
  }
  function counts(row, vector) {
    demand(positive(row.global_cells) && positive(row.global_dofs) && integer(row.dirichlet_dofs), "Malformed declared field counts");
    if (vector) demand(positive(row.global_nodes) && row.global_dofs === 2 * row.global_nodes && row.block_size === 2, "Vector blocked/scalar counts differ");
    else if (row.global_nodes !== undefined) demand(row.global_nodes === row.global_dofs, "Scalar node/DOF counts differ");
  }
  function addEntry(ctx, entries, used, row, studyIndex, stepIndex, study) {
    if (entries.length >= ENTRY_LIMIT) throw new Refusal("unavailable", "Catalog exceeds 2048 entries; download only");
    const vector = ctx.kind === "vector" || ctx.kind === "coupled"; counts(row, vector);
    const files = fileRefs(ctx, row, used);
    const entry = freeze({ id: `${studyIndex}:${stepIndex === null ? "field" : stepIndex}`, studyIndex, stepIndex,
      time: stepIndex === null ? null : row.time, cellsPerAxis: study.cells_per_axis ?? null, level: study.level ?? null,
      components: vector ? ["u0", "u1"] : ["u"], solverStatus: stepIndex === null ? "COMPLETED" : row.solver_status, files });
    entries.push(entry); ctx.entryData.set(entry, freeze({ row, study }));
  }
  async function loadCatalog(inspection, fetchBytes, isCurrent) {
    let ctx;
    try {
      ctx = context(inspection, fetchBytes, isCurrent); current(ctx);
      if (!ctx.kind) throw new Refusal("unavailable", "Backend representation is download-only in this reader");
      const headers = ["pde/input.json", "pde/source_manifest.json", "pde/worker_result.json"];
      if (headers.some((path) => !ctx.manifest.has(path))) throw new Refusal("partial", "Native input/source/worker history is incomplete; download only");
      const input = (await read(ctx, headers[0])).data, source = (await read(ctx, headers[1])).data, worker = (await read(ctx, headers[2])).data;
      const detail = ctx.saved.result.provenance.adapter_details;
      demand(equal(input, ctx.saved.proposal.execution), "Native input differs from selected Core execution settings");
      demand(object(detail) && detail.adapter === ctx.metadata.backend && detail.spec_sha256 === ctx.manifest.get(headers[0]).sha256 &&
        detail.source_manifest_sha256 === ctx.manifest.get(headers[1]).sha256 && detail.source_manifest === headers[1] &&
        worker.spec_sha256 === detail.spec_sha256 && worker.source_manifest_sha256 === detail.source_manifest_sha256, "Native spec/source/adapter identity differs");
      demand(source.schema_version === "1" && source.domain_plugin_version === detail.domain_plugin_version && object(source.files) &&
        object(detail.source_sha256) && equal(Object.keys(source.files).sort(), Object.keys(detail.source_sha256).sort()) && Object.keys(source.files).length > 0, "Copied source manifest differs");
      const copies = new Set();
      for (const [key, row] of Object.entries(source.files)) {
        demand(object(row) && typeof row.repository_path === "string" && SHA.test(row.sha256) && row.sha256 === detail.source_sha256[key], "Copied source hash differs from adapter");
        pathCheck(row.repository_path); const nativePath = pathCheck(row.copied_path);
        demand(!/^pde(?:\/|$)/i.test(nativePath), "Copied source path must be native-output-relative, without pde prefix");
        const path = pathCheck(`pde/${nativePath}`), artifact = ctx.manifest.get(path);
        demand(artifact && artifact.sha256 === row.sha256 && !copies.has(path), "Copied source bytes are not uniquely manifested"); copies.add(path);
      }
      demand(worker.schema_version === "1" && worker.mpi_size === 1 && worker.scalar_type === "float64", "Unsupported native worker identity/layout");
      for (const key of ["mpi_size", "scalar_type", "versions"]) if (detail[key] !== undefined) demand(equal(detail[key], worker[key]), `Native ${key}/adapter identity differs`);
      if (worker.status !== "COMPLETED") throw new Refusal("partial", "Native worker history is partial; no complete field catalog");
      ctx.input = freeze(input); ctx.worker = freeze(worker);
      const entries = [], used = new Set();
      demand(input.mesh?.degree === 1, "Only actual P1 triangular fields are supported");
      if (ctx.kind === "transient") {
        demand(["mesh", "time"].includes(input.refinement_axis) && Array.isArray(input.mesh.cell_counts) && Array.isArray(input.time?.step_counts) &&
          finite(input.time.end) && input.time.start === 0 && input.time.end > 0 && input.time.unit === "1" && input.time.scheme === "backward_euler", "Malformed transient input binding");
        const mesh = input.mesh.cell_counts, steps = input.time.step_counts;
        demand(mesh.every(positive) && steps.every(positive) && (input.refinement_axis === "mesh" ? steps.length === 1 : mesh.length === 1), "Ambiguous transient refinement pairs");
        const pairs = input.refinement_axis === "mesh" ? mesh.map((n) => [n, steps[0]]) : steps.map((n) => [mesh[0], n]);
        if (pairs.reduce((sum, [, n]) => sum + n + 1, 0) > ENTRY_LIMIT) throw new Refusal("unavailable", "Catalog exceeds 2048 entries; download only");
        demand(pairs.length > 0 && Array.isArray(worker.studies) && worker.studies.length === pairs.length, "Transient study count differs");
        for (let i = 0; i < pairs.length; i++) {
          const study = worker.studies[i], [n, count] = pairs[i];
          demand(object(study) && study.study_index === i && study.cells_per_axis === n && study.step_count === count &&
            study.refinement_axis === input.refinement_axis && study.dt === input.time.end / count && Array.isArray(study.steps) && study.steps.length === count + 1, "Transient study/grid identity differs");
          let previous = null;
          for (let j = 0; j <= count; j++) {
            const row = study.steps[j], time = j * input.time.end / count;
            demand(object(row) && row.index === j && row.time === time && row.native_time_value === time && row.dt === (j ? study.dt : 0) &&
              row.solver_status === (j ? "COMPLETED" : "NOT_RUN") && row.previous_values_sha256 === previous && SHA.test(row.current_values_sha256) && row.distinct_state === true, "Transient step/time/value chain differs");
            if (!j) demand(row.linear_residual === null && row.ksp_convergence_reason === null && row.ksp_iterations === null, "Initial snapshot must remain NOT_RUN");
            addEntry(ctx, entries, used, row, i, j, study); previous = row.current_values_sha256;
          }
        }
      } else {
        const levels = ctx.kind === "imported" ? input.mesh.levels : input.mesh.cell_counts;
        demand(Array.isArray(levels) && levels.length > 0 && Array.isArray(worker.mesh_studies) && worker.mesh_studies.length === levels.length, "Native mesh history differs from input");
        if (levels.length > ENTRY_LIMIT) throw new Refusal("unavailable", "Catalog exceeds 2048 entries; download only");
        for (let i = 0; i < levels.length; i++) {
          const row = worker.mesh_studies[i];
          demand(object(row) && row.degree === 1 && row.cell_type === "triangle" &&
            (ctx.kind === "imported" ? row.level === i : positive(levels[i]) && row.cells_per_axis === levels[i]), "Native refinement/triangle identity differs");
          addEntry(ctx, entries, used, row, i, null, row);
          if (ctx.kind === "imported") {
            const level = levels[i], files = entries[i].files;
            demand(object(level) && typeof level.data === "string" && !/[^\x00-\x7f]/.test(level.data) && SHA.test(level.sha256) &&
              row.source_sha256 === level.sha256 && ctx.manifest.get(files.original).sha256 === level.sha256 &&
              ctx.manifest.get(files.dense).sha256 === row.dense_sha256, "Original/dense imported mesh identity differs");
            demand(await hash(ctx, new TextEncoder().encode(level.data)) === level.sha256, "Imported original input bytes differ");
          }
        }
      }
      current(ctx);
      const catalog = freeze({ status: "available", reason: null, metadata: ctx.metadata, entries, downloads: ctx.downloads });
      catalogs.set(catalog, ctx); return catalog;
    } catch (error) { return fail(error, ctx?.metadata, ctx?.downloads, true); }
  }

  function ids(values, label, expected = null) {
    demand(Array.isArray(values) && values.every(integer) && new Set(values).size === values.length &&
      (expected === null || values.length === expected), `${label}: nonnegative unique exact IDs required`);
    return new Set(values);
  }
  function sorted(values, label) { demand(values.every((v, i) => i === 0 || v > values[i - 1]), `${label}: IDs must retain sorted native order`); }
  function sameSet(a, b, label) { demand(a.size === b.size && [...a].every((v) => b.has(v)), `${label}: identities differ`); }
  function values(array, count, vector, label) {
    demand(Array.isArray(array) && array.length === count && array.every((v) => vector ? Array.isArray(v) && v.length === 2 && v.every(finite) : finite(v)), `${label}: finite component shape differs`);
  }
  const edgeKey = (pair) => [...pair].sort((a, b) => a - b).join(",");
  function geometry(ctx, row, field) {
    const vector = ctx.kind === "vector" || ctx.kind === "coupled";
    demand(field.schema_version === "1" && field.coordinates_unit === "1" && field.field_unit === "1", "Native field schema/units differ");
    if (vector) demand(field.field_type === "vector" && field.block_size === 2 && equal(field.components, ["u0", "u1"]), "Native directed component/block order differs");
    else demand(field.field_type === undefined && field.components === undefined && field.block_size === undefined, "Scalar field has vector metadata");
    demand(Array.isArray(field.node_ids) && Array.isArray(field.cell_node_ids), "Native field arrays missing");
    if (field.node_ids.length > NODE_LIMIT || field.cell_node_ids.length > CELL_LIMIT) throw new Refusal("unavailable", "Field exceeds 200000 nodes/400000 triangles; download only");
    const nodeSet = ids(field.node_ids, "Native nodes", row.global_dofs / (vector ? 2 : 1)); sorted(field.node_ids, "Native nodes");
    demand(Array.isArray(field.coordinates) && field.coordinates.length === nodeSet.size && field.coordinates.every((p) => Array.isArray(p) && p.length === 2 && p.every(finite)), "Finite Nx2 native coordinates required");
    demand(new Set(field.coordinates.map((p) => p.join(","))).size === nodeSet.size, "Duplicate native coordinates");
    values(field.values, nodeSet.size, vector, "Actual nodal values");
    demand(field.cell_node_ids.length === row.global_cells, "Native triangle count differs");
    const explicit = ctx.kind === "coupled" || ctx.kind === "imported";
    if (explicit) ids(field.cell_ids, "Native cells", row.global_cells);
    else demand(field.cell_ids === undefined, "Unexpected native cell IDs; connectivity has row ordinals only");
    const edges = new Map(), triangles = new Set(), used = new Set();
    const points = new Map(field.node_ids.map((id, i) => [id, field.coordinates[i]]));
    field.cell_node_ids.forEach((cell, i) => {
      const members = ids(cell, "Triangle", 3); demand([...members].every((n) => nodeSet.has(n)), "Triangle references a foreign node");
      const key = [...members].sort((a, b) => a - b).join(","); demand(!triangles.has(key), "Duplicate native triangle"); triangles.add(key);
      const [a, b, c] = cell.map((id) => points.get(id));
      const area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
      demand(finite(area) && area !== 0, "Degenerate/nonfinite native triangle");
      members.forEach((n) => used.add(n));
      for (const pair of [[cell[0], cell[1]], [cell[1], cell[2]], [cell[2], cell[0]]]) {
        const edge = edgeKey(pair), adjacent = edges.get(edge) || []; adjacent.push(i); demand(adjacent.length <= 2, "Nonmanifold native triangle edge"); edges.set(edge, adjacent);
      }
    });
    sameSet(used, nodeSet, "Complete native P1 node coverage");
    return { vector, nodeSet, edges, explicit, dirichlet: new Set(), exteriorSeen: new Set(), facetsSeen: new Set() };
  }
  function boundary(ctx, shape, row, name, type) {
    demand(object(row), `Missing native boundary: ${name}`);
    const facets = ids(row.facet_ids, "Native facets"), endpoints = row.facet_node_ids, dofs = ids(row.dof_ids, "Boundary DOFs"); sorted(row.dof_ids, "Boundary DOFs");
    demand(Array.isArray(endpoints) && endpoints.length === facets.size, "Boundary facet/endpoint count differs");
    const union = new Set();
    endpoints.forEach((pair) => {
      ids(pair, "Boundary endpoints", 2); const key = edgeKey(pair);
      demand(pair.every((n) => shape.nodeSet.has(n)) && shape.edges.get(key)?.length === 1 && !shape.exteriorSeen.has(key), "Boundary does not uniquely partition native exterior");
      shape.exteriorSeen.add(key); pair.forEach((n) => union.add(n));
    });
    sameSet(dofs, union, "Boundary endpoints/DOFs");
    for (const id of facets) { demand(!shape.facetsSeen.has(id), "Overlapping native facet IDs"); shape.facetsSeen.add(id); }
    demand(finite(row.measure) && row.measure > 0 && Array.isArray(row.normal_integral) && row.normal_integral.length === 2 && row.normal_integral.every(finite), "Boundary measure/normal observation malformed");
    values(row.prescribed_values, dofs.size, shape.vector, "Native prescribed values");
    demand(shape.vector ? Array.isArray(row.prescribed_integral) && row.prescribed_integral.length === 2 && row.prescribed_integral.every(finite) : finite(row.prescribed_integral), "Prescribed integral shape differs");
    demand(["dirichlet", "neumann"].includes(type), "Boundary input type differs"); if (type === "dirichlet") dofs.forEach((n) => shape.dirichlet.add(n));
  }
  function boundaries(ctx, row, field, shape) {
    const input = ctx.input.problem?.boundaries; demand(object(input), "Missing input named boundaries");
    keys(field.boundaries, Object.keys(input), "Complete named boundaries");
    if (ctx.kind !== "imported") demand(equal(Object.keys(input).sort(), [...SIDES].sort()), "Named rectangle sides differ");
    for (const [name, declared] of Object.entries(input)) {
      if (ctx.kind === "coupled") {
        keys(field.boundaries[name], Object.keys(declared.value), "Split-side regions");
        for (const region of Object.keys(declared.value)) boundary(ctx, shape, field.boundaries[name][region], `${name}/${region}`, declared.type);
      } else boundary(ctx, shape, field.boundaries[name], name, declared.type);
    }
    sameSet(shape.exteriorSeen, new Set([...shape.edges].filter(([, adjacent]) => adjacent.length === 1).map(([edge]) => edge)), "Complete exterior coverage");
    const dirichlet = ids(field.dirichlet_node_ids, "Dirichlet nodes"); sorted(field.dirichlet_node_ids, "Dirichlet nodes"); sameSet(dirichlet, shape.dirichlet, "Input Dirichlet union");
    demand(row.dirichlet_dofs === dirichlet.size * (shape.vector ? 2 : 1) && (row.dirichlet_nodes === undefined || row.dirichlet_nodes === dirichlet.size), "Native prescribed node/scalar count differs");
  }
  function commonBinding(binding, field, vector) {
    demand(binding.schema_version === "1" && equal(binding.node_ids, field.node_ids), "Binding native node order differs");
    if (vector) demand(equal(binding.components, ["u0", "u1"]), "Binding directed components differ");
    values(binding.rhs_values, field.node_ids.length, vector, "Native RHS binding"); values(binding.reference_values, field.node_ids.length, vector, "Native reference binding");
  }
  function coupled(ctx, row, field, binding, shape) {
    demand(Array.isArray(field.cell_regions) && field.cell_regions.length === row.global_cells && field.cell_regions.every((r) => ["left", "right"].includes(r)), "Native cell region labels differ");
    const cellIndex = new Map(field.cell_ids.map((id, i) => [id, i])), regions = {};
    for (const region of ["left", "right"]) {
      const cells = [], nodes = new Set(); field.cell_regions.forEach((r, i) => { if (r === region) { cells.push(field.cell_ids[i]); field.cell_node_ids[i].forEach((n) => nodes.add(n)); } });
      demand(cells.length > 0 && row.region_cell_counts?.[region] === cells.length, "Native region cell count differs"); regions[region] = { cells: new Set(cells), nodes };
    }
    const face = field.interface; demand(object(face), "Native material interface missing");
    const facetIds = ids(face.facet_ids, "Interface facets"), seen = new Set(), nodes = new Set();
    demand(Array.isArray(face.facet_node_ids) && face.facet_node_ids.length === facetIds.size && Array.isArray(face.adjacent_cell_ids) && face.adjacent_cell_ids.length === facetIds.size &&
      finite(face.measure) && face.measure > 0 && equal(face.plus_x_normal, [1, 0]), "Native interface shape/normal differs");
    face.facet_node_ids.forEach((pair, i) => {
      ids(pair, "Interface endpoints", 2); const key = edgeKey(pair), adjacent = shape.edges.get(key), cells = face.adjacent_cell_ids[i];
      demand(pair.every((n) => shape.nodeSet.has(n)) && adjacent?.length === 2 && !seen.has(key), "Interface edge coverage differs"); seen.add(key); pair.forEach((n) => nodes.add(n));
      ids(cells, "Interface neighbour cells", 2);
      demand(regions.left.cells.has(cells[0]) && regions.right.cells.has(cells[1]) && equal([...adjacent].sort((a, b) => a - b), cells.map((id) => cellIndex.get(id)).sort((a, b) => a - b)), "Interface left/right cell identity differs");
    });
    const expected = new Set([...shape.edges].filter(([, indices]) => indices.length === 2 && field.cell_regions[indices[0]] !== field.cell_regions[indices[1]]).map(([edge]) => edge));
    sameSet(seen, expected, "Complete material interface"); sameSet(ids(face.node_ids, "Interface nodes"), nodes, "Interface endpoint union");
    for (const id of facetIds) demand(!shape.facetsSeen.has(id), "Interface facet overlaps exterior");
    demand(binding.schema_version === "1" && equal(binding.components, ["u0", "u1"]), "Regional binding components differ"); keys(binding.regions, ["left", "right"], "Regional bindings");
    for (const region of ["left", "right"]) {
      const b = binding.regions[region]; demand(object(b), "Regional binding missing");
      sameSet(ids(b.cell_ids, "Regional binding cells"), regions[region].cells, "Regional cell identity"); sameSet(ids(b.node_ids, "Regional binding nodes"), regions[region].nodes, "Regional node identity"); sorted(b.node_ids, "Regional binding nodes");
      values(b.rhs_values, b.node_ids.length, true, "Regional RHS traces"); values(b.reference_values, b.node_ids.length, true, "Regional reference traces");
      values(b.diffusion, 2, true, "Native diffusion matrix"); values(b.reaction, 2, true, "Native reaction matrix");
      demand(equal(b.diffusion, ctx.input.problem.weak_form.diffusion[region]) && equal(b.reaction, ctx.input.problem.weak_form.reaction) &&
        equal(b.diffusion, row.region_coefficients?.[region]) && equal(b.reaction, row.reaction_matrix), "Native regional coefficient binding differs");
    }
  }
  function imported(ctx, entry, row, field, binding, mapping) {
    const n = field.node_ids.length, m = field.cell_ids.length;
    const sourceNodes = ids(field.source_node_ids, "Original source node IDs", n); demand([...sourceNodes].every(positive), "Original mesh node IDs must be positive");
    const sourceCells = ids(field.source_cell_ids, "Original source cell IDs", m); demand([...sourceCells].every(positive), "Original mesh cell IDs must be positive");
    demand(mapping.schema_version === "1" && mapping.original_sha256 === row.source_sha256 && mapping.dense_sha256 === row.dense_sha256 &&
      binding.source_sha256 === row.source_sha256 && binding.dense_sha256 === row.dense_sha256 && equal(binding.source_node_ids, field.source_node_ids), "Imported raw/dense/binding identities differ");
    const originals = ids(mapping.original_node_ids, "Original sorted nodes", n); sorted(mapping.original_node_ids, "Original sorted nodes"); sameSet(originals, sourceNodes, "Original/native node bijection");
    demand(equal(mapping.dense_node_ids, Array.from({ length: n }, (_, i) => i + 1)), "Dense IDs are distinct from original/native IDs");
    const permutation = (a, size, label) => { const set = ids(a, label, size); demand([...set].every((id) => id < size), `${label}: index space differs`); };
    permutation(mapping.geometry_input_indices, n, "Geometry input indices");
    demand(equal(mapping.geometry_source_node_ids, mapping.geometry_input_indices.map((i) => mapping.original_node_ids[i])), "Geometry/source node map differs");
    ids(mapping.vertex_ids, "Native vertices", n); permutation(mapping.vertex_geometry_indices, n, "Vertex geometry indices");
    sameSet(ids(mapping.vertex_dof_ids, "Vertex DOF map", n), new Set(field.node_ids), "Native vertex/DOF bijection");
    const sourceByNode = new Map(field.node_ids.map((id, i) => [id, field.source_node_ids[i]]));
    demand(mapping.vertex_dof_ids.every((id, i) => sourceByNode.get(id) === mapping.geometry_source_node_ids[mapping.vertex_geometry_indices[i]]), "Vertex/native/source composition differs");
    permutation(mapping.original_cell_index, m, "Original cell row indices"); ids(mapping.importer_cell_source_ids, "Importer source cells", m);
    demand(equal(mapping.cell_ids, field.cell_ids) && equal(mapping.source_cell_ids, field.source_cell_ids) &&
      equal(mapping.source_cell_ids, mapping.original_cell_index.map((i) => mapping.importer_cell_source_ids[i])), "Original/importer/native cell bijection differs");
    demand(equal(mapping.physical_groups, row.physical_groups) && object(mapping.physical_groups), "Native physical names differ");
    const names = Object.keys(ctx.input.problem.boundaries), body = ctx.input.problem.domain.body;
    keys(mapping.physical_groups, [...names, body], "Complete physical names");
    const tags = new Set();
    for (const [name, group] of Object.entries(mapping.physical_groups)) {
      demand(object(group) && group.dim === (name === body ? 2 : 1) && positive(group.tag) && !tags.has(group.tag), "Physical group dimension/tag differs"); tags.add(group.tag);
    }
    keys(mapping.boundary_source_elements, names, "Original boundary element map"); const elements = new Set();
    for (const name of names) {
      const b = field.boundaries[name], ids_ = ids(b.source_element_ids, "Original boundary elements", b.facet_ids.length);
      demand([...ids_].every(positive) && equal(mapping.boundary_source_elements[name], b.source_element_ids), "Original/native boundary identity differs");
      for (const id of ids_) { demand(!elements.has(id) && !sourceCells.has(id), "Original element identities overlap"); elements.add(id); }
    }
    demand(equal(mapping.gmsh_initialization, { argv: [], read_config_files: false, finalized: true }), "Native Gmsh initialization identity differs");
    demand(finite(binding.diffusion) && finite(binding.reaction) && equal(binding.diffusion, ctx.input.problem.weak_form.diffusion) && equal(binding.reaction, ctx.input.problem.weak_form.reaction) &&
      equal(row.coefficients, { diffusion: binding.diffusion, reaction: binding.reaction }) &&
      ctx.manifest.get(entry.files.original).sha256 === mapping.original_sha256 && ctx.manifest.get(entry.files.dense).sha256 === mapping.dense_sha256, "Imported native coefficient/mesh binding differs");
  }
  async function valueHash(ctx, document) {
    const compact = (name) => {
      const fragment = document.raw[name];
      if (typeof fragment !== "string" || !/^\s*\[/.test(fragment) || /[^\s\[\],0-9eE+.\-]/.test(fragment)) throw new Refusal("unavailable", "Native numeric lexemes cannot be verified");
      const raw = fragment.replace(/\s/g, "");
      if (name === "node_ids") demand(/^\[(?:0|[1-9]\d*)(?:,(?:0|[1-9]\d*))*\]$/.test(raw), "Native integer node-ID lexemes differ");
      return raw;
    };
    // Exactly Python sort_keys=True canonical key order; the float tokens remain native.
    return hash(ctx, new TextEncoder().encode(`{"node_ids":${compact("node_ids")},"values":${compact("values")}}`));
  }
  function meshIdentity(field) {
    return { node_ids: field.node_ids, coordinates: field.coordinates, cell_node_ids: field.cell_node_ids,
      dirichlet_node_ids: field.dirichlet_node_ids, boundaries: Object.fromEntries(Object.entries(field.boundaries).map(([side, row]) =>
        [side, { facet_ids: row.facet_ids, facet_node_ids: row.facet_node_ids, dof_ids: row.dof_ids, measure: row.measure, normal_integral: row.normal_integral }])) };
  }
  async function loadField(catalog, entry, fetchBytes, isCurrent) {
    let ctx;
    try {
      const saved = catalogs.get(catalog);
      if (saved) ctx = { ...saved, fetchBytes, isCurrent };
      demand(saved && catalog.entries.includes(entry) && saved.entryData.has(entry), "Exact immutable catalog entry membership required");
      demand(typeof fetchBytes === "function" && typeof isCurrent === "function", "Reader callbacks required");
      current(ctx);
      const { row } = ctx.entryData.get(entry), document = await read(ctx, entry.files.dofs), field = document.data;
      const shape = geometry(ctx, row, field); boundaries(ctx, row, field, shape);
      let binding = null, mapping = null;
      if (entry.files.binding) {
        binding = (await read(ctx, entry.files.binding)).data;
        if (ctx.kind === "coupled") coupled(ctx, row, field, binding, shape);
        else commonBinding(binding, field, shape.vector);
      }
      if (ctx.kind === "imported") { mapping = (await read(ctx, entry.files.mapping)).data; imported(ctx, entry, row, field, binding, mapping); }
      if (ctx.kind === "transient") {
        binding = (await read(ctx, entry.files.time_binding)).data; commonBinding(binding, field, false);
        demand(binding.time === entry.time && await valueHash(ctx, document) === row.current_values_sha256, "Transient time/native numeric-array hash differs");
        if (entry.stepIndex > 0) {
          const previousEntry = catalog.entries.find((e) => e.studyIndex === entry.studyIndex && e.stepIndex === entry.stepIndex - 1);
          demand(previousEntry, "Previous time snapshot missing"); const previous = await read(ctx, previousEntry.files.dofs);
          const previousRow = ctx.entryData.get(previousEntry).row, previousShape = geometry(ctx, previousRow, previous.data);
          boundaries(ctx, previousRow, previous.data, previousShape);
          const previousBinding = (await read(ctx, previousEntry.files.time_binding)).data;
          commonBinding(previousBinding, previous.data, false); demand(previousBinding.time === previousEntry.time, "Previous native time binding differs");
          demand(await valueHash(ctx, previous) === row.previous_values_sha256 && equal(meshIdentity(previous.data), meshIdentity(field)), "Transient previous values/geometry identity differs");
        }
      }
      current(ctx);
      const nodes = field.node_ids.map((id, i) => ({ id, coordinates: field.coordinates[i], values: shape.vector ? field.values[i] : [field.values[i]], sourceId: field.source_node_ids?.[i] ?? null }));
      const cells = field.cell_node_ids.map((nodeIds, rowIndex) => ({ rowIndex, id: shape.explicit ? field.cell_ids[rowIndex] : null,
        nodeIds, region: field.cell_regions?.[rowIndex] ?? null, sourceId: field.source_cell_ids?.[rowIndex] ?? null }));
      return freeze({ status: "available", reason: null, metadata: ctx.metadata,
        selection: { entryId: entry.id, studyIndex: entry.studyIndex, stepIndex: entry.stepIndex, time: entry.time,
          cellsPerAxis: entry.cellsPerAxis, level: entry.level, solverStatus: entry.solverStatus },
        source: { artifact: entry.files.dofs, sha256: ctx.manifest.get(entry.files.dofs).sha256 },
        components: entry.components, nodes, cells, boundaries: field.boundaries, interface: field.interface ?? null, mapping, binding,
        downloads: ctx.downloads.filter((d) => Object.values(entry.files).includes(d.path)) });
    } catch (error) { return fail(error, ctx?.metadata || null, ctx?.downloads || []); }
  }
  function observationSelection(field, nodeId, component) {
    demand(field?.status === "available" && SHA.test(field.metadata?.modelRevision) &&
      SHA.test(field.source?.sha256) && typeof field.source.artifact === "string" &&
      integer(nodeId) && field.nodes.some(node => node.id === nodeId) && field.components.includes(component),
      "Select a node/component from this verified native PDE field");
    return freeze({kind:"pde_nodal",artifact:field.source.artifact,sha256:field.source.sha256,
      model_revision:field.metadata.modelRevision,study_index:field.selection.studyIndex,
      step_index:field.selection.stepIndex,node_id:nodeId,component});
  }
  const api = Object.freeze({ loadCatalog, loadField, observationSelection });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.pdeFieldInspector = api;
})(typeof window !== "undefined" ? window : globalThis);
