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
const temporarySource = `${prefix}\n${source}\nexport { createNativeHooks };\n`;
const { createNativeHooks } = await import(`data:text/javascript;base64,${Buffer.from(temporarySource).toString('base64')}`);
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
const input = () => ({ sessionID: 'ses_synthetic-01', agent: 'research', model: { providerID: 'openai-codex', id: 'test-explicit-model' } });
const refusal = code => error => error.name === 'CaeLabNativeGuardRefusal' && error.code === code && !error.message.includes('synthetic snapshot');
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
