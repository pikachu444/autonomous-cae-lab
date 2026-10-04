"use strict";

// Read retained contact values only. No reference, field, gap or verdict is computed.
(function (root) {
  const SHA = /^[0-9a-f]{64}$/, COMMIT = /^[0-9a-f]{40}$/;
  const BACKEND = "structural.code_aster.contact_patch", CASE = "ssnp121a_frictionless_patch";
  const JSON_LIMIT = 32 * 1024 * 1024, TOTAL_LIMIT = 16 * 1024 * 1024;
  const REF_SHA = "10a01110c2b8b07d9d4dd37b6690d6cdca3ee8145596d8ff8fa05e0583595ba7";
  const ORIGINAL = Object.freeze({ nodes: 313, quads: 265, segments: 92, slave: 13, master: 12,
    mesh: "825e79a01b983b14b136d4fc2490c2bc40e85ccc25ebd8ae6aa32e88dd544f91",
    catalog: "7398ce4349f076e225e76d1d840d60da1dfe24b57181c1ae1d7b5cfc069d8291" });
  const REFINED = Object.freeze({ nodes: 1154, quads: 1060, segments: 184, slave: 25, master: 23,
    mesh: "a23a617fe5de9eb8e52775fcbd10ddcac1aa14cac99ad09ab703e8b58f3b0f6c",
    catalog: "2c1de222fa076cd0afbe98d5dd911cac01f22cae21c96ed090e5be4a2e38b46d",
    profile: "3c157999052aaa37dd03c5b07981a3f047c921d784511c06f97fc5846475ca11",
    recipe: "d0ca8549f7f769c39dfc42b5dda9c3120c87c929e71aadacf18bd5bff688a3a8",
    generator: "4aa4233f9a788927a21f053159e670e6099a2aae5ce08c3ec09d073feb6d020e" });
  const PROFILE_FILE = "ssnp121a-17.4.0.uniform_quad4_2x.profile.json";
  const UPSTREAM = "50ebc13c70ee9df62faf93ddcb746a3757b3042a";
  const BOUNDARIES = ["AB", "BC", "CD", "DA", "EF", "FG", "GH", "HE"];
  const GENERATED_NODE_GROUPS = ["AB", "CD", "EF", "FG", "GH", "HE"];
  const LIMITATIONS = Object.freeze([
    "Available means retained bytes and full field identities are bound; it is not numerical PASS or release.",
    "U: native DX/DY in m; RF: native DX/DY in N/m, per unit out-of-plane thickness; no synthetic Z component.",
    "Pressure: signed native DEPL.LAGS_C in Pa at actual AB slave nodes only.",
    "Stress: native SIEF_ELGA SIXX/SIYY/SIZZ/SIXY in Pa at actual XY in m; COOR_Z is EGGAU2D.W in m^2.",
    "Gauss geometric Z and native contact gap are UNAVAILABLE. Derived projected gaps are omitted.",
    "No smoothing, averaging, extrapolation, force/area pressure, field reconstruction or scientific metric recomputation.",
    "Physical/material/strength/fatigue/contact-gap/cross-solver/fixture/corporate UNKNOWNs retain their recorded verdicts.",
    "Raw table and MED links retain manifested identities; only the bounded JSONs used for display are fetched here."
  ]);
  const object = x => x !== null && typeof x === "object" && !Array.isArray(x);
  const finite = x => typeof x === "number" && Number.isFinite(x);
  const integer = x => Number.isSafeInteger(x) && x >= 0;
  const text = x => typeof x === "string" && x.length > 0;
  class Refusal extends Error { constructor(status, reason) { super(reason); this.status = status; } }
  function demand(ok, reason) { if (!ok) throw new Refusal("error", reason); }
  function equal(a, b) {
    if (Object.is(a, b)) return true;
    if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((x, i) => equal(x, b[i]));
    return object(a) && object(b) && Object.keys(a).length === Object.keys(b).length &&
      Object.keys(a).every(k => Object.hasOwn(b, k) && equal(a[k], b[k]));
  }
  function keys(value, expected, label) { demand(object(value) && equal(Object.keys(value).sort(), [...expected].sort()), `${label}: keys differ`); }
  function copy(value, depth = 0) {
    if (depth > 64) throw new Refusal("unavailable", "Inspection nesting exceeds 64");
    if (Array.isArray(value)) return value.map(x => copy(x, depth + 1));
    if (object(value)) return Object.fromEntries(Object.entries(value).map(([k, x]) => [k, copy(x, depth + 1)]));
    demand(value === null || typeof value === "string" || typeof value === "boolean" || finite(value), "Inspection contains non-JSON or nonfinite values");
    return value;
  }
  function freeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) { Object.values(value).forEach(freeze); Object.freeze(value); }
    return value;
  }
  function pathCheck(path) {
    demand(text(path) && path.length <= 1024 && !/[\\\x00-\x20\x7f:#?%]/.test(path) &&
      path.split("/").every(part => part && part !== "." && part !== ".."), "Unsafe artifact path");
    return path;
  }
  function current(ctx) {
    if (ctx.isCurrent() !== true) throw new Refusal("error", "Selection changed; trusted contact fields cleared");
  }
  async function hash(ctx, bytes) {
    current(ctx);
    const crypto = root.crypto || (typeof module !== "undefined" && module.exports ? require("node:crypto").webcrypto : null);
    if (!crypto?.subtle?.digest) throw new Refusal("unavailable", "WebCrypto SHA-256 unavailable");
    let digest;
    try { digest = await crypto.subtle.digest("SHA-256", bytes); }
    catch (error) { current(ctx); throw new Refusal("unavailable", "WebCrypto SHA-256 failed"); }
    current(ctx);
    return Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, "0")).join("");
  }
  // Reject duplicate decoded keys (including escaped equivalents) before JSON.parse.
  function strictJson(bytes) {
    let source;
    try { source = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes); }
    catch (error) { throw new Refusal("error", "Malformed UTF-8 JSON artifact"); }
    let at = 0;
    const space = () => { while (/[ \t\r\n]/.test(source[at] || "") && at < source.length) at++; };
    function string() {
      const start = at++;
      while (at < source.length) {
        const c = source[at++];
        if (c === "\\") at++;
        else if (c === '"') { try { return JSON.parse(source.slice(start, at)); } catch (error) { break; } }
      }
      throw new Refusal("error", "Malformed JSON string");
    }
    function value(depth) {
      if (depth > 64) throw new Refusal("unavailable", "JSON nesting exceeds 64");
      space();
      if (source[at] === "{") {
        at++; space(); const seen = new Set();
        if (source[at] === "}") { at++; return; }
        for (;;) {
          demand(source[at] === '"', "Malformed JSON object"); const name = string();
          demand(!seen.has(name), "Duplicate JSON key"); seen.add(name); space();
          demand(source[at++] === ":", "Malformed JSON key"); value(depth + 1); space();
          const c = source[at++]; if (c === "}") return;
          demand(c === ",", "Malformed JSON object separator"); space();
        }
      }
      if (source[at] === "[") {
        at++; space(); if (source[at] === "]") { at++; return; }
        for (;;) { value(depth + 1); space(); const c = source[at++]; if (c === "]") return; demand(c === ",", "Malformed JSON array separator"); }
      }
      if (source[at] === '"') { string(); return; }
      const token = /^(?:-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)/.exec(source.slice(at));
      demand(!!token, "Malformed JSON value");
      if (!/^(?:true|false|null)$/.test(token[0])) demand(finite(Number(token[0])), "Nonfinite JSON number");
      at += token[0].length;
    }
    value(0); space(); demand(at === source.length, "Trailing JSON data");
    let result; try { result = JSON.parse(source); } catch (error) { throw new Refusal("error", "Malformed JSON artifact"); }
    demand(object(result), "JSON artifact must be an object"); return result;
  }
  function manifested(ctx, path, sha = null) {
    const artifact = ctx.manifest.get(pathCheck(path));
    if (!artifact) throw new Refusal("partial", `Artifact is not manifested: ${path}`);
    demand(sha === null || artifact.sha256 === sha, `Artifact/source identity differs: ${path}`); return artifact;
  }
  async function read(ctx, path) {
    current(ctx); const artifact = manifested(ctx, path);
    if (artifact.size_bytes > JSON_LIMIT) throw new Refusal("unavailable", `JSON exceeds 32 MiB reader limit: ${path}`);
    if (ctx.total + artifact.size_bytes > TOTAL_LIMIT) throw new Refusal("unavailable", "Total parsed payload exceeds 16 MiB; download only");
    let original;
    try { original = await ctx.fetchBytes(path); }
    catch (error) { current(ctx); throw new Refusal("partial", `Manifested artifact unavailable: ${path}`); }
    current(ctx); demand(original instanceof Uint8Array, "fetchBytes must return Uint8Array");
    const bytes = Uint8Array.from(original); // Never consume caller-owned mutable bytes across digest await.
    demand(bytes.byteLength === artifact.size_bytes, `Artifact byte length differs: ${path}`);
    demand(await hash(ctx, bytes) === artifact.sha256, `Artifact SHA-256 differs: ${path}`);
    current(ctx); ctx.total += bytes.byteLength; return strictJson(bytes);
  }
  function context(inspection, fetchBytes, isCurrent) {
    demand(typeof fetchBytes === "function" && typeof isCurrent === "function", "Reader callbacks required");
    const saved = copy(inspection); demand(saved?.integrity === "VERIFIED", "Inspection integrity must be VERIFIED");
    const r = saved.result, p = saved.proposal, h = saved.hashes;
    demand(object(r) && object(p) && text(r.experiment_id) && p.id === r.experiment_id && text(p.study_id) &&
      SHA.test(r.model_revision) && p.model_revision === r.model_revision && SHA.test(r.proposal_revision) &&
      r.provenance?.proposal_sha256 === r.proposal_revision && r.provenance.adapter === p.physics?.backend &&
      equal(r.provenance.execution_settings, p.execution), "Core proposal/result identity differs");
    demand(r.study?.id === p.study_id && saved.study?.id === p.study_id && saved.thread?.experiment === p.id &&
      saved.thread?.study === p.study_id && saved.thread?.model_revision === r.model_revision &&
      saved.thread?.result === "result.json" && saved.ledger?.experiment_id === p.id,
    "Inspection thread/study/ledger identity differs");
    demand(object(h) && [h.result_sha256, h.thread_sha256, h.proposal_sha256, h.ledger_sha256, h.study_sha256].every(x => SHA.test(x)) &&
      saved.ledger.result_sha256 === h.result_sha256 && saved.ledger.thread_sha256 === h.thread_sha256,
    "Inspection ledger/document byte hashes differ");
    demand(Array.isArray(r.artifacts) && r.artifacts.length <= 2048 && object(r.metrics) && Array.isArray(r.validations) &&
      Array.isArray(r.evidence) && text(r.status) && text(r.decision) && text(r.solver_status) && typeof r.converged === "boolean" &&
      COMMIT.test(r.provenance.source_commit) && COMMIT.test(r.provenance.core_commit), "Incomplete retained Core verdict/provenance");
    const manifest = new Map(), seen = new Set();
    for (const row of r.artifacts) {
      demand(object(row) && SHA.test(row.sha256) && integer(row.size_bytes) && row.revision === r.proposal_revision, "Artifact hash/size/proposal revision differs");
      const path = pathCheck(row.path), folded = path.toLowerCase(); demand(!seen.has(folded), "Duplicate artifact path");
      seen.add(folded); manifest.set(path, freeze(row));
    }
    demand(equal(h.artifacts, r.artifacts), "Inspection manifest copies differ");
    demand(manifest.get("proposal.json")?.sha256 === h.proposal_sha256, "Raw proposal file hash differs; canonical revision is separate");
    freeze(saved);
    const metadata = freeze({ experimentId: p.id, studyId: p.study_id, modelRevision: r.model_revision,
      proposalRevision: r.proposal_revision, sourceCommit: r.provenance.source_commit,
      sourceHashes: r.provenance.adapter_details?.captured_source_sha256 || {},
      meshVariant: p.execution?.mesh_variant ?? null, order: null, inst: null,
      status: r.status, decision: r.decision, solverStatus: r.solver_status, converged: r.converged,
      metrics: r.metrics, validations: r.validations, aliases: {} });
    const downloads = freeze([...manifest.values()].map(row => ({ path: row.path, sha256: row.sha256,
      sizeBytes: row.size_bytes, revision: row.revision })));
    return { saved, manifest, metadata, downloads, fetchBytes, isCurrent, total: 0 };
  }
  function settings(ctx) {
    const s = ctx.saved.proposal.execution, refined = Object.hasOwn(s, "mesh_variant");
    keys(s, ["case", "material", "top_displacement_m", "limits", ...(refined ? ["mesh_variant"] : [])], "Contact settings");
    if (refined) demand(s.mesh_variant === "uniform_quad4_2x", "Unsupported contact mesh selector");
    keys(s.material, ["youngs_modulus_pa", "poisson_ratio"], "Contact material"); keys(s.limits, ["reference_relative", "force_balance_relative"], "Contact limits");
    demand(s.case === CASE && finite(s.material.youngs_modulus_pa) && s.material.youngs_modulus_pa >= 1e4 &&
      s.material.youngs_modulus_pa <= 1e9 && s.material.poisson_ratio === 0 && finite(s.top_displacement_m) &&
      s.top_displacement_m <= -1e-4 && s.top_displacement_m >= -0.2 && s.limits.reference_relative === 0.01 &&
      s.limits.force_balance_relative === 1e-6, "Unsupported contact settings/reference limits");
    return refined ? REFINED : ORIGINAL;
  }
  function sourceBinding(ctx, profile) {
    const d = ctx.saved.result.provenance.adapter_details, s = d?.captured_source_sha256;
    demand(object(d) && d.adapter === BACKEND && object(s), "Missing captured contact source map");
    const required = ["codeaster_contact.py", "codeaster_contact_worker.py", "codeaster_worker.py", "codeaster_runtime_adapter.py",
      "codeaster_execution.py", "execution_control.py", "domain_reference.py", "reference_specification.json", "frozen_mesh.json"];
    if (profile === REFINED) required.push("codeaster_contact_mesh.py", "mesh_generation_recipe.json", PROFILE_FILE,
      "source_parent_mesh.json", "source_parent.mmed", "selected_source.mmed");
    demand(required.every(name => Object.hasOwn(s, name)), "Incomplete captured contact source map");
    for (const [name, sha] of Object.entries(s)) {
      demand(text(name) && !name.includes("/") && SHA.test(sha), "Unsafe or malformed source map entry");
      manifested(ctx, `simulation/${pathCheck(name)}`, sha);
    }
    demand(s["frozen_mesh.json"] === profile.catalog && s["reference_specification.json"] === REF_SHA &&
      d.mesh_sha256 === profile.mesh && d.mesh_catalog_sha256 === profile.catalog &&
      d.native_input === "simulation/level_0/mesh.mmed" && equal(d.native_fields, ["simulation/level_0/results.med"]),
    "Selected mesh/reference/native artifact identity differs");
    demand(d.domain_plugin?.module === "plugins.contact_patch.reference" &&
      d.domain_plugin.source_artifact === "simulation/domain_reference.py" && d.domain_plugin.source_sha256 === s["domain_reference.py"],
    "Domain source identity differs");
    manifested(ctx, d.native_input, profile.mesh); manifested(ctx, "simulation/level_0/results.med");
    for (const name of ["depl", "reac_noda", "lags_c", "sief_elga"]) manifested(ctx, `simulation/level_0/order_1_${name}.table.json`);
    if (profile === REFINED) {
      demand(d.mesh_variant === "uniform_quad4_2x" && d.mesh_profile_sha256 === profile.profile &&
        d.generation_recipe_sha256 === profile.recipe && d.generation_source_sha256 === profile.generator &&
        s[PROFILE_FILE] === profile.profile && s["mesh_generation_recipe.json"] === profile.recipe &&
        s["codeaster_contact_mesh.py"] === profile.generator && s["source_parent_mesh.json"] === ORIGINAL.catalog &&
        s["source_parent.mmed"] === ORIGINAL.mesh && s["selected_source.mmed"] === profile.mesh, "Refined source profile differs");
    } else demand(d.mesh_variant === undefined || d.mesh_variant === null, "Original source has a refined selector");
    return d;
  }
  function declaration(ctx, decl, reference, profile) {
    const p = ctx.saved.proposal, analysis = p.extensions?.model_analysis, s = p.execution, m = decl.model?.mesh;
    demand(analysis?.model_revision === p.model_revision && equal(analysis.declaration, decl) && decl.case === CASE &&
      equal(p.model, decl.model) && equal(p.boundary_conditions, decl.boundary_conditions) && equal(p.loads, decl.loads) &&
      ["fields", "load_parameter", "sample_coordinate_unit", "sample_points"].every(k => equal(p.outputs?.[k], decl.outputs?.[k])),
    "Retained declaration/proposal/model revision differs");
    demand(m?.node_count === profile.nodes && m.solid_cell_count === profile.quads && m.boundary_segment_count === profile.segments &&
      m.slave_contact_segment_count === profile.slave - 1 && m.master_contact_segment_count === profile.master - 1 &&
      m.topology === "quadrilateral" && m.order === 1 && m.original_coordinates_preserved === true &&
      m.coincident_interface_nodes_merged === false && equal(decl.history?.load_parameter, [0, 1]) &&
      equal(decl.outputs?.load_parameter, [0, 1]), "Declared contact profile/history differs");
    const outputs = decl.outputs.fields;
    demand(Array.isArray(outputs) && outputs.some(f => f.field === "displacement" && f.location === "nodes" && f.unit === "m" && equal(f.components, ["x", "y"])) &&
      outputs.some(f => f.field === "reactions" && f.location === "nodes" && f.unit === "N/m" && equal(f.components, ["x", "y"])) &&
      outputs.some(f => f.field === "normal_traction" && f.location === "slave_contact_nodes" && f.unit === "Pa" && f.compression_sign === "negative") &&
      outputs.some(f => f.field === "stress" && f.unit === "Pa"), "Declared field locations/units differ");
    demand(reference.schema_version === 1 && reference.id === "contact-patch-ssnp121a-v1" && reference.case === CASE &&
      reference.source?.tag === "17.4.0" && reference.source.commit === UPSTREAM &&
      reference.mesh?.native_med_sha256 === ORIGINAL.mesh && reference.mesh.native_catalog_sha256 === ORIGINAL.catalog,
    "Sealed original reference identity differs");
    demand(decl.reference?.case === CASE && decl.reference.reference_identity === "Code_Aster_SSNP121A" &&
      equal(decl.reference.material, s.material) && decl.reference.six_published_sample_relative_limits === s.limits.reference_relative &&
      decl.reference.units?.length === "m" && decl.reference.units.normal_traction === "Pa" && decl.reference.units.reaction_resultant === "N/m",
    "Declared reference/material/units differ");
    demand(decl.model.materials?.[0]?.youngs_modulus?.value === s.material.youngs_modulus_pa &&
      decl.model.materials[0].youngs_modulus.unit === "Pa" && decl.model.materials[0].poisson_ratio?.value === s.material.poisson_ratio &&
      decl.loads?.[0]?.unit === "m" && equal(decl.loads[0].values, [0, s.top_displacement_m]), "Declared material/loading differs from settings");
    if (profile === REFINED) {
      demand(m.mesh_variant === "uniform_quad4_2x" && m.asset_sha256 === profile.mesh && m.catalog_sha256 === profile.catalog &&
        m.mesh_profile_sha256 === profile.profile && m.generation_recipe_sha256 === profile.recipe && m.generation_source_sha256 === profile.generator &&
        m.parent_asset_sha256 === ORIGINAL.mesh && m.original_prefix_node_count === 313 && m.original_vendor_mesh_replication === false &&
        decl.reference.mesh_variant === "uniform_quad4_2x" && decl.reference.reference_kind === "analytical_mesh_refinement" &&
        decl.reference.canonical_original_inputs === false && decl.reference.original_vendor_mesh_replication === false,
      "Refined declaration masquerades as original replication");
    } else demand(m.mesh_variant === undefined && m.source === "fixed_original_nonmatching_mesh" &&
      ["original_published_analytical_case", "analytical_parameter_variant"].includes(decl.reference.reference_kind), "Original declaration profile differs");
  }
  function ids(values, count, label) {
    demand(Array.isArray(values) && values.length === count && values.every(integer) && new Set(values).size === count, `${label}: unique complete numeric IDs required`);
    return new Set(values);
  }
  function sameSet(a, b, label) { demand(a.size === b.size && [...a].every(x => b.has(x)), `${label}: ID membership differs`); }
  function vectors(values, count, size, label) {
    demand(Array.isArray(values) && values.length === count && values.every(v => Array.isArray(v) && v.length === size && v.every(finite)), `${label}: finite full component coverage required`);
  }
  function strings(values, count, label) {
    demand(Array.isArray(values) && values.length === count && values.every(text) && new Set(values).size === count, `${label}: unique raw identifiers required`);
  }
  function meshBinding(mesh, frozen, checks, profile) {
    demand(mesh.schema_version === "1" && mesh.node_indexing === "ZERO_BASED_CODE_ASTER_UNRENUMBERED" && mesh.native_node_names === null &&
      frozen.node_indexing === "ZERO_BASED_MEDLOADER_UNRENUMBERED", "Actual native mesh indexing/name observation differs");
    const nodeSet = ids(mesh.node_ids, profile.nodes, "Native nodes");
    demand(mesh.node_ids.every((id, i) => id === i), "Native numeric node order differs from frozen source");
    vectors(mesh.coordinates_m, profile.nodes, 3, "Native nodal XYZ"); vectors(frozen.coordinates_in_native_order, profile.nodes, 2, "Frozen original/refined XY");
    demand(mesh.coordinates_m.every((p, i) => equal(p, [...frozen.coordinates_in_native_order[i], 0])), "Native coordinate/order drift from frozen source");
    keys(frozen.levels, ["0", "-1"], "Frozen mesh levels");
    const cellsById = new Map(), sourceCells = new Map(), sourceGroups = new Map(), sourceByNative = new Map();
    for (const [level, type, count] of [["0", "QUAD4", profile.quads], ["-1", "SEG2", profile.segments]]) {
      const row = frozen.levels[level]; demand(row.node_count === profile.nodes && row.cell_count === count &&
        Array.isArray(row.cell_connectivity_in_native_order) && row.cell_connectivity_in_native_order.length === count && object(row.groups), "Frozen cell profile differs");
      row.cell_connectivity_in_native_order.forEach((conn, id) => {
        ids(conn, type === "QUAD4" ? 4 : 2, "Frozen connectivity"); demand(conn.every(n => nodeSet.has(n)), "Foreign frozen node");
        const key = `${type}:${conn.join(",")}`; demand(!sourceCells.has(key), "Ambiguous frozen directed connectivity"); sourceCells.set(key, `${level}:${id}`);
      });
      for (const [name, group] of Object.entries(row.groups)) {
        demand(!sourceGroups.has(name), "Duplicate frozen group name"); ids(group.cell_ids, group.cell_count, "Frozen group cells");
        demand(group.cell_ids.every(i => i < count), "Foreign frozen group cell"); sourceGroups.set(name, new Set(group.cell_ids.map(i => `${level}:${i}`)));
      }
    }
    demand(Array.isArray(mesh.cells) && mesh.cells.length === profile.quads + profile.segments, "Incomplete native cell catalogue");
    const seenSource = new Set(), usedNodes = new Set();
    for (const cell of mesh.cells) {
      demand(object(cell) && integer(cell.cell_id) && !cellsById.has(cell.cell_id) && ["QUAD4", "SEG2"].includes(cell.cell_type), "Duplicate/foreign native cell/type");
      ids(cell.node_ids, cell.cell_type === "QUAD4" ? 4 : 2, "Native connectivity"); demand(cell.node_ids.every(n => nodeSet.has(n)), "Foreign native cell node");
      const source = sourceCells.get(`${cell.cell_type}:${cell.node_ids.join(",")}`);
      demand(source !== undefined && !seenSource.has(source), "Native directed connectivity differs from frozen source");
      seenSource.add(source); sourceByNative.set(cell.cell_id, source); cellsById.set(cell.cell_id, cell); cell.node_ids.forEach(n => usedNodes.add(n));
    }
    sameSet(usedNodes, nodeSet, "Full native node/cell coverage");
    keys(mesh.group_cell_ids, [...sourceGroups.keys()], "Complete native cell groups");
    const boundaryNodes = {};
    for (const [name, expected] of sourceGroups) {
      const actual = ids(mesh.group_cell_ids[name], expected.size, "Native cell group");
      demand([...actual].every(id => cellsById.has(id)), "Foreign native group cell");
      sameSet(new Set([...actual].map(id => sourceByNative.get(id))), expected, `Frozen/native group ${name}`);
      if (BOUNDARIES.includes(name)) boundaryNodes[name] = new Set([...actual].flatMap(id => cellsById.get(id).node_ids));
    }
    demand(Object.keys(boundaryNodes).length === 8 && boundaryNodes.AB.size === profile.slave && boundaryNodes.EF.size === profile.master &&
      [...boundaryNodes.AB].every(id => !boundaryNodes.EF.has(id)), "Separate nonmatching slave/master interface differs");
    keys(mesh.group_node_ids, [...Object.keys(frozen.node_groups), ...GENERATED_NODE_GROUPS], "Complete original/generated node groups");
    for (const [name, row] of Object.entries(frozen.node_groups)) {
      const expected = ids(row.node_ids, row.node_ids.length, "Frozen named nodes");
      sameSet(ids(mesh.group_node_ids[name], expected.size, "Native named nodes"), expected, `Named group ${name}`);
      demand(equal(row.coordinates, row.node_ids.map(id => frozen.coordinates_in_native_order[id])), "Frozen named coordinate identity differs");
    }
    for (const name of GENERATED_NODE_GROUPS) sameSet(ids(mesh.group_node_ids[name], boundaryNodes[name].size, "Native generated group"), boundaryNodes[name], name);
    demand(checks?.status === "PASS" && checks.node_count === profile.nodes && checks.body_element_count === profile.quads &&
      checks.boundary_element_count === profile.segments && checks.total_cell_count === mesh.cells.length &&
      checks.mesh_sha256 === profile.mesh && checks.mesh_inspection_sha256 === profile.catalog, "Retained native mesh gate identity differs");
    demand(Array.isArray(checks.source_cell_mapping) && checks.source_cell_mapping.length === mesh.cells.length, "Incomplete captured source/native cell map");
    const mapped = new Set();
    for (const row of checks.source_cell_mapping) {
      demand(integer(row.native_cell_id) && integer(row.source_cell_id) && ["0", "-1"].includes(row.source_level) &&
        !mapped.has(row.native_cell_id) && sourceByNative.get(row.native_cell_id) === `${row.source_level}:${row.source_cell_id}`, "Captured source/native cell map differs");
      mapped.add(row.native_cell_id);
    }
    keys(checks.boundary_node_ids, BOUNDARIES, "Captured boundary coverage");
    for (const name of BOUNDARIES) sameSet(ids(checks.boundary_node_ids[name], boundaryNodes[name].size, "Captured boundary nodes"), boundaryNodes[name], name);
    return { nodeSet, cellsById, boundaryNodes };
  }
  function table(raw, columns, count, name, order) {
    keys(raw, columns, `Native ${name} table`);
    demand(Object.values(raw).every(v => Array.isArray(v) && v.length === count), `Native ${name} table column/row coverage differs`);
    demand(raw.NUME_ORDRE.every(v => v === order) && raw.NOM_CHAM.every(v => v === (name === "LAGS_C" ? "DEPL" : name)) &&
      raw.RESULTAT.every(text) && new Set(raw.RESULTAT).size === 1, `Native ${name} field/result/order differs`);
  }
  function nodal(raw, rawIds, coords, values, components, name) {
    const n = rawIds.length;
    strings(rawIds, n, `Normalized ${name} identifiers`);
    table(raw, ["NOEUD", "COOR_X", "COOR_Y", "COOR_Z", "NUME_ORDRE", "NOM_CHAM", "RESULTAT", ...components], n, name, 1);
    strings(raw.NOEUD, n, `Native ${name} identifiers`);
    const byRaw = new Map(raw.NOEUD.map((id, i) => [id, i]));
    rawIds.forEach((id, i) => {
      const r = byRaw.get(id); demand(r !== undefined, `Native ${name} raw identifier is not supplied by normalized mapping`);
      const actual = [raw.COOR_X[r], raw.COOR_Y[r], raw.COOR_Z[r]], v = components.map(c => raw[c][r]);
      demand(actual.every(finite) && v.every(finite) && equal(actual, coords[i]) && equal(v, values[i]), `Native ${name} coordinates/components differ from normalized rows`);
    });
  }
  function fields(worker, shape, decl, profile) {
    const observation = worker.observation, f = observation?.fields, mesh = worker.mesh;
    demand(object(observation) && object(f) && f.node_indexing === mesh.node_indexing && f.actual_result_order === 1 && f.load_parameter === 1 &&
      equal(f.node_ids, mesh.node_ids) && equal(f.coordinates_m, mesh.coordinates_m) && equal(f.displacement_component_order, ["dx", "dy"]) &&
      equal(f.stress_component_order, ["xx", "yy", "zz", "xy"]) && equal(f.stress_coordinate_component_order, ["x", "y"]), "Full normalized field identity/components/order differs");
    vectors(f.displacements_m, profile.nodes, 2, "Normalized U"); vectors(f.nodal_reactions_n_per_m, profile.nodes, 2, "Normalized RF");
    keys(worker.native_tables, ["DEPL", "REAC_NODA", "LAGS_C", "SIEF_ELGA"], "Complete native tables");
    const resultLabel = worker.native_tables.DEPL?.RESULTAT?.[0];
    demand(text(resultLabel) && Object.values(worker.native_tables).every(t =>
      Array.isArray(t.RESULTAT) && t.RESULTAT.every(label => label === resultLabel)), "Native tables refer to different actual result labels");
    nodal(worker.native_tables.DEPL, f.raw_node_identifiers, f.coordinates_m, f.displacements_m, ["DX", "DY"], "DEPL");
    nodal(worker.native_tables.REAC_NODA, f.raw_reaction_node_identifiers, f.coordinates_m, f.nodal_reactions_n_per_m, ["DX", "DY"], "REAC_NODA");
    const nodes = mesh.node_ids.map((id, i) => ({ id, rawDeplId: f.raw_node_identifiers[i], rawReactionId: f.raw_reaction_node_identifiers[i],
      xyz_m: f.coordinates_m[i], u: { dx: f.displacements_m[i][0], dy: f.displacements_m[i][1] },
      rf_n_per_m: { dx: f.nodal_reactions_n_per_m[i][0], dy: f.nodal_reactions_n_per_m[i][1] } }));
    const slave = observation.slave_contact;
    demand(object(slave) && slave.unit === "Pa" && slave.source_field === "DEPL.LAGS_C" && slave.sign === "Native signed normal traction retained", "Native signed slave traction provenance differs");
    sameSet(ids(slave.node_ids, profile.slave, "Normalized slave nodes"), shape.boundaryNodes.AB, "Complete actual slave coverage");
    demand(Array.isArray(slave.normal_traction_pa) && slave.normal_traction_pa.length === profile.slave && slave.normal_traction_pa.every(finite), "Incomplete/nonfinite slave pressure");
    const index = new Map(mesh.node_ids.map((id, i) => [id, i]));
    const slaveCoordinates = slave.node_ids.map(id => f.coordinates_m[index.get(id)]);
    nodal(worker.native_tables.LAGS_C, slave.raw_node_identifiers, slaveCoordinates, slave.normal_traction_pa.map(v => [v]), ["LAGS_C"], "LAGS_C");
    const slaves = slave.node_ids.map((id, i) => ({ id, rawId: slave.raw_node_identifiers[i], xyz_m: slaveCoordinates[i], normalTractionPa: slave.normal_traction_pa[i] }));
    demand(slaves.every(row => row.rawId === f.raw_node_identifiers[index.get(row.id)]), "Pressure/displacement raw node mappings differ");
    const aliases = {}, samples = observation.samples;
    keys(samples, ["A", "B", "N14"], "Published aliases");
    for (const [name, expected] of [["A", 0], ["B", 1], ["N14", 13]]) {
      const id = mesh.group_node_ids[name][0], sample = samples[name], row = slaves.find(v => v.id === id);
      demand(mesh.group_node_ids[name].length === 1 && id === expected && sample.node_id === id && row &&
        sample.raw_node_identifier === row.rawId && sample.normal_traction_pa === row.normalTractionPa &&
        sample.vertical_displacement_m === nodes[index.get(id)].u.dy && equal(decl.outputs.sample_points[name], row.xyz_m.slice(0, 2)), "Actual sample/group/field alias identity differs");
      aliases[name] = id;
    }
    demand(mesh.coordinates_m[13][0] === 2.98023223876953e-08 && mesh.coordinates_m[13][1] === 0, "N14 original nonzero coordinate was lost");
    const count = profile.quads * 4;
    vectors(f.stresses_pa, count, 4, "Normalized full stress"); vectors(f.stress_point_coordinates_m, count, 2, "Native stress XY");
    demand(Array.isArray(f.stress_integration_weights_m2) && f.stress_integration_weights_m2.length === count &&
      f.stress_integration_weights_m2.every(w => finite(w) && w > 0) && f.stress_geometric_z_m === null &&
      f.stress_geometric_z_status === "UNAVAILABLE; native EGGAU2D measures X/Y/W", "Genuine XY/W and unavailable geometric Z required");
    const wp = f.stress_integration_weight_provenance;
    demand(wp?.native_component === "EGGAU2D.W" && wp.raw_table_column === "COOR_Z" && wp.unit === "m^2" &&
      wp.upstream_commit === UPSTREAM && wp.upstream_tag === "17.4.0" && Array.isArray(wp.source_chain) && wp.source_chain.length === 4 &&
      wp.source_chain.every(text), "Native integration weight source/units differ");
    demand(Array.isArray(f.stress_identifiers) && f.stress_identifiers.length === count, "Incomplete actual stress point identifiers");
    const raw = worker.native_tables.SIEF_ELGA;
    table(raw, ["MAILLE", "NUME_ORDRE", "POINT", "SOUS_POINT", "NOM_CHAM", "RESULTAT", "COOR_X", "COOR_Y", "COOR_Z", "SIXX", "SIYY", "SIZZ", "SIXY"], count, "SIEF_ELGA", 1);
    const native = new Map(), tuple = (id, o, p, s) => JSON.stringify([id, o, p, s]);
    for (let i = 0; i < count; i++) {
      demand(text(raw.MAILLE[i]) && integer(raw.POINT[i]) && raw.POINT[i] >= 1 && raw.POINT[i] <= 4 && raw.SOUS_POINT[i] === 1, "Malformed native stress IDs/point/subpoint");
      const key = tuple(raw.MAILLE[i], raw.NUME_ORDRE[i], raw.POINT[i], raw.SOUS_POINT[i]); demand(!native.has(key), "Duplicate native stress tuple"); native.set(key, i);
    }
    const seen = new Set(), cellRaw = new Map(), rawCell = new Map(), points = new Map();
    const gauss = f.stress_identifiers.map((id, i) => {
      demand(object(id) && integer(id.cell_id) && shape.cellsById.get(id.cell_id)?.cell_type === "QUAD4" && id.order === 1 &&
        integer(id.point) && id.point >= 1 && id.point <= 4 && id.subpoint === 1 && text(id.raw_element_identifier), "Foreign/malformed normalized stress cell/order/point");
      const key = tuple(id.raw_element_identifier, id.order, id.point, id.subpoint), r = native.get(key);
      demand(r !== undefined && !seen.has(key), "Missing/duplicate normalized-to-native stress tuple"); seen.add(key);
      demand((!cellRaw.has(id.cell_id) || cellRaw.get(id.cell_id) === id.raw_element_identifier) &&
        (!rawCell.has(id.raw_element_identifier) || rawCell.get(id.raw_element_identifier) === id.cell_id), "Raw element/native cell bijection differs");
      cellRaw.set(id.cell_id, id.raw_element_identifier); rawCell.set(id.raw_element_identifier, id.cell_id);
      const cellPoints = points.get(id.cell_id) || new Set(); demand(!cellPoints.has(id.point), "Duplicate actual cell Gauss point"); cellPoints.add(id.point); points.set(id.cell_id, cellPoints);
      const xy = [raw.COOR_X[r], raw.COOR_Y[r]], stress = [raw.SIXX[r], raw.SIYY[r], raw.SIZZ[r], raw.SIXY[r]], weight = raw.COOR_Z[r];
      demand(xy.every(finite) && stress.every(finite) && finite(weight) && weight > 0 && equal(xy, f.stress_point_coordinates_m[i]) &&
        equal(stress, f.stresses_pa[i]) && weight === f.stress_integration_weights_m2[i], "Native stress components/XY/W differ from normalized rows");
      return { cellId: id.cell_id, rawElementId: id.raw_element_identifier, order: id.order, point: id.point, subpoint: id.subpoint,
        xy_m: xy, weight_m2: weight, stress_pa: { xx: stress[0], yy: stress[1], zz: stress[2], xy: stress[3] } };
    });
    const solids = new Set([...shape.cellsById.values()].filter(c => c.cell_type === "QUAD4").map(c => c.cell_id));
    sameSet(new Set(points.keys()), solids, "Full solid stress coverage"); demand([...points.values()].every(v => v.size === 4), "All four actual Gauss points required per solid cell");
    return { nodes, slave: slaves, gauss, aliases };
  }
  async function refinement(ctx, frozen, decl, profile, detail) {
    if (profile !== REFINED) return;
    const recipe = await read(ctx, "simulation/mesh_generation_recipe.json"); current(ctx);
    const record = await read(ctx, `simulation/${PROFILE_FILE}`); current(ctx);
    const parent = await read(ctx, "simulation/source_parent_mesh.json"); current(ctx);
    demand(record.kind === "SEALED_UNIFORM_QUAD4_2X_CONTACT_PROFILE" && record.readback_status === "PASS_FULL_COORDINATE_CONNECTIVITY_GROUP_NAME_IDENTITY" &&
      record.pins?.mesh_sha256 === profile.mesh && record.pins.catalog_sha256 === profile.catalog && record.pins.recipe_sha256 === profile.recipe &&
      record.pins.generator_sha256 === profile.generator && record.parent?.mesh_sha256 === ORIGINAL.mesh && record.parent.catalog_sha256 === ORIGINAL.catalog &&
      equal(record.parent, recipe.parent) && equal(record.parent, detail.source_parent_mesh), "Refined profile/generation/parent hash binding differs");
    demand(record.shape?.node_count === profile.nodes && record.shape.quad4_count === profile.quads && record.shape.seg2_count === profile.segments &&
      record.shape.slave_nodes === profile.slave && record.shape.master_nodes === profile.master && record.shape.variant === "uniform_quad4_2x" &&
      equal(record.shape, recipe.shape) && recipe.variant === "uniform_quad4_2x" && recipe.original_prefix_count === 313 &&
      recipe.generator_source_sha256 === profile.generator && equal(recipe.A_B_N14_original_ids, { A: 0, B: 1, N14: 13 }) &&
      equal(parent.coordinates_in_native_order, frozen.coordinates_in_native_order.slice(0, 313)) && parent.coordinates_in_native_order.length === 313,
    "Refined recipe/profile/original prefix differs");
    demand(Array.isArray(recipe.node_parent_map) && recipe.node_parent_map.length === profile.nodes &&
      Array.isArray(recipe.cell_parent_map?.["0"]) && recipe.cell_parent_map["0"].length === profile.quads &&
      Array.isArray(recipe.cell_parent_map?.["-1"]) && recipe.cell_parent_map["-1"].length === profile.segments,
    "Refined generation mappings incomplete");
  }
  function fail(error, ctx) {
    return freeze({ status: error instanceof Refusal ? error.status : "error", reason: error instanceof Refusal ? error.message : "Malformed retained contact record",
      metadata: ctx?.metadata || null, downloads: ctx?.downloads || [], nodes: [], cells: [], nodeGroups: {}, cellGroups: {}, slave: [], gauss: [], limitations: LIMITATIONS });
  }
  async function loadContactField(inspection, fetchBytes, isCurrent) {
    let ctx;
    try {
      ctx = context(inspection, fetchBytes, isCurrent); current(ctx);
      if (ctx.saved.result.provenance.adapter !== BACKEND) throw new Refusal("unavailable", "Backend is outside the bounded contact field reader");
      const profile = settings(ctx), detail = sourceBinding(ctx, profile);
      const decl = await read(ctx, "simulation/model_declaration.json"); current(ctx);
      const input = await read(ctx, "simulation/input.json"); current(ctx);
      const level = await read(ctx, "simulation/level_0/input.json"); current(ctx);
      const frozen = await read(ctx, "simulation/frozen_mesh.json"); current(ctx);
      const mesh = await read(ctx, "simulation/level_0/mesh_catalog.json"); current(ctx);
      const observation = await read(ctx, "simulation/level_0/parsed_contact.json"); current(ctx);
      const worker = await read(ctx, "simulation/level_0/worker_result.json"); current(ctx);
      const reference = await read(ctx, "simulation/reference_specification.json"); current(ctx);
      keys(level, ["settings", "mesh_sha256", "mesh_inspection_sha256"], "Captured worker input");
      demand(equal(input, ctx.saved.proposal.execution) && equal(level.settings, input) && level.mesh_sha256 === profile.mesh &&
        level.mesh_inspection_sha256 === profile.catalog, "Captured execution/input/selected mesh differs");
      declaration(ctx, decl, reference, profile);
      demand(worker.schema_version === "1" && worker.input_sha256 === manifested(ctx, "simulation/level_0/input.json").sha256 &&
        worker.mesh_input_sha256 === profile.mesh && worker.mesh_inspection_sha256 === profile.catalog && equal(worker.mesh, mesh) &&
        equal(worker.frozen_mesh, frozen) && equal(worker.observation, observation) &&
        (profile === REFINED ? worker.mesh_variant === "uniform_quad4_2x" : worker.mesh_variant === undefined || worker.mesh_variant === null),
      "Captured worker/input/mesh/observation identity differs");
      demand(worker.solver_status === "COMPLETED" && worker.converged === true && worker.order === 1 &&
        (equal(worker.available_orders, [0, 1]) || equal(worker.available_orders, [1])) &&
        equal(worker.access_parameters?.NUME_ORDRE, worker.available_orders) && equal(worker.access_parameters.INST, worker.available_orders),
      "Captured final order must be NUME_ORDRE1 / INST1");
      demand(equal(worker.native_policy, detail.nonlinear_policy) && worker.native_policy?.modelisation === "D_PLAN" &&
        worker.native_policy.relation === "ELAS" && worker.native_policy.deformation === "PETIT" &&
        worker.native_policy.convergence?.ARRET === "OUI" && worker.native_policy.convergence.RESI_GLOB_MAXI === 2e-8 &&
        worker.native_material?.ELAS?.E === input.material.youngs_modulus_pa && worker.native_material.ELAS.NU === 0 &&
        worker.native_material.unit === "Pa" && equal(worker.code_aster_runtime, detail.code_aster_runtime) && equal(worker.versions, detail.versions),
      "Captured native policy/material/runtime differs from provenance");
      await refinement(ctx, frozen, decl, profile, detail); current(ctx);
      const shape = meshBinding(mesh, frozen, worker.native_mesh_checks, profile), display = fields(worker, shape, decl, profile);
      current(ctx);
      ctx.metadata = freeze({ ...ctx.metadata, order: 1, inst: 1, aliases: display.aliases });
      return freeze({ status: "available", reason: null, metadata: ctx.metadata, downloads: ctx.downloads,
        nodes: display.nodes, cells: mesh.cells.map(c => ({ id: c.cell_id, type: c.cell_type, nodeIds: c.node_ids })),
        nodeGroups: mesh.group_node_ids, cellGroups: mesh.group_cell_ids, slave: display.slave, gauss: display.gauss, limitations: LIMITATIONS });
    } catch (error) { return fail(error, ctx); }
  }
  const api = Object.freeze({ loadContactField });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.contactFieldInspector = api;
})(typeof window !== "undefined" ? window : globalThis);
