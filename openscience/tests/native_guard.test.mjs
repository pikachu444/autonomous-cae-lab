import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const modulePath = fileURLToPath(new URL('../native_guard.mjs', import.meta.url));
const source = fs.readFileSync(modulePath, 'utf8');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
// This prefix substitutes only the independently tested existing Git snapshot
// implementation. The guard itself runs unchanged against real fixture files.
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
`;
const temporarySource = `${prefix}\n${source}\nexport { createNativeHooks, NativeGuardRefusal };\n`;
const { createNativeHooks, NativeGuardRefusal } = await import(`data:text/javascript;base64,${Buffer.from(temporarySource).toString('base64')}`);
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
const input = () => ({ sessionID: 'ses_synthetic-01', agent: 'research', model: { providerID: 'openai-codex', id: 'test-explicit-model' } });
const refusal = code => error => error.name === 'CaeLabNativeGuardRefusal' && error.code === code && !error.message.includes('synthetic snapshot');
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
  assert.deepEqual(Object.keys(check).sort(), ['capture', 'compare']);
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
  assert.ok(path.relative(f.profile, inside) && !path.relative(f.profile, inside).startsWith('..'));
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
  const f = fixture(t), hooks = f.hooks();
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
  const f = fixture(t), hooks = f.hooks();
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
  const f = fixture(t), hooks = f.hooks();
  f.writeGuard({ no_tools: true });
  await hooks['chat.params'](input(), immutable({}));
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, { args: {} }), refusal('NO_TOOLS_STAGE'));
  assert.equal(f.receipts().at(-1).accepted, false);
});

test('provider and model drift reject a logical stream', async t => {
  const f = fixture(t), hooks = f.hooks();
  for (const model of [undefined, { providerID: 'openai', id: 'test-explicit-model' },
    { providerID: 'openai-codex', id: 'other-model' }, { providerID: 'openai-codex', id: 'openai-codex/test-explicit-model' }]) {
    await assert.rejects(hooks['chat.params']({ ...input(), model }, {}), refusal('MODEL_CHANGED'));
  }
  assert.equal(f.receipts().filter(item => item.status === 'rejected').length, 4);
});

test('unexpected agents cannot stream', async t => {
  const f = fixture(t), hooks = f.hooks();
  for (const agent of ['title', 'general', { name: 'unknown' }, null])
    await assert.rejects(hooks['chat.params']({ ...input(), agent }, {}), refusal('AGENT_NOT_ALLOWED'));
});

test('actual tools obey the selected subset and exact required stage', async t => {
  const f = fixture(t, tools.slice(0, 2)), hooks = f.hooks();
  await hooks['tool.execute.before']({ tool: tools[0] }, { args: {} });
  for (const tool of ['shell', tools[5], null])
    await assert.rejects(hooks['tool.execute.before']({ tool }, { args: {} }), refusal('TOOL_NOT_ALLOWED'));
  f.writeGuard({ required: tools[0] });
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[1] }, { args: {} }), refusal('REQUIRED_TOOL_MISMATCH'));
});

test('stopping blocks both hooks without further source capture', async t => {
  const f = fixture(t), hooks = f.hooks(), before = f.counts.capture;
  f.writeGuard({ stopping: true });
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('RUNTIME_STOPPING'));
  await assert.rejects(hooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('RUNTIME_STOPPING'));
  assert.equal(f.counts.capture, before);
});

test('source and Git executable drift fail before actual tool execution', async t => {
  const f = fixture(t), hooks = f.hooks();
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
  const hooks = f.hooks();
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
  const hooks = f.hooks();
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

test('failed initial source capture retains a sanitized load refusal and yields no hooks', t => {
  const f = fixture(t);
  f.dependencies.capture = () => { throw Object.assign(new Error('SECRET INITIAL CAPTURE SENTINEL'), {
    code: 'ETIMEDOUT', stdout: 'SECRET INITIAL STDOUT SENTINEL', stderr: 'SECRET INITIAL STDERR SENTINEL',
  }); };
  assert.throws(f.hooks, error => {
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
  const hooks = f.hooks();
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
    const f = fixture(t), hooks = f.hooks();
    fs.appendFileSync(field === 'settingsPath' ? f.settingsPath : f.settings[field], '\n');
    await assert.rejects(hooks['chat.params'](input(), {}), refusal(code));
    assert.equal(f.receipts().at(-1).code, code);
  });
}

test('settings schema, model, tools, boot hash and confined paths are mandatory', t => {
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
    assert.throws(() => createNativeHooks(value, f.dependencies), error => error.name === 'CaeLabNativeGuardRefusal');
  }
  assert.equal(f.counts.capture, 0);
});

test('guard ownership, schema, exact ordered allowed list and state are revalidated', async t => {
  const f = fixture(t), hooks = f.hooks();
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
  const f = fixture(t), hooks = f.hooks();
  const outside = linkedDirectory(f, path.dirname(f.settings.configPath));
  const before = fs.readdirSync(outside);
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('PATH_LINKED'));
  assert.deepEqual(fs.readdirSync(outside), before);
  const g = fixture(t);
  linkedDirectory(g, path.dirname(g.settings.pluginPath));
  assert.throws(g.hooks, refusal('PATH_LINKED'));
  assert.equal(g.counts.capture, 0);
});

test('linked repository and Git executable ancestors fail closed', async t => {
  const f = fixture(t), hooks = f.hooks();
  const target = path.join(f.base, 'outside', 'repo');
  assert.equal(path.dirname(target), path.join(f.base, 'outside'));
  fs.renameSync(f.repo, target);
  fs.symlinkSync(target, f.repo, process.platform === 'win32' ? 'junction' : 'dir');
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('PATH_LINKED'));
  const g = fixture(t), otherHooks = g.hooks();
  const bin = path.join(g.base, 'bin'), otherBin = path.join(g.base, 'outside', 'bin');
  fs.renameSync(bin, otherBin);
  fs.symlinkSync(otherBin, bin, process.platform === 'win32' ? 'junction' : 'dir');
  await assert.rejects(otherHooks['tool.execute.before']({ tool: tools[0] }, {}), refusal('PATH_LINKED'));
});

test('linked receipt destination cannot receive an outside file or permit a stream', async t => {
  const f = fixture(t), hooks = f.hooks();
  const target = linkedDirectory(f, f.settings.receipts), before = fs.readdirSync(target);
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('RECEIPT_UNAVAILABLE'));
  assert.deepEqual(fs.readdirSync(target), before);
});

test('malformed guard and oversized files remain rejection evidence', async t => {
  const f = fixture(t), hooks = f.hooks();
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
  const hooks = createNativeHooks(f.settings, { ...f.dependencies, fs: io });
  fail = true;
  await assert.rejects(hooks['chat.params'](input(), {}), refusal('RECEIPT_UNAVAILABLE'));
});

test('receipt metadata rejects arbitrary session strings and never records message or arguments', async t => {
  const f = fixture(t), hooks = f.hooks();
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
  const f = managedFixture(t), hooks = f.hooks();
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

test('managed binding schema and exact immutable source fields fail closed', t => {
  const f = managedFixture(t), original = structuredClone(f.binding);
  for (const patch of [{ schema: 2 }, { kind: 'foreign' }, { project_id: 'foreign' }, { grant_id: 'foreign' },
    { source_directory: f.profile }, { working_root: f.profile }, { access: 'read' }, { extra: true },
    { project_directory: '.' }]) {
    f.settings.project_binding = { ...original, ...patch };
    json(f.settingsPath, f.settings);
    assert.throws(f.hooks, error => error.name === 'CaeLabNativeGuardRefusal' && officialStatuslessRetry(error) === undefined);
  }
  f.settings.project_binding = original;
  f.settings.schema = 1;
  json(f.settingsPath, f.settings);
  assert.throws(f.hooks, refusal('SETTINGS_INVALID'));
  f.settings.schema = 2;
  delete f.settings.project_binding;
  json(f.settingsPath, f.settings);
  assert.throws(f.hooks, refusal('SETTINGS_INVALID'));
  assert.equal(f.counts.capture, 0); assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
});

test('foreign initial project identity, client shape and non-loopback server are refused before capture', t => {
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
    assert.throws(f.hooks, refusal(code));
    assert.equal(f.counts.capture, 0); assert.equal(f.counts.session, 0); assert.equal(f.counts.filesystem, 0);
    const receipt = f.receipts().at(-1);
    assert.equal(receipt.accepted, false); assert.equal(receipt.project_check.identity, 'FAIL');
    assert.equal(JSON.stringify(receipt).includes('SECRET'), false);
  }
});

test('managed session IDs use the official strict prefix and never reach APIs when malformed', async t => {
  const f = managedFixture(t), hooks = f.hooks();
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
  const f = managedFixture(t), hooks = f.hooks(), original = structuredClone(f.state.session);
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
  const hooks = f.hooks();
  await assert.rejects(hooks['chat.params'](f.request(), {}), refusal('PROJECT_SESSION_CHANGED'));
  assert.equal(foreign.counts.session, 1);
  assert.equal(f.counts.filesystem, 0); assert.equal(f.counts.capture, 1);
});

test('filesystem session, identity and working roots are checked before either hook captures source', async t => {
  const f = managedFixture(t), hooks = f.hooks(), original = structuredClone(f.state.filesystem);
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
  const f = managedFixture(t), hooks = f.hooks(), original = structuredClone(f.state.filesystem.grants[0]);
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
  const hooks = f.hooks();
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
  const hooks = f.hooks();
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
    const f = managedFixture(t), hooks = f.hooks();
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
    const hooks = f.hooks();
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
      const hooks = f.hooks(); active = true;
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
    const hooks = f.hooks();
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
    const hooks = f.hooks(); active = true;
    await assert.rejects(hooks['chat.params'](managed ? f.request() : input(), {}), refusal(code));
    assert.equal(f.counts.capture, 2); assert.equal(f.receipts().at(-1).accepted, false);
  }
});

test('stopping managed hooks skip every metadata read and further source capture', async t => {
  const f = managedFixture(t), hooks = f.hooks();
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
  const hooks = f.hooks();
  await assert.rejects(hooks['chat.params'](f.request(), {}), refusal('PROJECT_SESSION_READ_FAILED'));
  assert.equal(f.counts.capture, 1); assert.equal(f.counts.filesystem, 0);
  assert.equal(f.receipts().at(-1).accepted, false);
});
