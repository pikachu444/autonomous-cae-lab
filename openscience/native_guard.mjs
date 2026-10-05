// The local controller prepends its existing repository-pin implementation to
// this module. This guard uses the public OpenScience 2.0.146 plugin hooks; it
// does not observe final offered schemas, individual HTTP retries or responses.
import nativeFs from 'node:fs';
import nativePath from 'node:path';
import nativeCrypto from 'node:crypto';
import { execFile as nativeExecFile } from 'node:child_process';
import { fileURLToPath as nativeFileURLToPath } from 'node:url';

const nativeLegacyResearchTools = Object.freeze([
  'caelab_study_create', 'caelab_study_inspect', 'caelab_parameters_discover',
  'caelab_parameters_register', 'caelab_parameters_list', 'caelab_experiment_run',
  'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare',
  'caelab_analysis_run', 'caelab_optimization_plan', 'caelab_optimization_run',
  'caelab_optimization_inspect', 'caelab_pde_run',
]);
const nativeKnownTools = Object.freeze([...nativeLegacyResearchTools, 'caelab_model_analysis_run']);
const nativeStructuralResearchTools = Object.freeze(['caelab_study_create', 'caelab_study_inspect',
  'caelab_model_analysis_run', 'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare']);
const nativeStructuralBackends = Object.freeze(['structural.families.calculix', 'structural.families.code_aster']);
const nativeStructuralCases = Object.freeze({ansys_vmd1_regular:['Fx','Fy','Fz'],
  lame_cylinder_plane_strain:['pressure'], scordelis_lo_solid:['gravity']});
const nativeStructuralRuntime = Object.freeze({MPLBACKEND:'Agg', OMP_NUM_THREADS:'2', QT_QPA_PLATFORM:'offscreen',
  CAELAB_CODEASTER_IMAGE:'/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif',
  CAELAB_CODEASTER_IMAGE_SHA256:'f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64',
  CAELAB_SINGULARITY_COMMAND:'/usr/bin/singularity'});
const nativeStructuralBudgets = Object.freeze({steps:24, mcp_timeout_seconds:3600, command_timeout_seconds:3600,
  model_analysis:{max_mesh_levels:3, max_axis_cells:48, max_elements_per_level:1024,
    max_nodes_per_level:10000, max_load_factor:2}});
const nativePdeResearchTools = Object.freeze(['caelab_study_create', 'caelab_study_inspect',
  'caelab_pde_run', 'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare']);
const nativePdeBackends = Object.freeze(['pde.fenicsx', 'pde.fenicsx.rectangle', 'pde.fenicsx.transient',
  'pde.fenicsx.coupled', 'pde.fenicsx.imported']);
const nativePdeRuntime = Object.freeze({MPLBACKEND:'Agg', OMP_NUM_THREADS:'2', QT_QPA_PLATFORM:'offscreen',
  CAELAB_FENICSX_PYTHON:'/usr/bin/python3'});
const nativePdeBudgets = Object.freeze({steps:24, mcp_timeout_seconds:3600, command_timeout_seconds:3600,
  pde:{max_cell_count:32, max_mesh_levels:3, min_mesh_levels:3, degree:1, max_time_steps:128,
    max_snapshot_node_values:200000, max_imported_bytes:98304, max_request_bytes:131072}});
const nativeAcceptanceTools = Object.freeze(nativeKnownTools.slice(0, 9));
const nativeResearchKeys = Object.freeze(['schema', 'kind', 'agent', 'allowed_tools',
  'runtime_environment', 'budgets', 'capabilities', 'limitations']);
const nativeSettingsKeys = Object.freeze([
  'schema', 'kind', 'repo_root', 'run_name', 'profile_root', 'model', 'allowed',
  'guardPath', 'configPath', 'config_sha256', 'pluginPath', 'plugin_sha256',
  'receipts', 'boot_source', 'boot_source_sha256',
]);
const nativeProjectBindingKeys = Object.freeze([
  'schema', 'kind', 'project_id', 'project_directory', 'source_directory',
  'grant_id', 'working_root', 'access',
]);
const nativeProjectReadTimeoutMs = 5000;
const nativeProjectResponseBound = 128 * 1024;
const nativeSourceReaderKeys = Object.freeze(['node_path', 'node_sha256', 'worker_path', 'worker_sha256']);
const nativeSourceReadTimeoutMs = 20_000;
const nativeSourceResponseBound = 16 * 1024 * 1024;
const nativeSourceEnvironmentKeys = Object.freeze(['SystemRoot', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP']);
// Same top-level import exclusions as the shared repository capture, applied
// independently at each repository/submodule root by the final byte gate.
const nativeIgnoredSourceRoots = Object.freeze(['artifacts', 'runs', '.venv', 'venv', 'node_modules', '.git', '.pytest_cache', '.mypy_cache', '.ruff_cache']);
const nativeSessionId = value => typeof value === 'string' && /^ses_[A-Za-z0-9]{1,124}$/.test(value);
// Official project grants use crypto.randomUUID() (v4); retain bounded legacy IDs.
const nativeGrantId = value => typeof value === 'string' &&
  /^fsg_(?:[A-Za-z0-9]{1,124}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})$/.exec(value)?.[0] === value;
const nativeGuardKeys = Object.freeze([
  'schema', 'kind', 'repo_root', 'run_name', 'profile_root', 'model', 'allowed',
  'required', 'no_tools', 'stopping', 'updated_utc',
]);
const nativeSha = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const nativeRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const nativeCanonical = value => JSON.stringify(value, (_, item) => nativeRecord(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const nativeFreeze = value => {
  if (value !== null && typeof value === 'object') {
    for (const item of Object.values(value)) nativeFreeze(item);
    Object.freeze(value);
  }
  return value;
};
// Exact opt-in PS descriptor; schema1 and all historical profiles are unchanged.
const nativeFixtureRefinementDefinition = nativeFreeze({
  "schema": 7,
  "kind": "autonomous-cae-lab.openscience-research-definition",
  "agent": "research",
  "allowed_tools": [
    "caelab_study_create",
    "caelab_study_inspect",
    "caelab_parameters_discover",
    "caelab_parameters_register",
    "caelab_parameters_list",
    "caelab_experiment_run",
    "caelab_experiment_inspect",
    "caelab_experiment_summary",
    "caelab_experiment_compare",
    "caelab_analysis_run",
    "caelab_optimization_plan",
    "caelab_optimization_run",
    "caelab_optimization_inspect",
    "caelab_pde_run"
  ],
  "runtime_environment": {
    "MPLBACKEND": "Agg",
    "OMP_NUM_THREADS": "2",
    "QT_QPA_PLATFORM": "offscreen",
    "CAELAB_FENICSX_PYTHON": "/usr/bin/python3"
  },
  "budgets": {
    "steps": 24,
    "mcp_timeout_seconds": 3600,
    "command_timeout_seconds": 3600,
    "optimization": {
      "max_generations": 1,
      "population_size": 5
    },
    "analysis": {
      "max_mesh_levels": 3
    },
    "pde": {
      "max_mesh_levels": 3,
      "max_cell_count": 32
    }
  },
  "capabilities": [
    {
      "backend": "fixture.cadquery",
      "operations": [
        "parameters_discover",
        "parameters_register",
        "experiment_run"
      ],
      "model": "roller_support",
      "inputs": "Discover native paths/current values/bounds first. Register only requested research variables; registration bounds must contain the current CAD value and stay within discovered native bounds, including fixed variables. A fixed variable must keep its discovered current_value. A requested different value needs free registration and an explicit experiment value. Unregistered CAD dimensions retain their current defaults.",
      "runtime": "Existing WslPython with pinned fixture/CadQuery dependencies",
      "evidence": "Core source/Python/platform and fixture source fingerprints; immutable CAD artifacts",
      "verification": "IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF"
    },
    {
      "backend": "fixture.calculix",
      "operations": [
        "analysis_run",
        "optimization_plan",
        "optimization_run",
        "optimization_inspect"
      ],
      "inputs": "analysis_run requires exactly parent_experiment_id, experiment_id, backend=fixture.calculix and settings with exactly load/material/mesh. load: force_per_support_N and source. material: model, provenance, qualification; orthotropic E_1_MPa/E_2_MPa/E_3_MPa/nu_12/nu_13/nu_23/G_12_MPa/G_13_MPa/G_23_MPa/axes, or isotropic elastic_modulus_MPa/poisson_ratio. mesh: max_sizes_mm, two or three positive strictly descending sizes in mm. optimization_plan uses this same analysis_settings and deterministic numerical engine.",
      "runtime": "Gmsh and ccx on the configured resident WSL PATH; existing SciPy numerical engine",
      "evidence": "Existing solver executable/version, parent STEP, raw fields, mesh/reaction checks and campaign journals",
      "verification": "IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF",
      "boundary_model": "One verified roller_support solid, roller diameter8.3mm and depth>=24mm: bottom fixed in X/Y/Z; total negative-Z saddle force distributed by clipped tessellated surface area over the central24mm. This idealization is fixed by the existing adapter, not caller-supplied bolt/contact conditions. Orthotropic axes are global CAD X/Y/Z; axes text declares provenance and does not rotate the constitutive tensor.",
      "numerical_verdict": "Existing final-two-mesh displacement relative change<=5% and signed all-axis reaction balance<=1% remain unchanged. Peak stress is an invalid diagnostic, not strength evidence. Three meshes alone do not establish asymptotic convergence."
    },
    {
      "backend": "pde.fenicsx",
      "operations": [
        "pde_run"
      ],
      "inputs": "Bounded scalar linear elliptic weak form on unit square, Dirichlet data, manufactured reference and declared mesh/error limits",
      "runtime": "Existing isolated /usr/bin/python3 FEniCSx worker; not the Lab venv",
      "evidence": "Existing worker source/version/interpreter, fields, reference errors/rates and residual checks",
      "verification": "IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF"
    }
  ],
  "limitations": [
    "Capability metadata does not establish installation, a numerical PASS or engineering approval.",
    "CFD/Navier-Stokes, arbitrary geometry/domain/equation families and PDE input-binding optimization are not admitted by this profile.",
    "One bounded numerical generation does not establish a converged/global optimum.",
    "Solver completion does not qualify strength, materials, physical loads or release.",
    "Other implemented adapters remain outside this bounded research profile until their phase acceptance.",
    "In-flight solver/campaign cancellation is not established by the historical CAD-only cancellation proof.",
    "This opt-in profile admits one additional analysis mesh level; the historical FixtureScalar default remains two. Tool/backend/model/security/cleanup and native execution policies are unchanged.",
    "Arbitrary support boundaries, material rotations, bolt/contact mechanics and original assembly mechanics are not admitted. Missing physical material/load data stay explicitly assumed and UNKNOWN; all results remain NOT_RELEASED."
  ],
  "profile": "fixture-refinement-v1"
});
const nativeMaterialLimits = nativeFreeze({stress_absolute_mpa:1e-10, stress_relative:1e-8,
  tangent_relative:1e-8, energy_absolute_mpa:1e-10, energy_relative:1e-8,
  finite_difference_relative:1e-6, finite_difference_steps:[1e-7,1e-8,1e-9]});
const nativeMaterialDefinition = nativeFreeze({
  schema:4, kind:'autonomous-cae-lab.openscience-research-definition', profile:'material-points-v1', agent:'research',
  allowed_tools:[...nativeStructuralResearchTools], runtime_environment:{...nativeStructuralRuntime},
  budgets:{steps:24, mcp_timeout_seconds:3600, command_timeout_seconds:3600,
    material_point:{min_history_entries:3,max_history_entries:12,max_signed_probe_states:594,max_request_bytes:65536}},
  capabilities:[{backend:'material.mfront.hyperelastic',operations:['model_analysis_run'],cases:['saint_venant_kirchhoff'],
    inputs:'Exact case/material/temperature_k/history/limits; physical nine-component F with 3..12 ordered entries. Domain owns finite-strain/probe scientific admission and fixed reference limits.',
    runtime:'Existing exact17.4 SIF and SHA, TFEL5/MGIS3/MTest and Singularity containment; no runtime or model fallback.',
    evidence:'Immutable Core metrics/checks and hash-bound actual native F/P/A/W histories, all signed probes and same-library MTest. Summaries do not expose full measured histories.',
    verification:'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF'}],
  limitations:[
    'Declared scope is not current native execution proof, physical qualification or engineering release.',
    'Unmodified SVK covers large proper rotations with small Green strain, not general rubber, large-stretch stability or finite-element constitutive coupling.',
    'Work budgets bound parsed-hook JSON and signed-probe counts, not original MCP wire bytes or scientific accuracy. Native wall defaultNone and positive CPU86400 are separate execution policies.',
    'Only the six listed tools are admitted; variable registration, jobs and numerical optimizer tools are not provided. Numerical engines own search candidates.',
    'Interpret actual returned IDs, revisions, metrics and UNKNOWNs. Full measured F/P/A/W histories require same-record hash-bound artifacts and are not invented from summaries.',
    'Material, physical, strength, durability, binary/source equivalence and deployment requirements remain UNKNOWN; all outcomes remain NOT_RELEASED.'],
});
const nativeViscoelasticLimits = nativeFreeze({stress_absolute_mpa:1e-10, stress_relative:1e-8,
  tangent_relative:1e-8, energy_absolute_mpa:1e-12, energy_relative:1e-8,
  finite_difference_steps:[1e-7,1e-8,1e-9]});
const nativeViscoelasticDefinition = nativeFreeze({
  schema:5, kind:'autonomous-cae-lab.openscience-research-definition', profile:'viscoelastic-points-v1', agent:'research',
  allowed_tools:[...nativeStructuralResearchTools], runtime_environment:{MPLBACKEND:'Agg', OMP_NUM_THREADS:'2', QT_QPA_PLATFORM:'offscreen',
    CAELAB_MFRONT_IMAGE:'/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif',
    CAELAB_MFRONT_IMAGE_SHA256:'f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64',
    CAELAB_SINGULARITY_COMMAND:'/usr/bin/singularity'},
  budgets:{steps:24, mcp_timeout_seconds:3600, command_timeout_seconds:3600,
    material_point:{min_history_entries:2,max_history_entries:17,max_signed_probe_states:576,max_request_bytes:65536}},
  capabilities:[{backend:'material.mfront.viscoelastic',operations:['model_analysis_run'],cases:['single_branch_maxwell'],
    inputs:'Exact case/material/temperature_k/history/limits; physical six-component tensor strain xx,yy,zz,xy,xz,yz and 2..17 ordered entries. Domain owns initial-state, representability and fixed stress/tangent/energy verdicts.',
    runtime:'Existing exact17.4 SIF and SHA, TFEL5/MGIS3/MTest and Singularity containment; no runtime or model fallback.',
    evidence:'Immutable Core metrics/checks and hash-bound actual stress, BranchStress, tangent and native stored/dissipated energy histories, all signed probes and same-library MTest.',
    verification:'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF'}],
  limitations:[
    'Declared scope is not current native execution proof, physical qualification or engineering release.',
    'Synthetic infinitesimal isotropic single-branch Maxwell material point; measured materials, finite-strain viscoelasticity, multiple branches and spatial finite-element coupling remain unqualified.',
    'Work budgets bound parsed-hook JSON and signed-probe counts, not original MCP wire bytes or scientific accuracy. Native wall defaultNone and positive CPU86400 are separate execution policies.',
    'Only the six listed tools are admitted; variable registration, jobs and numerical optimizer tools are not provided. Numerical engines own search candidates.',
    'Interpret actual returned IDs, revisions, metrics and UNKNOWNs. Complete measured histories require same-record hash-bound artifacts; summary error metrics cannot substitute for response histories.',
    'Shared-time refinement checks composition of the identical piecewise-linear path, not temporal convergence order; increment tangents depend on dt.',
    'Material, physical, strength, durability, binary/source equivalence and deployment requirements remain UNKNOWN; all outcomes remain NOT_RELEASED.'],
});
const nativeContactLimits = nativeFreeze({reference_relative:.01, force_balance_relative:1e-6});
const nativeContactDefinition = nativeFreeze({
  "schema": 6,
  "kind": "autonomous-cae-lab.openscience-research-definition",
  "profile": "contact-patches-v1",
  "agent": "research",
  "runtime_environment": {
    "MPLBACKEND": "Agg",
    "OMP_NUM_THREADS": "1",
    "QT_QPA_PLATFORM": "offscreen",
    "CAELAB_CODEASTER_IMAGE": "/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif",
    "CAELAB_CODEASTER_IMAGE_SHA256": "f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64",
    "CAELAB_SINGULARITY_COMMAND": "/usr/bin/singularity"
  },
  "budgets": {
    "steps": 24,
    "mcp_timeout_seconds": 3600,
    "command_timeout_seconds": 3600,
    "contact_patch": {
      "max_nodes": 1154,
      "max_solid_cells": 1060,
      "max_boundary_segments": 184,
      "max_stress_locations": 4240,
      "max_slave_pressure_nodes": 25,
      "max_request_bytes": 16384
    }
  },
  "capabilities": [
    {
      "backend": "structural.code_aster.contact_patch",
      "operations": [
        "model_analysis_run"
      ],
      "cases": [
        "ssnp121a_frictionless_patch"
      ],
      "inputs": "Exact case/material/top_displacement_m/limits with optional mesh_variant=uniform_quad4_2x; omitted selector preserves original. Domain owns finite scientific admission and unchanged six1%/reaction1%/balance1e-6 verdicts. No arbitrary code, paths, counts or levels.",
      "runtime": "Existing exact Code_Aster17.4 SIF and SHA with OMP1 and Singularity containment; no runtime or model fallback.",
      "evidence": "Code_Aster SSNP121A: original313 nodes/265 QUAD4/92 SEG2 or uniform2 1154/1060/184 with original313 name/coordinate prefix. Native pressure13/25 nodes, stress1060/4240 locations, complete U/RF and hash-bound JSON/MED fields.",
      "verification": "IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF"
    }
  ],
  "limitations": [
    "Declared research scope is not current connected Research execution proof, physical qualification or engineering release.",
    "This is native Code_Aster SSNP121A, not NAFEMS CGS1 or MIDAS replication. Failed CalculiX pilot7PASS/6FAIL remains failed and outside this production scope.",
    "One uniform subdivision establishes sensitivity, not asymptotic convergence. Measured stress XY and native integration weight W remain separate; native contact gap and measured geometric stress Z are unavailable. Projected gap is diagnostic.",
    "Budgets bound parsed-hook JSON and retained resource counts, not original MCP wire bytes or engineering accuracy. Native wall defaultNone and positive CPU86400 remain separate execution policies.",
    "Only the six listed tools are admitted. OpenScience chooses questions, hypotheses, conditions and interpretation; deterministic numerical engines own search candidates.",
    "Inspect actual returned IDs/revisions, signed pressure versus positive magnitude, sample metrics versus whole-field diagnostics, checks and raw artifact references. Full native fields require same-record hash-bound JSON/MED, not summary arrays.",
    "Generic Lab Results offers metrics and raw downloads, with no contact preset or contact full-field viewer. The PDE field viewer excludes contact; conversation/result identity and human full-field visual inspection are separate gates.",
    "All ten blocking engineering UNKNOWNs remain. Preserve failed results and invalid metrics; no automatic model/backend fallback, retry, reference response substitution or release claim. All outcomes remain NOT_RELEASED."
  ],
  "allowed_tools": [...nativeStructuralResearchTools]
});
class NativeGuardRefusal extends Error {
  constructor(code) {
    // Upstream classifies statusless Error text as a provider failure. Keep
    // detailed policy codes in the explicit field and receipts, not this text.
    super('CAE native guard denied this operation.');
    this.name = 'CaeLabNativeGuardRefusal';
    this.code = code;
  }
}
const nativeRefuse = code => { throw new NativeGuardRefusal(code); };
const nativeSourceErrorKind = error => {
  // Only own data properties are inspected. No message, output, path or
  // arbitrary property getter can enter the diagnostic classification.
  try {
    const code = Object.getOwnPropertyDescriptor(error, 'code')?.value;
    switch (code) {
      case 'ETIMEDOUT': return 'TIMEOUT';
      case 'ENOBUFS': return 'OUTPUT_LIMIT';
      case 'ENOENT': return 'NOT_FOUND';
      case 'EACCES': case 'EPERM': return 'ACCESS_DENIED';
      case 'EIO': return 'IO_FAILURE';
    }
    if (Number.isInteger(Object.getOwnPropertyDescriptor(error, 'status')?.value)) return 'CHILD_EXIT';
  } catch {}
  return 'CHECK_EXCEPTION';
};
const nativeElapsedMs = started => Math.min(2_147_483_647,
  Number((process.hrtime.bigint() - started) / 1_000_000n));
const nativeReaderFailure = error => {
  // Node execFile uses numeric exit codes and fixed killed/signal data for its
  // timeout. Normalize only these own-data markers into the existing classes.
  try {
    const code = Object.getOwnPropertyDescriptor(error, 'code')?.value;
    if (code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER') return { code: 'ENOBUFS' };
    if (Number.isInteger(code)) return { status: code };
    if ((code === null || code === undefined) &&
        Object.getOwnPropertyDescriptor(error, 'killed')?.value === true &&
        Object.getOwnPropertyDescriptor(error, 'signal')?.value === 'SIGTERM') return { code: 'ETIMEDOUT' };
  } catch { return {}; }
  return error;
};

// Internal factory: test code may append an export to its temporary module.
// Production exports only the actual plugin, so the upstream loader cannot
// mistakenly invoke a second exported function as another plugin.
async function createNativeHooks(suppliedSettings, dependencies = {}) {
  const io = dependencies.fs ?? nativeFs;
  const paths = dependencies.path ?? nativePath;
  const digest = dependencies.digest ?? (bytes => nativeCrypto.createHash('sha256').update(bytes).digest('hex'));
  const capture = dependencies.capture ?? captureRepositorySourcePin;
  const assertPin = dependencies.assertPin ?? assertRepositorySourcePin;
  const assertGitState = dependencies.assertGitState ?? ((...args) => assertNativeGitState(...args));
  const pinSha = dependencies.pinSha ?? sourcePinSha;
  const settingsPath = dependencies.settingsPath;
  const loadedPluginPath = dependencies.pluginPath ?? suppliedSettings?.pluginPath;
  const pluginInput = dependencies.pluginInput;
  const fetchMetadata = dependencies.fetch ?? globalThis.fetch;
  const execFile = dependencies.execFile ?? nativeExecFile;
  const sourceEnvironment = dependencies.environment ?? process.env;
  const sourceClock = dependencies.monotonic ?? (() => process.hrtime.bigint());
  let sessionClient, sessionApi, sessionGetter, metadataOrigin;
  let settings;
  let settingsSha;
  let sequence = 0;

  const exactKeys = (value, keys, code) => {
    if (!nativeRecord(value) || Object.keys(value).length !== keys.length ||
        keys.some(key => !Object.hasOwn(value, key))) nativeRefuse(code);
  };
  const noLinks = (value, expectedKind) => {
    if (typeof value !== 'string' || !paths.isAbsolute(value) || paths.resolve(value) !== value) nativeRefuse('PATH_INVALID');
    const root = paths.parse(value).root;
    let current = root;
    const parts = paths.relative(root, value).split(paths.sep).filter(Boolean);
    for (let index = -1; index < parts.length; index++) {
      if (index >= 0) current = paths.join(current, parts[index]);
      let stat;
      try { stat = io.lstatSync(current); } catch { nativeRefuse('PATH_UNAVAILABLE'); }
      if (stat.isSymbolicLink()) nativeRefuse('PATH_LINKED');
      if (index < parts.length - 1 && !stat.isDirectory()) nativeRefuse('PATH_INVALID');
      if (index === parts.length - 1 && expectedKind === 'file' && !stat.isFile()) nativeRefuse('PATH_INVALID');
      if (index === parts.length - 1 && expectedKind === 'directory' && !stat.isDirectory()) nativeRefuse('PATH_INVALID');
    }
    return value;
  };
  const owned = (value, expectedKind) => {
    if (typeof value !== 'string' || !paths.isAbsolute(value)) nativeRefuse('PATH_INVALID');
    const relative = paths.relative(settings.profile_root, value);
    if (!relative || paths.isAbsolute(relative) || relative === '..' || relative.startsWith(`..${paths.sep}`)) nativeRefuse('PATH_OUTSIDE_PROFILE');
    return noLinks(value, expectedKind);
  };
  const read = (value, bound) => {
    noLinks(value, 'file');
    let bytes;
    try {
      const size = io.statSync(value).size;
      if (size > bound) nativeRefuse('FILE_SIZE_INVALID');
      bytes = io.readFileSync(value);
    } catch (error) {
      if (error instanceof NativeGuardRefusal) throw error;
      nativeRefuse('FILE_UNAVAILABLE');
    }
    if (bytes.length > bound) nativeRefuse('FILE_SIZE_INVALID');
    return bytes;
  };
  const readJson = (value, bound, code) => {
    const bytes = read(value, bound);
    try { return { value: JSON.parse(bytes.toString('utf8')), sha256: digest(bytes) }; }
    catch { nativeRefuse(code); }
  };
  const validateSettings = () => {
    const keys = [...nativeSettingsKeys];
    if (settings?.schema === 3) keys.push('source_reader');
    if (settings?.schema === 3 && Object.hasOwn(settings, 'research')) keys.push('research');
    if (settings?.schema === 2 || (settings?.schema === 3 && Object.hasOwn(settings, 'project_binding'))) keys.push('project_binding');
    exactKeys(settings, keys, 'SETTINGS_INVALID');
    if (![1, 2, 3].includes(settings.schema) || settings.kind !== 'autonomous-cae-lab.openscience-native-guard' ||
        typeof settings.run_name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(settings.run_name) ||
        typeof settings.model !== 'string' || !/^openai-codex\/[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(settings.model) ||
        !Array.isArray(settings.allowed) || !settings.allowed.length || new Set(settings.allowed).size !== settings.allowed.length ||
        settings.allowed.some(tool => !(Object.hasOwn(settings, 'research')
          ? (Array.isArray(settings.research?.allowed_tools) ? settings.research.allowed_tools : []) : nativeAcceptanceTools).includes(tool)) ||
        !nativeSha(settings.config_sha256) || !nativeSha(settings.plugin_sha256) || !nativeSha(settings.boot_source_sha256)) nativeRefuse('SETTINGS_INVALID');
    if (Object.hasOwn(settings, 'research')) {
      const research = settings.research;
      exactKeys(research, [3,4,5,6,7].includes(research.schema) ? [...nativeResearchKeys, 'profile'] :
        research.schema === 2 ? [...nativeResearchKeys, 'profile', 'benchmark_definition'] : nativeResearchKeys,
        'RESEARCH_DEFINITION_INVALID');
      if (research.schema === 7) {
        if (nativeCanonical(research) !== nativeCanonical(nativeFixtureRefinementDefinition)) nativeRefuse('RESEARCH_DEFINITION_INVALID');
      } else if (research.schema === 6) {
        if (nativeCanonical(research) !== nativeCanonical(nativeContactDefinition)) nativeRefuse('RESEARCH_DEFINITION_INVALID');
      } else if (research.schema === 5) {
        if (nativeCanonical(research) !== nativeCanonical(nativeViscoelasticDefinition)) nativeRefuse('RESEARCH_DEFINITION_INVALID');
      } else if (research.schema === 4) {
        if (nativeCanonical(research) !== nativeCanonical(nativeMaterialDefinition)) nativeRefuse('RESEARCH_DEFINITION_INVALID');
      } else if (research.schema === 3) {
        if (research.kind !== 'autonomous-cae-lab.openscience-research-definition' || research.agent !== 'research' ||
            research.profile !== 'pde-fields-v1' ||
            nativeCanonical(research.allowed_tools) !== nativeCanonical(nativePdeResearchTools) ||
            nativeCanonical(research.runtime_environment) !== nativeCanonical(nativePdeRuntime) ||
            nativeCanonical(research.budgets) !== nativeCanonical(nativePdeBudgets) ||
            !Array.isArray(research.capabilities) || research.capabilities.length !== nativePdeBackends.length ||
            nativeCanonical(research.capabilities.map(value => value?.backend)) !== nativeCanonical(nativePdeBackends) ||
            research.capabilities.some(value => !nativeRecord(value) ||
              nativeCanonical(value.operations) !== nativeCanonical(['pde_run'])) ||
            !Array.isArray(research.limitations)) nativeRefuse('RESEARCH_DEFINITION_INVALID');
      } else if (research.schema === 2) {
        if (research.kind !== 'autonomous-cae-lab.openscience-research-definition' || research.agent !== 'research' ||
            research.profile !== 'structural-families-v1' ||
            nativeCanonical(research.benchmark_definition) !== nativeCanonical({id:'P2-family-v1-20261002',
              path:'benchmarks/specifications/structural-families-v1.json'}) ||
            nativeCanonical(research.allowed_tools) !== nativeCanonical(nativeStructuralResearchTools) ||
            nativeCanonical(research.runtime_environment) !== nativeCanonical(nativeStructuralRuntime) ||
            nativeCanonical(research.budgets) !== nativeCanonical(nativeStructuralBudgets) ||
            !Array.isArray(research.capabilities) || research.capabilities.length !== 2 ||
            nativeCanonical(research.capabilities.map(value => value?.backend)) !== nativeCanonical(nativeStructuralBackends) ||
            research.capabilities.some(value => nativeCanonical(value?.cases) !== nativeCanonical(Object.keys(nativeStructuralCases)) ||
              nativeCanonical(value?.operations) !== nativeCanonical(['model_analysis_run'])) ||
            !Array.isArray(research.limitations)) nativeRefuse('RESEARCH_DEFINITION_INVALID');
      } else if (research.schema !== 1 || research.kind !== 'autonomous-cae-lab.openscience-research-definition' ||
          research.agent !== 'research' || nativeCanonical(research.allowed_tools) !== nativeCanonical(nativeLegacyResearchTools) ||
          nativeCanonical(research.runtime_environment) !== nativeCanonical({MPLBACKEND:'Agg', OMP_NUM_THREADS:'2',
            QT_QPA_PLATFORM:'offscreen', CAELAB_FENICSX_PYTHON:'/usr/bin/python3'}) ||
          nativeCanonical(research.budgets) !== nativeCanonical({steps:24, mcp_timeout_seconds:3600, command_timeout_seconds:3600,
            optimization:{max_generations:1, population_size:5}, analysis:{max_mesh_levels:2},
            pde:{max_cell_count:32, max_mesh_levels:3}}) ||
          !Array.isArray(research.capabilities) || research.capabilities.length !== 3 ||
          nativeCanonical(research.capabilities.map(value => value?.backend)) !==
            nativeCanonical(['fixture.cadquery','fixture.calculix','pde.fenicsx']) ||
          !Array.isArray(research.limitations)) nativeRefuse('RESEARCH_DEFINITION_INVALID');
    }
    noLinks(settings.profile_root, 'directory');
    noLinks(settings.repo_root, 'directory');
    if (managed()) {
      const binding = settings.project_binding;
      exactKeys(binding, nativeProjectBindingKeys, 'PROJECT_BINDING_INVALID');
      if (binding.schema !== 1 || binding.kind !== 'autonomous-cae-lab.openscience-project-binding' ||
          typeof binding.project_id !== 'string' || !/^prj_[A-Za-z0-9]{1,124}$/.test(binding.project_id) ||
          !nativeGrantId(binding.grant_id) ||
          binding.source_directory !== settings.repo_root || binding.working_root !== binding.source_directory ||
          binding.access !== 'write') nativeRefuse('PROJECT_BINDING_INVALID');
      noLinks(binding.project_directory, 'directory');
    }
    if (settings.schema === 3) {
      const reader = settings.source_reader;
      exactKeys(reader, nativeSourceReaderKeys, 'SOURCE_READER_INVALID');
      if (!nativeSha(reader.node_sha256) || !nativeSha(reader.worker_sha256) ||
          reader.worker_path !== paths.join(settings.profile_root, 'source-reader.mjs')) nativeRefuse('SOURCE_READER_INVALID');
      noLinks(reader.node_path, 'file');
      owned(reader.worker_path, 'file');
    }
    for (const file of [settingsPath, settings.guardPath, settings.configPath, settings.pluginPath]) owned(file, 'file');
    owned(settings.receipts, 'directory');
    if (loadedPluginPath !== settings.pluginPath ||
        settingsPath !== paths.join(paths.dirname(settings.pluginPath), 'native-guard-settings.json')) nativeRefuse('SETTINGS_LOCATION_INVALID');
    const boot = settings.boot_source;
    if (!nativeRecord(boot) || boot.schema !== 1 || boot.kind !== 'autonomous-cae-lab.repository-source-pin' ||
        boot.repo_root !== settings.repo_root || !nativeSha(boot.git_sha256) || !nativeSha(boot.source_tree_sha256) ||
        typeof boot.source_commit !== 'string' || !/^[0-9a-f]{40,64}$/.test(boot.source_commit) ||
        !Array.isArray(boot.files) || !Array.isArray(boot.submodules) || !Array.isArray(boot.source_dirty)) nativeRefuse('BOOT_SOURCE_INVALID');
    noLinks(boot.git_path, 'file');
    if (pinSha(boot) !== settings.boot_source_sha256) nativeRefuse('BOOT_SOURCE_HASH_CHANGED');
  };
  const stableFiles = () => {
    validateSettings();
    if (digest(read(settingsPath, 16 * 1024 * 1024)) !== settingsSha) nativeRefuse('SETTINGS_CHANGED');
    if (digest(read(settings.configPath, 1024 * 1024)) !== settings.config_sha256) nativeRefuse('CONFIG_CHANGED');
    if (digest(read(settings.pluginPath, 1024 * 1024)) !== settings.plugin_sha256) nativeRefuse('PLUGIN_CHANGED');
    if (settings.schema === 3) {
      if (digest(read(settings.source_reader.node_path, 128 * 1024 * 1024)) !== settings.source_reader.node_sha256) nativeRefuse('NODE_EXECUTABLE_CHANGED');
      if (digest(read(settings.source_reader.worker_path, 1024 * 1024)) !== settings.source_reader.worker_sha256) nativeRefuse('SOURCE_READER_CHANGED');
    }
  };
  const managed = () => settings.schema === 2 || (settings.schema === 3 && Object.hasOwn(settings, 'project_binding'));
  const guardFor = () => {
    const parsed = readJson(settings.guardPath, 128 * 1024, 'GUARD_INVALID');
    const guard = parsed.value;
    exactKeys(guard, nativeGuardKeys, 'GUARD_INVALID');
    if (guard.schema !== 1 || guard.kind !== 'autonomous-cae-lab.openscience-tool-guard' ||
        ['repo_root', 'run_name', 'profile_root', 'model'].some(key => guard[key] !== settings[key]) ||
        !Array.isArray(guard.allowed) || nativeCanonical(guard.allowed) !== nativeCanonical(settings.allowed) ||
        typeof guard.no_tools !== 'boolean' || typeof guard.stopping !== 'boolean' ||
        !(guard.required === null || (typeof guard.required === 'string' && guard.allowed.includes(guard.required))) ||
        (guard.no_tools && guard.required !== null) || typeof guard.updated_utc !== 'string' ||
        guard.updated_utc.length > 64 || !Number.isFinite(Date.parse(guard.updated_utc))) nativeRefuse('GUARD_INVALID');
    return { guard, sha256: parsed.sha256 };
  };
  const sameDirectory = (value, expected) => {
    if (typeof value !== 'string' || value.length > 32768 || !paths.isAbsolute(value)) return false;
    const canonical = paths.resolve(value);
    return process.platform === 'win32' ? canonical.toLowerCase() === expected.toLowerCase() : canonical === expected;
  };
  const projectInputFor = () => {
    const binding = settings.project_binding;
    if (!nativeRecord(pluginInput) || !nativeRecord(pluginInput.project) ||
        pluginInput.project.id !== binding.project_id ||
        !sameDirectory(pluginInput.directory, binding.project_directory) ||
        !sameDirectory(pluginInput.worktree, binding.project_directory) ||
        !sameDirectory(pluginInput.project.worktree, binding.project_directory)) nativeRefuse('PROJECT_INPUT_CHANGED');
    const client = pluginInput.client, api = client?.session, getter = api?.get;
    if (!nativeRecord(client) || !nativeRecord(api) || typeof getter !== 'function') nativeRefuse('PROJECT_CLIENT_INVALID');
    if (sessionGetter && (client !== sessionClient || api !== sessionApi || getter !== sessionGetter)) nativeRefuse('PROJECT_CLIENT_CHANGED');
    let server;
    try {
      if (!(typeof pluginInput.serverUrl === 'string' || pluginInput.serverUrl instanceof URL)) nativeRefuse('PROJECT_SERVER_INVALID');
      server = new URL(pluginInput.serverUrl);
    } catch { nativeRefuse('PROJECT_SERVER_INVALID'); }
    if (server.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(server.hostname) ||
        server.username || server.password || server.pathname !== '/' || server.search || server.hash) nativeRefuse('PROJECT_SERVER_INVALID');
    if (metadataOrigin && server.origin !== metadataOrigin) nativeRefuse('PROJECT_SERVER_CHANGED');
    sessionClient = client; sessionApi = api; sessionGetter = getter; metadataOrigin = server.origin;
  };
  const boundedProjectRead = async (operation, code) => {
    const signal = AbortSignal.timeout(nativeProjectReadTimeoutMs);
    let abort;
    const stopped = new Promise((_, reject) => {
      abort = () => reject(new NativeGuardRefusal(code));
      signal.addEventListener('abort', abort, { once: true });
    });
    try { return await Promise.race([Promise.resolve().then(() => operation(signal)), stopped]); }
    catch { nativeRefuse(code); }
    finally { signal.removeEventListener('abort', abort); }
  };
  const loadSession = dependencies.loadSession ?? (async (sessionID, signal) => {
    // Public v1 client supplied by the official loader is already bound to
    // this Instance's project/directory and its internal fetch implementation.
    const response = await sessionGetter.call(sessionApi, { path: { id: sessionID }, throwOnError: true, signal });
    if (!nativeRecord(response) || response.error !== undefined || !nativeRecord(response.data)) nativeRefuse('PROJECT_SESSION_READ_FAILED');
    return response.data;
  });
  const loadFilesystem = dependencies.loadFilesystem ?? (async (sessionID, signal) => {
    // Pinned v1 SDK has no filesystem getter. Use the official read-only route
    // with exact Instance headers; redirects and oversized bodies are refused.
    const response = await fetchMetadata(`${metadataOrigin}/session/${sessionID}/filesystem`, {
      method: 'GET', redirect: 'error', signal,
      headers: { 'x-openscience-project': settings.project_binding.project_id,
        'x-openscience-directory': settings.project_binding.project_directory },
    });
    if (response?.status !== 200 || response.ok !== true || response.redirected !== false) nativeRefuse('PROJECT_FILESYSTEM_READ_FAILED');
    const declaredSize = response.headers.get('content-length');
    if (declaredSize !== null && (!/^\d+$/.test(declaredSize) || Number(declaredSize) > nativeProjectResponseBound)) nativeRefuse('PROJECT_FILESYSTEM_READ_FAILED');
    const reader = response.body?.getReader();
    if (!reader) nativeRefuse('PROJECT_FILESYSTEM_READ_FAILED');
    const chunks = [];
    let size = 0;
    try {
      for (;;) {
        const chunk = await reader.read();
        if (chunk.done) break;
        size += chunk.value.byteLength;
        if (size > nativeProjectResponseBound) nativeRefuse('PROJECT_FILESYSTEM_READ_FAILED');
        chunks.push(Buffer.from(chunk.value));
      }
      return JSON.parse(Buffer.concat(chunks).toString('utf8'));
    } finally { try { await reader.cancel(); } catch {} }
  });
  const projectFor = async (sessionID, hashes) => {
    const check = hashes.projectCheck = { identity: 'FAIL', session: 'NOT_RUN', filesystem: 'NOT_RUN' };
    projectInputFor();
    check.identity = 'PASS';
    if (!nativeSessionId(sessionID)) nativeRefuse('PROJECT_SESSION_ID_INVALID');
    const binding = settings.project_binding;
    check.session = 'FAIL';
    const session = await boundedProjectRead(signal => loadSession(sessionID, signal), 'PROJECT_SESSION_READ_FAILED');
    if (!nativeRecord(session) || session.id !== sessionID || session.projectID !== binding.project_id ||
        !sameDirectory(session.directory, binding.project_directory)) nativeRefuse('PROJECT_SESSION_CHANGED');
    check.session = 'PASS';
    check.filesystem = 'FAIL';
    const filesystem = await boundedProjectRead(signal => loadFilesystem(sessionID, signal), 'PROJECT_FILESYSTEM_READ_FAILED');
    if (!nativeRecord(filesystem) || filesystem.version !== 1 || filesystem.sessionID !== sessionID ||
        filesystem.projectID !== binding.project_id || !sameDirectory(filesystem.directory, binding.project_directory) ||
        !sameDirectory(filesystem.toolDirectory, binding.source_directory) ||
        !sameDirectory(filesystem.workingRoot, binding.working_root) || !Array.isArray(filesystem.grants)) nativeRefuse('PROJECT_FILESYSTEM_CHANGED');
    const matching = filesystem.grants.filter(grant => nativeRecord(grant) && grant.id === binding.grant_id);
    const grant = matching[0];
    if (matching.length !== 1 || !sameDirectory(grant.path, binding.source_directory) ||
        grant.access !== 'write' || grant.scope !== 'project' || !nativeRecord(grant.time) ||
        !Number.isFinite(grant.time.created) || grant.time.created < 0 ||
        Object.hasOwn(grant.time, 'revoked')) nativeRefuse('PROJECT_GRANT_CHANGED');
    check.filesystem = 'PASS';
    check.identity = 'FAIL';
    projectInputFor();
    check.identity = 'PASS';
  };
  const stableSession = (input, sessionID, hashes) => {
    if (input?.sessionID !== sessionID) {
      hashes.projectCheck.session = 'FAIL';
      nativeRefuse('PROJECT_SESSION_CHANGED');
    }
  };
  const captureWithReader = () => new Promise((resolve, reject) => {
    const reader = settings.source_reader, env = Object.create(null);
    // Read only the permitted OS values; no Node/Git/provider environment is
    // inherited by the child, and no environment value enters a receipt.
    for (const key of Object.keys(sourceEnvironment)) {
      const allowed = nativeSourceEnvironmentKeys.find(item => item.toUpperCase() === key.toUpperCase());
      if (allowed && !Object.hasOwn(env, allowed)) env[allowed] = sourceEnvironment[key];
    }
    const child = execFile(reader.node_path, [reader.worker_path, settings.repo_root, settings.boot_source.git_path, settingsPath], {
      cwd: settings.repo_root, env, timeout: nativeSourceReadTimeoutMs,
      maxBuffer: nativeSourceResponseBound, windowsHide: true, shell: false, encoding: 'utf8',
    }, (error, stdout, _stderr) => {
      if (error) { reject(nativeReaderFailure(error)); return; }
      try {
        if (typeof stdout !== 'string' || Buffer.byteLength(stdout) > nativeSourceResponseBound) throw new Error();
        const result = JSON.parse(stdout);
        exactKeys(result, ['schema', 'kind', 'pin', 'git_state'], 'SOURCE_READER_RESULT_INVALID');
        if (result.schema !== 1 || result.kind !== 'autonomous-cae-lab.source-reader-result' ||
            !nativeRecord(result.pin) || !nativeRecord(result.git_state)) throw new Error();
        resolve(result);
      } catch { reject({}); }
    });
    // execFile always pipes stdin. Close it immediately without writing any
    // input; its supported API has no stdio-ignore option.
    child.stdin?.end();
    child.stdin?.destroy();
  });
  const sourceFor = async hashes => {
    const boot = settings.boot_source;
    if (digest(read(boot.git_path, 128 * 1024 * 1024)) !== boot.git_sha256) nativeRefuse('GIT_EXECUTABLE_CHANGED');
    const check = hashes.sourceCheck = {
      capture: { status: 'NOT_RUN', elapsed_ms: null, error_kind: null },
      compare: { status: 'NOT_RUN', elapsed_ms: null, error_kind: null },
    };
    if (settings.schema === 3) check.final_bytes = { status: 'NOT_RUN', elapsed_ms: null, error_kind: null };
    let current;
    const captureStarted = process.hrtime.bigint();
    try {
      if (settings.schema === 3) {
        const result = await captureWithReader();
        current = result.pin;
        hashes.sourceGitState = result.git_state;
      } else current = await capture(settings.repo_root, boot.git_path);
      check.capture.status = 'PASS';
    } catch (error) {
      check.capture.status = 'FAIL';
      check.capture.error_kind = nativeSourceErrorKind(error);
      nativeRefuse('SOURCE_CHANGED_OR_UNAVAILABLE');
    } finally { check.capture.elapsed_ms = nativeElapsedMs(captureStarted); }
    const compareStarted = process.hrtime.bigint();
    try {
      assertPin(boot, current);
      check.compare.status = 'PASS';
    } catch (error) {
      check.compare.status = 'FAIL';
      check.compare.error_kind = nativeSourceErrorKind(error);
      nativeRefuse('SOURCE_CHANGED_OR_UNAVAILABLE');
    } finally { check.compare.elapsed_ms = nativeElapsedMs(compareStarted); }
    return settings.boot_source_sha256;
  };
  const finalSourceBytes = hashes => {
    const check = hashes.sourceCheck.final_bytes;
    const started = process.hrtime.bigint();
    const deadlineStarted = sourceClock();
    const deadline = () => {
      if (sourceClock() - deadlineStarted >= BigInt(nativeSourceReadTimeoutMs) * 1_000_000n) nativeRefuse('SOURCE_BYTES_CHECK_TIMEOUT');
    };
    const key = value => process.platform === 'win32' ? value.toLowerCase() : value;
    const sourcePath = relative => {
      if (typeof relative !== 'string' || !relative.length || relative.length > 32768 ||
          relative.includes('\\') || paths.parse(relative).root ||
          relative.split('/').some(part => !part || part === '.' || part === '..')) nativeRefuse('BOOT_SOURCE_INVALID');
      const absolute = paths.resolve(settings.repo_root, relative);
      const local = paths.relative(settings.repo_root, absolute);
      if (!local || paths.isAbsolute(local) || local === '..' || local.startsWith(`..${paths.sep}`)) nativeRefuse('BOOT_SOURCE_INVALID');
      return absolute;
    };
    const fixedFiles = () => {
      deadline(); stableFiles(); deadline();
      if (digest(read(settings.boot_source.git_path, 128 * 1024 * 1024)) !== settings.boot_source.git_sha256) nativeRefuse('GIT_EXECUTABLE_CHANGED');
      deadline();
    };
    try {
      fixedFiles();
      const files = new Set(), repositories = new Set([key(settings.repo_root)]);
      for (const file of settings.boot_source.files) {
        deadline();
        if (!nativeRecord(file) || !nativeSha(file.sha256)) nativeRefuse('BOOT_SOURCE_INVALID');
        const absolute = sourcePath(file.path);
        if (files.has(key(absolute))) nativeRefuse('BOOT_SOURCE_INVALID');
        files.add(key(absolute));
        if (digest(read(absolute, 128 * 1024 * 1024)) !== file.sha256) nativeRefuse('SOURCE_BYTES_CHANGED');
        deadline();
      }
      for (const submodule of settings.boot_source.submodules) {
        deadline();
        if (!nativeRecord(submodule)) nativeRefuse('BOOT_SOURCE_INVALID');
        const absolute = sourcePath(submodule.path);
        noLinks(absolute, 'directory'); repositories.add(key(absolute));
      }
      const walk = (directory, repository) => {
        deadline();
        noLinks(directory, 'directory');
        if (repositories.has(key(directory))) repository = directory;
        const entries = io.opendirSync(directory);
        try {
          for (let entry; (entry = entries.readSync()) !== null;) {
            deadline();
            const absolute = paths.join(directory, entry.name);
            const relative = paths.relative(repository, absolute).split(paths.sep).join('/');
            const parts = relative.split('/');
            if (nativeIgnoredSourceRoots.includes(parts[0])) continue;
            // Never follow a link into an unpinned import tree.
            const stat = io.lstatSync(absolute);
            if (stat.isSymbolicLink()) nativeRefuse('PATH_LINKED');
            if (stat.isDirectory()) walk(absolute, repository);
            else if (/\.(py|pyi|pyc|pyd|so|pth)$/i.test(entry.name) &&
                !(parts.includes('__pycache__') && relative.endsWith('.pyc')) &&
                !files.has(key(absolute))) nativeRefuse('SOURCE_IMPORTABLE_CHANGED');
          }
        } finally { entries.closeSync(); }
      };
      walk(settings.repo_root, settings.repo_root);
      // Final bytes/imports and fixed Git metadata use files only. This does
      // not repeat the reader's full Git/source capture after the last await.
      fixedFiles();
      try { assertGitState(settings.repo_root, settings.boot_source.submodules, hashes.sourceGitState, deadline); }
      catch (error) {
        if (error instanceof NativeGuardRefusal) throw error;
        nativeRefuse('GIT_STATE_CHANGED');
      }
      deadline();
      check.status = 'PASS';
    } catch (error) {
      check.status = 'FAIL';
      check.error_kind = error instanceof NativeGuardRefusal && error.code === 'SOURCE_BYTES_CHECK_TIMEOUT'
        ? 'TIMEOUT' : nativeSourceErrorKind(error);
      if (error instanceof NativeGuardRefusal) throw error;
      nativeRefuse('SOURCE_BYTES_CHECK_FAILED');
    } finally { check.elapsed_ms = nativeElapsedMs(started); }
  };
  const metadataId = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(value) ? value : null;
  const receipt = (hook, input, status, code, hashes) => {
    if (++sequence > 999999) nativeRefuse('RECEIPT_LIMIT');
    // Validate the saved owned destination independently of mutable settings.
    // A changed/linked destination fails closed; no outside receipt is written.
    owned(settings.receipts, 'directory');
    const value = {
      schema: 1, kind: 'autonomous-cae-lab.openscience-native-guard-receipt',
      pid: process.pid, sequence, timestamp_utc: new Date().toISOString(), hook,
      session_id: managed() ? (nativeSessionId(hashes.sessionID) ? hashes.sessionID : null) : metadataId(input?.sessionID),
      tool: nativeKnownTools.includes(input?.tool) ? input.tool : null,
      status, accepted: status === 'accepted', code, boot_source_sha256: hashes.source ?? null,
      guard_sha256: hashes.guard ?? null, settings_sha256: settingsSha,
      config_sha256: settings.config_sha256, plugin_sha256: settings.plugin_sha256,
      source_check: hashes.sourceCheck ?? null,
      project_check: hashes.projectCheck ?? null,
    };
    const name = `native-hook-${process.pid}-${String(sequence).padStart(6, '0')}-${nativeCrypto.randomUUID()}.json`;
    const file = paths.join(settings.receipts, name);
    let handle;
    try {
      handle = io.openSync(file, 'wx', 0o600);
      io.writeFileSync(handle, JSON.stringify(value, null, 2) + '\n');
    } catch { nativeRefuse('RECEIPT_UNAVAILABLE'); }
    finally { if (handle !== undefined) io.closeSync(handle); }
  };
  // This research schema is independent of the native-context schema.
  // Check parsed JSON shape/resource admission only; Domain/adapters own AST,
  // coefficient definiteness, references, fluxes and numerical verdicts.
  const materialArguments = args => {
    const bound = settings.research.budgets.material_point;
    exactKeys(args, ['study_id','experiment_id','backend','settings',
      ...(Object.hasOwn(args,'hypothesis_id') ? ['hypothesis_id'] : [])], 'RESEARCH_ARGUMENTS_REQUIRED');
    if (args.backend !== 'material.mfront.hyperelastic') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
    if (typeof args.study_id !== 'string' || !args.study_id.trim() || typeof args.experiment_id !== 'string' ||
        !args.experiment_id.trim() || (Object.hasOwn(args,'hypothesis_id') && args.hypothesis_id !== null &&
        (typeof args.hypothesis_id !== 'string' || !args.hypothesis_id.trim()))) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    const request = args.settings;
    exactKeys(request, ['case','material','temperature_k','history','limits'], 'RESEARCH_ARGUMENTS_REQUIRED');
    if (request.case !== 'saint_venant_kirchhoff') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
    exactKeys(request.material, ['youngs_modulus_mpa','poisson_ratio'], 'RESEARCH_ARGUMENTS_REQUIRED');
    const real = value => typeof value === 'number' && Number.isFinite(value);
    const material = request.material;
    if (!real(material.youngs_modulus_mpa) || material.youngs_modulus_mpa <= 0 || material.youngs_modulus_mpa > 1e9 ||
        !real(material.poisson_ratio) || material.poisson_ratio <= -1 || material.poisson_ratio >= .5 ||
        !real(request.temperature_k) || request.temperature_k <= 0 || request.temperature_k > 5000)
      nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    exactKeys(request.limits, Object.keys(nativeMaterialLimits), 'RESEARCH_ARGUMENTS_REQUIRED');
    if (nativeCanonical(request.limits) !== nativeCanonical(nativeMaterialLimits)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    const history = request.history;
    if (!Array.isArray(history) || history.length < bound.min_history_entries || history.length > bound.max_history_entries ||
        (history.length-1)*request.limits.finite_difference_steps.length*9*2 > bound.max_signed_probe_states)
      nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
    let previous = -1;
    for (const entry of history) {
      exactKeys(entry, ['time_s','deformation_gradient'], 'RESEARCH_ARGUMENTS_REQUIRED');
      if (!real(entry.time_s) || entry.time_s < 0 || entry.time_s > 1e6 || entry.time_s <= previous ||
          (previous === -1 && entry.time_s !== 0) || !Array.isArray(entry.deformation_gradient) ||
          entry.deformation_gradient.length !== 9) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      for (const value of entry.deformation_gradient) if (!real(value)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      previous = entry.time_s;
    }
    // Hook arguments are parsed JSON; this is not an original MCP wire bound.
    let encoded;
    try { encoded = JSON.stringify(args); } catch { nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED'); }
    if (Buffer.byteLength(encoded,'utf8') > bound.max_request_bytes) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
  };
  const viscoelasticArguments = args => {
    const bound = settings.research.budgets.material_point;
    exactKeys(args, ['study_id','experiment_id','backend','settings',
      ...(Object.hasOwn(args,'hypothesis_id') ? ['hypothesis_id'] : [])], 'RESEARCH_ARGUMENTS_REQUIRED');
    if (args.backend !== 'material.mfront.viscoelastic') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
    if (typeof args.study_id !== 'string' || !args.study_id.trim() || typeof args.experiment_id !== 'string' ||
        !args.experiment_id.trim() || (Object.hasOwn(args,'hypothesis_id') && args.hypothesis_id !== null &&
        (typeof args.hypothesis_id !== 'string' || !args.hypothesis_id.trim()))) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    const request = args.settings;
    exactKeys(request, ['case','material','temperature_k','history','limits'], 'RESEARCH_ARGUMENTS_REQUIRED');
    if (request.case !== 'single_branch_maxwell') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
    const materialKeys = ['equilibrium_bulk_modulus_mpa','equilibrium_shear_modulus_mpa',
      'branch_bulk_modulus_mpa','branch_shear_modulus_mpa','relaxation_time_s'];
    exactKeys(request.material, materialKeys, 'RESEARCH_ARGUMENTS_REQUIRED');
    const real = value => typeof value === 'number' && Number.isFinite(value);
    for (const key of materialKeys) {
      const value = request.material[key], upper = key === 'relaxation_time_s' ? 1e6 : 1e9;
      if (!real(value) || value < 1e-6 || value > upper) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    }
    if (!real(request.temperature_k) || request.temperature_k <= 0 || request.temperature_k > 5000)
      nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    exactKeys(request.limits, Object.keys(nativeViscoelasticLimits), 'RESEARCH_ARGUMENTS_REQUIRED');
    if (nativeCanonical(request.limits) !== nativeCanonical(nativeViscoelasticLimits)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    const history = request.history;
    if (!Array.isArray(history) || history.length < bound.min_history_entries || history.length > bound.max_history_entries ||
        (history.length-1)*request.limits.finite_difference_steps.length*6*2 > bound.max_signed_probe_states)
      nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
    let previous = -1;
    for (const entry of history) {
      exactKeys(entry, ['time_s','strain'], 'RESEARCH_ARGUMENTS_REQUIRED');
      if (!real(entry.time_s) || entry.time_s < 0 || entry.time_s > 1e6 || entry.time_s <= previous ||
          (previous === -1 && entry.time_s !== 0) || !Array.isArray(entry.strain) ||
          entry.strain.length !== 6) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      for (const value of entry.strain) if (!real(value)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      previous = entry.time_s;
    }
    // Finite scientific-invalid strain/initial-state/ratio requests reach Domain
    // preflight unchanged; a parsed JSON bound never certifies native physics.
    let encoded;
    try { encoded = JSON.stringify(args); } catch { nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED'); }
    if (Buffer.byteLength(encoded,'utf8') > bound.max_request_bytes) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
  };
  const pdeArguments = args => {
    const bound = settings.research.budgets.pde;
    exactKeys(args, ['study_id', 'experiment_id', 'backend', 'settings',
      ...(Object.hasOwn(args, 'hypothesis_id') ? ['hypothesis_id'] : [])], 'RESEARCH_ARGUMENTS_REQUIRED');
    if (!nativePdeBackends.includes(args.backend)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
    if (typeof args.study_id !== 'string' || !args.study_id.trim() || typeof args.experiment_id !== 'string' ||
        !args.experiment_id.trim() || (Object.hasOwn(args, 'hypothesis_id') && args.hypothesis_id !== null &&
          typeof args.hypothesis_id !== 'string')) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    const transient = args.backend === 'pde.fenicsx.transient';
    const coupled = args.backend === 'pde.fenicsx.coupled';
    const imported = args.backend === 'pde.fenicsx.imported';
    const linear = args.backend === 'pde.fenicsx';
    const request = args.settings;
    exactKeys(request, transient ? ['problem', 'mesh', 'time', 'refinement_axis', 'validation'] :
      ['problem', 'mesh', 'validation'], 'RESEARCH_ARGUMENTS_REQUIRED');
    const problem = request.problem;
    exactKeys(problem, linear ? ['domain', 'weak_form', 'dirichlet', 'reference'] :
      ['domain', 'weak_form', 'boundaries', 'reference', ...(transient ? ['initial'] : [])], 'RESEARCH_ARGUMENTS_REQUIRED');
    const string = value => { if (typeof value !== 'string') nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED'); };
    const number = value => { if (typeof value !== 'number' || !Number.isFinite(value)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED'); };
    const vector = value => {
      if (!Array.isArray(value) || value.length !== 2) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      for (const component of value) string(component);
    };
    const matrix = value => {
      if (!Array.isArray(value) || value.length !== 2) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      for (const row of value) {
        if (!Array.isArray(row) || row.length !== 2) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
        for (const component of row) number(component);
      }
    };
    if (linear) {
      if (problem.domain !== 'unit_square') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      string(problem.dirichlet);
    } else {
      exactKeys(problem.domain, imported ? ['type', 'body'] :
        ['type', 'lengths', ...(coupled ? ['interface'] : [])], 'RESEARCH_ARGUMENTS_REQUIRED');
      if (problem.domain.type !== (imported ? 'imported_mesh' : 'rectangle')) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      if (imported) string(problem.domain.body);
      else {
        if (!Array.isArray(problem.domain.lengths) || problem.domain.lengths.length !== 2) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
        for (const length of problem.domain.lengths) number(length);
      }
      if (coupled) {
        exactKeys(problem.domain.interface, ['axis', 'fraction'], 'RESEARCH_ARGUMENTS_REQUIRED');
        if (problem.domain.interface.axis !== 0 || problem.domain.interface.fraction !== .5) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      }
      const names = imported ? Object.keys(nativeRecord(problem.boundaries) ? problem.boundaries : {}) : ['xmin', 'xmax', 'ymin', 'ymax'];
      if (!names.length) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      exactKeys(problem.boundaries, names, 'RESEARCH_ARGUMENTS_REQUIRED');
      for (const name of names) {
        const boundary = problem.boundaries[name];
        exactKeys(boundary, ['type', 'value'], 'RESEARCH_ARGUMENTS_REQUIRED');
        if (!['dirichlet', 'neumann'].includes(boundary.type)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
        if (coupled) {
          const regions = name === 'xmin' ? ['left'] : name === 'xmax' ? ['right'] : ['left', 'right'];
          exactKeys(boundary.value, regions, 'RESEARCH_ARGUMENTS_REQUIRED');
          regions.forEach(region => vector(boundary.value[region]));
        } else string(boundary.value);
      }
    }
    const weak = problem.weak_form;
    exactKeys(weak, ['diffusion', 'reaction', 'rhs', ...(coupled ? ['family'] : [])], 'RESEARCH_ARGUMENTS_REQUIRED');
    if (coupled) {
      if (weak.family !== 'coupled_diffusion') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      exactKeys(weak.diffusion, ['left', 'right'], 'RESEARCH_ARGUMENTS_REQUIRED');
      exactKeys(weak.rhs, ['left', 'right'], 'RESEARCH_ARGUMENTS_REQUIRED');
      for (const region of ['left', 'right']) { matrix(weak.diffusion[region]); vector(weak.rhs[region]); }
      matrix(weak.reaction);
    } else { number(weak.diffusion); number(weak.reaction); string(weak.rhs); }
    exactKeys(problem.reference, ['solution', 'source'], 'RESEARCH_ARGUMENTS_REQUIRED');
    string(problem.reference.source);
    if (coupled) {
      exactKeys(problem.reference.solution, ['left', 'right'], 'RESEARCH_ARGUMENTS_REQUIRED');
      ['left', 'right'].forEach(region => vector(problem.reference.solution[region]));
    } else string(problem.reference.solution);
    if (transient) { exactKeys(problem.initial, ['value'], 'RESEARCH_ARGUMENTS_REQUIRED'); string(problem.initial.value); }
    const validations = ['max_l2_error', 'min_l2_rate', 'max_residual_relative',
      ...(!linear ? ['max_h1_seminorm_error', 'min_h1_rate'] : [])];
    exactKeys(request.validation, validations, 'RESEARCH_ARGUMENTS_REQUIRED');
    validations.forEach(key => number(request.validation[key]));
    const mesh = request.mesh;
    exactKeys(mesh, imported ? ['degree', 'levels'] : ['degree', 'cell_counts'], 'RESEARCH_ARGUMENTS_REQUIRED');
    if (mesh.degree !== bound.degree) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
    const counts = (values, changing, maximum) => {
      const expected = changing ? bound.max_mesh_levels : 1;
      if (!Array.isArray(values) || values.length !== expected || Array.from(values).some((value, i) =>
          !Number.isInteger(value) || value < 1 || value > maximum || (changing && i > 0 && value !== 2*values[i-1])))
        nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
    };
    if (imported) {
      if (!Array.isArray(mesh.levels) || mesh.levels.length !== bound.max_mesh_levels) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
      let bytes = 0;
      for (const level of mesh.levels) {
        exactKeys(level, ['format', 'data', 'sha256', 'source'], 'RESEARCH_ARGUMENTS_REQUIRED');
        if (level.format !== 'gmsh_msh2_ascii' || typeof level.data !== 'string' || !level.data.length ||
            /[^\x00-\x7f]/.test(level.data) || typeof level.source !== 'string' || !level.source.trim() ||
            [...level.source].length > 256 || !nativeSha(level.sha256)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
        bytes += Buffer.byteLength(level.data, 'ascii');
        if (bytes > bound.max_imported_bytes) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
        if (digest(Buffer.from(level.data, 'ascii')) !== level.sha256) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      }
    } else if (transient) {
      if (!['mesh', 'time'].includes(request.refinement_axis)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      exactKeys(request.time, ['start', 'end', 'step_counts', 'scheme', 'unit'], 'RESEARCH_ARGUMENTS_REQUIRED');
      const time = request.time;
      if (typeof time.start !== 'number' || time.start !== 0 || typeof time.end !== 'number' ||
          !Number.isFinite(time.end) || time.end < .001 || time.end > 1000 || time.scheme !== 'backward_euler' || time.unit !== '1')
        nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
      counts(mesh.cell_counts, request.refinement_axis === 'mesh', bound.max_cell_count);
      counts(time.step_counts, request.refinement_axis === 'time', bound.max_time_steps);
      let retained = 0;
      for (const cells of mesh.cell_counts) for (const steps of time.step_counts) retained += (steps+1)*(cells+1)**2;
      if (retained > bound.max_snapshot_node_values) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
    } else counts(mesh.cell_counts, true, bound.max_cell_count);
    // Public hooks expose parsed arguments only, not original MCP/wire bytes.
    let encoded;
    try { encoded = JSON.stringify(args); } catch { nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED'); }
    if (Buffer.byteLength(encoded, 'utf8') > bound.max_request_bytes) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
  };
  const contactArguments = (tool, args) => {
    if (!nativeStructuralResearchTools.includes(tool)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
    const strings = keys => {
      for (const key of keys) if (typeof args[key] !== 'string' || !args[key].trim()) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    };
    if (tool === 'caelab_model_analysis_run') {
      const outer = ['study_id','experiment_id','backend','settings'];
      if (Object.hasOwn(args,'hypothesis_id')) outer.push('hypothesis_id');
      exactKeys(args, outer, 'RESEARCH_ARGUMENTS_REQUIRED');
      strings(['study_id','experiment_id']);
      if (args.hypothesis_id != null && (typeof args.hypothesis_id !== 'string' || !args.hypothesis_id.trim())) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      if (args.backend !== 'structural.code_aster.contact_patch') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      const request = args.settings;
      const keys = ['case','material','top_displacement_m','limits'];
      if (nativeRecord(request) && Object.hasOwn(request,'mesh_variant')) keys.push('mesh_variant');
      exactKeys(request, keys, 'RESEARCH_ARGUMENTS_REQUIRED');
      if (request.case !== 'ssnp121a_frictionless_patch' ||
          (Object.hasOwn(request,'mesh_variant') && request.mesh_variant !== 'uniform_quad4_2x')) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      exactKeys(request.material, ['youngs_modulus_pa','poisson_ratio'], 'RESEARCH_ARGUMENTS_REQUIRED');
      exactKeys(request.limits, ['reference_relative','force_balance_relative'], 'RESEARCH_ARGUMENTS_REQUIRED');
      for (const value of [request.material.youngs_modulus_pa,request.material.poisson_ratio,request.top_displacement_m])
        if (typeof value !== 'number' || !Number.isFinite(value)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      for (const [key,value] of Object.entries(nativeContactLimits))
        if (typeof request.limits[key] !== 'number' || request.limits[key] !== value) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
      // Finite scientific-invalid E/nu/displacement pass unchanged to Domain.
      // This hook never applies engineering ranges, fills settings or runs a solver.
    } else if (tool === 'caelab_study_create') {
      exactKeys(args,['study_id','name','research_question','hypothesis','objective'],'RESEARCH_ARGUMENTS_REQUIRED');
      strings(['study_id','name','research_question','hypothesis','objective']);
    } else if (tool === 'caelab_study_inspect') {
      exactKeys(args,['study_id'],'RESEARCH_ARGUMENTS_REQUIRED'); strings(['study_id']);
    } else if (tool === 'caelab_experiment_compare') {
      exactKeys(args,['experiment_ids'],'RESEARCH_ARGUMENTS_REQUIRED');
      if (!Array.isArray(args.experiment_ids) || !args.experiment_ids.length ||
          args.experiment_ids.some(value => typeof value !== 'string' || !value.trim())) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    } else {
      exactKeys(args,['experiment_id'],'RESEARCH_ARGUMENTS_REQUIRED'); strings(['experiment_id']);
    }
    // Tool hooks expose parsed arguments, not the original MCP wire bytes.
    let encoded;
    try { encoded = JSON.stringify(args); } catch { nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED'); }
    if (Buffer.byteLength(encoded,'utf8') > settings.research.budgets.contact_patch.max_request_bytes)
      nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
  };
  const researchArguments = (tool, args) => {
    if (!Object.hasOwn(settings, 'research')) return;
    if (!nativeRecord(args)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    const budget = settings.research.budgets;
    if (settings.research.schema === 6) {
      contactArguments(tool, args);
      return;
    }
    if (settings.research.schema === 5) {
      if (!nativeStructuralResearchTools.includes(tool)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      if (tool === 'caelab_model_analysis_run') viscoelasticArguments(args);
      return;
    }
    if (settings.research.schema === 4) {
      if (!nativeStructuralResearchTools.includes(tool)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      if (tool === 'caelab_model_analysis_run') materialArguments(args);
      return;
    }
    if (settings.research.schema === 3) {
      if (!nativePdeResearchTools.includes(tool)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      if (tool === 'caelab_pde_run') pdeArguments(args);
      return;
    }
    if (settings.research.schema === 2) {
      if (!nativeStructuralResearchTools.includes(tool)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      if (tool !== 'caelab_model_analysis_run') return;
      if (!nativeStructuralBackends.includes(args.backend) || !nativeRecord(args.settings)) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      const request = args.settings;
      exactKeys(request, ['case','load_case','load_factor','mesh_cells'], 'RESEARCH_ARGUMENTS_REQUIRED');
      if (!Object.hasOwn(nativeStructuralCases, request.case) || !nativeStructuralCases[request.case].includes(request.load_case))
        nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      const bound = budget.model_analysis;
      if (typeof request.load_factor !== 'number' || !Number.isFinite(request.load_factor) || request.load_factor <= 0 ||
          request.load_factor > bound.max_load_factor || !Array.isArray(request.mesh_cells) ||
          request.mesh_cells.length < 2 || request.mesh_cells.length > bound.max_mesh_levels) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
      let previous;
      for (const grid of request.mesh_cells) {
        if (!Array.isArray(grid) || grid.length !== 3 || grid.some(value => !Number.isInteger(value) || value < 1 || value > bound.max_axis_cells))
          nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
        const [x,y,z] = grid;
        const elements = x*y*z;
        const nodes = (x+1)*(y+1)*(z+1) + x*(y+1)*(z+1) + (x+1)*y*(z+1) + (x+1)*(y+1)*z;
        if (elements > bound.max_elements_per_level || nodes > bound.max_nodes_per_level ||
            (previous && (grid.some((value,axis) => value < previous[axis]) || grid.every((value,axis) => value === previous[axis]))))
          nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
        previous = grid;
      }
      return;
    }
    if (['caelab_parameters_discover','caelab_parameters_register','caelab_experiment_run','caelab_optimization_plan'].includes(tool) &&
        (args.backend !== 'fixture.cadquery' || args.model !== 'roller_support')) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
    const analysisMesh = value => {
      // Historical profiles describe refinement inputs only. A new adapter
      // opt-in must not become Research admission through the old count gate.
      if (nativeRecord(value?.mesh) && Object.hasOwn(value.mesh, 'mode'))
        nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      if (!Array.isArray(value?.mesh?.max_sizes_mm) || !value.mesh.max_sizes_mm.length ||
          value.mesh.max_sizes_mm.length > budget.analysis.max_mesh_levels) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
    };
    if (tool === 'caelab_analysis_run') {
      if (args.backend !== 'fixture.calculix') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      analysisMesh(args.settings);
    }
    if (tool === 'caelab_optimization_plan') {
      const generations = args.max_generations ?? 1, population = args.population_size ?? 5;
      if (!Number.isInteger(generations) || generations < 1 || generations > budget.optimization.max_generations ||
          !Number.isInteger(population) || population !== budget.optimization.population_size)
        nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
      if ((args.engine ?? 'scipy.differential_evolution') !== 'scipy.differential_evolution') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      if (args.analysis_backend != null) {
        if (args.analysis_backend !== 'fixture.calculix') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
        analysisMesh(args.analysis_settings);
      }
    }
    if (tool === 'caelab_pde_run') {
      if (args.backend !== 'pde.fenicsx' || args.settings?.problem?.domain !== 'unit_square') nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
      const mesh = args.settings?.mesh;
      if (!Array.isArray(mesh?.cell_counts) || !mesh.cell_counts.length || mesh.cell_counts.length > budget.pde.max_mesh_levels ||
          mesh.cell_counts.some(value => !Number.isInteger(value) || value < 1 || value > budget.pde.max_cell_count) ||
          mesh.degree !== 1) nativeRefuse('RESEARCH_WORK_BUDGET_EXCEEDED');
    }
  };
  const evaluate = async (hook, input, output) => {
    const hashes = {};
    try {
      if (managed()) hashes.sessionID = input?.sessionID;
      stableFiles();
      let parsed = guardFor();
      hashes.guard = parsed.sha256;
      if (parsed.guard.stopping) nativeRefuse('RUNTIME_STOPPING');
      if (managed()) {
        await projectFor(hashes.sessionID, hashes);
        // Asynchronous metadata reads must not admit a stale stage/config.
        stableSession(input, hashes.sessionID, hashes);
        stableFiles();
        const currentGuard = guardFor();
        if (currentGuard.guard.stopping) nativeRefuse('RUNTIME_STOPPING');
        if (currentGuard.sha256 !== parsed.sha256) nativeRefuse('GUARD_CHANGED_DURING_CHECK');
      }
      hashes.source = await sourceFor(hashes);
      // A Node reader permits the native event loop to process grant/session
      // changes. Refresh ownership, then apply policy after the last await.
      if (settings.schema === 3 && managed()) await projectFor(hashes.sessionID, hashes);
      if (settings.schema === 3) finalSourceBytes(hashes);
      else {
        stableFiles();
        if (digest(read(settings.boot_source.git_path, 128 * 1024 * 1024)) !== settings.boot_source.git_sha256) nativeRefuse('GIT_EXECUTABLE_CHANGED');
      }
      if (managed()) {
        stableSession(input, hashes.sessionID, hashes);
        hashes.projectCheck.identity = 'FAIL';
        projectInputFor();
        hashes.projectCheck.identity = 'PASS';
      }
      parsed = guardFor();
      hashes.guard = parsed.sha256;
      if (parsed.guard.stopping) nativeRefuse('RUNTIME_STOPPING');
      if (hook === 'chat.params') {
        const model = input?.model;
        if (!nativeRecord(model) || model.providerID !== 'openai-codex' ||
            `${model.providerID}/${model.id}` !== settings.model) nativeRefuse('MODEL_CHANGED');
        const agent = typeof input?.agent === 'string' ? input.agent : input?.agent?.name;
        if (!(Object.hasOwn(settings, 'research') ? ['research'] : ['research', 'caelab-acceptance']).includes(agent)) nativeRefuse('AGENT_NOT_ALLOWED');
      } else {
        if (parsed.guard.no_tools) nativeRefuse('NO_TOOLS_STAGE');
        if (!settings.allowed.includes(input?.tool)) nativeRefuse('TOOL_NOT_ALLOWED');
        if (parsed.guard.required !== null && input.tool !== parsed.guard.required) nativeRefuse('REQUIRED_TOOL_MISMATCH');
        researchArguments(input.tool, output?.args);
      }
      receipt(hook, input, 'accepted', 'CHECKS_PASSED', hashes);
    } catch (error) {
      const code = error instanceof NativeGuardRefusal ? error.code : 'CHECK_FAILED';
      try { receipt(hook, input, 'rejected', code, hashes); }
      catch { nativeRefuse('RECEIPT_UNAVAILABLE'); }
      nativeRefuse(code);
    }
  };

  try { settings = nativeFreeze(JSON.parse(JSON.stringify(suppliedSettings))); }
  catch { nativeRefuse('SETTINGS_INVALID'); }
  validateSettings();
  const parsedSettings = readJson(settingsPath, 16 * 1024 * 1024, 'SETTINGS_INVALID');
  if (nativeCanonical(parsedSettings.value) !== nativeCanonical(settings)) nativeRefuse('SETTINGS_CHANGED');
  settingsSha = parsedSettings.sha256;
  stableFiles();
  const initialGuard = guardFor();
  const initialHashes = { guard: initialGuard.sha256 };
  try {
    if (managed()) {
      initialHashes.projectCheck = { identity: 'FAIL', session: 'NOT_RUN', filesystem: 'NOT_RUN' };
      projectInputFor();
      initialHashes.projectCheck.identity = 'PASS';
    }
    initialHashes.source = await sourceFor(initialHashes);
    if (settings.schema === 3) finalSourceBytes(initialHashes);
    else {
      stableFiles();
      if (digest(read(settings.boot_source.git_path, 128 * 1024 * 1024)) !== settings.boot_source.git_sha256) nativeRefuse('GIT_EXECUTABLE_CHANGED');
    }
    if (managed()) {
      initialHashes.projectCheck.identity = 'FAIL';
      projectInputFor();
      initialHashes.projectCheck.identity = 'PASS';
    }
    const currentGuard = guardFor();
    initialHashes.guard = currentGuard.sha256;
    if (currentGuard.guard.stopping) nativeRefuse('RUNTIME_STOPPING');
  }
  catch (error) {
    const code = error instanceof NativeGuardRefusal ? error.code : 'CHECK_FAILED';
    try { receipt('plugin.loaded', null, 'rejected', code, initialHashes); }
    catch { nativeRefuse('RECEIPT_UNAVAILABLE'); }
    nativeRefuse(code);
  }
  receipt('plugin.loaded', null, 'accepted', 'PLUGIN_LOADED', initialHashes);
  return {
    'chat.params': async (input, output) => evaluate('chat.params', input, output),
    'tool.execute.before': async (input, output) => evaluate('tool.execute.before', input, output),
  };
}

export async function CaeLabNativeGuard(pluginInput) {
  const pluginPath = nativeFileURLToPath(import.meta.url);
  const settingsPath = nativePath.join(nativePath.dirname(pluginPath), 'native-guard-settings.json');
  // Check ancestors before reading even the settings that define ownership.
  let current = nativePath.parse(settingsPath).root;
  for (const part of nativePath.relative(current, settingsPath).split(nativePath.sep).filter(Boolean)) {
    current = nativePath.join(current, part);
    let stat;
    try { stat = nativeFs.lstatSync(current); } catch { nativeRefuse('PATH_UNAVAILABLE'); }
    if (stat.isSymbolicLink()) nativeRefuse('PATH_LINKED');
  }
  let settings;
  try {
    if (nativeFs.statSync(settingsPath).size > 16 * 1024 * 1024) nativeRefuse('FILE_SIZE_INVALID');
    settings = JSON.parse(nativeFs.readFileSync(settingsPath, 'utf8'));
  } catch (error) {
    if (error instanceof NativeGuardRefusal) throw error;
    nativeRefuse('SETTINGS_INVALID');
  }
  return createNativeHooks(settings, { settingsPath, pluginPath, pluginInput });
}
