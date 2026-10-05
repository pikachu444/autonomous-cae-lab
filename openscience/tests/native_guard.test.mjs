import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const modulePath = fileURLToPath(new URL('../native_guard.mjs', import.meta.url));
const source = fs.readFileSync(modulePath, 'utf8');
const gitStateSource = fs.readFileSync(new URL('../native_git_state.mjs', import.meta.url), 'utf8');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
// This prefix substitutes only the independently tested existing Git snapshot
// implementation. The guard and final Git-state helper run unchanged on files.
// There is no provider, Core, credential access or executable invocation.
const prefix = `
import testSourceFs from 'node:fs';
import testSourcePath from 'node:path';
import testSourceCrypto from 'node:crypto';
const sourceDigest = bytes => testSourceCrypto.createHash('sha256').update(bytes).digest('hex');
const sourceCanonical = value => JSON.stringify(value, (_,item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key,item[key]])) : item);
const sourcePinSha = value => sourceDigest(sourceCanonical(value));
function captureRepositorySourcePin(root, _git) {
  return JSON.parse(testSourceFs.readFileSync(testSourcePath.join(root,'source-state.json'),'utf8'));
}
function assertRepositorySourcePin(expected,current) {
  if (sourceCanonical(expected) !== sourceCanonical(current)) throw new Error('synthetic snapshot differs');
}
${gitStateSource}
`;
const temporarySource = `${prefix}\n${source}\nexport { createNativeHooks, NativeGuardRefusal, assertNativeGitState, nativeFixtureSelectedDefinition, nativeMaterialDefinition, nativeMaterialLimits, nativeViscoelasticDefinition, nativeViscoelasticLimits, nativeContactDefinition, nativeContactLimits };\n`;
const { createNativeHooks, NativeGuardRefusal, assertNativeGitState, nativeFixtureSelectedDefinition, nativeMaterialDefinition, nativeMaterialLimits, nativeViscoelasticDefinition, nativeViscoelasticLimits, nativeContactDefinition, nativeContactLimits } = await import(`data:text/javascript;base64,${Buffer.from(temporarySource).toString('base64')}`);
const tools = [
  'caelab_study_create', 'caelab_study_inspect', 'caelab_parameters_discover',
  'caelab_parameters_register', 'caelab_parameters_list', 'caelab_experiment_run',
  'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare',
];
const json = (file, value) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
function fixture(t, selected = tools) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'caelab-native-guard-'));
  t.after(() => {
    const absolute = path.resolve(base);
    assert.equal(path.dirname(absolute), path.resolve(os.tmpdir()));
    assert.ok(path.basename(absolute).startsWith('caelab-native-guard-'));
    fs.rmSync(absolute, { recursive: true, force: true });
  });
  const profile = path.join(base, 'profile'), repo = path.join(base, 'repo');
  for (const directory of [profile, repo, path.join(profile, 'runtime'), path.join(profile, 'config'),
    path.join(profile, 'receipts'), path.join(base, 'bin'), path.join(base, 'outside')]) fs.mkdirSync(directory, { recursive: true });
  const git = path.join(base, 'bin', 'git-synthetic.exe');
  fs.writeFileSync(git, 'SYNTHETIC DATA; THIS FILE IS NEVER EXECUTED');
  const configPath = path.join(profile, 'config', 'openscience.json');
  json(configPath, { model: 'openai-codex/test-explicit-model', permission: { '*': 'deny' } });
  const pluginPath = path.join(profile, 'runtime', 'native-guard.mjs');
  fs.writeFileSync(pluginPath, `${prefix}\n${source}`);
  const settingsPath = path.join(profile, 'runtime', 'native-guard-settings.json');
  const boot = {
    schema: 1, kind: 'autonomous-cae-lab.repository-source-pin', repo_root: repo,
    git_path: git, git_sha256: sha(fs.readFileSync(git)), source_commit: 'a'.repeat(40),
    source_tree_sha256: 'b'.repeat(64), source_dirty: [], files: [], submodules: [],
  };
  const statePath = path.join(repo, 'source-state.json');
  json(statePath, boot);
  const settings = {
    schema: 1, kind: 'autonomous-cae-lab.openscience-native-guard', repo_root: repo,
    run_name: 'native-fixture-01', profile_root: profile, model: 'openai-codex/test-explicit-model',
    allowed: [...selected], guardPath: path.join(profile, 'tool-guard.json'), configPath,
    config_sha256: sha(fs.readFileSync(configPath)), pluginPath, plugin_sha256: sha(fs.readFileSync(pluginPath)),
    receipts: path.join(profile, 'receipts'), boot_source: boot, boot_source_sha256: sha(canonical(boot)),
  };
  const guard = {
    schema: 1, kind: 'autonomous-cae-lab.openscience-tool-guard', repo_root: repo,
    run_name: settings.run_name, profile_root: profile, model: settings.model, allowed: [...selected],
    required: null, no_tools: false, stopping: false, updated_utc: '2026-10-01T00:00:00.000Z',
  };
  json(settingsPath, settings); json(settings.guardPath, guard);
  const counts = { capture: 0 };
  const capture = () => { counts.capture++; return JSON.parse(fs.readFileSync(statePath, 'utf8')); };
  const dependencies = {
    settingsPath, pluginPath, capture, pinSha: value => sha(canonical(value)),
    assertPin: (expected, current) => assert.equal(canonical(current), canonical(expected)),
  };
  const hooks = () => createNativeHooks(settings, dependencies);
  const writeGuard = patch => json(settings.guardPath, { ...guard, ...patch });
  const receipts = () => fs.readdirSync(settings.receipts).map(name => JSON.parse(fs.readFileSync(path.join(settings.receipts, name), 'utf8')))
    .sort((a, b) => a.sequence - b.sequence);
  return { base, profile, repo, settings, settingsPath, guard, boot, statePath, counts, dependencies, hooks, writeGuard, receipts };
}
function managedFixture(t) {
  const f = fixture(t);
  const identity = path.join(f.base, 'managed-identity');
  fs.mkdirSync(identity);
  const binding = {
    schema: 1, kind: 'autonomous-cae-lab.openscience-project-binding', project_id: 'prj_fixture01',
    project_directory: identity, source_directory: f.repo, grant_id: 'fsg_fixture01', working_root: f.repo, access: 'write',
  };
  f.settings.schema = 2;
  f.settings.project_binding = binding;
  json(f.settingsPath, f.settings);
  const sessionID = 'ses_fixture01';
  const state = {
    session: { id: sessionID, projectID: binding.project_id, directory: identity, workspace: { mode: 'isolated' } },
    filesystem: { version: 1, revision: 1, sessionID, projectID: binding.project_id, directory: identity,
      toolDirectory: f.repo, workingRoot: f.repo, workspace: { mode: 'isolated' }, enforcement: {},
      grants: [{ id: binding.grant_id, path: f.repo, access: 'write', scope: 'project', source: 'fixture', time: { created: 1 } }] },
  };
  f.counts.session = 0; f.counts.filesystem = 0;
  const pluginInput = {
    project: { id: binding.project_id, worktree: identity }, directory: identity, worktree: identity,
    serverUrl: new URL('http://127.0.0.1:4098/'),
    client: { session: { get: async options => {
      f.counts.session++;
      assert.deepEqual(options.path, { id: sessionID });
      assert.equal(options.throwOnError, true);
      assert.ok(options.signal instanceof AbortSignal);
      if (state.sessionError) throw state.sessionError;
      return state.sessionEnvelope ?? { data: structuredClone(state.session) };
    } } },
  };
  f.dependencies.pluginInput = pluginInput;
  f.dependencies.loadFilesystem = async (id, signal) => {
    f.counts.filesystem++;
    assert.equal(id, sessionID);
    assert.ok(signal instanceof AbortSignal);
    if (state.filesystemError) throw state.filesystemError;
    return structuredClone(state.filesystem);
  };
  return { ...f, binding, identity, sessionID, state, pluginInput,
    request: () => ({ ...input(), sessionID }),
  };
}
function initializeFixtureGit(repo) {
  const directory = path.join(repo, '.git');
  fs.mkdirSync(directory, { recursive: true });
  fs.writeFileSync(path.join(directory, 'HEAD'), 'a'.repeat(40) + '\n');
  fs.writeFileSync(path.join(directory, 'index'), 'SYNTHETIC INDEX BYTES\n');
}
function fixtureGitState(f) {
  const repositories = [f.repo, ...f.boot.submodules.map(module => path.resolve(f.repo, module.path))].map(repo => ({
    repo_root: repo,
    entries: ['git-pointer', 'HEAD', 'index', 'config', 'config.worktree', 'commondir', 'info/exclude', 'info/sparse-checkout'].map(slot => {
      const absolute = slot === 'git-pointer' ? path.join(repo, '.git') : path.join(repo, '.git', slot);
      const stat = fs.existsSync(absolute) ? fs.lstatSync(absolute) : null;
      return { slot, path: absolute, state: stat?.isFile() ? 'file' : stat?.isDirectory() ? 'directory' : 'missing',
        sha256: stat?.isFile() ? sha(fs.readFileSync(absolute)) : null };
    }), refs: [], packed_ref: null,
  }));
  return { schema: 1, kind: 'autonomous-cae-lab.native-git-state', repositories };
}
const readerResult = (f, pin = f.boot, gitState = fixtureGitState(f)) => ({
  schema: 1, kind: 'autonomous-cae-lab.source-reader-result', pin, git_state: gitState,
});
function readerFixture(t, { managed = false, actual = false, workerSource } = {}) {
  const f = managed ? managedFixture(t) : fixture(t);
  initializeFixtureGit(f.repo);
  const gitStatePath = path.join(f.profile, 'synthetic-git-state.json');
  json(gitStatePath, fixtureGitState(f));
  const nodePath = actual ? path.resolve(process.execPath) : path.join(f.base, 'bin', 'node-synthetic.exe');
  if (!actual) fs.writeFileSync(nodePath, 'SYNTHETIC NODE DATA; NEVER EXECUTED');
  const workerPath = path.join(f.profile, 'source-reader.mjs');
  const worker = workerSource ?? `
import fs from 'node:fs';
import path from 'node:path';
process.stdin.on('data', () => process.exit(3));
process.stdin.on('end', () => {
  const root = process.argv[2], git = process.argv[3], settingsPath = process.argv[4];
  const pin = JSON.parse(fs.readFileSync(path.join(root, 'source-state.json'), 'utf8'));
  const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
  const gitState = JSON.parse(fs.readFileSync(path.join(settings.profile_root, 'synthetic-git-state.json'), 'utf8'));
  if (process.argv.length !== 5 || process.cwd() !== root || pin.git_path !== git ||
      settings.repo_root !== root || settings.boot_source.git_path !== git ||
      Object.keys(process.env).some(key => /^(NODE_OPTIONS|NODE_PATH|GIT_|OPENAI_|PROVIDER_)/i.test(key))) process.exit(4);
  process.stdout.write(JSON.stringify({ schema: 1, kind: 'autonomous-cae-lab.source-reader-result', pin, git_state: gitState }) + '\\n');
});
`;
  fs.writeFileSync(workerPath, worker);
  f.settings.schema = 3;
  f.settings.source_reader = { node_path: nodePath, node_sha256: sha(fs.readFileSync(nodePath)),
    worker_path: workerPath, worker_sha256: sha(fs.readFileSync(workerPath)) };
  json(f.settingsPath, f.settings);
  f.dependencies.capture = () => { throw new Error('LEGACY SYNC CAPTURE MUST NOT RUN'); };
  const reader = { calls: 0, ended: 0, destroyed: 0, seen: [], error: null, stdout: undefined, beforeReturn: null };
  if (!actual) {
    f.dependencies.execFile = (file, args, options, callback) => {
      reader.calls++; reader.seen.push({ file, args, options });
      const gitState = fixtureGitState(f);
      Promise.resolve().then(() => reader.beforeReturn?.()).then(() => callback(reader.error,
        reader.stdout ?? JSON.stringify(readerResult(f, JSON.parse(fs.readFileSync(f.statePath, 'utf8')), gitState)), 'SECRET CHILD STDERR SENTINEL'),
      error => callback(error, '', 'SECRET CHILD STDERR SENTINEL'));
      return { stdin: { end: () => reader.ended++, destroy: () => reader.destroyed++ } };
    };
  }
  return { ...f, nodePath, workerPath, gitStatePath, reader };
}
function pinFixtureFile(f, relative, content = 'PINNED SYNTHETIC SOURCE\n') {
  const absolute = path.join(f.repo, relative);
  fs.mkdirSync(path.dirname(absolute), { recursive: true });
  fs.writeFileSync(absolute, content);
  f.boot.files.push({ path: relative, sha256: sha(fs.readFileSync(absolute)), index_object: 'a'.repeat(40), index_mode: '100644' });
  f.settings.boot_source_sha256 = sha(canonical(f.boot));
  json(f.statePath, f.boot); json(f.settingsPath, f.settings);
  return absolute;
}
const input = () => ({ sessionID: 'ses_synthetic-01', agent: 'research', model: { providerID: 'openai-codex', id: 'test-explicit-model' } });
function researchFixture(t) {
  const f = readerFixture(t, { managed: true });
  const selected = [...tools, 'caelab_analysis_run', 'caelab_optimization_plan',
    'caelab_optimization_run', 'caelab_optimization_inspect', 'caelab_pde_run'];
  f.settings.allowed = [...selected]; f.guard.allowed = [...selected];
  f.settings.research = {
    schema: 1, kind: 'autonomous-cae-lab.openscience-research-definition', agent: 'research', allowed_tools: [...selected],
    runtime_environment: { MPLBACKEND:'Agg', OMP_NUM_THREADS:'2', QT_QPA_PLATFORM:'offscreen', CAELAB_FENICSX_PYTHON:'/usr/bin/python3' },
    budgets: {steps:24, mcp_timeout_seconds:3600, command_timeout_seconds:3600,
      optimization:{max_generations:1, population_size:5}, analysis:{max_mesh_levels:2}, pde:{max_cell_count:32, max_mesh_levels:3}},
    capabilities: ['fixture.cadquery','fixture.calculix','pde.fenicsx'].map(backend => ({backend, verification:'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF'})),
    limitations: ['Synthetic admission test; no solver or provider executed.'],
  };
  json(f.settingsPath, f.settings); f.writeGuard({});
  return f;
}
function structuralResearchFixture(t) {
  const f = readerFixture(t, {managed:true});
  const selected = ['caelab_study_create','caelab_study_inspect','caelab_model_analysis_run',
    'caelab_experiment_inspect','caelab_experiment_summary','caelab_experiment_compare'];
  f.settings.allowed = [...selected]; f.guard.allowed = [...selected];
  f.settings.research = {
    schema:2, kind:'autonomous-cae-lab.openscience-research-definition', agent:'research', profile:'structural-families-v1',
    benchmark_definition:{id:'P2-family-v1-20261002',path:'benchmarks/specifications/structural-families-v1.json'},
    allowed_tools:[...selected],
    runtime_environment:{MPLBACKEND:'Agg',OMP_NUM_THREADS:'2',QT_QPA_PLATFORM:'offscreen',
      CAELAB_CODEASTER_IMAGE:'/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif',
      CAELAB_CODEASTER_IMAGE_SHA256:'f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64',
      CAELAB_SINGULARITY_COMMAND:'/usr/bin/singularity'},
    budgets:{steps:24,mcp_timeout_seconds:3600,command_timeout_seconds:3600,
      model_analysis:{max_mesh_levels:3,max_axis_cells:48,max_elements_per_level:1024,max_nodes_per_level:10000,max_load_factor:2}},
    capabilities:['structural.families.calculix','structural.families.code_aster'].map(backend => ({backend,
      cases:['ansys_vmd1_regular','lame_cylinder_plane_strain','scordelis_lo_solid'],operations:['model_analysis_run']})),
    limitations:['Synthetic source admission; no model, solver or Core calls.'],
  };
  json(f.settingsPath,f.settings); f.writeGuard({});
  return f;
}
// The canonical descriptor is embedded in the guard for the copied plugin.
// PS parity is separately checked using its actual exported definition below.
const refinementDefinition = JSON.parse(source.match(
  /const nativeFixtureRefinementDefinition = nativeFreeze\((\{[\s\S]*?\})\);/)[1]);
function refinementResearchFixture(t, definition = refinementDefinition) {
  const f = readerFixture(t, {managed:true});
  f.settings.allowed = [...definition.allowed_tools]; f.guard.allowed = [...definition.allowed_tools];
  f.settings.research = structuredClone(definition);
  json(f.settingsPath,f.settings); f.writeGuard({});
  return f;
}
function refinementAnalysis(mesh = [4,3,2]) {
  return {parent_experiment_id:'cad32',experiment_id:'solve32',backend:'fixture.calculix',settings:{
    load:{force_per_support_N:100,source:'Hypothetical test load'},
    material:{model:'orthotropic',E_1_MPa:1800,E_2_MPa:1800,E_3_MPa:900,
      nu_12:.3,nu_13:.3,nu_23:.3,G_12_MPa:650,G_13_MPa:320,G_23_MPa:320,
      axes:'global CAD X/Y/Z',provenance:'Synthetic assumption',qualification:'UNKNOWN'},
    mesh:{max_sizes_mm:mesh}}};
}
test('fixture refinement actual PS definition exactly matches the copied native guard',
  {skip:!process.env.CAELAB_FIXTURE_REFINEMENT_DEFINITION_PATH && 'External actual PS definition was not supplied.'},async t => {
    const definition = JSON.parse(fs.readFileSync(process.env.CAELAB_FIXTURE_REFINEMENT_DEFINITION_PATH,'utf8'));
    assert.equal(canonical(definition),canonical(refinementDefinition));
    const f = refinementResearchFixture(t,definition), hooks = await f.hooks();
    await hooks['chat.params'](f.request(),{});
    assert.equal(definition.schema,7); assert.equal(definition.profile,'fixture-refinement-v1');
    assert.equal(definition.allowed_tools.length,14);
    const args = refinementAnalysis(), original = structuredClone(args);
    await hooks['tool.execute.before']({tool:'caelab_analysis_run',sessionID:f.sessionID},{args});
    assert.deepEqual(args,original); assert.equal(f.receipts().at(-1).accepted,true);
  });
test('fixture refinement analysis and numerical planning admit three requested meshes without rewriting conditions',async t => {
  const f = refinementResearchFixture(t), hooks = await f.hooks();
  for (const mesh of [[4,3],[4,3,2]]) {
    const analysis = refinementAnalysis(mesh);
    for (const [tool,args] of [['caelab_analysis_run',analysis],['caelab_optimization_plan',{
      backend:'fixture.cadquery',model:'roller_support',analysis_backend:'fixture.calculix',
      analysis_settings:analysis.settings,seed:13,max_generations:1,population_size:5}]]) {
      const original = structuredClone(args);
      await hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args});
      assert.deepEqual(args,original); assert.equal(f.receipts().at(-1).accepted,true);
    }
  }
});
test('fixture refinement retains finite scientific-invalid conditions for Domain rejection',async t => {
  const f = refinementResearchFixture(t), hooks = await f.hooks();
  // Work count is this hook's boundary; scientific limits belong to Domain.
  for (const mesh of [[2,4],[-1,-2],[4]]) {
    const args = refinementAnalysis(mesh); args.settings.load.force_per_support_N = -100;
    const original = structuredClone(args);
    await hooks['tool.execute.before']({tool:'caelab_analysis_run',sessionID:f.sessionID},{args});
    assert.deepEqual(args,original); assert.equal(f.receipts().at(-1).accepted,true);
  }
});
for (const [label,mesh] of [['four meshes',[5,4,3,2]],['missing list',undefined],['empty list',[]]]) {
  test(`fixture refinement refuses ${label} for analysis and numerical planning`,async t => {
    const f = refinementResearchFixture(t), hooks = await f.hooks();
    const analysis = refinementAnalysis(mesh);
    if (mesh === undefined) analysis.settings.mesh = {element_size_mm:4};
    for (const [tool,args] of [['caelab_analysis_run',analysis],['caelab_optimization_plan',{
      backend:'fixture.cadquery',model:'roller_support',analysis_backend:'fixture.calculix',analysis_settings:analysis.settings}]]) {
      const original = structuredClone(args);
      await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
      assert.deepEqual(args,original); assert.equal(f.receipts().at(-1).accepted,false);
    }
  });
}
test('fixture refinement rejects descriptor tampering including boundary metadata and larger work budgets',async t => {
  for (const change of [d => d.budgets.analysis.max_mesh_levels=4,d => d.profile='fixture-refinement-v2',
    d => d.runtime_environment.OMP_NUM_THREADS='8',d => d.allowed_tools.push('caelab_model_analysis_run'),
    d => d.capabilities[1].boundary_model='Invented bolt clamp',d => d.capabilities[1].numerical_verdict='Always PASS']) {
    const f = refinementResearchFixture(t); change(f.settings.research); json(f.settingsPath,f.settings);
    await assert.rejects(f.hooks(),refusal('RESEARCH_DEFINITION_INVALID'));
  }
});
test('fixture refinement preserves source grant and stopping gates for admitted analysis',async t => {
  for (const drift of ['source','grant','stopping']) {
    const f = refinementResearchFixture(t), hooks = await f.hooks();
    if (drift === 'source') json(f.statePath,{...f.boot,source_commit:'f'.repeat(40)});
    if (drift === 'grant') f.state.filesystem.grants[0].access='read';
    if (drift === 'stopping') f.writeGuard({stopping:true});
    const args = refinementAnalysis(), original = structuredClone(args);
    await assert.rejects(hooks['tool.execute.before']({tool:'caelab_analysis_run',sessionID:f.sessionID},{args}));
    assert.deepEqual(args,original); assert.equal(f.receipts().at(-1).accepted,false);
  }
});
test('fixture refinement keeps backend numerical engine and population admission limits',async t => {
  const f = refinementResearchFixture(t), hooks = await f.hooks();
  for (const [tool,args,code] of [
    ['caelab_analysis_run',{...refinementAnalysis(),backend:'structural.code_aster.contact_patch'},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
    ['caelab_optimization_plan',{backend:'fixture.cadquery',model:'roller_support',engine:'llm.optimizer'},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
    ['caelab_optimization_plan',{backend:'fixture.cadquery',model:'roller_support',population_size:6},'RESEARCH_WORK_BUDGET_EXCEEDED']]) {
    const original = structuredClone(args);
    await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args}),refusal(code));
    assert.deepEqual(args,original); assert.equal(f.receipts().at(-1).accepted,false);
  }
});
const refusal = code => error => error.name === 'CaeLabNativeGuardRefusal' && error.code === code && !error.message.includes('synthetic snapshot');
test('historical fixture research scopes refuse undeclared selected mesh mode before Core',async t => {
  for (const fixtureFactory of [researchFixture,refinementResearchFixture]) {
    const f = fixtureFactory(t), hooks = await f.hooks();
    for (const mode of ['selected','refinement',true,null,undefined]) {
      const analysis = refinementAnalysis([4]);
      analysis.settings.mesh.mode = mode;
      const requests = [
        ['caelab_analysis_run',analysis],
        ['caelab_optimization_plan',{backend:'fixture.cadquery',model:'roller_support',
          analysis_backend:'fixture.calculix',analysis_settings:analysis.settings}],
      ];
      for (const [tool,args] of requests) {
        const original = structuredClone(args);
        await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args}),
          refusal('RESEARCH_CAPABILITY_NOT_ADMITTED'));
        assert.deepEqual(args,original); assert.equal(f.receipts().at(-1).accepted,false);
      }
    }
  }
});

// TEST_ONLY parsed-hook controls. They never execute a provider, Core or solver.
// The copied native descriptor has an independent frozen canonical pin, and the
// optional external file exercises the actual PowerShell factory export.
const selectedDefinitionSha = 'b501a8216d63baea80b0b5d1ce9b727409f2680e3d84ee5212e244a9f3f26626';
const selectedResearchFixture = (t,definition=nativeFixtureSelectedDefinition) => refinementResearchFixture(t,definition);
function selectedAnalysis(size=4) {
  const request=refinementAnalysis([size]);
  request.settings.mesh.mode='selected';
  return request;
}
const selectedPlan = analysis => ({backend:'fixture.cadquery',model:'roller_support',seed:13,
  engine:'scipy.differential_evolution',max_generations:1,population_size:5,
  analysis_backend:'fixture.calculix',analysis_settings:analysis.settings});
const selectedRequests = analysis => [['caelab_analysis_run',analysis],['caelab_optimization_plan',selectedPlan(analysis)]];
async function checkSelectedRequest(f,hooks,tool,args,code) {
  const output={args},original=structuredClone(output),before=f.receipts().length;
  const action=hooks['tool.execute.before']({tool,sessionID:f.sessionID},output);
  if (code) await assert.rejects(action,refusal(code));
  else await action;
  assert.deepEqual(output,original,'The hook must preserve all supplied arguments, including refusals.');
  assert.equal(f.receipts().length,before+1);
  const receipt=f.receipts().at(-1);
  assert.equal(receipt.tool,tool); assert.equal(receipt.accepted,!code);
  if (code) assert.equal(receipt.code,code);
}

test('fixture selected descriptor keeps the frozen scope and historical refinement pin',() => {
  assert.equal(sha(canonical(nativeFixtureSelectedDefinition)),selectedDefinitionSha);
  assert.equal(sha(canonical(refinementDefinition)),'bd7e341d373ce732d72f7c4263d35b015047efd4cde0f181aee73e1a11459632');
  assert.equal(nativeFixtureSelectedDefinition.schema,8);
  assert.equal(nativeFixtureSelectedDefinition.profile,'fixture-selected-mesh-v1');
  assert.deepEqual(nativeFixtureSelectedDefinition.allowed_tools,refinementDefinition.allowed_tools);
  assert.equal(nativeFixtureSelectedDefinition.allowed_tools.length,14);
  assert.deepEqual(nativeFixtureSelectedDefinition.runtime_environment,refinementDefinition.runtime_environment);
  const expectedBudgets=structuredClone(refinementDefinition.budgets); expectedBudgets.analysis.max_mesh_levels=1;
  assert.deepEqual(nativeFixtureSelectedDefinition.budgets,expectedBudgets);
  assert.deepEqual(nativeFixtureSelectedDefinition.capabilities.map(item => item.backend),
    ['fixture.cadquery','fixture.calculix','pde.fenicsx']);
  assert.equal(nativeFixtureSelectedDefinition.capabilities[1].boundary_model,refinementDefinition.capabilities[1].boundary_model);
  const verdict=nativeFixtureSelectedDefinition.capabilities[1].numerical_verdict;
  for (const text of ['reaction balance<=1%','NOT_ASSESSED','invalid-null','no displacement_mesh_trend',
    'linear solve completion only','Peak stress remains invalid','seven engineering UNKNOWNs','NOT_RELEASED']) assert.ok(verdict.includes(text),text);
  assert.ok(Object.isFrozen(nativeFixtureSelectedDefinition));
  assert.ok(Object.isFrozen(nativeFixtureSelectedDefinition.budgets.analysis));
});

test('fixture selected actual PS definition exactly matches the native guard and admits both operations unchanged',
  {skip:!process.env.CAELAB_FIXTURE_SELECTED_DEFINITION_PATH && 'External actual PS definition was not supplied.'},async t => {
    const definition=JSON.parse(fs.readFileSync(process.env.CAELAB_FIXTURE_SELECTED_DEFINITION_PATH,'utf8'));
    assert.equal(sha(canonical(definition)),selectedDefinitionSha);
    assert.equal(canonical(definition),canonical(nativeFixtureSelectedDefinition));
    const f=selectedResearchFixture(t,definition),hooks=await f.hooks();
    await hooks['chat.params'](f.request(),{});
    for (const [tool,args] of selectedRequests(selectedAnalysis())) await checkSelectedRequest(f,hooks,tool,args);
  });

test('fixture selected admits one finite numerical size for analysis and deterministic planning',async t => {
  const f=selectedResearchFixture(t),hooks=await f.hooks();
  await hooks['chat.params'](f.request(),{});
  for (const size of [4,1e-12,1e3]) {
    for (const [tool,args] of selectedRequests(selectedAnalysis(size))) await checkSelectedRequest(f,hooks,tool,args);
  }
});

test('fixture selected finite scientific-invalid conditions forward unchanged for Domain rejection',async t => {
  const f=selectedResearchFixture(t),hooks=await f.hooks();
  const negativeLoad=selectedAnalysis(); negativeLoad.settings.load.force_per_support_N=-100;
  const invalidMaterial=selectedAnalysis(); invalidMaterial.settings.material.E_3_MPa=-900;
  // These are hook admission checks, never a scientific PASS. No value is fixed
  // or replaced; actual Domain rejection and native execution are separate gates.
  for (const analysis of [selectedAnalysis(0),selectedAnalysis(-4),negativeLoad,invalidMaterial]) {
    for (const [tool,args] of selectedRequests(analysis)) await checkSelectedRequest(f,hooks,tool,args);
  }
});

for (const [label,mesh,code] of [
  ['missing mesh',undefined,'RESEARCH_ARGUMENTS_REQUIRED'],
  ['nonobject mesh',[],'RESEARCH_ARGUMENTS_REQUIRED'],
  ['omitted mode',{max_sizes_mm:[4]},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['refinement mode',{mode:'refinement',max_sizes_mm:[4]},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['case changed mode',{mode:'Selected',max_sizes_mm:[4]},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['boolean mode',{mode:true,max_sizes_mm:[4]},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['numeric mode',{mode:1,max_sizes_mm:[4]},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['null mode',{mode:null,max_sizes_mm:[4]},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['undefined own mode',{mode:undefined,max_sizes_mm:[4]},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['extra mesh key',{mode:'selected',max_sizes_mm:[4],element_size_mm:4},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['missing size list',{mode:'selected'},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['nonarray size list',{mode:'selected',max_sizes_mm:4},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['zero sizes',{mode:'selected',max_sizes_mm:[]},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['two sizes',{mode:'selected',max_sizes_mm:[4,2]},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['NaN size',{mode:'selected',max_sizes_mm:[NaN]},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['positive infinity size',{mode:'selected',max_sizes_mm:[Infinity]},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['negative infinity size',{mode:'selected',max_sizes_mm:[-Infinity]},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['string size',{mode:'selected',max_sizes_mm:['4']},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['boolean size',{mode:'selected',max_sizes_mm:[true]},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['null size',{mode:'selected',max_sizes_mm:[null]},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['object size',{mode:'selected',max_sizes_mm:[{value:4}]},'RESEARCH_ARGUMENTS_REQUIRED'],
  ['absent vector entry',{mode:'selected',max_sizes_mm:new Array(1)},'RESEARCH_ARGUMENTS_REQUIRED'],
]) test(`fixture selected refuses ${label} for both operations with retained receipts`,async t => {
  const f=selectedResearchFixture(t),hooks=await f.hooks(),analysis=selectedAnalysis();
  analysis.settings.mesh=structuredClone(mesh);
  for (const [tool,args] of selectedRequests(analysis)) await checkSelectedRequest(f,hooks,tool,args,code);
});

test('fixture selected planning requires explicit CalculiX analysis while historical CAD-only plans remain admitted',async t => {
  const f=selectedResearchFixture(t),hooks=await f.hooks();
  for (const backend of [undefined,null,'fixture.cadquery']) {
    const args=selectedPlan(selectedAnalysis());
    if (backend===undefined) delete args.analysis_backend; else args.analysis_backend=backend;
    await checkSelectedRequest(f,hooks,'caelab_optimization_plan',args,'RESEARCH_CAPABILITY_NOT_ADMITTED');
  }
  const missingSettings=selectedPlan(selectedAnalysis()); delete missingSettings.analysis_settings;
  await checkSelectedRequest(f,hooks,'caelab_optimization_plan',missingSettings,'RESEARCH_ARGUMENTS_REQUIRED');
  for (const factory of [researchFixture,refinementResearchFixture]) {
    const old=factory(t),oldHooks=await old.hooks();
    await checkSelectedRequest(old,oldHooks,'caelab_optimization_plan',
      {backend:'fixture.cadquery',model:'roller_support',seed:13,max_generations:1,population_size:5});
  }
});

for (const [label,change] of [
  ['profile',d => d.profile='fixture-selected-mesh-v2'],
  ['schema',d => d.schema=7],
  ['analysis budget',d => d.budgets.analysis.max_mesh_levels=2],
  ['steps',d => d.budgets.steps=25],
  ['optimization budget',d => d.budgets.optimization.max_generations=2],
  ['runtime',d => d.runtime_environment.OMP_NUM_THREADS='8'],
  ['tool',d => d.allowed_tools.push('caelab_model_analysis_run')],
  ['backend',d => d.capabilities[1].backend='fixture.fake'],
  ['boundary',d => d.capabilities[1].boundary_model='Invented bolt clamps'],
  ['verdict',d => d.capabilities[1].numerical_verdict='Convergence always PASS'],
  ['limitations',d => d.limitations=[]],
]) test(`fixture selected refuses descriptor ${label} tampering before loading hooks`,async t => {
  const f=selectedResearchFixture(t); change(f.settings.research); json(f.settingsPath,f.settings);
  await assert.rejects(f.hooks(),refusal('RESEARCH_DEFINITION_INVALID'));
});

test('fixture selected keeps backend numerical engine and population boundaries',async t => {
  const f=selectedResearchFixture(t),hooks=await f.hooks();
  for (const [tool,args,code] of [
    ['caelab_analysis_run',{...selectedAnalysis(),backend:'fixture.cadquery'},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
    ['caelab_optimization_plan',{...selectedPlan(selectedAnalysis()),backend:'fixture.calculix'},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
    ['caelab_optimization_plan',{...selectedPlan(selectedAnalysis()),model:'other_support'},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
    ['caelab_optimization_plan',{...selectedPlan(selectedAnalysis()),engine:'llm.optimizer'},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
    ['caelab_optimization_plan',{...selectedPlan(selectedAnalysis()),max_generations:2},'RESEARCH_WORK_BUDGET_EXCEEDED'],
    ['caelab_optimization_plan',{...selectedPlan(selectedAnalysis()),population_size:6},'RESEARCH_WORK_BUDGET_EXCEEDED'],
    ['caelab_optimization_plan',{...selectedPlan(selectedAnalysis()),population_size:4},'RESEARCH_WORK_BUDGET_EXCEEDED'],
    ['caelab_optimization_plan',{...selectedPlan(selectedAnalysis()),population_size:true},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ]) await checkSelectedRequest(f,hooks,tool,args,code);
});

for (const [drift,code] of [['source','SOURCE_CHANGED_OR_UNAVAILABLE'],['grant','PROJECT_GRANT_CHANGED'],['stopping','RUNTIME_STOPPING']]) {
  test(`fixture selected retains ${drift} refusal for analysis and numerical planning`,async t => {
    for (const [tool,args] of selectedRequests(selectedAnalysis())) {
      const f=selectedResearchFixture(t),hooks=await f.hooks();
      if (drift==='source') json(f.statePath,{...f.boot,source_commit:'f'.repeat(40)});
      if (drift==='grant') f.state.filesystem.grants[0].access='read';
      if (drift==='stopping') f.writeGuard({stopping:true});
      await checkSelectedRequest(f,hooks,tool,args,code);
    }
  });
}
// Pinned official 4082a2ecb73e166d4503963798228ba700f3840f:
// backend/cli/src/session/message-v2.ts general Error -> UnknownError branch
// retains e.toString(), not e.code; retry.ts:329-349 then checks this text.
// This reproduces those positive signals for a statusless, non-JSON Error.
// No upstream runtime, provider or network is invoked by the regression.
const officialStatuslessRetry = error => {
  const signal = error.toString().toLowerCase();
  if (signal.includes('too many requests')) return 'Too Many Requests';
  if (signal.includes('rate_limit') || signal.includes('rate limit')) return 'Rate Limited';
  if (['resource_exhausted', 'resource exhausted', 'unavailable', 'overloaded'].some(value => signal.includes(value)))
    return 'Provider is overloaded';
  if (signal.includes('no_kv_space')) return 'Provider Server Error';
  return undefined;
};
const boundedSourceCheck = check => {
  assert.deepEqual(Object.keys(check).sort(), Object.hasOwn(check, 'final_bytes') ? ['capture', 'compare', 'final_bytes'] : ['capture', 'compare']);
  for (const phase of Object.values(check)) {
    assert.deepEqual(Object.keys(phase).sort(), ['elapsed_ms', 'error_kind', 'status']);
    assert.ok(['PASS', 'FAIL', 'NOT_RUN'].includes(phase.status));
    if (phase.status === 'NOT_RUN') assert.equal(phase.elapsed_ms, null);
    else assert.ok(Number.isSafeInteger(phase.elapsed_ms) && phase.elapsed_ms >= 0 && phase.elapsed_ms <= 2_147_483_647);
    if (phase.status !== 'FAIL') assert.equal(phase.error_kind, null);
    else assert.ok(['TIMEOUT', 'OUTPUT_LIMIT', 'NOT_FOUND', 'ACCESS_DENIED', 'IO_FAILURE', 'CHILD_EXIT', 'CHECK_EXCEPTION'].includes(phase.error_kind));
  }
};
const immutable = value => {
  if (value && typeof value === 'object') { for (const item of Object.values(value)) immutable(item); Object.freeze(value); }
  return value;
};
function linkedDirectory(f, inside) {
  const target = path.join(f.base, 'outside', `linked-${crypto.randomUUID()}`);
  const relative = path.relative(f.profile, inside);
  assert.ok(!path.isAbsolute(relative) && relative !== '..' && !relative.startsWith(`..${path.sep}`));
  assert.equal(path.dirname(path.dirname(target)), f.base);
  fs.renameSync(inside, target);
  fs.symlinkSync(target, inside, process.platform === 'win32' ? 'junction' : 'dir');
  return target;
}

test('production exposes only one plugin and emits a source-bound native PID load receipt', async t => {
  const f = fixture(t);
  const exports = await import(pathToFileURL(f.settings.pluginPath));
  assert.deepEqual(Object.keys(exports), ['CaeLabNativeGuard']);
  const hooks = await exports.CaeLabNativeGuard({ client: {} });
  assert.deepEqual(Object.keys(hooks), ['chat.params', 'tool.execute.before']);
  const receipt = f.receipts()[0];
  assert.equal(receipt.hook, 'plugin.loaded'); assert.equal(receipt.pid, process.pid);
  assert.equal(receipt.accepted, true); assert.equal(receipt.boot_source_sha256, f.settings.boot_source_sha256);
  assert.equal(receipt.tool, null); assert.equal(receipt.session_id, null);
  assert.equal(Object.hasOwn(receipt, 'offered_tools'), false);
});

test('logical streams accept exact models and either public agent shape without changing input or output', async t => {
  const f = fixture(t), hooks = await f.hooks();
  const output = immutable({ options: { reasoningEffort: 'low', prompt: 'PRIVATE SYNTHETIC PROMPT' }, temperature: 0.6 });
  for (const agent of ['research', { name: 'caelab-acceptance' }]) {
    const request = immutable({ ...input(), agent, message: { text: 'PRIVATE SYNTHETIC MESSAGE' } });
    const before = JSON.stringify({ request, output });
    await hooks['chat.params'](request, output);
    assert.equal(JSON.stringify({ request, output }), before);
  }
  assert.equal(f.counts.capture, 3);
  assert.equal(f.receipts().filter(item => item.hook === 'chat.params' && item.accepted).length, 2);
  assert.equal(JSON.stringify(f.receipts()).includes('PRIVATE SYNTHETIC'), false);
});

test('required actual tool is allowed with unchanged nested arguments', async t => {
  const f = fixture(t), hooks = await f.hooks();
  f.writeGuard({ required: tools[5] });
  const request = immutable({ tool: tools[5], sessionID: 'ses_synthetic-01', callID: 'ignored-call', prompt: 'PRIVATE' });
  const output = immutable({ args: { study_id: 'synthetic', values: { width: 38 }, secrets: 'NEVER RETAIN THIS ARGUMENT' } });
  const before = JSON.stringify({ request, output });
  await hooks['tool.execute.before'](request, output);
  assert.equal(JSON.stringify({ request, output }), before);
  assert.equal(f.receipts().at(-1).tool, tools[5]);
  assert.equal(JSON.stringify(f.receipts()).includes('NEVER RETAIN'), false);
});

test('no-tools interpretation may stream but actual tool execution is rejected', async t => {
  const f = fixture(t), hooks = await f.hooks();
  f.writeGuard({ no_tools: true });
  await hooks['chat.params'](input(), immutable({}));
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, { args: {} }), refusal('NO_TOOLS_STAGE'));
  assert.equal(f.receipts().at(-1).accepted, false);
});

test('provider and model drift reject a logical stream', async t => {
  const f = fixture(t), hooks = await f.hooks();
  for (const model of [undefined, { providerID: 'openai', id: 'test-explicit-model' },
    { providerID: 'openai-codex', id: 'other-model' }, { providerID: 'openai-codex', id: 'openai-codex/test-explicit-model' }]) {
    await assert.rejects(hooks['chat.params']({ ...input(), model }, {}), refusal('MODEL_CHANGED'));
  }
  assert.equal(f.receipts().filter(item => item.status === 'rejected').length, 4);
});

test('unexpected agents cannot stream', async t => {
  const f = fixture(t), hooks = await f.hooks();
  for (const agent of ['title', 'general', { name: 'unknown' }, null])
    await assert.rejects(hooks['chat.params']({ ...input(), agent }, {}), refusal('AGENT_NOT_ALLOWED'));
});

test('actual tools obey the selected subset and exact required stage', async t => {
  const f = fixture(t, tools.slice(0, 2)), hooks = await f.hooks();
  await hooks['tool.execute.before']({ tool: tools[0] }, { args: {} });
  for (const tool of ['shell', tools[5], null])
    await assert.rejects(hooks['tool.execute.before']({ tool }, { args: {} }), refusal('TOOL_NOT_ALLOWED'));
  f.writeGuard({ required: tools[0] });
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[1] }, { args: {} }), refusal('REQUIRED_TOOL_MISMATCH'));
});

test('stopping blocks both hooks without further source capture', async t => {
  const f = fixture(t), hooks = await f.hooks(), before = f.counts.capture;
  f.writeGuard({ stopping: true });
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('RUNTIME_STOPPING'));
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('RUNTIME_STOPPING'));
  assert.equal(f.counts.capture, before);
});

test('source and Git executable drift fail before actual tool execution', async t => {
  const f = fixture(t), hooks = await f.hooks();
  json(f.statePath, { ...f.boot, source_commit: 'c'.repeat(40) });
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
  json(f.statePath, f.boot);
  const count = f.counts.capture;
  fs.appendFileSync(f.boot.git_path, 'CHANGED');
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('GIT_EXECUTABLE_CHANGED'));
  assert.equal(f.counts.capture, count);
  assert.equal(f.receipts().at(-1).boot_source_sha256, null);
});

test('guard denials preserve detailed codes without official provider retry signals', () => {
  assert.equal(officialStatuslessRetry(new Error('CAE native guard refused: SOURCE_CHANGED_OR_UNAVAILABLE')),
    'Provider is overloaded');
  for (const code of ['SOURCE_CHANGED_OR_UNAVAILABLE', 'PATH_UNAVAILABLE', 'FILE_UNAVAILABLE',
    'RECEIPT_UNAVAILABLE', 'CONFIG_CHANGED', 'TOOL_NOT_ALLOWED', 'RUNTIME_STOPPING']) {
    const error = new NativeGuardRefusal(code);
    assert.equal(error.name, 'CaeLabNativeGuardRefusal');
    assert.equal(error.code, code);
    assert.equal(error.message, 'CAE native guard denied this operation.');
    assert.equal(officialStatuslessRetry(error), undefined);
    assert.doesNotMatch(error.toString(), /unavailable|overloaded|rate[ _-]?limit|temporar/i);
  }
});

test('capture failure and exact pin mismatch have distinct bounded source receipts', async t => {
  const f = fixture(t), capture = f.dependencies.capture;
  let failCapture = false, comparisons = 0;
  f.dependencies.capture = (...args) => {
    if (failCapture) throw Object.assign(new Error('SECRET SOURCE CAPTURE SENTINEL'), {
      code: 'ETIMEDOUT', stdout: 'SECRET STDOUT SENTINEL', stderr: 'SECRET STDERR SENTINEL',
      path: 'SECRET PATH SENTINEL', env: { TOKEN: 'SECRET ENV SENTINEL' },
    });
    return capture(...args);
  };
  const assertPin = f.dependencies.assertPin;
  f.dependencies.assertPin = (...args) => { comparisons++; return assertPin(...args); };
  const hooks = await f.hooks();
  failCapture = true;
  await assert.rejects(hooks['chat.params'](input(), {}), error => {
    assert.equal(officialStatuslessRetry(error), undefined);
    return refusal('SOURCE_CHANGED_OR_UNAVAILABLE')(error);
  });
  assert.equal(comparisons, 1);
  const captureReceipt = f.receipts().at(-1);
  assert.equal(captureReceipt.accepted, false);
  assert.equal(captureReceipt.code, 'SOURCE_CHANGED_OR_UNAVAILABLE');
  assert.equal(captureReceipt.boot_source_sha256, null);
  assert.equal(captureReceipt.source_check.capture.status, 'FAIL');
  assert.equal(captureReceipt.source_check.capture.error_kind, 'TIMEOUT');
  assert.equal(captureReceipt.source_check.compare.status, 'NOT_RUN');
  boundedSourceCheck(captureReceipt.source_check);
  failCapture = false;
  json(f.statePath, { ...f.boot, source_commit: 'c'.repeat(40), source_dirty: ['SECRET PIN COMPARISON SENTINEL'] });
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
  assert.equal(comparisons, 2);
  const mismatchReceipt = f.receipts().at(-1);
  assert.equal(mismatchReceipt.accepted, false);
  assert.equal(mismatchReceipt.code, 'SOURCE_CHANGED_OR_UNAVAILABLE');
  assert.equal(mismatchReceipt.boot_source_sha256, null);
  assert.equal(mismatchReceipt.source_check.capture.status, 'PASS');
  assert.equal(mismatchReceipt.source_check.compare.status, 'FAIL');
  assert.equal(mismatchReceipt.source_check.compare.error_kind, 'CHECK_EXCEPTION');
  boundedSourceCheck(mismatchReceipt.source_check);
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
  assert.equal(JSON.stringify(f.receipts()).includes(f.base), false);
  json(f.statePath, f.boot);
  await hooks['chat.params'](input(), {});
  const accepted = f.receipts().at(-1);
  assert.equal(accepted.accepted, true);
  assert.equal(accepted.boot_source_sha256, f.settings.boot_source_sha256);
  assert.deepEqual([accepted.source_check.capture.status, accepted.source_check.compare.status], ['PASS', 'PASS']);
  boundedSourceCheck(accepted.source_check);
  assert.equal(comparisons, 3);
});

test('probe errors use fixed classifications without reading raw fields or getters', async t => {
  const f = fixture(t), capture = f.dependencies.capture;
  let failure;
  f.dependencies.capture = (...args) => { if (failure) throw failure; return capture(...args); };
  const hooks = await f.hooks();
  const cases = [
    ['ETIMEDOUT', 'TIMEOUT'], ['ENOBUFS', 'OUTPUT_LIMIT'], ['ENOENT', 'NOT_FOUND'],
    ['EACCES', 'ACCESS_DENIED'], ['EPERM', 'ACCESS_DENIED'], ['EIO', 'IO_FAILURE'],
    ['SECRET ERROR CODE SENTINEL', 'CHECK_EXCEPTION'],
  ].map(([code, expected]) => ({ error: Object.assign(new Error('SECRET PROBE ERROR SENTINEL'), {
    code, stdout: 'SECRET STDOUT SENTINEL', stderr: 'SECRET STDERR SENTINEL',
  }), expected }));
  cases.push({ error: Object.assign(new Error('SECRET CHILD EXIT SENTINEL'), { status: 128 }), expected: 'CHILD_EXIT' });
  let getterReads = 0;
  const hostile = new Error('SECRET HOSTILE SENTINEL');
  for (const key of ['code', 'status', 'message', 'stdout', 'stderr', 'path', 'env'])
    Object.defineProperty(hostile, key, { get() { getterReads++; throw new Error('SECRET GETTER SENTINEL'); } });
  cases.push({ error: hostile, expected: 'CHECK_EXCEPTION' });
  cases.push({ error: new Proxy({}, { getOwnPropertyDescriptor() { throw new Error('SECRET PROXY SENTINEL'); } }),
    expected: 'CHECK_EXCEPTION' });
  for (const item of cases) {
    failure = item.error;
    await assert.rejects(hooks['chat.params'](input(), {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
    const receipt = f.receipts().at(-1);
    assert.equal(receipt.accepted, false);
    assert.equal(receipt.source_check.capture.error_kind, item.expected);
    assert.equal(receipt.source_check.compare.status, 'NOT_RUN');
    boundedSourceCheck(receipt.source_check);
    assert.ok(Buffer.byteLength(JSON.stringify(receipt)) < 2048);
  }
  assert.equal(getterReads, 0);
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
});

test('failed initial source capture retains a sanitized load refusal and yields no hooks', async t => {
  const f = fixture(t);
  f.dependencies.capture = () => { throw Object.assign(new Error('SECRET INITIAL CAPTURE SENTINEL'), {
    code: 'ETIMEDOUT', stdout: 'SECRET INITIAL STDOUT SENTINEL', stderr: 'SECRET INITIAL STDERR SENTINEL',
  }); };
  await assert.rejects(f.hooks, error => {
    assert.equal(officialStatuslessRetry(error), undefined);
    return refusal('SOURCE_CHANGED_OR_UNAVAILABLE')(error);
  });
  const receipts = f.receipts();
  assert.equal(receipts.length, 1);
  assert.equal(receipts[0].hook, 'plugin.loaded');
  assert.equal(receipts[0].accepted, false);
  assert.equal(receipts[0].code, 'SOURCE_CHANGED_OR_UNAVAILABLE');
  assert.equal(receipts[0].boot_source_sha256, null);
  assert.equal(receipts[0].source_check.capture.status, 'FAIL');
  assert.equal(receipts[0].source_check.compare.status, 'NOT_RUN');
  boundedSourceCheck(receipts[0].source_check);
  assert.equal(JSON.stringify(receipts).includes('SECRET'), false);
});

test('comparison exceptions refuse a matching captured pin instead of accepting boot cache', async t => {
  const f = fixture(t), assertPin = f.dependencies.assertPin;
  let failCompare = false;
  f.dependencies.assertPin = (...args) => {
    if (failCompare) throw new Error('SECRET COMPARISON SENTINEL');
    return assertPin(...args);
  };
  const hooks = await f.hooks();
  failCompare = true;
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
  assert.equal(f.counts.capture, 2);
  const receipt = f.receipts().at(-1);
  assert.equal(receipt.accepted, false);
  assert.equal(receipt.boot_source_sha256, null);
  assert.deepEqual([receipt.source_check.capture.status, receipt.source_check.compare.status], ['PASS', 'FAIL']);
  boundedSourceCheck(receipt.source_check);
  assert.equal(JSON.stringify(receipt).includes('SECRET'), false);
});

for (const [field, code] of [['configPath', 'CONFIG_CHANGED'], ['pluginPath', 'PLUGIN_CHANGED'], ['settingsPath', 'SETTINGS_CHANGED']]) {
  test(`${field} byte changes fail even when JSON meaning is unchanged`, async t => {
    const f = fixture(t), hooks = await f.hooks();
    fs.appendFileSync(field === 'settingsPath' ? f.settingsPath : f.settings[field], '\n');
    await assert.rejects(hooks['chat.params'](input(), {}), refusal(code));
    assert.equal(f.receipts().at(-1).code, code);
  });
}

test('settings schema, model, tools, boot hash and confined paths are mandatory', async t => {
  const f = fixture(t);
  for (const patch of [
    { schema: 2 }, { kind: 'other' }, { extra: true }, { model: 'ollama/arbitrary' },
    { allowed: [] }, { allowed: [tools[0], tools[0]] }, { allowed: [tools[0], 'shell'] },
    { boot_source_sha256: 'f'.repeat(64) }, { configPath: path.join(f.base, 'outside', 'config.json') },
    { guardPath: null }, { pluginPath: 42 },
    { boot_source: { ...f.boot, repo_root: f.profile } },
  ]) {
    const value = { ...f.settings, ...patch };
    json(f.settingsPath, value);
    await assert.rejects(() => createNativeHooks(value, f.dependencies), error => error.name === 'CaeLabNativeGuardRefusal');
  }
  assert.equal(f.counts.capture, 0);
});

test('guard ownership, schema, exact ordered allowed list and state are revalidated', async t => {
  const f = fixture(t), hooks = await f.hooks();
  for (const patch of [
    { schema: 2 }, { kind: 'other' }, { run_name: 'foreign' }, { repo_root: f.profile },
    { profile_root: f.repo }, { model: 'openai-codex/other' }, { allowed: [...tools].reverse() },
    { allowed: [...tools, 'shell'] }, { allowed: [tools[0], tools[0]] }, { required: 'shell' },
    { no_tools: true, required: tools[0] }, { no_tools: 'false' }, { stopping: null },
    { updated_utc: 'unknown' }, { extra: true },
  ]) {
    f.writeGuard(patch);
    await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('GUARD_INVALID'));
  }
});

test('configuration and plugin ancestor links are rejected before reading linked targets', async t => {
  const f = fixture(t), hooks = await f.hooks();
  const outside = linkedDirectory(f, path.dirname(f.settings.configPath));
  const before = fs.readdirSync(outside);
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('PATH_LINKED'));
  assert.deepEqual(fs.readdirSync(outside), before);
  const g = fixture(t);
  linkedDirectory(g, path.dirname(g.settings.pluginPath));
  await assert.rejects(g.hooks, refusal('PATH_LINKED'));
  assert.equal(g.counts.capture, 0);
});

test('linked repository and Git executable ancestors fail closed', async t => {
  const f = fixture(t), hooks = await f.hooks();
  const target = path.join(f.base, 'outside', 'repo');
  assert.equal(path.dirname(target), path.join(f.base, 'outside'));
  fs.renameSync(f.repo, target);
  fs.symlinkSync(target, f.repo, process.platform === 'win32' ? 'junction' : 'dir');
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('PATH_LINKED'));
  const g = fixture(t), otherHooks = await g.hooks();
  const bin = path.join(g.base, 'bin'), otherBin = path.join(g.base, 'outside', 'bin');
  fs.renameSync(bin, otherBin);
  fs.symlinkSync(otherBin, bin, process.platform === 'win32' ? 'junction' : 'dir');
  await assert.rejects(otherHooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('PATH_LINKED'));
});

test('linked receipt destination cannot receive an outside file or permit a stream', async t => {
  const f = fixture(t), hooks = await f.hooks();
  const target = linkedDirectory(f, f.settings.receipts), before = fs.readdirSync(target);
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('RECEIPT_UNAVAILABLE'));
  assert.deepEqual(fs.readdirSync(target), before);
});

test('malformed guard and oversized files remain rejection evidence', async t => {
  const f = fixture(t), hooks = await f.hooks();
  fs.writeFileSync(f.settings.guardPath, 'NOT JSON');
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('GUARD_INVALID'));
  fs.writeFileSync(f.settings.guardPath, Buffer.alloc(128 * 1024 + 1, 32));
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('FILE_SIZE_INVALID'));
  assert.deepEqual(f.receipts().slice(-2).map(item => item.accepted), [false, false]);
});

test('receipt storage failure blocks the operation without exposing raw errors', async t => {
  const f = fixture(t);
  let fail = false;
  const io = new Proxy(fs, { get(target, key) {
    if (key === 'writeFileSync') return (...args) => {
      if (fail && typeof args[0] === 'number') throw new Error('PRIVATE SYNTHETIC ERROR');
      return target.writeFileSync(...args);
    };
    return target[key];
  } });
  const hooks = await createNativeHooks(f.settings, { ...f.dependencies, fs: io });
  fail = true;
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('RECEIPT_UNAVAILABLE'));
});

test('receipt metadata rejects arbitrary session strings and never records message or arguments', async t => {
  const f = fixture(t), hooks = await f.hooks();
  await hooks['chat.params']({ ...input(), sessionID: 'SECRET SESSION\nWITH PROMPT', message: 'SECRET INPUT' }, { prompt: 'SECRET OUTPUT' });
  const receipt = f.receipts().at(-1);
  assert.equal(receipt.session_id, null);
  assert.equal(JSON.stringify(receipt).includes('SECRET'), false);
  assert.ok(Buffer.byteLength(JSON.stringify(receipt)) < 2048);
  assert.equal(Object.hasOwn(receipt, 'http_request_verified'), false);
});

test('schema2 public plugin startup binds managed identity without session or HTTP reads', async t => {
  const f = managedFixture(t);
  const exports = await import(pathToFileURL(f.settings.pluginPath));
  assert.deepEqual(Object.keys(exports), ['CaeLabNativeGuard']);
  const hooks = await exports.CaeLabNativeGuard(f.pluginInput);
  assert.deepEqual(Object.keys(hooks), ['chat.params', 'tool.execute.before']);
  assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
  const receipt = f.receipts()[0];
  assert.equal(receipt.accepted, true);
  assert.deepEqual(receipt.project_check, { identity: 'PASS', session: 'NOT_RUN', filesystem: 'NOT_RUN' });
  assert.equal(receipt.session_id, null);
});

test('managed hooks verify exact session and project grant while allowing isolated GUI workspace', async t => {
  const f = managedFixture(t), hooks = await f.hooks();
  f.state.filesystem.workspace.directory = 'SECRET ISOLATED WORKSPACE SENTINEL';
  const request = immutable(f.request()), output = immutable({ args: { private: 'SECRET ARGUMENT SENTINEL' } });
  const before = JSON.stringify({ request, output });
  await hooks['chat.params'](request, output);
  await hooks['tool.execute.before']({ tool: tools[0], sessionID: f.sessionID }, output);
  assert.equal(JSON.stringify({ request, output }), before);
  assert.equal(f.counts.capture, 3); assert.equal(f.counts.session, 2); assert.equal(f.counts.filesystem, 2);
  for (const receipt of f.receipts().slice(1)) {
    assert.equal(receipt.accepted, true); assert.equal(receipt.session_id, f.sessionID);
    assert.deepEqual(receipt.project_check, { identity: 'PASS', session: 'PASS', filesystem: 'PASS' });
    assert.equal(receipt.guard_sha256, sha(fs.readFileSync(f.settings.guardPath)));
  }
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
  assert.equal(JSON.stringify(f.receipts()).includes(f.base), false);
});

test('managed binding schema and exact immutable source fields fail closed', async t => {
  const f = managedFixture(t), original = structuredClone(f.binding);
  for (const patch of [{ schema: 2 }, { kind: 'foreign' }, { project_id: 'foreign' }, { grant_id: 'foreign' },
    { source_directory: f.profile }, { working_root: f.profile }, { access: 'read' }, { extra: true },
    { project_directory: '.' }]) {
    f.settings.project_binding = { ...original, ...patch };
    json(f.settingsPath, f.settings);
    await assert.rejects(f.hooks, error => error.name === 'CaeLabNativeGuardRefusal' && officialStatuslessRetry(error) === undefined);
  }
  f.settings.project_binding = original;
  f.settings.schema = 1;
  json(f.settingsPath, f.settings);
  await assert.rejects(f.hooks, refusal('SETTINGS_INVALID'));
  f.settings.schema = 2;
  delete f.settings.project_binding;
  json(f.settingsPath, f.settings);
  await assert.rejects(f.hooks, refusal('SETTINGS_INVALID'));
  assert.equal(f.counts.capture, 0); assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
});

test('official v4 UUID grant IDs admit only the exact bound project grant', async t => {
  // Exact official 4082 filesystem.ts:402-408 generator: fsg_${crypto.randomUUID()}.
  const observed = 'fsg_7af276cb-370a-468e-9c54-39ba96612dfd';
  for (const grantID of [observed, observed.toUpperCase().replace('FSG_', 'fsg_')]) {
    const f = managedFixture(t);
    f.binding.grant_id = grantID;
    f.state.filesystem.grants[0].id = grantID;
    f.state.filesystem.grants[0].source = 'api';
    json(f.settingsPath, f.settings);
    const hooks = await f.hooks();
    for (const hook of ['chat.params', 'tool.execute.before'])
      await hooks[hook]({ ...f.request(), tool: tools[0] }, {});
    assert.equal(f.counts.capture, 3);
    assert.ok(f.receipts().every(receipt => receipt.accepted));
    f.state.filesystem.grants[0].id = 'fsg_5af276cb-370a-468e-9c54-39ba96612dfd';
    for (const hook of ['chat.params', 'tool.execute.before']) {
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0] }, {}), refusal('PROJECT_GRANT_CHANGED'));
      assert.equal(f.receipts().at(-1).project_check.filesystem, 'FAIL');
    }
    assert.equal(f.counts.capture, 3);
  }
});

test('malformed or non-v4 grant IDs are refused before metadata or source capture', async t => {
  const f = managedFixture(t), observed = 'fsg_7af276cb-370a-468e-9c54-39ba96612dfd';
  for (const grantID of [null, '', 'fsg_', 'foreign', 'fsg_fixture-01', `fsg_${'a'.repeat(125)}`,
    observed.replace('7af276cb', '7gf276cb'), observed.replace('-370a-', '-370-'),
    observed.replace('-468e-', '-368e-'), observed.replace('-9c54-', '-7c54-'),
    observed.replaceAll('-', '_'), `${observed}-extra`, `${observed}\n`, 'fsg_fixture01\n']) {
    f.binding.grant_id = grantID;
    json(f.settingsPath, f.settings);
    await assert.rejects(f.hooks, refusal('PROJECT_BINDING_INVALID'));
  }
  assert.equal(f.counts.capture, 0); assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
});

test('foreign initial project identity, client shape and non-loopback server are refused before capture', async t => {
  const patches = [
    [f => { f.pluginInput.project.id = 'prj_foreign01'; }, 'PROJECT_INPUT_CHANGED'],
    [f => { f.pluginInput.directory = f.repo; }, 'PROJECT_INPUT_CHANGED'],
    [f => { f.pluginInput.worktree = f.repo; }, 'PROJECT_INPUT_CHANGED'],
    [f => { f.pluginInput.project.worktree = f.repo; }, 'PROJECT_INPUT_CHANGED'],
    [f => { f.pluginInput.client = {}; }, 'PROJECT_CLIENT_INVALID'],
    [f => { f.pluginInput.client.session.get = null; }, 'PROJECT_CLIENT_INVALID'],
    [f => { f.pluginInput.serverUrl = 'https://127.0.0.1:4098/'; }, 'PROJECT_SERVER_INVALID'],
    [f => { f.pluginInput.serverUrl = 'http://127.0.0.1.example:4098/'; }, 'PROJECT_SERVER_INVALID'],
    [f => { f.pluginInput.serverUrl = 'http://SECRET:SECRET@127.0.0.1:4098/'; }, 'PROJECT_SERVER_INVALID'],
    [f => { f.pluginInput.serverUrl = 'http://127.0.0.1:4098/SECRET'; }, 'PROJECT_SERVER_INVALID'],
  ];
  for (const [patch, code] of patches) {
    const f = managedFixture(t);
    patch(f);
    await assert.rejects(f.hooks, refusal(code));
    assert.equal(f.counts.capture, 0); assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
    const receipt = f.receipts().at(-1);
    assert.equal(receipt.accepted, false); assert.equal(receipt.project_check.identity, 'FAIL');
    assert.equal(JSON.stringify(receipt).includes('SECRET'), false);
  }
});

test('managed session IDs use the official strict prefix and never reach APIs when malformed', async t => {
  const f = managedFixture(t), hooks = await f.hooks();
  for (const sessionID of [undefined, null, 'ses_', 'ses_SECRET VALUE', 'ses_synthetic-01', 'foreign', `ses_${'x'.repeat(125)}`]) {
    for (const hook of ['chat.params', 'tool.execute.before']) {
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0], sessionID }, {}), refusal('PROJECT_SESSION_ID_INVALID'));
      const receipt = f.receipts().at(-1);
      assert.equal(receipt.session_id, null); assert.equal(receipt.source_check, null);
      assert.deepEqual(receipt.project_check, { identity: 'PASS', session: 'NOT_RUN', filesystem: 'NOT_RUN' });
    }
  }
  assert.equal(f.counts.capture, 1); assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
});

test('SDK session ownership and error responses block both hooks before filesystem or source', async t => {
  const f = managedFixture(t), hooks = await f.hooks(), original = structuredClone(f.state.session);
  const cases = [
    [{ ...original, id: 'ses_foreign01' }, 'PROJECT_SESSION_CHANGED'],
    [{ ...original, projectID: 'prj_foreign01' }, 'PROJECT_SESSION_CHANGED'],
    [{ ...original, directory: f.repo }, 'PROJECT_SESSION_CHANGED'],
    [{ ...original, directory: 'SECRET DIRECTORY SENTINEL' }, 'PROJECT_SESSION_CHANGED'],
    [null, 'PROJECT_SESSION_READ_FAILED'],
  ];
  for (const [session, code] of cases) {
    f.state.session = session;
    for (const hook of ['chat.params', 'tool.execute.before'])
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0] }, {}), refusal(code));
  }
  f.state.session = original;
  f.state.sessionEnvelope = { data: original, error: { message: 'SECRET SDK HTTP ERROR SENTINEL' } };
  await assert.rejects(hooks['chat.params'](f.request(), {}), refusal('PROJECT_SESSION_READ_FAILED'));
  delete f.state.sessionEnvelope;
  f.state.sessionError = new Error('SECRET SDK HTTP ERROR unavailable SENTINEL');
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0], sessionID: f.sessionID }, {}), error => {
    assert.equal(officialStatuslessRetry(error), undefined);
    return refusal('PROJECT_SESSION_READ_FAILED')(error);
  });
  assert.equal(f.counts.filesystem, 0); assert.equal(f.counts.capture, 1);
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
});

test('a foreign bound client cannot substitute another managed project session', async t => {
  const f = managedFixture(t), foreign = managedFixture(t);
  f.pluginInput.client = foreign.pluginInput.client;
  const hooks = await f.hooks();
  await assert.rejects(hooks['chat.params'](f.request(), {}), refusal('PROJECT_SESSION_CHANGED'));
  assert.equal(foreign.counts.session, 1);
  assert.equal(f.counts.filesystem, 0); assert.equal(f.counts.capture, 1);
});

test('filesystem session, identity and working roots are checked before either hook captures source', async t => {
  const f = managedFixture(t), hooks = await f.hooks(), original = structuredClone(f.state.filesystem);
  for (const patch of [{ version: 2 }, { sessionID: 'ses_foreign01' }, { projectID: 'prj_foreign01' },
    { directory: f.repo }, { toolDirectory: f.identity }, { workingRoot: f.profile },
    { workingRoot: undefined }, { grants: null }]) {
    f.state.filesystem = { ...original, ...patch };
    for (const hook of ['chat.params', 'tool.execute.before']) {
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0] }, {}), refusal('PROJECT_FILESYSTEM_CHANGED'));
      assert.equal(f.receipts().at(-1).source_check, null);
      assert.deepEqual(f.receipts().at(-1).project_check, { identity: 'PASS', session: 'PASS', filesystem: 'FAIL' });
    }
  }
  assert.equal(f.counts.capture, 1);
});

test('matching write grant must be unique, project-scoped and active', async t => {
  const f = managedFixture(t), hooks = await f.hooks(), original = structuredClone(f.state.filesystem.grants[0]);
  const grants = [[], [{ ...original, id: 'fsg_foreign01' }], [{ ...original, path: f.profile }],
    [{ ...original, access: 'read' }], [{ ...original, scope: 'session' }],
    [{ ...original, time: { created: 1, revoked: 0 } }], [{ ...original, time: { created: 1, revoked: null } }],
    [{ ...original, time: null }], [{ ...original, time: { created: NaN } }], [original, structuredClone(original)]];
  for (const value of grants) {
    f.state.filesystem.grants = value;
    for (const hook of ['chat.params', 'tool.execute.before'])
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0] }, {}), refusal('PROJECT_GRANT_CHANGED'));
  }
  assert.equal(f.counts.capture, 1);
});

test('production filesystem read uses exact Instance headers, bounded signal and redirect refusal', async t => {
  const f = managedFixture(t);
  delete f.dependencies.loadFilesystem;
  f.dependencies.fetch = async (url, options) => {
    f.counts.filesystem++;
    assert.equal(url, `http://127.0.0.1:4098/session/${f.sessionID}/filesystem`);
    assert.equal(options.method, 'GET'); assert.equal(options.redirect, 'error');
    assert.ok(options.signal instanceof AbortSignal);
    assert.deepEqual(options.headers, { 'x-openscience-project': f.binding.project_id,
      'x-openscience-directory': f.identity });
    assert.equal(Object.hasOwn(options, 'body'), false);
    return new Response(JSON.stringify(f.state.filesystem), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  const hooks = await f.hooks();
  assert.equal(f.counts.filesystem, 0);
  await hooks['tool.execute.before']({ tool: tools[0], sessionID: f.sessionID }, {});
  assert.equal(f.counts.filesystem, 1); assert.equal(f.counts.capture, 2);
  assert.equal(f.receipts().at(-1).accepted, true);
});

test('HTTP errors, redirects, malformed JSON and bounded body failures retain fixed refusals only', async t => {
  const f = managedFixture(t);
  delete f.dependencies.loadFilesystem;
  let respond;
  f.dependencies.fetch = async () => respond();
  const hooks = await f.hooks();
  const redirected = () => {
    const response = new Response(JSON.stringify(f.state.filesystem));
    Object.defineProperty(response, 'redirected', { value: true });
    return response;
  };
  for (const response of [
    () => { throw Object.assign(new Error('SECRET HTTP ERROR unavailable SENTINEL'), { stdout: 'SECRET OUTPUT SENTINEL' }); },
    () => new Response('SECRET SERVER ERROR SENTINEL', { status: 500 }),
    () => new Response('SECRET REDIRECT SENTINEL', { status: 302 }), redirected,
    () => new Response('SECRET MALFORMED JSON SENTINEL'),
    () => new Response(' '.repeat(128 * 1024 + 1)),
    () => new Response('{}', { headers: { 'content-length': String(128 * 1024 + 1) } }),
    () => new Response('{}', { headers: { 'content-length': 'SECRET' } }),
    () => new Response(null),
  ]) {
    respond = response;
    for (const hook of ['chat.params', 'tool.execute.before']) {
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0] }, {}), error => {
        assert.equal(officialStatuslessRetry(error), undefined);
        return refusal('PROJECT_FILESYSTEM_READ_FAILED')(error);
      });
      const receipt = f.receipts().at(-1);
      assert.equal(receipt.accepted, false); assert.equal(receipt.source_check, null);
    }
  }
  assert.equal(f.counts.capture, 1);
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
  assert.equal(JSON.stringify(f.receipts()).includes(f.base), false);
});

test('managed public input and client drift are rejected before later metadata reads', async t => {
  for (const [patch, code] of [
    [f => { f.pluginInput.project.id = 'prj_foreign01'; }, 'PROJECT_INPUT_CHANGED'],
    [f => { f.pluginInput.directory = f.repo; }, 'PROJECT_INPUT_CHANGED'],
    [f => { f.pluginInput.client = { session: { get: async () => ({}) } }; }, 'PROJECT_CLIENT_CHANGED'],
    [f => { f.pluginInput.client.session.get = async () => ({}); }, 'PROJECT_CLIENT_CHANGED'],
    [f => { f.pluginInput.serverUrl = new URL('http://127.0.0.1:4099/'); }, 'PROJECT_SERVER_CHANGED'],
  ]) {
    const f = managedFixture(t), hooks = await f.hooks();
    patch(f);
    await assert.rejects(hooks['chat.params'](f.request(), {}), refusal(code));
    assert.equal(f.counts.capture, 1); assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
  }
});

test('metadata await cannot admit configuration, stage, stopping or public identity drift', async t => {
  for (const [patch, code] of [
    [f => fs.appendFileSync(f.settings.configPath, '\n'), 'CONFIG_CHANGED'],
    [f => fs.appendFileSync(f.settingsPath, '\n'), 'SETTINGS_CHANGED'],
    [f => f.writeGuard({ required: tools[1] }), 'GUARD_CHANGED_DURING_CHECK'],
    [f => f.writeGuard({ stopping: true }), 'RUNTIME_STOPPING'],
    [f => { f.pluginInput.project.id = 'prj_foreign01'; }, 'PROJECT_INPUT_CHANGED'],
  ]) {
    const f = managedFixture(t), load = f.dependencies.loadFilesystem;
    f.dependencies.loadFilesystem = async (...args) => {
      const data = await load(...args);
      patch(f);
      return data;
    };
    const hooks = await f.hooks();
    await assert.rejects(hooks['tool.execute.before']({ tool: tools[0], sessionID: f.sessionID }, {}), refusal(code));
    assert.equal(f.counts.capture, 1); assert.equal(f.receipts().at(-1).accepted, false);
  }
});

test('managed hook session identity cannot change during metadata reads or source capture', async t => {
  for (const hook of ['chat.params', 'tool.execute.before']) {
    for (const phase of ['metadata', 'capture']) {
      const f = managedFixture(t), request = { ...f.request(), tool: tools[0] };
      let active = false;
      if (phase === 'metadata') {
        const load = f.dependencies.loadFilesystem;
        f.dependencies.loadFilesystem = async (...args) => {
          const data = await load(...args);
          request.sessionID = 'ses_foreign01';
          return data;
        };
      } else {
        const capture = f.dependencies.capture;
        f.dependencies.capture = (...args) => {
          const current = capture(...args);
          if (active) request.sessionID = 'ses_foreign01';
          return current;
        };
      }
      const hooks = await f.hooks(); active = true;
      await assert.rejects(hooks[hook](request, {}), refusal('PROJECT_SESSION_CHANGED'));
      assert.equal(f.counts.capture, phase === 'metadata' ? 1 : 2);
      const receipt = f.receipts().at(-1);
      assert.equal(receipt.accepted, false); assert.equal(receipt.project_check.session, 'FAIL');
      assert.equal(receipt.session_id, f.sessionID);
    }
  }
});

test('late stopping, required-tool and no-tools policies after source capture use the last guard hash', async t => {
  for (const [patch, code] of [[{ stopping: true }, 'RUNTIME_STOPPING'], [{ required: tools[1] }, 'REQUIRED_TOOL_MISMATCH'],
    [{ no_tools: true }, 'NO_TOOLS_STAGE'], [{ updated_utc: '2026-10-01T00:00:01.000Z' }, null]]) {
    const f = managedFixture(t), capture = f.dependencies.capture;
    let active = false;
    f.dependencies.capture = (...args) => {
      const current = capture(...args);
      if (active) f.writeGuard(patch);
      return current;
    };
    const hooks = await f.hooks();
    active = true;
    const request = hooks['tool.execute.before']({ tool: tools[0], sessionID: f.sessionID }, {});
    if (code) await assert.rejects(request, refusal(code));
    else await request;
    assert.equal(f.counts.capture, 2);
    const receipt = f.receipts().at(-1);
    assert.equal(receipt.accepted, code === null);
    assert.equal(receipt.guard_sha256, sha(fs.readFileSync(f.settings.guardPath)));
    assert.deepEqual([receipt.source_check.capture.status, receipt.source_check.compare.status], ['PASS', 'PASS']);
  }
});

test('late configuration drift and legacy stopping after source capture cannot admit an operation', async t => {
  for (const [managed, patch, code] of [
    [true, f => fs.appendFileSync(f.settings.configPath, '\n'), 'CONFIG_CHANGED'],
    [true, f => fs.appendFileSync(f.settings.pluginPath, '\n'), 'PLUGIN_CHANGED'],
    [false, f => f.writeGuard({ stopping: true }), 'RUNTIME_STOPPING'],
  ]) {
    const f = managed ? managedFixture(t) : fixture(t), capture = f.dependencies.capture;
    let active = false;
    f.dependencies.capture = (...args) => { const current = capture(...args); if (active) patch(f); return current; };
    const hooks = await f.hooks(); active = true;
    await assert.rejects(hooks['chat.params'](managed ? f.request() : input(), {}), refusal(code));
    assert.equal(f.counts.capture, 2); assert.equal(f.receipts().at(-1).accepted, false);
  }
});

test('stopping managed hooks skip every metadata read and further source capture', async t => {
  const f = managedFixture(t), hooks = await f.hooks();
  f.writeGuard({ stopping: true });
  await assert.rejects(hooks['chat.params'](f.request(), {}), refusal('RUNTIME_STOPPING'));
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0], sessionID: f.sessionID }, {}), refusal('RUNTIME_STOPPING'));
  assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0); assert.equal(f.counts.capture, 1);
});

test('a metadata getter that ignores abort is still bounded and never reaches source or tools', async t => {
  const f = managedFixture(t);
  f.dependencies.loadSession = () => new Promise(() => {});
  const keepAlive = setTimeout(() => {}, 6000);
  t.after(() => clearTimeout(keepAlive));
  const hooks = await f.hooks();
  await assert.rejects(hooks['chat.params'](f.request(), {}), refusal('PROJECT_SESSION_READ_FAILED'));
  assert.equal(f.counts.capture, 1); assert.equal(f.counts.filesystem, 0);
  assert.equal(f.receipts().at(-1).accepted, false);
});

test('schema3 invokes only the pinned Node reader with fixed arguments, limits and closed stdin', async t => {
  const f = readerFixture(t);
  let secretReads = 0;
  f.dependencies.environment = { SystemRoot: 'C:\\Windows', windir: 'C:\\Windows', COMSPEC: 'synthetic.exe',
    Path: 'SYNTHETIC OS PATH', PATHEXT: '.EXE', TEMP: 'SYNTHETIC TEMP', TMP: 'SYNTHETIC TMP' };
  for (const key of ['NODE_OPTIONS', 'NODE_PATH', 'GIT_DIR', 'OPENAI_API_KEY', 'PROVIDER_TOKEN'])
    Object.defineProperty(f.dependencies.environment, key, { enumerable: true, get() { secretReads++; throw new Error('SECRET ENV SENTINEL'); } });
  const hooks = await f.hooks();
  await hooks['chat.params'](input(), {});
  await hooks['tool.execute.before']({ tool: tools[0] }, {});
  assert.equal(f.reader.calls, 3); assert.equal(f.reader.ended, 3); assert.equal(f.reader.destroyed, 3);
  assert.equal(f.counts.capture, 0); assert.equal(secretReads, 0);
  for (const invocation of f.reader.seen) {
    assert.equal(invocation.file, f.nodePath);
    assert.deepEqual(invocation.args, [f.workerPath, f.repo, f.boot.git_path, f.settingsPath]);
    assert.equal(invocation.options.cwd, f.repo);
    assert.equal(invocation.options.timeout, 20000); assert.equal(invocation.options.maxBuffer, 16 * 1024 * 1024);
    assert.equal(invocation.options.windowsHide, true); assert.equal(invocation.options.shell, false);
    assert.equal(invocation.options.encoding, 'utf8'); assert.equal(Object.hasOwn(invocation.options, 'stdio'), false);
    assert.deepEqual(Object.keys(invocation.options.env).sort(), ['COMSPEC', 'PATH', 'PATHEXT', 'SystemRoot', 'TEMP', 'TMP', 'WINDIR'].sort());
  }
  assert.ok(f.receipts().every(receipt => receipt.accepted));
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
  assert.equal(JSON.stringify(f.receipts()).includes(f.base), false);
  assert.equal(JSON.stringify(f.receipts()).includes('git_state'), false);
  assert.equal(JSON.stringify(f.receipts()).includes('repositories'), false);
});

test('real Node reader accepts exact synthetic pins for schema3 standalone and managed public plugins', async t => {
  for (const managed of [false, true]) {
    const f = readerFixture(t, { managed, actual: true });
    const exports = await import(pathToFileURL(f.settings.pluginPath));
    assert.deepEqual(Object.keys(exports), ['CaeLabNativeGuard']);
    const hooks = await exports.CaeLabNativeGuard(f.pluginInput);
    // Use factory hooks with the same real child and mocked managed metadata.
    const tested = managed ? await f.hooks() : hooks;
    await tested['chat.params'](managed ? f.request() : input(), {});
    await tested['tool.execute.before']({ tool: tools[0], sessionID: managed ? f.sessionID : undefined }, {});
    assert.ok(f.receipts().every(receipt => receipt.accepted));
    if (managed) { assert.equal(f.counts.session, 4); assert.equal(f.counts.filesystem, 4); }
    assert.equal(f.counts.capture, 0);
  }
});

test('schema3 reader exact keys, canonical owned path and executable hashes are mandatory', async t => {
  const f = readerFixture(t), original = { ...f.settings.source_reader };
  for (const patch of [{ extra: true }, { node_path: null }, { node_path: '.' }, { node_sha256: 'bad' },
    { worker_sha256: 'bad' }, { worker_path: path.join(f.profile, 'runtime', 'source-reader.mjs') }]) {
    f.settings.source_reader = { ...original, ...patch };
    json(f.settingsPath, f.settings);
    await assert.rejects(f.hooks, error => error.name === 'CaeLabNativeGuardRefusal');
  }
  f.settings.source_reader = original;
  f.settings.extra = true; json(f.settingsPath, f.settings);
  await assert.rejects(f.hooks, refusal('SETTINGS_INVALID'));
  delete f.settings.extra; delete f.settings.source_reader; json(f.settingsPath, f.settings);
  await assert.rejects(f.hooks, refusal('SETTINGS_INVALID'));
  assert.equal(f.reader.calls, 0);
});

test('schema3 source output must contain one exact result whose pin exactly matches boot', async t => {
  const f = readerFixture(t), hooks = await f.hooks();
  for (const stdout of ['', 'SECRET INVALID OUTPUT SENTINEL', 'null', '[]', '{}\n{}', ' '.repeat(16 * 1024 * 1024 + 1)]) {
    f.reader.stdout = stdout;
    await assert.rejects(hooks['chat.params'](input(), {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
    const receipt = f.receipts().at(-1);
    assert.deepEqual([receipt.source_check.capture.status, receipt.source_check.compare.status], ['FAIL', 'NOT_RUN']);
    assert.equal(receipt.source_check.capture.error_kind, 'CHECK_EXCEPTION');
    boundedSourceCheck(receipt.source_check);
  }
  f.reader.stdout = JSON.stringify(readerResult(f, { ...f.boot, source_commit: 'c'.repeat(40) }));
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
  assert.deepEqual([f.receipts().at(-1).source_check.capture.status, f.receipts().at(-1).source_check.compare.status], ['PASS', 'FAIL']);
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
});

test('Node reader error diagnostics inspect fixed own markers without reading secrets or getters', async t => {
  const f = readerFixture(t), hooks = await f.hooks();
  let getterReads = 0;
  const hostile = new Error('SECRET HOSTILE NODE ERROR');
  for (const key of ['code', 'status', 'killed', 'signal', 'message', 'stdout', 'stderr', 'path', 'env'])
    Object.defineProperty(hostile, key, { get() { getterReads++; throw new Error('SECRET GETTER'); } });
  for (const [fields, kind] of [[{ code: 'ETIMEDOUT' }, 'TIMEOUT'], [{ code: null, killed: true, signal: 'SIGTERM' }, 'TIMEOUT'],
    [{ code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER' }, 'OUTPUT_LIMIT'], [{ code: 7 }, 'CHILD_EXIT'],
    [{ code: 'ENOENT' }, 'NOT_FOUND'], [{ code: 'SECRET RAW CODE' }, 'CHECK_EXCEPTION']]) {
    f.reader.error = Object.assign(new Error('SECRET NODE ERROR unavailable'), fields, { stdout: 'SECRET STDOUT', stderr: 'SECRET STDERR' });
    await assert.rejects(hooks['chat.params'](input(), {}), error => officialStatuslessRetry(error) === undefined && refusal('SOURCE_CHANGED_OR_UNAVAILABLE')(error));
    assert.equal(f.receipts().at(-1).source_check.capture.error_kind, kind);
  }
  f.reader.error = hostile;
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
  assert.equal(getterReads, 0);
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
});

test('changed Node, reader and linked reader files never launch the child', async t => {
  for (const field of ['nodePath', 'workerPath']) {
    const f = readerFixture(t), hooks = await f.hooks();
    fs.appendFileSync(f[field], '\nCHANGED');
    await assert.rejects(hooks['chat.params'](input(), {}), refusal(field === 'nodePath' ? 'NODE_EXECUTABLE_CHANGED' : 'SOURCE_READER_CHANGED'));
    assert.equal(f.reader.calls, 1);
  }
  const f = readerFixture(t);
  linkedDirectory(f, f.profile);
  await assert.rejects(f.hooks, refusal('PATH_LINKED'));
  assert.equal(f.reader.calls, 0);
});

test('real reader exit, malformed JSON and output overflow retain sanitized failure receipts', async t => {
  for (const [workerSource, kind] of [
    ["process.stderr.write('SECRET REAL CHILD ERROR unavailable'); process.exit(7);", 'CHILD_EXIT'],
    ["process.stdout.write('SECRET NON-JSON OUTPUT');", 'CHECK_EXCEPTION'],
    ["process.stdout.write('[]');", 'CHECK_EXCEPTION'],
    ["process.stdout.write('x'.repeat(16 * 1024 * 1024 + 1));", 'OUTPUT_LIMIT'],
  ]) {
    const f = readerFixture(t, { actual: true, workerSource });
    await assert.rejects(f.hooks, error => officialStatuslessRetry(error) === undefined && refusal('SOURCE_CHANGED_OR_UNAVAILABLE')(error));
    const receipt = f.receipts().at(-1);
    assert.equal(receipt.hook, 'plugin.loaded'); assert.equal(receipt.accepted, false);
    assert.equal(receipt.source_check.capture.error_kind, kind);
    assert.equal(receipt.source_check.compare.status, 'NOT_RUN');
    assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
    assert.equal(JSON.stringify(f.receipts()).includes(f.base), false);
  }
});

test('real reader timeout stops once within the fixed twenty-second child budget', async t => {
  const f = readerFixture(t, { actual: true, workerSource: 'setInterval(() => {}, 1000);' });
  await assert.rejects(f.hooks, refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
  const receipt = f.receipts().at(-1);
  assert.equal(receipt.accepted, false); assert.equal(receipt.source_check.capture.error_kind, 'TIMEOUT');
  assert.ok(receipt.source_check.capture.elapsed_ms >= 19000 && receipt.source_check.capture.elapsed_ms < 30000);
  assert.equal(receipt.source_check.compare.status, 'NOT_RUN');
  assert.equal(f.receipts().length, 1);
});

test('reader startup rechecks files, stopping and public identity after its asynchronous child', async t => {
  for (const [managed, patch, code] of [
    [false, f => fs.appendFileSync(f.settingsPath, '\n'), 'SETTINGS_CHANGED'],
    [false, f => fs.appendFileSync(f.settings.configPath, '\n'), 'CONFIG_CHANGED'],
    [false, f => fs.appendFileSync(f.workerPath, '\n'), 'SOURCE_READER_CHANGED'],
    [false, f => fs.appendFileSync(f.nodePath, '\n'), 'NODE_EXECUTABLE_CHANGED'],
    [false, f => f.writeGuard({ stopping: true }), 'RUNTIME_STOPPING'],
    [true, f => { f.pluginInput.project.id = 'prj_foreign01'; }, 'PROJECT_INPUT_CHANGED'],
  ]) {
    const f = readerFixture(t, { managed });
    f.reader.beforeReturn = async () => { await Promise.resolve(); patch(f); };
    await assert.rejects(f.hooks, refusal(code));
    assert.equal(f.reader.calls, 1); assert.equal(f.receipts().at(-1).accepted, false);
    if (managed) { assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0); }
  }
});

test('asynchronous capture mismatch rejects an old pin instead of retaining it as cache', async t => {
  const f = readerFixture(t), hooks = await f.hooks();
  f.reader.beforeReturn = async () => {
    await Promise.resolve();
    json(f.statePath, { ...f.boot, source_commit: 'c'.repeat(40) });
  };
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
  assert.equal(f.reader.calls, 2);
  const receipt = f.receipts().at(-1);
  assert.equal(receipt.boot_source_sha256, null);
  assert.deepEqual([receipt.source_check.capture.status, receipt.source_check.compare.status], ['PASS', 'FAIL']);
});

test('schema3 managed metadata refresh rejects grant and session root drift during capture', async t => {
  for (const hook of ['chat.params', 'tool.execute.before']) {
    for (const [patch, code] of [
      [f => { f.state.filesystem.grants[0].time.revoked = 1; }, 'PROJECT_GRANT_CHANGED'],
      [f => { f.state.filesystem.toolDirectory = f.identity; }, 'PROJECT_FILESYSTEM_CHANGED'],
      [f => { f.state.filesystem.workingRoot = f.profile; }, 'PROJECT_FILESYSTEM_CHANGED'],
      [f => { f.state.session.directory = f.repo; }, 'PROJECT_SESSION_CHANGED'],
    ]) {
      const f = readerFixture(t, { managed: true }), hooks = await f.hooks();
      f.reader.beforeReturn = async () => { await Promise.resolve(); patch(f); };
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0] }, {}), refusal(code));
      assert.equal(f.reader.calls, 2); assert.equal(f.counts.session, 2);
      assert.equal(f.receipts().at(-1).accepted, false);
    }
  }
});

test('schema3 latest stage and fixed files are checked after capture and the last metadata await', async t => {
  for (const phase of ['capture', 'metadata']) {
    for (const [patch, code] of [
      [f => f.writeGuard({ stopping: true }), 'RUNTIME_STOPPING'],
      [f => f.writeGuard({ no_tools: true }), 'NO_TOOLS_STAGE'],
      [f => f.writeGuard({ required: tools[1] }), 'REQUIRED_TOOL_MISMATCH'],
      [f => fs.appendFileSync(f.settings.configPath, '\n'), 'CONFIG_CHANGED'],
      [f => fs.appendFileSync(f.workerPath, '\n'), 'SOURCE_READER_CHANGED'],
      [f => fs.appendFileSync(f.nodePath, '\n'), 'NODE_EXECUTABLE_CHANGED'],
    ]) {
      const f = readerFixture(t, { managed: true });
      let active = false;
      if (phase === 'capture') f.reader.beforeReturn = async () => { if (active) { await Promise.resolve(); patch(f); } };
      else {
        const load = f.dependencies.loadFilesystem;
        f.dependencies.loadFilesystem = async (...args) => {
          const data = await load(...args);
          if (f.counts.filesystem === 2) { await Promise.resolve(); patch(f); }
          return data;
        };
      }
      const hooks = await f.hooks(); active = true;
      await assert.rejects(hooks['tool.execute.before']({ tool: tools[0], sessionID: f.sessionID }, {}), refusal(code));
      const receipt = f.receipts().at(-1);
      assert.equal(receipt.accepted, false);
      if (['RUNTIME_STOPPING', 'NO_TOOLS_STAGE', 'REQUIRED_TOOL_MISMATCH'].includes(code))
        assert.equal(receipt.guard_sha256, sha(fs.readFileSync(f.settings.guardPath)));
    }
  }
});

test('final byte gate rejects a tracked file change or added import after the last metadata await', async t => {
  for (const hook of ['chat.params', 'tool.execute.before']) {
    for (const changed of [true, false]) {
      const f = readerFixture(t, { managed: true }), tracked = pinFixtureFile(f, 'tracked.py');
      const load = f.dependencies.loadFilesystem;
      f.dependencies.loadFilesystem = async (...args) => {
        const data = await load(...args);
        if (f.counts.filesystem === 2) {
          await Promise.resolve();
          if (changed) fs.appendFileSync(tracked, 'CHANGED');
          else fs.writeFileSync(path.join(f.repo, 'late_added.py'), 'SECRET LATE IMPORT SENTINEL');
        }
        return data;
      };
      const hooks = await f.hooks();
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0] }, {}), refusal(changed ? 'SOURCE_BYTES_CHANGED' : 'SOURCE_IMPORTABLE_CHANGED'));
      assert.equal(f.reader.calls, 2); assert.equal(f.counts.session, 2); assert.equal(f.counts.filesystem, 2);
      const receipt = f.receipts().at(-1);
      assert.deepEqual([receipt.source_check.capture.status, receipt.source_check.compare.status, receipt.source_check.final_bytes.status], ['PASS', 'PASS', 'FAIL']);
      boundedSourceCheck(receipt.source_check);
      assert.equal(receipt.accepted, false); assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
    }
  }
});

test('final import walker preserves exact repository and submodule exclusions and cache policy', async t => {
  const f = readerFixture(t);
  pinFixtureFile(f, 'pinned.py');
  const nested = path.join(f.repo, 'nested', 'upstream');
  fs.mkdirSync(nested, { recursive: true });
  initializeFixtureGit(nested);
  f.boot.submodules.push({ path: 'nested/upstream', head: 'a'.repeat(40), index_commit: 'a'.repeat(40) });
  pinFixtureFile(f, 'nested/upstream/pinned.py');
  for (const root of [f.repo, nested]) {
    for (const ignored of ['artifacts', 'runs', '.venv', 'venv', 'node_modules', '.git', '.pytest_cache', '.mypy_cache', '.ruff_cache']) {
      const directory = path.join(root, ignored);
      fs.mkdirSync(directory, { recursive: true });
      fs.writeFileSync(path.join(directory, 'ignored.py'), 'EXEMPT SYNTHETIC IMPORT');
    }
    const cache = path.join(root, 'package', '__pycache__');
    fs.mkdirSync(cache, { recursive: true }); fs.writeFileSync(path.join(cache, 'cached.pyc'), 'EXEMPT CACHE');
  }
  const hooks = await f.hooks();
  await hooks['chat.params'](input(), {});
  assert.equal(f.receipts().at(-1).source_check.final_bytes.status, 'PASS');
  fs.writeFileSync(path.join(nested, 'package', '__pycache__', 'not_cached.py'), 'UNPINNED SOURCE');
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('SOURCE_IMPORTABLE_CHANGED'));
});

test('late importable extensions including native bindings cannot evade the final walk', async t => {
  const f = readerFixture(t), hooks = await f.hooks();
  for (const suffix of ['py', 'pyi', 'pyc', 'pyd', 'so', 'pth', 'PY']) {
    const file = path.join(f.repo, `late.${suffix}`);
    fs.writeFileSync(file, 'UNPINNED IMPORT');
    await assert.rejects(hooks['chat.params'](input(), {}), refusal('SOURCE_IMPORTABLE_CHANGED'));
    fs.unlinkSync(file);
  }
});

test('final pinned file paths cannot escape, alias or follow linked ancestors', async t => {
  for (const relative of ['../outside.py', '/outside.py', 'nested/../outside.py', 'nested\\outside.py', 'nested//outside.py', './outside.py']) {
    const f = readerFixture(t);
    f.boot.files.push({ path: relative, sha256: 'a'.repeat(64) });
    f.settings.boot_source_sha256 = sha(canonical(f.boot)); json(f.statePath, f.boot); json(f.settingsPath, f.settings);
    await assert.rejects(f.hooks, refusal('BOOT_SOURCE_INVALID'));
    assert.equal(f.reader.calls, 1); assert.equal(f.receipts().at(-1).source_check.final_bytes.status, 'FAIL');
  }
  const f = readerFixture(t);
  pinFixtureFile(f, 'source/pinned.py');
  const sourceDirectory = path.join(f.repo, 'source'), target = path.join(f.base, 'outside', 'source');
  fs.renameSync(sourceDirectory, target);
  fs.symlinkSync(target, sourceDirectory, process.platform === 'win32' ? 'junction' : 'dir');
  await assert.rejects(f.hooks, refusal('PATH_LINKED'));
});

test('final byte deadline and filesystem errors fail closed with bounded fixed diagnostics', async t => {
  const f = readerFixture(t);
  let expired = false;
  f.dependencies.monotonic = () => expired ? 20_000_000_000n : 0n;
  const io = new Proxy(fs, { get(target, property) {
    if (property === 'opendirSync') return (...args) => { expired = true; return target.opendirSync(...args); };
    return target[property];
  } });
  await assert.rejects(() => createNativeHooks(f.settings, { ...f.dependencies, fs: io }), refusal('SOURCE_BYTES_CHECK_TIMEOUT'));
  const deadlineReceipt = f.receipts().at(-1);
  assert.equal(deadlineReceipt.source_check.final_bytes.status, 'FAIL');
  assert.equal(deadlineReceipt.source_check.final_bytes.error_kind, 'TIMEOUT');
  boundedSourceCheck(deadlineReceipt.source_check);
  const g = readerFixture(t);
  const failed = new Proxy(fs, { get(target, property) {
    if (property === 'opendirSync') return () => { throw Object.assign(new Error('SECRET WALK ERROR SENTINEL'), { code: 'EIO' }); };
    return target[property];
  } });
  await assert.rejects(() => createNativeHooks(g.settings, { ...g.dependencies, fs: failed }), refusal('SOURCE_BYTES_CHECK_FAILED'));
  assert.equal(g.receipts().at(-1).source_check.final_bytes.error_kind, 'IO_FAILURE');
  assert.equal(JSON.stringify(g.receipts()).includes('SECRET'), false);
});

test('schema3 rejects bare pins and malformed result envelopes before pin comparison', async t => {
  const f = readerFixture(t), hooks = await f.hooks(), valid = readerResult(f);
  for (const result of [f.boot, { ...valid, schema: 2 }, { ...valid, kind: 'SECRET FOREIGN KIND' },
    { ...valid, extra: 'SECRET EXTRA RESULT FIELD' }, { ...valid, pin: null }, { ...valid, pin: [] },
    { ...valid, git_state: undefined }, { ...valid, git_state: null }, { ...valid, git_state: [] }]) {
    f.reader.stdout = JSON.stringify(result);
    await assert.rejects(hooks['chat.params'](input(), {}), refusal('SOURCE_CHANGED_OR_UNAVAILABLE'));
    const receipt = f.receipts().at(-1);
    assert.deepEqual(Object.values(receipt.source_check).map(check => check.status), ['FAIL', 'NOT_RUN', 'NOT_RUN']);
    boundedSourceCheck(receipt.source_check);
    assert.equal(receipt.accepted, false);
  }
  assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
  assert.equal(JSON.stringify(f.receipts()).includes(f.base), false);
});

test('missing, malformed and foreign Git-state records fail the final gate without leaking their contents', async t => {
  const f = readerFixture(t), hooks = await f.hooks(), valid = fixtureGitState(f);
  const missingSlot = structuredClone(valid); missingSlot.repositories[0].entries.pop();
  const foreignRoot = structuredClone(valid); foreignRoot.repositories[0].repo_root = path.join(f.base, 'SECRET FOREIGN ROOT');
  const foreignPath = structuredClone(valid); foreignPath.repositories[0].entries[1].path = path.join(f.base, 'SECRET FOREIGN HEAD');
  const foreignRef = structuredClone(valid);
  foreignRef.repositories[0].refs.push({ ref: 'refs/heads/SECRET', path: path.join(f.base, 'SECRET REF PATH'), state: 'file', sha256: 'a'.repeat(64) });
  const extra = structuredClone(valid); extra.repositories[0].entries[0].extra = 'SECRET ADMIN FIELD';
  for (const gitState of [{}, { ...valid, schema: 2 }, { ...valid, kind: 'SECRET FOREIGN STATE KIND' },
    { ...valid, repositories: [] }, missingSlot, foreignRoot, foreignPath, foreignRef, extra]) {
    f.reader.stdout = JSON.stringify(readerResult(f, f.boot, gitState));
    await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), error =>
      officialStatuslessRetry(error) === undefined && refusal('GIT_STATE_CHANGED')(error));
    const receipt = f.receipts().at(-1);
    assert.deepEqual(Object.values(receipt.source_check).map(check => check.status), ['PASS', 'PASS', 'FAIL']);
    assert.equal(receipt.source_check.final_bytes.error_kind, 'CHECK_EXCEPTION');
    boundedSourceCheck(receipt.source_check);
    assert.equal(receipt.accepted, false);
  }
  const receipts = JSON.stringify(f.receipts());
  for (const text of ['SECRET', f.base, 'git_state', 'repositories', 'packed_ref']) assert.equal(receipts.includes(text), false);
});

test('HEAD and index drift during the last managed metadata await cannot admit unchanged source bytes', async t => {
  for (const hook of ['chat.params', 'tool.execute.before']) {
    for (const slot of ['HEAD', 'index']) {
      const f = readerFixture(t, { managed: true }), tracked = pinFixtureFile(f, 'tracked.py');
      const pinnedBytes = fs.readFileSync(tracked), pinnedState = fs.readFileSync(f.statePath);
      const load = f.dependencies.loadFilesystem;
      f.dependencies.loadFilesystem = async (...args) => {
        const data = await load(...args);
        if (f.counts.filesystem === 2) {
          await Promise.resolve();
          fs.writeFileSync(path.join(f.repo, '.git', slot), slot === 'HEAD' ? 'c'.repeat(40) + '\n' : 'SECRET FILEMODE INDEX CHANGE\n');
        }
        return data;
      };
      const hooks = await f.hooks();
      await assert.rejects(hooks[hook]({ ...f.request(), tool: tools[0] }, {}), refusal('GIT_STATE_CHANGED'));
      assert.deepEqual(fs.readFileSync(tracked), pinnedBytes); assert.deepEqual(fs.readFileSync(f.statePath), pinnedState);
      assert.equal(f.reader.calls, 2); assert.equal(f.counts.session, 2); assert.equal(f.counts.filesystem, 2);
      const receipt = f.receipts().at(-1);
      assert.deepEqual(Object.values(receipt.source_check).map(check => check.status), ['PASS', 'PASS', 'FAIL']);
      assert.equal(receipt.accepted, false); boundedSourceCheck(receipt.source_check);
      assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
      assert.equal(JSON.stringify(f.receipts()).includes(f.base), false);
    }
  }
});

test('reader startup refuses HEAD or index drift after asynchronous capture without requesting session metadata', async t => {
  for (const slot of ['HEAD', 'index']) {
    const f = readerFixture(t, { managed: true });
    f.reader.beforeReturn = async () => {
      await Promise.resolve();
      fs.appendFileSync(path.join(f.repo, '.git', slot), 'SECRET ASYNC GIT DRIFT');
    };
    await assert.rejects(f.hooks, refusal('GIT_STATE_CHANGED'));
    assert.equal(f.reader.calls, 1); assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
    const receipt = f.receipts().at(-1);
    assert.equal(receipt.hook, 'plugin.loaded'); assert.equal(receipt.accepted, false);
    assert.deepEqual(Object.values(receipt.source_check).map(check => check.status), ['PASS', 'PASS', 'FAIL']);
    assert.equal(JSON.stringify(f.receipts()).includes('SECRET'), false);
  }
});

test('the real final Git-state helper obeys the same bounded byte-gate deadline', async t => {
  const f = readerFixture(t);
  let active = false, expired = false, finalChecks = 0;
  f.dependencies.monotonic = () => expired ? 20_000_000_000n : 0n;
  f.dependencies.assertGitState = (root, submodules, state, deadline) => {
    finalChecks++;
    if (active) expired = true;
    assertNativeGitState(root, submodules, state, deadline);
  };
  const hooks = await f.hooks(); active = true;
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('SOURCE_BYTES_CHECK_TIMEOUT'));
  assert.equal(finalChecks, 2);
  const receipt = f.receipts().at(-1);
  assert.deepEqual(Object.values(receipt.source_check).map(check => check.status), ['PASS', 'PASS', 'FAIL']);
  assert.equal(receipt.source_check.final_bytes.error_kind, 'TIMEOUT');
  assert.equal(receipt.accepted, false); boundedSourceCheck(receipt.source_check);
});

test('research purpose admits multiple existing categories without mutating supplied arguments', async t => {
  const f = researchFixture(t), hooks = await f.hooks();
  await hooks['chat.params'](f.request(), {});
  for (const [tool,args] of [
    ['caelab_analysis_run',{backend:'fixture.calculix',settings:{mesh:{max_sizes_mm:[2,1.5]}}}],
    ['caelab_optimization_plan',{backend:'fixture.cadquery',model:'roller_support',seed:13,
      max_generations:1,population_size:5,analysis_backend:'fixture.calculix',analysis_settings:{mesh:{max_sizes_mm:[2,1.5]}}}],
    ['caelab_pde_run',{backend:'pde.fenicsx',settings:{problem:{domain:'unit_square'},mesh:{cell_counts:[8,16,32],degree:1}}}],
    ['caelab_optimization_run',{campaign_id:'C-numerical'}],
    ['caelab_optimization_inspect',{campaign_id:'C-numerical'}],
  ]) {
    const output = {args}, original = structuredClone(output);
    await hooks['tool.execute.before']({tool,sessionID:f.sessionID},output);
    assert.deepEqual(output, original); assert.equal(f.receipts().at(-1).tool,tool);
    assert.equal(f.receipts().at(-1).accepted,true);
  }
  await assert.rejects(hooks['chat.params']({...f.request(),agent:'caelab-acceptance'},{}),refusal('AGENT_NOT_ALLOWED'));
});

test('legacy native settings cannot admit newly connected solver tools without research purpose', async t => {
  const f = readerFixture(t);
  f.settings.allowed = [...tools,'caelab_analysis_run']; f.guard.allowed = f.settings.allowed;
  json(f.settingsPath,f.settings); f.writeGuard({});
  await assert.rejects(f.hooks(),refusal('SETTINGS_INVALID'));
});

for (const [label,tool,args,code] of [
  ['unknown solver','caelab_analysis_run',{backend:'cfd.unknown',settings:{mesh:{max_sizes_mm:[2,1.5]}}},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['unadmitted CAD','caelab_experiment_run',{backend:'fixture.freecad',model:'roller_support'},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['larger search','caelab_optimization_plan',{backend:'fixture.cadquery',model:'roller_support',max_generations:2,population_size:5},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['larger population','caelab_optimization_plan',{backend:'fixture.cadquery',model:'roller_support',max_generations:1,population_size:6},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['different engine','caelab_optimization_plan',{backend:'fixture.cadquery',model:'roller_support',engine:'llm.optimizer'},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['more analysis meshes','caelab_analysis_run',{backend:'fixture.calculix',settings:{mesh:{max_sizes_mm:[3,2,1.5]}}},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['missing analysis mesh','caelab_analysis_run',{backend:'fixture.calculix',settings:{}},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['different PDE domain','caelab_pde_run',{backend:'pde.fenicsx',settings:{problem:{domain:'arbitrary'},mesh:{cell_counts:[8,16,32],degree:1}}},'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['larger PDE mesh','caelab_pde_run',{backend:'pde.fenicsx',settings:{problem:{domain:'unit_square'},mesh:{cell_counts:[8,16,64],degree:1}}},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['missing arguments','caelab_pde_run',undefined,'RESEARCH_ARGUMENTS_REQUIRED'],
]) test(`research purpose refuses ${label} before any admitted tool execution`,async t => {
  const f = researchFixture(t), hooks = await f.hooks(), output = {args}, original = structuredClone(output);
  await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},output),refusal(code));
  assert.deepEqual(output,original); assert.equal(f.receipts().at(-1).accepted,false);
  assert.equal(f.receipts().at(-1).code,code);
});

test('research purpose retains late source/grant/stopping gates for new solver tools',async t => {
  for (const drift of ['source','grant','stopping']) {
    const f = researchFixture(t), hooks = await f.hooks();
    if (drift === 'source') json(f.statePath,{...f.boot,source_commit:'f'.repeat(40)});
    if (drift === 'grant') f.state.filesystem.grants[0].access = 'read';
    if (drift === 'stopping') f.writeGuard({stopping:true});
    await assert.rejects(hooks['tool.execute.before']({tool:'caelab_analysis_run',sessionID:f.sessionID},
      {args:{backend:'fixture.calculix',settings:{mesh:{max_sizes_mm:[2,1.5]}}}}));
    assert.equal(f.receipts().at(-1).accepted,false);
  }
});

test('research budget/runtime descriptor tampering fails before loading tools',async t => {
  for (const slot of ['budget','runtime','scope']) {
    const f = researchFixture(t);
    if (slot === 'budget') f.settings.research.budgets.optimization.max_generations = 2;
    if (slot === 'runtime') f.settings.research.runtime_environment.OPENAI_API_KEY = 'SYNTHETIC_MUST_BE_REFUSED';
    if (slot === 'scope') f.settings.research.allowed_tools.push('caelab_unknown');
    json(f.settingsPath,f.settings);
    await assert.rejects(f.hooks(),refusal('RESEARCH_DEFINITION_INVALID'));
  }
});

const structuralRequest = () => ({backend:'structural.families.calculix',settings:{
  case:'ansys_vmd1_regular',load_case:'Fz',load_factor:1,mesh_cells:[[6,1,1],[12,2,2],[24,4,4]]}});
test('explicit structural profile admits both solvers and changed loads without rewriting arguments',async t => {
  const f = structuralResearchFixture(t), hooks = await f.hooks();
  await hooks['chat.params'](f.request(),{});
  for (const backend of ['structural.families.calculix','structural.families.code_aster']) {
    for (const [caseId,load,grid] of [['ansys_vmd1_regular','Fx',[[6,1,1],[12,2,2]]],
      ['lame_cylinder_plane_strain','pressure',[[2,4,1],[4,8,1],[8,16,2]]],
      ['scordelis_lo_solid','gravity',[[4,4,1],[8,8,1],[16,16,2]]]]) {
      const output = {args:{backend,settings:{case:caseId,load_case:load,load_factor:.5,mesh_cells:grid}}};
      const original = structuredClone(output);
      await hooks['tool.execute.before']({tool:'caelab_model_analysis_run',sessionID:f.sessionID},output);
      assert.deepEqual(output,original); assert.equal(f.receipts().at(-1).accepted,true);
    }
  }
});
test('historical fourteen-tool research cannot silently admit model_analysis',async t => {
  const f = researchFixture(t);
  f.settings.allowed.push('caelab_model_analysis_run'); f.guard.allowed = [...f.settings.allowed];
  json(f.settingsPath,f.settings); f.writeGuard({});
  await assert.rejects(f.hooks(),refusal('SETTINGS_INVALID'));
});
for (const [label,mutate,code] of [
  ['unadmitted solver',a => a.backend='structural.code_aster.plasticity','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['unadmitted finite-rotation beam',a => a.backend='structural.code_aster.geometric_nonlinearity','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['unresolved torsion',a => a.settings.load_case='Mx','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['arbitrary family',a => a.settings.case='unknown_case','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['numeric booleans',a => a.settings.load_factor=true,'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['zero load',a => a.settings.load_factor=0,'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['larger load',a => a.settings.load_factor=2.1,'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['one mesh',a => a.settings.mesh_cells=[[6,1,1]],'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['unbounded cells',a => a.settings.mesh_cells=[[48,48,1],[48,48,2]],'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['repeated mesh',a => a.settings.mesh_cells=[[6,1,1],[6,1,1]],'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['decreasing axis',a => a.settings.mesh_cells=[[6,2,1],[12,1,2]],'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['caller tolerance',a => a.settings.limits={reference_relative:1},'RESEARCH_ARGUMENTS_REQUIRED'],
]) test(`structural admission refuses ${label} before tool execution`,async t => {
  const f = structuralResearchFixture(t), hooks = await f.hooks(), args = structuralRequest();
  mutate(args); const output = {args}, original = structuredClone(output);
  await assert.rejects(hooks['tool.execute.before']({tool:'caelab_model_analysis_run',sessionID:f.sessionID},output),refusal(code));
  assert.deepEqual(output,original); assert.equal(f.receipts().at(-1).accepted,false);
});
test('structural definition cannot broaden its image, cases or tools',async t => {
  for (const change of [f => f.settings.research.runtime_environment.CAELAB_CODEASTER_IMAGE_SHA256='0'.repeat(64),
    f => f.settings.research.capabilities[0].cases.push('unknown'),
    f => f.settings.research.allowed_tools.push('caelab_optimization_run'),
    f => f.settings.research.benchmark_definition.path='../outside.json']) {
    const f = structuralResearchFixture(t); change(f); json(f.settingsPath,f.settings);
    await assert.rejects(f.hooks(),refusal('RESEARCH_DEFINITION_INVALID'));
  }
});
test('structural tools preserve source, ownership and Stop refusals',async t => {
  for (const drift of ['source','grant','stopping']) {
    const f = structuralResearchFixture(t), hooks = await f.hooks();
    if (drift === 'source') json(f.statePath,{...f.boot,source_commit:'f'.repeat(40)});
    if (drift === 'grant') f.state.filesystem.grants[0].access='read';
    if (drift === 'stopping') f.writeGuard({stopping:true});
    await assert.rejects(hooks['tool.execute.before']({tool:'caelab_model_analysis_run',sessionID:f.sessionID},
      {args:structuralRequest()}));
    assert.equal(f.receipts().at(-1).accepted,false);
  }
});


// PDEFields transport/policy fixtures are deliberately UNSOLVED. The mock
// source reader and project metadata make no provider, Core or native calls.
// The separate external PS descriptor test below is the actual definition pin;
// these small synthetic declarations are not reported as PS parity/evidence.
const pdeTools = ['caelab_study_create', 'caelab_study_inspect', 'caelab_pde_run',
  'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare'];
const pdeBackends = ['pde.fenicsx', 'pde.fenicsx.rectangle', 'pde.fenicsx.transient',
  'pde.fenicsx.coupled', 'pde.fenicsx.imported'];
function syntheticPdeDefinition() {
  return {schema:3,kind:'autonomous-cae-lab.openscience-research-definition',agent:'research',profile:'pde-fields-v1',
    allowed_tools:[...pdeTools], runtime_environment:{MPLBACKEND:'Agg',OMP_NUM_THREADS:'2',QT_QPA_PLATFORM:'offscreen',
      CAELAB_FENICSX_PYTHON:'/usr/bin/python3'},
    budgets:{steps:24,mcp_timeout_seconds:3600,command_timeout_seconds:3600,pde:{max_cell_count:32,
      max_mesh_levels:3,min_mesh_levels:3,degree:1,max_time_steps:128,max_snapshot_node_values:200000,
      max_imported_bytes:98304,max_request_bytes:131072}},
    capabilities:pdeBackends.map(backend => ({backend,operations:['pde_run'],
      verification:'SYNTHETIC_UNSOLVED_POLICY_TEST_ONLY'})),
    limitations:['Synthetic transport; no mathematics, provider, Core or native solve verified.']};
}
function pdeResearchFixture(t, definition = syntheticPdeDefinition()) {
  const f = readerFixture(t, {managed:true});
  f.settings.research = structuredClone(definition);
  f.settings.allowed = [...definition.allowed_tools]; f.guard.allowed = [...definition.allowed_tools];
  json(f.settingsPath,f.settings); f.writeGuard({});
  return f;
}
function pdeRequest(backend = 'pde.fenicsx.rectangle') {
  const linear = backend === 'pde.fenicsx', coupled = backend === 'pde.fenicsx.coupled';
  const problem = {domain:linear ? 'unit_square' : {type:'rectangle',lengths:[2,1]},
    weak_form:{diffusion:1,reaction:0,rhs:'1.0'},
    reference:{solution:'x[0]+2.0*x[1]',source:'SYNTHETIC UNSOLVED policy fixture'}};
  if (linear) problem.dirichlet = '0.0';
  else problem.boundaries = Object.fromEntries(['xmin','xmax','ymin','ymax'].map(name =>
    [name,{type:'dirichlet',value:'0.0'}]));
  const settings = {problem,mesh:{cell_counts:[8,16,32],degree:1},
    validation:{max_l2_error:.02,min_l2_rate:1.8,max_residual_relative:1e-10,
      ...(!linear ? {max_h1_seminorm_error:.3,min_h1_rate:.9} : {})}};
  if (backend === 'pde.fenicsx.transient') {
    problem.initial = {value:'x[0]+2.0*x[1]'};
    settings.time = {start:0,end:.5,step_counts:[16],scheme:'backward_euler',unit:'1'};
    settings.refinement_axis = 'mesh';
  }
  if (coupled) {
    problem.domain.interface = {axis:0,fraction:.5};
    problem.weak_form = {family:'coupled_diffusion',diffusion:{left:[[2,.1],[.1,1]],right:[[3,.2],[.2,2]]},
      reaction:[[0,0],[0,0]],rhs:{left:['1.0','2.0'],right:['3.0','4.0']}};
    problem.reference.solution = {left:['x[0]','x[1]'],right:['x[0]','x[1]']};
    for (const name of ['xmin','xmax','ymin','ymax']) problem.boundaries[name].value = Object.fromEntries(
      (name === 'xmin' ? ['left'] : name === 'xmax' ? ['right'] : ['left','right']).map(region => [region,['0.0','0.0']]));
  }
  if (backend === 'pde.fenicsx.imported') {
    problem.domain = {type:'imported_mesh',body:'DOMAIN'};
    problem.boundaries = {west:{type:'dirichlet',value:'0.0'},'named top':{type:'neumann',value:'1.0'}};
    settings.mesh = {degree:1,levels:[0,1,2].map(i => {
      const data = `SYNTHETIC ASCII SOURCE SHAPE ONLY ${i}\n`;
      return {format:'gmsh_msh2_ascii',data,sha256:sha(Buffer.from(data,'ascii')),source:`unsolved-level-${i}.msh`};
    })};
  }
  return {study_id:'S-pde-policy',experiment_id:'E-pde-policy',backend,settings};
}
const pdeBefore = (hooks,f,output) => hooks['tool.execute.before']({tool:'caelab_pde_run',sessionID:f.sessionID},output);

test('PDEFields actual exported PowerShell definition has its frozen canonical pin and is admitted unchanged',
  {skip:!process.env.CAELAB_PDE_RESEARCH_DEFINITION_PATH && 'External PS definition fixture was not supplied.'}, async t => {
    const bytes = fs.readFileSync(process.env.CAELAB_PDE_RESEARCH_DEFINITION_PATH);
    const definition = JSON.parse(bytes.toString('utf8'));
    assert.equal(sha(canonical(definition)), '4d30008657b8d887e05617b1d1933609374ea40b275b6a64fbba3210b5f50c31');
    const f = pdeResearchFixture(t,definition), hooks = await f.hooks();
    await hooks['chat.params'](immutable(f.request()),immutable({options:{reasoningEffort:'low'}}));
    for (const backend of pdeBackends) {
      const output = immutable({args:pdeRequest(backend)}), before = canonical(output);
      await pdeBefore(hooks,f,output);
      assert.equal(canonical(output),before); assert.equal(f.receipts().at(-1).accepted,true);
    }
    assert.equal(canonical(f.settings.research),canonical(definition));
    assert.equal(f.guard.required,null); assert.equal(f.reader.calls,7);
  });

test('PDEFields admits only the six supplied tools, all five families and both transient axes without mutation',async t => {
  const f = pdeResearchFixture(t), hooks = await f.hooks();
  const request = immutable(f.request()), output = immutable({options:{prompt:'PRIVATE PDE INPUT',reasoningEffort:'low'}});
  const before = canonical({request,output});
  await hooks['chat.params'](request,output); assert.equal(canonical({request,output}),before);
  for (const tool of pdeTools.filter(value => value !== 'caelab_pde_run')) {
    const result = immutable({args:{study_id:'S-pde-policy',experiment_id:'E-pde-policy'}}), saved = canonical(result);
    await hooks['tool.execute.before']({tool,sessionID:f.sessionID},result);
    assert.equal(canonical(result),saved); assert.equal(f.receipts().at(-1).accepted,true);
  }
  const requests = pdeBackends.map(pdeRequest), time = pdeRequest('pde.fenicsx.transient');
  time.settings.refinement_axis = 'time'; time.settings.mesh.cell_counts = [28]; time.settings.time.step_counts = [32,64,128];
  // 29^2 * (33+65+129) =190907; accepted independently of the native backend's larger cap.
  requests.push(time);
  for (const args of requests) {
    const result = immutable({args}), saved = canonical(result);
    await pdeBefore(hooks,f,result); assert.equal(canonical(result),saved);
    assert.equal(f.receipts().at(-1).accepted,true); assert.equal(f.receipts().at(-1).tool,'caelab_pde_run');
  }
  assert.equal(f.guard.required,null);
  const receipts = JSON.stringify(f.receipts());
  for (const privateText of ['PRIVATE PDE INPUT','S-pde-policy','SYNTHETIC ASCII','weak_form','reference'])
    assert.equal(receipts.includes(privateText),false);
});

test('PDEFields leaves finite scientific failures and unsafe AST strings to unchanged Domain/adapter preflight',async t => {
  const f = pdeResearchFixture(t), hooks = await f.hooks();
  const wrong = pdeRequest(); wrong.settings.problem.reference.solution = '999.0';
  wrong.settings.problem.boundaries.xmax = {type:'neumann',value:'-777.0'};
  const unsafe = pdeRequest('pde.fenicsx.transient');
  unsafe.settings.problem.weak_form.rhs = '__import__("os").system("UNSAFE TEST STRING NEVER EXECUTED")';
  unsafe.settings.problem.initial.value = 'unknown_call(t)';
  const nonSpd = pdeRequest('pde.fenicsx.coupled');
  nonSpd.settings.problem.weak_form.diffusion.left = [[-1,2],[3,0]];
  nonSpd.settings.problem.weak_form.reaction = [[-4,5],[6,-7]];
  const wrongLimits = pdeRequest(); wrongLimits.settings.validation.max_l2_error = -1;
  wrongLimits.settings.problem.weak_form.diffusion = -2;
  for (const args of [wrong,unsafe,nonSpd,wrongLimits]) {
    const result = immutable({args}), saved = canonical(result);
    await pdeBefore(hooks,f,result); assert.equal(canonical(result),saved);
    assert.equal(f.receipts().at(-1).accepted,true);
  }
  assert.equal(f.reader.seen.every(call => call.file === f.nodePath),true);
});

test('PDEFields cannot broaden or confuse its research schema with the native context schema',async t => {
  const patches = [
    r => r.schema=1, r => r.schema=2, r => r.profile='PDE-FIELDS-v1',
    r => r.agent='caelab-acceptance', r => r.kind='other-research-kind',
    r => r.allowed_tools.reverse(), r => r.allowed_tools.push('caelab_optimization_run'),
    r => r.runtime_environment.CAELAB_FENICSX_PYTHON='/tmp/other-python',
    r => r.runtime_environment.OMP_NUM_THREADS=2, r => r.runtime_environment.NEW_VARIABLE='synthetic',
    r => r.budgets.pde.max_snapshot_node_values=2000000, r => r.budgets.pde.max_request_bytes++,
    r => r.budgets.command_timeout_seconds=3601, r => r.capabilities.reverse(),
    r => r.capabilities[0].operations.push('job_run'), r => r.capabilities[0].backend='pde.fenicsx.vector',
    r => r.capabilities.push({backend:'pde.fenicsx.nonlinear',operations:['pde_run']}),
    r => r.benchmark_definition={path:'benchmarks/specifications/other.json'},
  ];
  for (const patch of patches) {
    const f = pdeResearchFixture(t); patch(f.settings.research); json(f.settingsPath,f.settings);
    await assert.rejects(f.hooks(),refusal('RESEARCH_DEFINITION_INVALID'));
    assert.equal(f.reader.calls,0); assert.equal(f.counts.session,0);
  }
  const f = pdeResearchFixture(t); f.settings.schema = 1; delete f.settings.source_reader;
  json(f.settingsPath,f.settings); await assert.rejects(f.hooks(),refusal('SETTINGS_INVALID'));
});

test('PDEFields refuses unsupported backends and execution categories before dispatch',async t => {
  const f = pdeResearchFixture(t), hooks = await f.hooks();
  for (const backend of ['pde.fenicsx.vector','pde.fenicsx.nonlinear','structural.families.calculix','cfd.openfoam']) {
    const args = pdeRequest(); args.backend = backend;
    await assert.rejects(pdeBefore(hooks,f,{args}),refusal('RESEARCH_CAPABILITY_NOT_ADMITTED'));
  }
  for (const tool of ['caelab_model_analysis_run','caelab_analysis_run','caelab_experiment_run',
    'caelab_optimization_plan','caelab_parameters_register','caelab_job_run','shell']) {
    await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args:pdeRequest()}),refusal('TOOL_NOT_ALLOWED'));
  }
  await assert.rejects(hooks['chat.params']({...f.request(),agent:'caelab-acceptance'},{}),refusal('AGENT_NOT_ALLOWED'));
  assert.equal(f.receipts().at(-1).accepted,false);
});

test('PDEFields closes argument/settings/side/form shape and rejects malformed or nonfinite JSON values',async t => {
  const f = pdeResearchFixture(t), hooks = await f.hooks();
  const invalid = [
    a => delete a.study_id, a => a.experiment_id=' ', a => a.extra_metadata='not admitted',
    a => a.model='fixture.cadquery', a => a.settings.native_path='C:/arbitrary.msh',
    a => a.settings.problem.reference.extra='unexpected',
    a => a.settings.problem.weak_form.callback='not admitted',
    a => delete a.settings.problem.boundaries.ymax,
    a => a.settings.problem.boundaries.extra={type:'dirichlet',value:'0.0'},
    a => a.settings.problem.boundaries.xmin.extra='unrecognized',
    a => a.settings.problem.weak_form.diffusion=true,
    a => a.settings.problem.weak_form.reaction=NaN,
    a => a.settings.problem.weak_form.rhs=1,
    a => a.settings.validation.min_l2_rate=Infinity,
    a => a.settings.problem.domain.lengths=[2,undefined],
    a => a.settings.problem.domain.lengths=new Array(2),
    a => a.hypothesis_id=17,
  ];
  for (const patch of invalid) {
    const args = pdeRequest(); patch(args); const result = {args}, saved = structuredClone(result);
    await assert.rejects(pdeBefore(hooks,f,result),refusal('RESEARCH_ARGUMENTS_REQUIRED'));
    assert.deepEqual(result,saved); assert.equal(f.receipts().at(-1).accepted,false);
  }
  for (const args of [undefined,null,[],42])
    await assert.rejects(pdeBefore(hooks,f,{args}),refusal('RESEARCH_ARGUMENTS_REQUIRED'));
  const coupled = pdeRequest('pde.fenicsx.coupled'); coupled.settings.problem.weak_form.rhs.left = new Array(2);
  await assert.rejects(pdeBefore(hooks,f,{args:coupled}),refusal('RESEARCH_ARGUMENTS_REQUIRED'));
  coupled.settings.problem.weak_form.rhs.left=['0.0','0.0']; coupled.settings.problem.weak_form.diffusion.right=[[1,0],[0]];
  await assert.rejects(pdeBefore(hooks,f,{args:coupled}),refusal('RESEARCH_ARGUMENTS_REQUIRED'));
  coupled.settings.problem.weak_form.diffusion.right=[[1,0],new Array(2)];
  await assert.rejects(pdeBefore(hooks,f,{args:coupled}),refusal('RESEARCH_ARGUMENTS_REQUIRED'));
  const optional = immutable({args:{...pdeRequest(),hypothesis_id:null}}); await pdeBefore(hooks,f,optional);
});

test('PDEFields stationary meshes require exactly three positive doubling bounded P1 counts',async t => {
  const f = pdeResearchFixture(t), hooks = await f.hooks();
  for (const counts of [[8],[8,16],[4,8,16,32],[8,16,64],[8,12,24],[8,8,16],[-1,2,4],
    [0,0,0],[true,2,4],[4.5,9,18],new Array(3)]) {
    const args = pdeRequest(); args.settings.mesh.cell_counts = counts;
    await assert.rejects(pdeBefore(hooks,f,{args}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
  }
  const degree = pdeRequest(); degree.settings.mesh.degree = 2;
  await assert.rejects(pdeBefore(hooks,f,{args:degree}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
  degree.settings.mesh.degree = true;
  await assert.rejects(pdeBefore(hooks,f,{args:degree}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
  const shape = pdeRequest(); shape.settings.mesh.extra='unexpected';
  await assert.rejects(pdeBefore(hooks,f,{args:shape}),refusal('RESEARCH_ARGUMENTS_REQUIRED'));
});

test('PDEFields transient axis, scheme, time, step counts and exact retained values budget are enforced',async t => {
  const f = pdeResearchFixture(t), hooks = await f.hooks();
  const changes = [
    a => a.settings.time.step_counts=[8,16,32],
    a => a.settings.refinement_axis='time',
    a => a.settings.time.scheme='crank_nicolson', a => a.settings.time.unit='s',
    a => a.settings.time.start=-.01, a => a.settings.time.start=false,
    a => a.settings.time.end=.0009, a => a.settings.time.end=1001,
    a => a.settings.time.end=NaN, a => a.settings.time.step_counts=[129],
    a => a.settings.time.step_counts=[true],
    a => {a.settings.refinement_axis='time';a.settings.mesh.cell_counts=[16];a.settings.time.step_counts=[32,64,256];},
    a => {a.settings.refinement_axis='time';a.settings.mesh.cell_counts=[32];a.settings.time.step_counts=[32,64,128];},
  ];
  for (const change of changes) {
    const args = pdeRequest('pde.fenicsx.transient'); change(args);
    const result = {args}, saved = structuredClone(result);
    await assert.rejects(pdeBefore(hooks,f,result),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
    assert.deepEqual(result,saved);
  }
  const axis = pdeRequest('pde.fenicsx.transient'); axis.settings.refinement_axis='both';
  await assert.rejects(pdeBefore(hooks,f,{args:axis}),refusal('RESEARCH_CAPABILITY_NOT_ADMITTED'));
  const extra = pdeRequest('pde.fenicsx.transient'); extra.settings.time.extra=0;
  await assert.rejects(pdeBefore(hooks,f,{args:extra}),refusal('RESEARCH_ARGUMENTS_REQUIRED'));
  for (const end of [.001,1000]) {
    const args = pdeRequest('pde.fenicsx.transient'); args.settings.time.end=end;
    await pdeBefore(hooks,f,immutable({args}));
  }
});

test('PDEFields imported original ASCII identity, named sides, labels and total byte budget remain immutable',async t => {
  const f = pdeResearchFixture(t), hooks = await f.hooks();
  const invalid = [
    a => a.settings.mesh.levels[0].path='C:/arbitrary.msh',
    a => a.settings.mesh.levels[0].format='gmsh_binary',
    a => a.settings.mesh.levels[0].data='nonASCII 한글',
    a => a.settings.mesh.levels[0].sha256='a'.repeat(64),
    a => a.settings.mesh.levels[0].sha256=a.settings.mesh.levels[0].sha256.toUpperCase(),
    a => a.settings.mesh.levels[0].source=' ',
    a => a.settings.mesh.levels[0].source='a'.repeat(257),
    a => a.settings.problem.boundaries={},
  ];
  for (const patch of invalid) {
    const args = pdeRequest('pde.fenicsx.imported'); patch(args);
    const result = {args}, saved = structuredClone(result);
    await assert.rejects(pdeBefore(hooks,f,result),refusal('RESEARCH_ARGUMENTS_REQUIRED')); assert.deepEqual(result,saved);
  }
  for (const levels of [1,2,4]) {
    const args = pdeRequest('pde.fenicsx.imported');
    args.settings.mesh.levels=Array.from({length:levels},()=>structuredClone(args.settings.mesh.levels[0]));
    await assert.rejects(pdeBefore(hooks,f,{args}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
  }
  const exact = pdeRequest('pde.fenicsx.imported');
  exact.settings.mesh.levels.forEach((level,i) => {
    level.data=String(i).repeat(32768);level.sha256=sha(Buffer.from(level.data,'ascii'));level.source='한'.repeat(256);
  });
  const output = immutable({args:exact}), saved = canonical(output);
  await pdeBefore(hooks,f,output); assert.equal(canonical(output),saved);
  const larger = structuredClone(exact); larger.settings.mesh.levels[2].data+='3';
  larger.settings.mesh.levels[2].sha256=sha(Buffer.from(larger.settings.mesh.levels[2].data,'ascii'));
  await assert.rejects(pdeBefore(hooks,f,{args:larger}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
});

test('PDEFields bounds parsed JSON UTF8 bytes exactly without claiming original MCP wire size',async t => {
  const f = pdeResearchFixture(t), hooks = await f.hooks();
  const exact = pdeRequest(), base = Buffer.byteLength(JSON.stringify(exact),'utf8');
  exact.settings.problem.reference.source += 'a'.repeat(131072-base);
  assert.equal(Buffer.byteLength(JSON.stringify(exact),'utf8'),131072);
  await pdeBefore(hooks,f,immutable({args:exact}));
  const tooLarge = structuredClone(exact); tooLarge.settings.problem.reference.source+='a';
  await assert.rejects(pdeBefore(hooks,f,{args:tooLarge}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
  const unicode = pdeRequest(); unicode.settings.problem.reference.source='한'.repeat(45000);
  assert.ok(JSON.stringify(unicode).length < 131072); assert.ok(Buffer.byteLength(JSON.stringify(unicode),'utf8') > 131072);
  await assert.rejects(pdeBefore(hooks,f,{args:unicode}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
  assert.equal(Object.hasOwn(f.receipts().at(-1),'wire_bytes'),false);
});

test('PDEFields uses existing final async source/config/settings/grant/Stop and stage gates',async t => {
  for (const [drift,code] of [['source','SOURCE_CHANGED_OR_UNAVAILABLE'],['grant','PROJECT_GRANT_CHANGED'],
    ['config','CONFIG_CHANGED'],['settings','SETTINGS_CHANGED'],['stopping','RUNTIME_STOPPING'],
    ['no_tools','NO_TOOLS_STAGE'],['required','REQUIRED_TOOL_MISMATCH']]) {
    const f = pdeResearchFixture(t), load = f.dependencies.loadFilesystem;
    f.dependencies.loadFilesystem = async (...args) => {
      const data = await load(...args);
      if (f.counts.filesystem === 2) {
        await Promise.resolve();
        if (drift === 'source') fs.writeFileSync(path.join(f.repo,'new_import.py'),'SECRET UNPINNED IMPORT');
        if (drift === 'grant') {f.state.filesystem.grants[0].access='read';data.grants[0].access='read';}
        if (drift === 'config') fs.appendFileSync(f.settings.configPath,' ');
        if (drift === 'settings') fs.appendFileSync(f.settingsPath,' ');
        if (drift === 'stopping') f.writeGuard({stopping:true});
        if (drift === 'no_tools') f.writeGuard({no_tools:true});
        if (drift === 'required') f.writeGuard({required:'caelab_study_inspect'});
      }
      return data;
    };
    const hooks = await f.hooks(), result = immutable({args:pdeRequest()});
    await assert.rejects(pdeBefore(hooks,f,result),refusal(drift === 'source' ? 'SOURCE_IMPORTABLE_CHANGED' : code));
    assert.equal(f.reader.calls,2); assert.equal(f.receipts().at(-1).accepted,false);
    assert.equal(JSON.stringify(f.receipts()).includes('SECRET'),false);
  }
});

test('PDEFields late model and provider changes cannot pass the logical stream gate',async t => {
  for (const patch of [request => request.model.id='other-model',request => request.model.providerID='other-provider']) {
    const f = pdeResearchFixture(t), load = f.dependencies.loadFilesystem, request = f.request();
    f.dependencies.loadFilesystem = async (...args) => {
      const data = await load(...args); if (f.counts.filesystem===2) {await Promise.resolve();patch(request);} return data;
    };
    const hooks = await f.hooks();
    await assert.rejects(hooks['chat.params'](request,immutable({options:{reasoningEffort:'low'}})),refusal('MODEL_CHANGED'));
    assert.equal(f.reader.calls,2); assert.equal(f.receipts().at(-1).accepted,false);
  }
});

// Source-only MaterialPoints admission fixtures. These are inputs and mocked
// metadata; no behaviour, native library, Core or model is invoked.
function materialResearchFixture(t, definition = nativeMaterialDefinition) {
  const f = readerFixture(t, {managed:true});
  f.settings.research = structuredClone(definition);
  f.settings.allowed = [...definition.allowed_tools]; f.guard.allowed = [...definition.allowed_tools];
  f.settings.model = f.guard.model = 'openai-codex/gpt-5.6-sol';
  json(f.settings.configPath,{model:f.settings.model,permission:{'*':'deny'}});
  f.settings.config_sha256 = sha(fs.readFileSync(f.settings.configPath));
  json(f.settingsPath,f.settings); f.writeGuard({});
  return {...f,request:() => ({...f.request(),model:{providerID:'openai-codex',id:'gpt-5.6-sol'}})};
}
function materialSettings() {
  // Exact canonical Domain input, including physical xx,yy,zz,xy,yx,xz,zx,yz,zy
  // order. It is not a synthetic native response or scientific PASS.
  const gradients = [
    [1,1,1,0,0,0,0,0,0], [1,1,1,0,0,0,0,0,0],
    [1.001,1,1,0,0,0,0,0,0], [.999,1.0007,1.0003,0,0,0,0,0,0],
    [1,1,1,.0006,0,0,0,0,0], [1,1,1,0,-.0004,0,0,0,0],
    [1.001,.9995,1.0007,.0004,.00015,-.0002,.00025,.0003,-.00035],
    [.707707821950556,.7070360705084289,1.0007,-.7064703850834796,.7079199539849119,-.0003535533905932737,.00025,7.071067811865474e-5,-.00035],
    [.5003700961894324,.43327119554127336,.8666200190267093,-.8653923910825464,.7506899519052838,-.0003598076211353316,.43369972094505754,-.5003700961894322,.24974509618943236],
    [1.001,.9995,1.0007,.0004,.00015,-.0002,.00025,.0003,-.00035],
    [.5000000000000001,.5000000000000001,1,-.8660254037844386,.8660254037844386,0,0,0,0],
    [1,1,1,0,0,0,0,0,0],
  ];
  return {case:'saint_venant_kirchhoff',material:{youngs_modulus_mpa:210000,poisson_ratio:.3},
    temperature_k:293.15,history:gradients.map((deformation_gradient,time_s) => ({time_s,deformation_gradient})),
    limits:structuredClone(nativeMaterialLimits)};
}
const materialRequest = () => ({study_id:'S-material-source-only',experiment_id:'E-material-source-only',
  backend:'material.mfront.hyperelastic',settings:materialSettings()});
const materialBefore = (hooks,f,output) => hooks['tool.execute.before']({tool:'caelab_model_analysis_run',sessionID:f.sessionID},output);

test('MaterialPoints descriptor is exact, frozen and independent of the native context schema',async t => {
  assert.equal(nativeMaterialDefinition.schema,4); assert.equal(nativeMaterialDefinition.profile,'material-points-v1');
  assert.deepEqual(nativeMaterialDefinition.allowed_tools,['caelab_study_create','caelab_study_inspect','caelab_model_analysis_run',
    'caelab_experiment_inspect','caelab_experiment_summary','caelab_experiment_compare']);
  assert.equal(Object.isFrozen(nativeMaterialDefinition.budgets.material_point),true);
  assert.equal(Object.isFrozen(nativeMaterialLimits.finite_difference_steps),true);
  const f = materialResearchFixture(t), hooks = await f.hooks();
  assert.equal(f.settings.schema,3); await hooks['chat.params'](f.request(),immutable({options:{}}));
  assert.equal(f.receipts().at(-1).accepted,true);
});

test('MaterialPoints actual PowerShell descriptor and pure Domain inputs match the admitted Node constants',
  {skip:!process.env.CAELAB_MATERIAL_RESEARCH_DEFINITION_PATH && 'External PS descriptor/pure Domain fixture was not supplied.'},async t => {
    const definition = JSON.parse(fs.readFileSync(process.env.CAELAB_MATERIAL_RESEARCH_DEFINITION_PATH,'utf8'));
    assert.equal(canonical(definition),canonical(nativeMaterialDefinition));
    const limits = JSON.parse(fs.readFileSync(process.env.CAELAB_MATERIAL_FIXED_LIMITS_PATH,'utf8'));
    const settings = JSON.parse(fs.readFileSync(process.env.CAELAB_MATERIAL_CANONICAL_SETTINGS_PATH,'utf8'));
    assert.equal(canonical(limits),canonical(nativeMaterialLimits));
    assert.equal(canonical(settings),canonical(materialSettings()));
    const f = materialResearchFixture(t,definition), hooks = await f.hooks();
    await materialBefore(hooks,f,immutable({args:{...materialRequest(),settings}}));
    assert.equal(f.receipts().at(-1).accepted,true);
  });

test('MaterialPoints admits its full canonical history, second assumed E and existing six tools without mutation',async t => {
  const f = materialResearchFixture(t), hooks = await f.hooks();
  for (const E of [210000,105000]) {
    const args = materialRequest(); args.settings.material.youngs_modulus_mpa = E;
    const output = immutable({args}), original = JSON.stringify(output);
    await materialBefore(hooks,f,output); assert.equal(JSON.stringify(output),original);
    assert.equal((args.settings.history.length-1)*3*9*2,594);
  }
  for (const tool of nativeMaterialDefinition.allowed_tools.filter(tool => tool !== 'caelab_model_analysis_run')) {
    const args = immutable({study_id:'S-material-source-only',experiment_id:'E-material-source-only'}), output = immutable({args});
    await hooks['tool.execute.before']({tool,sessionID:f.sessionID},output);
    assert.equal(f.receipts().at(-1).accepted,true); assert.equal(f.receipts().at(-1).tool,tool);
  }
});

test('MaterialPoints forwards finite scientific-invalid inputs unchanged to Domain preflight',async t => {
  const f = materialResearchFixture(t), hooks = await f.hooks(), args = materialRequest();
  args.settings.history[2].deformation_gradient = [0,0,0,0,0,0,0,0,0];
  const output = immutable({args}), original = JSON.stringify(output);
  await materialBefore(hooks,f,output); assert.equal(JSON.stringify(output),original);
  // Guard admission is not native execution or a Domain verdict.
  assert.equal(f.receipts().at(-1).accepted,true);
});

for (const [label,patch,code='RESEARCH_ARGUMENTS_REQUIRED'] of [
  ['missing settings',a => delete a.settings], ['extra outer key',a => a.unlisted='x'],
  ['empty study',a => a.study_id=' '], ['empty experiment',a => a.experiment_id=''],
  ['boolean hypothesis',a => a.hypothesis_id=true], ['empty hypothesis',a => a.hypothesis_id=' '],
  ['alternate backend',a => a.backend='material.mfront','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['alternate case',a => a.settings.case='neo_hookean','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['missing limit',a => delete a.settings.limits.tangent_relative],
  ['extra setting',a => a.settings.optimize=true], ['extra material',a => a.settings.material.density=1],
  ['string E',a => a.settings.material.youngs_modulus_mpa='210000'],
  ['boolean E',a => a.settings.material.youngs_modulus_mpa=true], ['nonfinite E',a => a.settings.material.youngs_modulus_mpa=Infinity],
  ['zero E',a => a.settings.material.youngs_modulus_mpa=0], ['overbound E',a => a.settings.material.youngs_modulus_mpa=1e9+1],
  ['nu upper',a => a.settings.material.poisson_ratio=.5], ['nu lower',a => a.settings.material.poisson_ratio=-1],
  ['string temperature',a => a.settings.temperature_k='293.15'], ['zero temperature',a => a.settings.temperature_k=0],
  ['overbound temperature',a => a.settings.temperature_k=5001],
  ['relaxed tolerance',a => a.settings.limits.stress_relative=1e-7],
  ['reordered h',a => a.settings.limits.finite_difference_steps.reverse()],
  ['missing h',a => a.settings.limits.finite_difference_steps.pop()],
  ['numeric-string h',a => a.settings.limits.finite_difference_steps[0]='1e-7'],
  ['two history entries',a => a.settings.history.length=2,'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['thirteen history entries',a => a.settings.history.push({time_s:12,deformation_gradient:[1,1,1,0,0,0,0,0,0]}),'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['extra entry',a => a.settings.history[2].extra=0], ['nonzero first time',a => a.settings.history[0].time_s=.1],
  ['duplicate time',a => a.settings.history[2].time_s=1], ['reverse time',a => a.settings.history[2].time_s=.5],
  ['time beyond cap',a => a.settings.history[11].time_s=1e6+1], ['string time',a => a.settings.history[1].time_s='1'],
  ['short F',a => a.settings.history[2].deformation_gradient.pop()],
  ['sparse F',a => delete a.settings.history[2].deformation_gradient[3]],
  ['nonfinite F',a => a.settings.history[2].deformation_gradient[3]=NaN],
  ['boolean F',a => a.settings.history[2].deformation_gradient[3]=false],
  ['string F',a => a.settings.history[2].deformation_gradient[3]='.0006'],
]) test(`MaterialPoints refuses ${label} without rewriting arguments`,async t => {
  const f = materialResearchFixture(t), hooks = await f.hooks(), args = materialRequest(); patch(args);
  const original = structuredClone(args), output = {args};
  await assert.rejects(materialBefore(hooks,f,output),refusal(code)); assert.deepEqual(output.args,original);
  assert.equal(f.receipts().at(-1).accepted,false);
});

test('MaterialPoints admits the minimum history and exact parsed UTF8 byte cap, refuses one byte more',async t => {
  const f = materialResearchFixture(t), hooks = await f.hooks(), args = materialRequest(); args.settings.history.length=3;
  args.hypothesis_id = '가'.repeat(100);
  args.hypothesis_id += 'x'.repeat(65536-Buffer.byteLength(JSON.stringify(args),'utf8'));
  assert.equal(Buffer.byteLength(JSON.stringify(args),'utf8'),65536);
  await materialBefore(hooks,f,immutable({args}));
  const excessive = structuredClone(args); excessive.hypothesis_id += 'x';
  await assert.rejects(materialBefore(hooks,f,immutable({args:excessive})),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
});

test('MaterialPoints canonical descriptor cannot widen runtime, image, tools, schema or any work budget',async t => {
  for (const patch of [d => d.schema=3,d => d.profile='MaterialPoints',d => d.profile='material-points-v2',
    d => d.allowed_tools.push('caelab_jobs_submit'),d => d.runtime_environment.CAELAB_CODEASTER_IMAGE='/other.sif',
    d => d.runtime_environment.CAELAB_CODEASTER_IMAGE_SHA256='0'.repeat(64),d => d.runtime_environment.OMP_NUM_THREADS='8',
    d => d.capabilities[0].backend='material.mfront',d => d.capabilities[0].cases.push('neo_hookean'),
    ...['steps','mcp_timeout_seconds','command_timeout_seconds'].map(key => d => d.budgets[key]++),
    ...Object.keys(nativeMaterialDefinition.budgets.material_point).map(key => d => d.budgets.material_point[key]++),
  ]) {
    const f = materialResearchFixture(t), definition = f.settings.research; patch(definition); json(f.settingsPath,f.settings);
    await assert.rejects(f.hooks(),refusal('RESEARCH_DEFINITION_INVALID'));
  }
});

test('MaterialPoints refuses optimizer/job/register tools and historical scopes cannot admit its backend',async t => {
  const f = materialResearchFixture(t), hooks = await f.hooks();
  for (const tool of ['caelab_parameters_register','caelab_optimization_run','caelab_job_submit','caelab_pde_run'])
    await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args:{}}),refusal('TOOL_NOT_ALLOWED'));
  for (const make of [researchFixture,structuralResearchFixture,pdeResearchFixture]) {
    const prior = make(t), priorHooks = await prior.hooks();
    await assert.rejects(priorHooks['tool.execute.before']({tool:'caelab_model_analysis_run',sessionID:prior.sessionID},
      {args:materialRequest()}),refusal(make===structuralResearchFixture ? 'RESEARCH_CAPABILITY_NOT_ADMITTED' : 'TOOL_NOT_ALLOWED'));
  }
});

test('MaterialPoints retains late source, session/grant/config/settings/Stop and stage refusals',async t => {
  for (const [drift,code] of [['source','SOURCE_IMPORTABLE_CHANGED'],['session','PROJECT_SESSION_CHANGED'],
    ['grant','PROJECT_GRANT_CHANGED'],['config','CONFIG_CHANGED'],['settings','SETTINGS_CHANGED'],
    ['stopping','RUNTIME_STOPPING'],['no_tools','NO_TOOLS_STAGE'],['required','REQUIRED_TOOL_MISMATCH']]) {
    const f = materialResearchFixture(t), load = f.dependencies.loadFilesystem;
    if (drift==='session') {
      const get = f.pluginInput.client.session.get;
      f.pluginInput.client.session.get = async (...args) => {
        const response = await get(...args);
        if (f.counts.session===2) response.data.projectID='prj_foreign';
        return response;
      };
    }
    f.dependencies.loadFilesystem = async (...args) => {
      const data = await load(...args);
      if (f.counts.filesystem===2) {
        if (drift==='source') fs.writeFileSync(path.join(f.repo,'new_material.py'),'SECRET UNPINNED IMPORT');
        if (drift==='grant') {f.state.filesystem.grants[0].access='read';data.grants[0].access='read';}
        if (drift==='config') fs.appendFileSync(f.settings.configPath,' ');
        if (drift==='settings') fs.appendFileSync(f.settingsPath,' ');
        if (drift==='stopping') f.writeGuard({stopping:true});
        if (drift==='no_tools') f.writeGuard({no_tools:true});
        if (drift==='required') f.writeGuard({required:'caelab_study_inspect'});
      }
      return data;
    };
    const hooks = await f.hooks(); await assert.rejects(materialBefore(hooks,f,immutable({args:materialRequest()})),refusal(code),drift);
    assert.equal(f.receipts().at(-1).accepted,false); assert.equal(JSON.stringify(f.receipts()).includes('SECRET'),false);
  }
});

test('MaterialPoints exact approved model has no fallback on late provider/model changes',async t => {
  for (const patch of [r => r.model.id='gpt-other',r => r.model.providerID='ollama']) {
    const f = materialResearchFixture(t), request = f.request(), load = f.dependencies.loadFilesystem;
    f.dependencies.loadFilesystem = async (...args) => {const data=await load(...args);if(f.counts.filesystem===2) patch(request);return data;};
    const hooks = await f.hooks(); await assert.rejects(hooks['chat.params'](request,immutable({options:{}})),refusal('MODEL_CHANGED'));
    assert.equal(f.receipts().at(-1).accepted,false);
  }
});

// ViscoelasticPoints fixtures are declared inputs and synthetic hook metadata.
// No material reference equation, native law, Core or provider is executed.
const viscoelasticResearchFixture = (t,definition=nativeViscoelasticDefinition) => materialResearchFixture(t,definition);
function viscoelasticSettings({refined=false,relaxation_time_s=1}={}) {
  let times=[0,.2,1,1.2,2,2.2,3,3.2,4],amplitudes=[0,1,1,0,0,-.5,-.5,0,0];
  const direction=[.001,-.0002,.0003,.0004,-.0003,.0002];
  if(refined) {
    times=times.flatMap((value,index,all) => index<all.length-1 ? [value,(value+all[index+1])/2] : [value]);
    amplitudes=amplitudes.flatMap((value,index,all) => index<all.length-1 ? [value,(value+all[index+1])/2] : [value]);
  }
  return {case:'single_branch_maxwell',material:{equilibrium_bulk_modulus_mpa:1000,equilibrium_shear_modulus_mpa:500,
    branch_bulk_modulus_mpa:2000,branch_shear_modulus_mpa:1000,relaxation_time_s},temperature_k:293.15,
    history:times.map((time_s,index) => ({time_s,strain:direction.map(value => value*amplitudes[index])})),
    limits:structuredClone(nativeViscoelasticLimits)};
}
const viscoelasticRequest = options => ({study_id:'S-viscoelastic-source-only',experiment_id:'E-viscoelastic-source-only',
  backend:'material.mfront.viscoelastic',settings:viscoelasticSettings(options)});

test('ViscoelasticPoints actual PS descriptor and Domain canonical9/refined17/tau2 inputs have exact source parity',
  {skip:!process.env.CAELAB_VISCOELASTIC_RESEARCH_DEFINITION_PATH && 'External PS descriptor/pure Domain fixtures were not supplied.'},async t => {
    const definition=JSON.parse(fs.readFileSync(process.env.CAELAB_VISCOELASTIC_RESEARCH_DEFINITION_PATH,'utf8'));
    assert.equal(sha(canonical(definition)),'23028f399c79e099a054294a4599e08efa89410ccd380f81e047eabb4c06d99b');
    assert.equal(canonical(definition),canonical(nativeViscoelasticDefinition));
    const limits=JSON.parse(fs.readFileSync(process.env.CAELAB_VISCOELASTIC_FIXED_LIMITS_PATH,'utf8'));
    assert.equal(canonical(limits),canonical(nativeViscoelasticLimits));
    const f=viscoelasticResearchFixture(t,definition),hooks=await f.hooks();
    for(const [variable,options] of [['CAELAB_VISCOELASTIC_CANONICAL_SETTINGS_PATH',{}],
      ['CAELAB_VISCOELASTIC_REFINED_SETTINGS_PATH',{refined:true}],['CAELAB_VISCOELASTIC_TAU2_SETTINGS_PATH',{relaxation_time_s:2}]]) {
      const settings=JSON.parse(fs.readFileSync(process.env[variable],'utf8'));
      assert.equal(canonical(settings),canonical(viscoelasticSettings(options)));
      const output=immutable({args:{...viscoelasticRequest(options),settings}}),before=JSON.stringify(output);
      await materialBefore(hooks,f,output);assert.equal(JSON.stringify(output),before);
    }
  });

test('ViscoelasticPoints schema5 is separately frozen with exact six tools, MFront image and workload ceilings',async t => {
  assert.equal(nativeViscoelasticDefinition.schema,5);assert.equal(nativeViscoelasticDefinition.profile,'viscoelastic-points-v1');
  assert.deepEqual(nativeViscoelasticDefinition.allowed_tools,nativeMaterialDefinition.allowed_tools);
  assert.deepEqual(nativeViscoelasticDefinition.capabilities.map(c => [c.backend,c.operations,c.cases]),
    [['material.mfront.viscoelastic',['model_analysis_run'],['single_branch_maxwell']]]);
  assert.deepEqual(nativeViscoelasticDefinition.budgets,{steps:24,mcp_timeout_seconds:3600,command_timeout_seconds:3600,
    material_point:{min_history_entries:2,max_history_entries:17,max_signed_probe_states:576,max_request_bytes:65536}});
  assert.equal(nativeViscoelasticDefinition.runtime_environment.CAELAB_MFRONT_IMAGE,
    '/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif');
  assert.equal(nativeViscoelasticDefinition.runtime_environment.CAELAB_MFRONT_IMAGE_SHA256,
    'f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64');
  assert.equal(Object.hasOwn(nativeViscoelasticDefinition.runtime_environment,'CAELAB_CODEASTER_IMAGE'),false);
  assert.equal(Object.isFrozen(nativeViscoelasticDefinition.budgets.material_point),true);
  assert.equal(Object.isFrozen(nativeViscoelasticLimits.finite_difference_steps),true);
  assert.equal(nativeViscoelasticLimits.energy_absolute_mpa,1e-12);
  assert.equal(Object.hasOwn(nativeViscoelasticLimits,'finite_difference_relative'),false);
  const f=viscoelasticResearchFixture(t),hooks=await f.hooks();assert.equal(f.settings.schema,3);
  await hooks['chat.params'](f.request(),immutable({options:{}}));assert.equal(f.receipts().at(-1).accepted,true);
});

test('ViscoelasticPoints admits canonical9/refined17/tau2 and all six existing tools with unchanged physical strain',async t => {
  const f=viscoelasticResearchFixture(t),hooks=await f.hooks();
  for(const options of [{},{refined:true},{relaxation_time_s:2}]) {
    const args=viscoelasticRequest(options),output=immutable({args}),before=JSON.stringify(output);
    await materialBefore(hooks,f,output);assert.equal(JSON.stringify(output),before);assert.equal(f.receipts().at(-1).accepted,true);
    assert.equal((args.settings.history.length-1)*3*6*2,options.refined?576:288);
  }
  for(const [tool,args] of [['caelab_study_create',{study_id:'S-viscoelastic-source-only',title:'Source-only admission'}],
    ['caelab_study_inspect',{study_id:'S-viscoelastic-source-only'}],
    ['caelab_experiment_inspect',{experiment_id:'E-viscoelastic-source-only'}],
    ['caelab_experiment_summary',{experiment_id:'E-viscoelastic-source-only'}],
    ['caelab_experiment_compare',{experiment_ids:['E-viscoelastic-source-only','E-viscoelastic-source-only-tau2']}]]) {
    const output=immutable({args}),before=JSON.stringify(output);
    await hooks['tool.execute.before']({tool,sessionID:f.sessionID},output);
    assert.equal(JSON.stringify(output),before);assert.equal(f.receipts().at(-1).tool,tool);assert.equal(f.receipts().at(-1).accepted,true);
  }
});

test('ViscoelasticPoints admits exactly2 and17 entries plus nullable/supplied hypothesis routing',async t => {
  const f=viscoelasticResearchFixture(t),hooks=await f.hooks();
  for(const [count,hypothesis] of [[2,null],[17,'H-explicit-source-only']]) {
    const args=viscoelasticRequest({refined:true});args.settings.history.length=count;args.hypothesis_id=hypothesis;
    await materialBefore(hooks,f,immutable({args}));assert.equal(f.receipts().at(-1).accepted,true);
  }
});

test('ViscoelasticPoints forwards finite scientific-invalid strain, initial state and dt/tau unchanged to Domain',async t => {
  for(const patch of [a => a.settings.history[2].strain[3]=.02,a => a.settings.history[0].strain[0]=.001,
    a => {a.settings.history[1].time_s=Number.MIN_VALUE;a.settings.material.relaxation_time_s=1e6;}]) {
    const f=viscoelasticResearchFixture(t),hooks=await f.hooks(),args=viscoelasticRequest();patch(args);
    const output=immutable({args}),before=JSON.stringify(output);await materialBefore(hooks,f,output);
    assert.equal(JSON.stringify(output),before);assert.equal(f.receipts().at(-1).accepted,true);
    // Source admission is neither a Domain verdict nor any native execution.
  }
});

for(const [label,patch,code='RESEARCH_ARGUMENTS_REQUIRED'] of [
  ['SVK backend',a => a.backend='material.mfront.hyperelastic','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['other backend',a => a.backend='material.mfront','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['SVK case',a => a.settings.case='saint_venant_kirchhoff','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['missing settings',a => delete a.settings],['missing setting',a => delete a.settings.temperature_k],
  ['extra setting',a => a.settings.deformation_gradient=[1,1,1]],['extra outer key',a => a.request_id='x'],
  ['empty study',a => a.study_id=' '],['empty experiment',a => a.experiment_id=''],['boolean hypothesis',a => a.hypothesis_id=true],
  ['extra SVK material',a => a.settings.material.youngs_modulus_mpa=210000],
  ['missing branch modulus',a => delete a.settings.material.branch_bulk_modulus_mpa],
  ['string modulus',a => a.settings.material.equilibrium_bulk_modulus_mpa='1000'],
  ['boolean modulus',a => a.settings.material.equilibrium_shear_modulus_mpa=true],
  ['nonfinite modulus',a => a.settings.material.branch_shear_modulus_mpa=Infinity],
  ['below modulus bound',a => a.settings.material.branch_bulk_modulus_mpa=1e-7],
  ['above modulus bound',a => a.settings.material.branch_bulk_modulus_mpa=1e9+1],
  ['below tau bound',a => a.settings.material.relaxation_time_s=0],['above tau bound',a => a.settings.material.relaxation_time_s=1e6+1],
  ['string temperature',a => a.settings.temperature_k='293.15'],['zero temperature',a => a.settings.temperature_k=0],
  ['above temperature bound',a => a.settings.temperature_k=5001],
  ['SVK energy absolute limit',a => a.settings.limits.energy_absolute_mpa=1e-10],
  ['SVK extra FD relative limit',a => a.settings.limits.finite_difference_relative=1e-6],
  ['missing fixed limit',a => delete a.settings.limits.tangent_relative],
  ['relaxed stress limit',a => a.settings.limits.stress_relative=1e-7],
  ['reversed FD order',a => a.settings.limits.finite_difference_steps.reverse()],
  ['omitted FD step',a => a.settings.limits.finite_difference_steps.pop()],
  ['string FD step',a => a.settings.limits.finite_difference_steps[0]='1e-7'],
  ['one history entry',a => a.settings.history.length=1,'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['eighteen entries',a => {a.settings=viscoelasticSettings({refined:true});a.settings.history.push({time_s:5,strain:[0,0,0,0,0,0]});},'RESEARCH_WORK_BUDGET_EXCEEDED'],
  ['extra history field',a => a.settings.history[2].dt_s=.8],['nonzero first time',a => a.settings.history[0].time_s=.1],
  ['duplicate time',a => a.settings.history[2].time_s=.2],['reversed time',a => a.settings.history[2].time_s=.1],
  ['string time',a => a.settings.history[1].time_s='.2'],['nonfinite time',a => a.settings.history[1].time_s=NaN],
  ['overbound time',a => a.settings.history[8].time_s=1e6+1],
  ['short strain',a => a.settings.history[2].strain.pop()],['F9 in strain',a => a.settings.history[2].strain.push(0,0,0)],
  ['sparse physical strain',a => delete a.settings.history[2].strain[3]],
  ['string strain',a => a.settings.history[2].strain[3]='.0004'],['boolean strain',a => a.settings.history[2].strain[3]=false],
  ['nonfinite strain',a => a.settings.history[2].strain[3]=Infinity],
]) test(`ViscoelasticPoints refuses ${label} before dispatch and preserves original arguments`,async t => {
  const f=viscoelasticResearchFixture(t),hooks=await f.hooks(),args=viscoelasticRequest();patch(args);
  const before=structuredClone(args);await assert.rejects(materialBefore(hooks,f,{args}),refusal(code),label);
  assert.deepEqual(args,before);assert.equal(f.receipts().at(-1).accepted,false);
});

test('ViscoelasticPoints exact parsed UTF8 cap admits65536 and rejects65537 without a raw-wire claim',async t => {
  const f=viscoelasticResearchFixture(t),hooks=await f.hooks(),args=viscoelasticRequest({refined:true});
  args.hypothesis_id='가'.repeat(100);args.hypothesis_id+='x'.repeat(65536-Buffer.byteLength(JSON.stringify(args),'utf8'));
  assert.equal(Buffer.byteLength(JSON.stringify(args),'utf8'),65536);await materialBefore(hooks,f,immutable({args}));
  const tooLarge=structuredClone(args);tooLarge.hypothesis_id+='x';
  await assert.rejects(materialBefore(hooks,f,immutable({args:tooLarge})),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
});

test('ViscoelasticPoints exact descriptor rejects schema/case/runtime/tool/capability/budget drift before hooks load',async t => {
  for(const patch of [d => d.schema=4,d => d.schema=6,d => d.profile='ViscoelasticPoints',d => d.profile='viscoelastic-points-v2',
    d => d.agent='caelab-acceptance',d => d.kind='other',d => d.allowed_tools.push('caelab_research_job_start'),
    d => d.capabilities[0].backend='material.mfront.hyperelastic',d => d.capabilities[0].cases.push('other_law'),
    d => d.capabilities[0].operations.push('optimization_run'),d => d.runtime_environment.CAELAB_MFRONT_IMAGE='/other.sif',
    d => d.runtime_environment.CAELAB_MFRONT_IMAGE_SHA256='0'.repeat(64),d => d.runtime_environment.OMP_NUM_THREADS='4',
    d => d.runtime_environment.CAELAB_SINGULARITY_COMMAND='/other/singularity',
    ...['steps','mcp_timeout_seconds','command_timeout_seconds'].map(key => d => d.budgets[key]++),
    ...Object.keys(nativeViscoelasticDefinition.budgets.material_point).map(key => d => d.budgets.material_point[key]++),
  ]) {
    const f=viscoelasticResearchFixture(t);patch(f.settings.research);json(f.settingsPath,f.settings);
    await assert.rejects(f.hooks(),refusal('RESEARCH_DEFINITION_INVALID'));
  }
});

test('Historical scopes including MaterialPoints stay closed to Maxwell; ViscoelasticPoints exposes no new jobs/search/register/PDE',async t => {
  for(const make of [researchFixture,structuralResearchFixture,pdeResearchFixture,materialResearchFixture]) {
    const f=make(t),hooks=await f.hooks();
    await assert.rejects(hooks['tool.execute.before']({tool:'caelab_model_analysis_run',sessionID:f.sessionID},{args:viscoelasticRequest()}),
      refusal([structuralResearchFixture,materialResearchFixture].includes(make)?'RESEARCH_CAPABILITY_NOT_ADMITTED':'TOOL_NOT_ALLOWED'));
  }
  const f=viscoelasticResearchFixture(t),hooks=await f.hooks();
  for(const tool of ['caelab_research_job_start','caelab_research_job_cancel','caelab_model_optimization_plan',
    'caelab_model_parameters_register','caelab_parameters_register','caelab_optimization_run','caelab_pde_run'])
    await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args:{}}),refusal('TOOL_NOT_ALLOWED'));
});

test('ViscoelasticPoints retains existing latest source/session/grant/config/settings/Stop/no-tools/required-stage boundaries',async t => {
  for(const [drift,code] of [['source','SOURCE_IMPORTABLE_CHANGED'],['session','PROJECT_SESSION_CHANGED'],
    ['grant','PROJECT_GRANT_CHANGED'],['config','CONFIG_CHANGED'],['settings','SETTINGS_CHANGED'],
    ['stopping','RUNTIME_STOPPING'],['no_tools','NO_TOOLS_STAGE'],['required','REQUIRED_TOOL_MISMATCH']]) {
    const f=viscoelasticResearchFixture(t),load=f.dependencies.loadFilesystem;
    if(drift==='session') {
      const get=f.pluginInput.client.session.get;
      f.pluginInput.client.session.get=async(...args) => {const response=await get(...args);if(f.counts.session===2) response.data.projectID='prj_foreign';return response;};
    }
    f.dependencies.loadFilesystem=async(...args) => {
      const data=await load(...args);
      if(f.counts.filesystem===2) {
        if(drift==='source') fs.writeFileSync(path.join(f.repo,'new_maxwell.py'),'SECRET UNPINNED IMPORT');
        if(drift==='grant') {f.state.filesystem.grants[0].access='read';data.grants[0].access='read';}
        if(drift==='config') fs.appendFileSync(f.settings.configPath,' ');
        if(drift==='settings') fs.appendFileSync(f.settingsPath,' ');
        if(drift==='stopping') f.writeGuard({stopping:true});
        if(drift==='no_tools') f.writeGuard({no_tools:true});
        if(drift==='required') f.writeGuard({required:'caelab_study_inspect'});
      }
      return data;
    };
    const hooks=await f.hooks();await assert.rejects(materialBefore(hooks,f,immutable({args:viscoelasticRequest()})),refusal(code),drift);
    assert.equal(f.receipts().at(-1).accepted,false);assert.equal(JSON.stringify(f.receipts()).includes('SECRET'),false);
  }
});

test('ViscoelasticPoints retains selected5.6Sol and refuses late model/provider change without fallback',async t => {
  for(const patch of [r => r.model.id='other-model',r => r.model.providerID='ollama']) {
    const f=viscoelasticResearchFixture(t),request=f.request(),load=f.dependencies.loadFilesystem;
    f.dependencies.loadFilesystem=async(...args) => {const data=await load(...args);if(f.counts.filesystem===2) patch(request);return data;};
    const hooks=await f.hooks();await assert.rejects(hooks['chat.params'](request,immutable({options:{}})),refusal('MODEL_CHANGED'));
    assert.equal(f.receipts().at(-1).accepted,false);
  }
});


// ContactPatches source-only admission. All responses below are mock metadata;
// the canonical inputs and scientific-invalid rejections come from actual pure
// Domain code in the supplied source receipt. No response field is fabricated.
const contactResearchFixture = (t,definition=nativeContactDefinition) => materialResearchFixture(t,definition);
// Default unit-test discovery must not require private external evidence. These
// fallback values are synthetic REQUEST INPUTS only, never native responses or
// a claimed Domain verdict. External PS/Domain proof tests are explicitly skipped
// unless their independently captured source receipts are supplied.
const contactDomain = process.env.CAELAB_CONTACT_DOMAIN_FIXTURE_PATH
  ? JSON.parse(fs.readFileSync(process.env.CAELAB_CONTACT_DOMAIN_FIXTURE_PATH,'utf8')) : null;
const contactMockOriginal = {case:'ssnp121a_frictionless_patch',material:{youngs_modulus_pa:2e6,poisson_ratio:0},
  top_displacement_m:-.1,limits:{reference_relative:.01,force_balance_relative:1e-6}};
const contactMockCanonical = {original:contactMockOriginal,
  uniform2:{...structuredClone(contactMockOriginal),mesh_variant:'uniform_quad4_2x'}};
const contactDomainCases = contactDomain?.scientific_invalid ?? ['E below','E above','E negative','nu nonzero',
  'DY zero','DY positive','DY too small','DY too large'].map(label => ({label}));
const contactRequest = (variant='original') => ({study_id:'S-contact-source-only',experiment_id:'E-contact-'+variant,
  backend:'structural.code_aster.contact_patch',settings:structuredClone((contactDomain?.canonical ?? contactMockCanonical)[variant])});

test('ContactPatches actual PS descriptor and pure Domain original/refined settings agree',
  {skip:(!contactDomain || !process.env.CAELAB_CONTACT_RESEARCH_DEFINITION_PATH) && 'External actual PS/pure Domain source receipts were not supplied.'},async t => {
  const definition=JSON.parse(fs.readFileSync(process.env.CAELAB_CONTACT_RESEARCH_DEFINITION_PATH,'utf8'));
  assert.equal(canonical(definition),canonical(nativeContactDefinition));
  assert.equal(canonical(contactDomain.fixed_limits),canonical(nativeContactLimits));
  assert.equal(contactDomain.native_calls,0);assert.equal(contactDomain.provider_calls,0);
  assert.match(contactDomain.source_sha256,/^[0-9a-f]{64}$/);
  assert.equal(Object.isFrozen(nativeContactDefinition.budgets.contact_patch),true);
  assert.equal(Object.isFrozen(nativeContactLimits),true);
  for(const variant of ['original','uniform2']) {
    const f=contactResearchFixture(t,definition),hooks=await f.hooks();
    const output=immutable({args:contactRequest(variant)}),before=JSON.stringify(output);
    await materialBefore(hooks,f,output);assert.equal(JSON.stringify(output),before);
    assert.equal(f.settings.schema,3);assert.equal(f.receipts().at(-1).accepted,true);
  }
  assert.equal(Object.hasOwn(contactDomain.canonical.original,'mesh_variant'),false);
  assert.equal(contactDomain.canonical.uniform2.mesh_variant,'uniform_quad4_2x');
});

const contactSixArgs = {
  caelab_study_create:{study_id:'S-contact-source-only',name:'contact',research_question:'same conditions?',hypothesis:'refinement reduces errors',objective:'compare actual signed samples'},
  caelab_study_inspect:{study_id:'S-contact-source-only'},
  caelab_model_analysis_run:contactRequest(),
  caelab_experiment_inspect:{experiment_id:'E-contact-original'},
  caelab_experiment_summary:{experiment_id:'E-contact-original'},
  caelab_experiment_compare:{experiment_ids:['E-contact-original','E-contact-uniform2']},
};
for(const [tool,args] of Object.entries(contactSixArgs)) {
  test('ContactPatches admits exact unchanged '+tool,async t => {
    const f=contactResearchFixture(t),hooks=await f.hooks(),output=immutable({args:structuredClone(args)}),before=JSON.stringify(output);
    await hooks['tool.execute.before']({tool,sessionID:f.sessionID},output);
    assert.equal(JSON.stringify(output),before);assert.equal(f.receipts().at(-1).accepted,true);
  });
  test('ContactPatches refuses extra path/code argument for '+tool,async t => {
    const f=contactResearchFixture(t),hooks=await f.hooks(),wrong={...structuredClone(args),code:'solver(path)'};
    await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args:wrong}),refusal('RESEARCH_ARGUMENTS_REQUIRED'));
  });
}

for(const item of contactDomainCases) {
  test('ContactPatches forwards finite Domain-invalid '+item.label+' unchanged',
    {skip:!contactDomain && 'Actual pure Domain source rejection receipt was not supplied.'},async t => {
    assert.equal(item.domain_preflight,'REJECTED_PURE_SETTINGS');assert.equal(item.native_calls,0);
    assert.ok(item.reason.length>0);
    const f=contactResearchFixture(t),hooks=await f.hooks(),args=contactRequest();args.settings=structuredClone(item.settings);
    const output=immutable({args}),before=JSON.stringify(output);
    await materialBefore(hooks,f,output);assert.equal(JSON.stringify(output),before);assert.equal(f.receipts().at(-1).accepted,true);
  });
}

for(const [label,patch,code='RESEARCH_ARGUMENTS_REQUIRED'] of [
  ['missing settings',a => delete a.settings],['null settings',a => a.settings=null],['extra outer',a => a.path='/tmp/file'],
  ['empty study',a => a.study_id=' '],['bool experiment',a => a.experiment_id=true],['bool hypothesis',a => a.hypothesis_id=true],
  ['foreign backend',a => a.backend='structural.families.code_aster','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['foreign case',a => a.settings.case='CGS1','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['missing material',a => delete a.settings.material],['null material',a => a.settings.material=null],
  ['extra settings path',a => a.settings.mesh_path='/tmp/mesh.mmed'],['extra settings code',a => a.settings.code='STAT_NON_LINE()'],
  ['extra material',a => a.settings.material.density=1],['missing E',a => delete a.settings.material.youngs_modulus_pa],
  ['string E',a => a.settings.material.youngs_modulus_pa='2000000'],['bool E',a => a.settings.material.youngs_modulus_pa=true],
  ['infinite E',a => a.settings.material.youngs_modulus_pa=Infinity],['NaN nu',a => a.settings.material.poisson_ratio=NaN],
  ['null nu',a => a.settings.material.poisson_ratio=null],['bool DY',a => a.settings.top_displacement_m=false],
  ['nonfinite DY',a => a.settings.top_displacement_m=-Infinity],['missing DY',a => delete a.settings.top_displacement_m],
  ['missing limits',a => delete a.settings.limits],['extra limit',a => a.settings.limits.residual=2e-8],
  ['reference drift',a => a.settings.limits.reference_relative=.011],['balance drift',a => a.settings.limits.force_balance_relative=1e-5],
  ['bool limit',a => a.settings.limits.reference_relative=true],['string limit',a => a.settings.limits.force_balance_relative='0.000001'],
  ['null selector',a => a.settings.mesh_variant=null,'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['bool selector',a => a.settings.mesh_variant=true,'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['explicit original selector',a => a.settings.mesh_variant='original','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['arbitrary level selector',a => a.settings.mesh_variant=4,'RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['selector case drift',a => a.settings.mesh_variant='Uniform_quad4_2x','RESEARCH_CAPABILITY_NOT_ADMITTED'],
  ['selector path',a => a.settings.mesh_variant='../mesh','RESEARCH_CAPABILITY_NOT_ADMITTED'],
]) test('ContactPatches refuses '+label,async t => {
  const f=contactResearchFixture(t),hooks=await f.hooks(),args=contactRequest();patch(args);
  await assert.rejects(materialBefore(hooks,f,immutable({args})),refusal(code));assert.equal(f.receipts().at(-1).accepted,false);
});

test('ContactPatches permits nullable hypothesis without filling omitted settings',async t => {
  const f=contactResearchFixture(t),hooks=await f.hooks(),args=contactRequest();args.hypothesis_id=null;
  const output=immutable({args}),before=JSON.stringify(output);await materialBefore(hooks,f,output);assert.equal(JSON.stringify(output),before);
});
test('ContactPatches applies UTF8 parsed-request bound exactly at 16384 and rejects overflow',async t => {
  const f=contactResearchFixture(t),hooks=await f.hooks();
  const args=structuredClone(contactSixArgs.caelab_study_create);
  args.research_question='한'.repeat(5000);let size=Buffer.byteLength(JSON.stringify(args),'utf8');
  assert.ok(size<16384);args.research_question+='x'.repeat(16384-size);
  assert.equal(Buffer.byteLength(JSON.stringify(args),'utf8'),16384);
  await hooks['tool.execute.before']({tool:'caelab_study_create',sessionID:f.sessionID},immutable({args}));
  const overflow=structuredClone(args);overflow.research_question+='한';
  await assert.rejects(hooks['tool.execute.before']({tool:'caelab_study_create',sessionID:f.sessionID},{args:overflow}),refusal('RESEARCH_WORK_BUDGET_EXCEEDED'));
});

for(const [label,patch] of [
  ['schema',d => d.schema=5],['profile',d => d.profile='ContactPatches'],['kind',d => d.kind+='x'],['agent',d => d.agent='other'],
  ['extra key',d => d.extra=1],['tool7',d => d.allowed_tools.push('caelab_pde_run')],['tools order',d => d.allowed_tools.reverse()],
  ['backend',d => d.capabilities[0].backend='structural.families.code_aster'],['case',d => d.capabilities[0].cases=['CGS1']],
  ['capability text',d => d.capabilities[0].evidence+='x'],['limitations text',d => d.limitations[0]+='x'],
  ['runtime OMP',d => d.runtime_environment.OMP_NUM_THREADS='2'],['runtime image',d => d.runtime_environment.CAELAB_CODEASTER_IMAGE+='x'],
  ['image SHA',d => d.runtime_environment.CAELAB_CODEASTER_IMAGE_SHA256='0'.repeat(64)],
  ['steps',d => d.budgets.steps=23],['command timeout',d => d.budgets.command_timeout_seconds=3601],['MCP timeout',d => d.budgets.mcp_timeout_seconds=3599],
  ...Object.keys(nativeContactDefinition.budgets.contact_patch).map(key => ['budget '+key,d => d.budgets.contact_patch[key]++]),
]) test('ContactPatches exact canonical descriptor refuses '+label,async t => {
  const f=contactResearchFixture(t);patch(f.settings.research);json(f.settingsPath,f.settings);
  await assert.rejects(f.hooks(),refusal('RESEARCH_DEFINITION_INVALID'));
});

test('ContactPatches keeps every historical scope closed and exposes no extra job/search/PDE tool',async t => {
  for(const make of [researchFixture,structuralResearchFixture,pdeResearchFixture,materialResearchFixture,viscoelasticResearchFixture]) {
    const f=make(t),hooks=await f.hooks();
    await assert.rejects(materialBefore(hooks,f,{args:contactRequest()}),refusal([structuralResearchFixture,materialResearchFixture,viscoelasticResearchFixture].includes(make)?'RESEARCH_CAPABILITY_NOT_ADMITTED':'TOOL_NOT_ALLOWED'));
  }
  const f=contactResearchFixture(t),hooks=await f.hooks();
  for(const tool of ['caelab_research_job_start','caelab_research_job_cancel','caelab_parameters_register','caelab_optimization_run','caelab_pde_run'])
    await assert.rejects(hooks['tool.execute.before']({tool,sessionID:f.sessionID},{args:{}}),refusal('TOOL_NOT_ALLOWED'));
});

for(const [drift,code] of [['source','SOURCE_IMPORTABLE_CHANGED'],['session','PROJECT_SESSION_CHANGED'],
  ['grant','PROJECT_GRANT_CHANGED'],['project','PROJECT_FILESYSTEM_CHANGED'],['config','CONFIG_CHANGED'],['settings','SETTINGS_CHANGED'],
  ['stopping','RUNTIME_STOPPING'],['no_tools','NO_TOOLS_STAGE'],['required','REQUIRED_TOOL_MISMATCH']]) {
  test('ContactPatches retains late '+drift+' refusal',async t => {
    const f=contactResearchFixture(t),load=f.dependencies.loadFilesystem;
    if(drift==='session') {
      const get=f.pluginInput.client.session.get;
      f.pluginInput.client.session.get=async(...args) => {const response=await get(...args);if(f.counts.session===2) response.data.projectID='prj_foreign';return response;};
    }
    f.dependencies.loadFilesystem=async(...args) => {
      const data=await load(...args);
      if(f.counts.filesystem===2) {
        if(drift==='source') fs.writeFileSync(path.join(f.repo,'unadmitted_contact.py'),'UNPINNED SOURCE TEST DATA');
        if(drift==='grant') {f.state.filesystem.grants[0].access='read';data.grants[0].access='read';}
        if(drift==='project') {f.state.filesystem.projectID='prj_foreign';data.projectID='prj_foreign';}
        if(drift==='config') fs.appendFileSync(f.settings.configPath,' ');
        if(drift==='settings') fs.appendFileSync(f.settingsPath,' ');
        if(drift==='stopping') f.writeGuard({stopping:true});
        if(drift==='no_tools') f.writeGuard({no_tools:true});
        if(drift==='required') f.writeGuard({required:'caelab_study_inspect'});
      }
      return data;
    };
    const hooks=await f.hooks();await assert.rejects(materialBefore(hooks,f,immutable({args:contactRequest()})),refusal(code));
    assert.equal(f.receipts().at(-1).accepted,false);
  });
}
for(const [label,patch] of [['model',r => r.model.id='other-model'],['provider',r => r.model.providerID='ollama']])
test('ContactPatches selected5.6Sol late '+label+' change is refused',async t => {
  const f=contactResearchFixture(t),request=f.request(),load=f.dependencies.loadFilesystem;
  f.dependencies.loadFilesystem=async(...args) => {const data=await load(...args);if(f.counts.filesystem===2) patch(request);return data;};
  const hooks=await f.hooks();await assert.rejects(hooks['chat.params'](request,immutable({options:{}})),refusal('MODEL_CHANGED'));
});
