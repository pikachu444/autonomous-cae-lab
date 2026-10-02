import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

// Execute the actual PowerShell-owned helper. Only its imported dependencies are
// injected for observing real Git calls and deterministic filesystem races.
const repository = fileURLToPath(new URL('../../', import.meta.url));
const scriptPath = path.join(repository, 'scripts', 'openscience-server-local.ps1');
const script = fs.readFileSync(scriptPath, 'utf8');
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const excluded = ['artifacts', 'runs', '.venv', 'venv', 'node_modules', '.git', '.pytest_cache', '.mypy_cache', '.ruff_cache'];
const sourcePattern = /^function Get-OpenScienceRepositoryPinSource \{\r?\n[\s\S]*?^[ \t]*@'\r?\n([\s\S]*?)^'@\r?\n\}/m;
function extractSource(text) {
  const match = sourcePattern.exec(text);
  assert.ok(match, 'The actual repository-pin PowerShell helper must be available');
  return match[1];
}
const actualSource = extractSource(script);
let helperSequence = 0;
async function helper({ filesystem = fs, execute = execFileSync, clock = Date, source = actualSource } = {}) {
  const name = `__caelab_source_pin_test_${++helperSequence}`;
  globalThis[name] = { filesystem, execute, clock };
  const imports = [
    ["import sourceFs from 'node:fs';", 'const sourceFs = sourceTestDependencies.filesystem;'],
    ["import {execFileSync as sourceExec} from 'node:child_process';", 'const sourceExec = sourceTestDependencies.execute;'],
  ];
  let body = source;
  for (const [original, replacement] of imports) {
    assert.equal(body.split(original).length, 2, 'Inject only the exact dependency import');
    body = body.replace(original, replacement);
  }
  body = `const sourceTestDependencies = globalThis[${JSON.stringify(name)}];\nconst Date = sourceTestDependencies.clock;\n${body}\nexport { captureRepositorySourcePin, assertRepositorySourcePin, sourcePinSha };`;
  try { return await import(`data:text/javascript;base64,${Buffer.from(body).toString('base64')}`); }
  finally { delete globalThis[name]; }
}
function findGit() {
  if (process.env.CAELAB_SOURCE_PIN_GIT_PATH) return path.resolve(process.env.CAELAB_SOURCE_PIN_GIT_PATH);
  const search = Object.entries(process.env).find(([key]) => key.toUpperCase() === 'PATH')?.[1] ?? '';
  for (const directory of search.split(path.delimiter)) {
    const candidate = path.join(directory.replace(/^"|"$/g, ''), process.platform === 'win32' ? 'git.exe' : 'git');
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return fs.realpathSync(candidate);
  }
  throw new Error('An existing Git executable is required; this test never installs Git');
}
const gitPath = findGit();
const retainedRoot = process.env.CAELAB_SOURCE_PIN_FIXTURE_ROOT && path.resolve(process.env.CAELAB_SOURCE_PIN_FIXTURE_ROOT);
if (retainedRoot) {
  assert.equal(fs.existsSync(retainedRoot), false, 'Use a fresh retained fixture directory');
  fs.mkdirSync(retainedRoot, { recursive: true });
}
function eraseOwned(base, target) {
  const owner = path.resolve(base), resolved = path.resolve(target);
  assert.ok(resolved === owner || resolved.startsWith(owner + path.sep), 'Delete only the explicitly owned synthetic fixture');
  fs.rmSync(resolved, { recursive: true, force: true });
}
function fixture(t, { ignore = '', empty = false } = {}) {
  const base = fs.mkdtempSync(path.join(retainedRoot ?? os.tmpdir(), 'caelab-source-pin-'));
  const root = path.join(base, 'repository'), hooks = path.join(base, 'no-hooks'), excludes = path.join(base, 'empty-excludes');
  fs.mkdirSync(root); fs.mkdirSync(hooks); fs.writeFileSync(excludes, '');
  const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^GIT_/i.test(key)));
  const git = (args, cwd = root) => execFileSync(gitPath, ['-C', cwd,
    '-c', `core.hooksPath=${hooks}`, '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false',
    '-c', 'core.fsmonitor=false', '-c', 'user.name=CAE-Lab Synthetic Test', '-c', 'user.email=synthetic@example.invalid', ...args],
  { encoding: 'utf8', timeout: 10000, maxBuffer: 16 * 1024 * 1024, windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'], env: environment });
  git(['init', '--quiet']);
  git(['config', 'core.excludesFile', excludes]); git(['config', 'core.hooksPath', hooks]); git(['config', 'core.autocrlf', 'false']);
  const put = (relative, bytes = 'SYNTHETIC SOURCE ONLY\n') => {
    const file = path.resolve(root, relative);
    assert.ok(file.startsWith(root + path.sep));
    fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, bytes); return file;
  };
  if (!empty) {
    put('pinned.py', 'VALUE = "source-A"\n'); put('.gitignore', ignore);
    git(['add', '--force', 'pinned.py', '.gitignore']);
  }
  git(['commit', '--quiet', '--allow-empty', '-m', 'Synthetic source fixture']);
  if (!retainedRoot) t.after(() => eraseOwned(base, base));
  return { root, base, git, put, remove: relative => eraseOwned(root, path.resolve(root, relative)) };
}
function observed(afterGit) {
  const calls = [];
  return { calls, execute(file, args, options) {
    const output = execFileSync(file, args, options);
    calls.push({ file, args: [...args], options, output });
    afterGit?.(calls.at(-1)); return output;
  } };
}
const ignoredQueries = calls => calls.filter(call => call.args.includes('--ignored'));
const capture = (module, f) => module.captureRepositorySourcePin(f.root, gitPath);
const importRefusal = /Untracked importable repository source is not pinned/;

test('cold real-Git capture retains two full snapshots, exact literal scopes and bounded clean execution', async t => {
  const f = fixture(t), probe = observed(), module = await helper({ execute: probe.execute });
  const sentinel = 'GIT_CAE_SYNTHETIC_SOURCE_SENTINEL', previous = process.env[sentinel];
  process.env[sentinel] = 'DO_NOT_FORWARD';
  let pin;
  try { pin = capture(module, f); } finally {
    if (previous === undefined) delete process.env[sentinel]; else process.env[sentinel] = previous;
  }
  assert.equal(pin.schema, 1); assert.equal(pin.kind, 'autonomous-cae-lab.repository-source-pin');
  assert.equal(pin.source_commit, f.git(['rev-parse', 'HEAD']).trim());
  assert.equal(pin.git_sha256, digest(fs.readFileSync(gitPath))); assert.deepEqual(pin.source_dirty, []);
  assert.deepEqual(pin.files.map(file => file.path), ['.gitignore', 'pinned.py']);
  assert.equal(pin.files.find(file => file.path === 'pinned.py').sha256, digest(fs.readFileSync(path.join(f.root, 'pinned.py'))));
  assert.match(module.sourcePinSha(pin), /^[0-9a-f]{64}$/);
  const queries = ignoredQueries(probe.calls); assert.equal(queries.length, 2);
  for (const query of queries) {
    assert.deepEqual(query.args.slice(query.args.indexOf('--') + 1), ['.gitignore', 'pinned.py'].map(name => `:(top,literal)${name}`));
  }
  assert.equal(probe.calls.filter(call => call.args.includes('--stage')).length, 4);
  for (const call of probe.calls) {
    assert.equal(call.file, gitPath); assert.ok(call.args.includes('core.fsmonitor=false'));
    assert.ok(call.options.timeout > 0 && call.options.timeout <= 10000);
    assert.equal(call.options.maxBuffer, 16 * 1024 * 1024); assert.equal(call.options.windowsHide, true);
    assert.deepEqual(call.options.stdio, ['ignore', 'pipe', 'pipe']);
    assert.equal(Object.keys(call.options.env).some(key => /^GIT_/i.test(key)), false);
    assert.equal(call.options.shell, undefined);
  }
});

test('ignored imports in fresh allowed roots and root dotfiles reject every suffix under both Git case configurations', async t => {
  const module = await helper();
  for (const ignoreCase of ['false', 'true']) {
    const f = fixture(t, { ignore: '/*\n' }); f.git(['config', 'core.ignorecase', ignoreCase]);
    const baseline = capture(module, f);
    for (const [index, suffix] of ['py', 'pyi', 'pyc', 'pyd', 'so', 'pth', 'PY', 'PyI', 'PYC', 'PYD', 'SO', 'PTH'].entries()) {
      const relative = index % 2 ? `.root-shadow.${suffix}` : `fresh-allowed/shadow.${suffix}`;
      f.put(relative); assert.throws(() => capture(module, f), importRefusal, `${ignoreCase}/${relative}`);
      f.remove(relative);
    }
    module.assertRepositorySourcePin(baseline, capture(module, f));
  }
});

test('ordinary untracked imports remain blocked independently of ignored-import discovery', async t => {
  const f = fixture(t), module = await helper();
  for (const relative of ['ordinary.py', 'package/binding.SO', '.root-hook.PTH']) {
    f.put(relative); assert.throws(() => capture(module, f), importRefusal, relative); f.remove(relative);
  }
});

test('exact top exemptions and lowercase bytecode preserve pins; nested and case-changed exemption names do not', async t => {
  const f = fixture(t, { ignore: '/*\n' }), module = await helper(), baseline = capture(module, f);
  for (const root of excluded) f.put(`${root}/retained.py`);
  f.put('package/__pycache__/cached.pyc');
  module.assertRepositorySourcePin(baseline, capture(module, f));
  for (const root of excluded) f.put(`${root}/retained.py`, 'CHANGED EXEMPT SYNTHETIC BYTES\n');
  module.assertRepositorySourcePin(baseline, capture(module, f));
  for (const relative of ['package/artifacts/shadow.py', 'package/runs/shadow.py', 'package/__pycache__/uppercase_cached.PYC']) {
    f.put(relative); assert.throws(() => capture(module, f), importRefusal, relative); f.remove(relative);
  }
  const upper = fixture(t, { ignore: '/*\n' }); upper.put('Artifacts/shadow.py');
  assert.throws(() => capture(module, upper), importRefusal);
});

test('actual positive literal Git scopes retain bracket, dash, dot, space and Unicode root names', async t => {
  const f = fixture(t, { ignore: '/*\n' }), probe = observed(), module = await helper({ execute: probe.execute });
  for (const root of ['[ab] source', '-leading-dash', '.hidden-allowed', 'space directory', '한글[대괄호]']) {
    f.put(`${root}/shadow.py`);
    assert.throws(() => capture(module, f), importRefusal, root);
    const query = ignoredQueries(probe.calls).at(-1);
    assert.ok(query.args.includes(`:(top,literal)${root}`));
    assert.ok(query.output.split('\0').includes(`${root}/shadow.py`)); f.remove(root);
  }
});

test('POSIX-only colon Git magic and wildcard names cannot widen or evade literal roots', { skip: process.platform === 'win32' }, async t => {
  const f = fixture(t, { ignore: '/*\n' }), probe = observed(), module = await helper({ execute: probe.execute });
  for (const root of [':(exclude)magic', 'star*root', 'question?root', ':literal']) {
    f.put(`${root}/shadow.py`); assert.throws(() => capture(module, f), importRefusal, root);
    const query = ignoredQueries(probe.calls).at(-1);
    assert.ok(query.args.includes(`:(top,literal)${root}`));
    assert.ok(query.output.split('\0').includes(`${root}/shadow.py`)); f.remove(root);
  }
});

test('an empty positive scope never issues a root-wide ignored query', async t => {
  const f = fixture(t, { empty: true }), probe = observed(), module = await helper({ execute: probe.execute });
  fs.writeFileSync(path.join(f.root, '.git', 'info', 'exclude'), '/artifacts/\n/runs/\n');
  f.put('artifacts/retained.py'); f.put('runs/retained.pth');
  const baseline = capture(module, f);
  assert.equal(ignoredQueries(probe.calls).length, 0); assert.deepEqual(baseline.files, []);
  assert.deepEqual(baseline.source_dirty, []);
  f.put('artifacts/retained.py', 'EXEMPT CHANGED\n'); module.assertRepositorySourcePin(baseline, capture(module, f));
  assert.equal(ignoredQueries(probe.calls).length, 0);
});

test('actual root entry addition and removal during the ignored query refuse capture', async t => {
  for (const mutation of ['add', 'remove']) {
    const f = fixture(t, { ignore: '/*\n' }); if (mutation === 'remove') f.put('gone/data.txt');
    let changed = false;
    const probe = observed(call => {
      if (changed || !call.args.includes('--ignored')) return;
      changed = true;
      if (mutation === 'add') f.put('.late-ignored.py'); else f.remove('gone');
    });
    const module = await helper({ execute: probe.execute });
    assert.throws(() => capture(module, f), /Repository changed during source capture/, mutation);
    assert.equal(changed, true); assert.equal(ignoredQueries(probe.calls).length, 1);
  }
});

test('tracked working bytes, staged identity and source HEAD remain part of the exact owned pin', async t => {
  const f = fixture(t), module = await helper(), baseline = capture(module, f);
  f.put('pinned.py', 'VALUE = "source-B"\n');
  const bytes = capture(module, f); assert.equal(bytes.source_commit, baseline.source_commit);
  assert.notEqual(bytes.source_tree_sha256, baseline.source_tree_sha256);
  assert.throws(() => module.assertRepositorySourcePin(baseline, bytes), /differs/);
  f.git(['add', 'pinned.py']); const staged = capture(module, f);
  assert.notEqual(staged.files.find(file => file.path === 'pinned.py').index_object, baseline.files.find(file => file.path === 'pinned.py').index_object);
  assert.throws(() => module.assertRepositorySourcePin(baseline, staged), /differs/);
  f.git(['commit', '--quiet', '-m', 'Synthetic source B']); const committed = capture(module, f);
  assert.notEqual(committed.source_commit, baseline.source_commit);
  assert.throws(() => module.assertRepositorySourcePin(baseline, committed), /differs/);
});

test('two real snapshots reject byte drift even when Git dirty status stays unchanged', async t => {
  const f = fixture(t), target = f.put('pinned.py', 'VALUE = "already-dirty-A"\n'); let changed = false;
  const filesystem = new Proxy(fs, { get(object, name) {
    if (name !== 'readFileSync') return object[name];
    return (file, ...args) => {
      const bytes = object.readFileSync(file, ...args);
      if (!changed && path.resolve(String(file)) === target) { changed = true; f.put('pinned.py', 'VALUE = "already-dirty-B"\n'); }
      return bytes;
    };
  } });
  const module = await helper({ filesystem });
  assert.throws(() => capture(module, f), /Source bytes changed during capture/); assert.equal(changed, true);
});

test('recursive real submodule bytes, HEAD and ignored shadows remain checked', async t => {
  const parent = fixture(t), upstream = fixture(t), module = await helper();
  parent.git(['-c', 'protocol.file.allow=always', 'submodule', 'add', '--quiet', upstream.root, 'plugins/upstream']);
  parent.git(['commit', '--quiet', '-m', 'Synthetic pinned submodule']);
  const child = path.join(parent.root, 'plugins', 'upstream'), file = path.join(child, 'pinned.py');
  const baseline = capture(module, parent), row = baseline.submodules.find(item => item.path === 'plugins/upstream');
  assert.ok(row); assert.equal(row.head, row.index_commit);
  assert.ok(baseline.files.some(item => item.path === 'plugins/upstream/pinned.py'));
  const original = fs.readFileSync(file); fs.writeFileSync(file, 'VALUE = "submodule-drift"\n');
  assert.throws(() => module.assertRepositorySourcePin(baseline, capture(module, parent)), /differs/);
  fs.writeFileSync(file, original); module.assertRepositorySourcePin(baseline, capture(module, parent));
  const gitDirectory = path.resolve(child, parent.git(['rev-parse', '--git-dir'], child).trim());
  fs.appendFileSync(path.join(gitDirectory, 'info', 'exclude'), '\n/allowed/\n');
  fs.mkdirSync(path.join(child, 'allowed')); fs.writeFileSync(path.join(child, 'allowed', 'shadow.PYI'), 'UNPINNED SYNTHETIC IMPORT\n');
  assert.throws(() => capture(module, parent), importRefusal); eraseOwned(parent.base, path.join(child, 'allowed'));
  fs.writeFileSync(file, 'VALUE = "submodule-commit-B"\n'); parent.git(['add', 'pinned.py'], child);
  parent.git(['commit', '--quiet', '-m', 'Synthetic submodule B'], child);
  const current = capture(module, parent), changed = current.submodules.find(item => item.path === 'plugins/upstream');
  assert.notEqual(changed.head, row.head); assert.equal(changed.index_commit, row.index_commit);
  assert.throws(() => module.assertRepositorySourcePin(baseline, current), /differs/);
});

test('tracked linked ancestors and linked repository roots are refused without reading their source', async t => {
  const f = fixture(t), outside = path.join(f.base, 'outside-source'), alias = path.join(f.base, 'linked-repository');
  let linkedReads = 0;
  const filesystem = new Proxy(fs, { get(object, name) {
    if (name !== 'readFileSync') return object[name];
    return (file, ...args) => {
      const absolute = path.resolve(String(file));
      if (absolute.startsWith(path.join(f.root, 'package') + path.sep) || absolute.startsWith(alias + path.sep)) linkedReads++;
      return object.readFileSync(file, ...args);
    };
  } });
  const module = await helper({ filesystem });
  f.put('package/pinned.py', 'VALUE = "linked-source"\n'); f.git(['add', 'package/pinned.py']); f.git(['commit', '--quiet', '-m', 'Synthetic nested source']);
  fs.renameSync(path.join(f.root, 'package'), outside);
  fs.symlinkSync(outside, path.join(f.root, 'package'), process.platform === 'win32' ? 'junction' : 'dir');
  assert.throws(() => capture(module, f), /Linked source is not pinned|Tracked source is missing or unsupported/);
  fs.symlinkSync(f.root, alias, process.platform === 'win32' ? 'junction' : 'dir');
  assert.throws(() => module.captureRepositorySourcePin(alias, gitPath), /Linked source is not pinned|Submodule checkout is unavailable/);
  assert.equal(linkedReads, 0);
});

test('the shared20s deadline and10s subprocess cap stay bounded without wallclock timing assertions', async t => {
  const f = fixture(t); let now = 0, invocations = 0, firstTimeout;
  const module = await helper({ clock: { now: () => now }, execute(file, args, options) {
    invocations++; firstTimeout = options.timeout; const value = execFileSync(file, args, options); now = 20000; return value;
  } });
  assert.throws(() => capture(module, f), /Bounded source snapshot expired/);
  assert.equal(invocations, 1); assert.equal(firstTimeout, 10000);
  let clockReads = 0, remainingTimeout;
  const remaining = await helper({ clock: { now: () => ++clockReads === 1 ? 0 : 15999 }, execute(file, args, options) {
    remainingTimeout = options.timeout; execFileSync(file, args, options); throw new Error('SYNTHETIC stop after actual first Git call');
  } });
  assert.throws(() => capture(remaining, f), /SYNTHETIC stop/); assert.equal(remainingTimeout, 4001);
});

test('optional actual historical helper preserves lowercase admission and pins without weakening uppercase refusal',
  { skip: !process.env.CAELAB_SOURCE_PIN_BASELINE_SCRIPT }, async t => {
    const baselineSource = extractSource(fs.readFileSync(process.env.CAELAB_SOURCE_PIN_BASELINE_SCRIPT, 'utf8'));
    const old = await helper({ source: baselineSource }), current = await helper(), f = fixture(t, { ignore: '/*\n' });
    assert.notEqual(digest(baselineSource), digest(actualSource), 'Compare actual distinct historical/current source bodies');
    for (const root of excluded) f.put(`${root}/retained.py`);
    f.put('package/__pycache__/cached.pyc'); f.put('[ab] source/nonimport.txt');
    old.assertRepositorySourcePin(capture(old, f), capture(current, f));
    for (const relative of ['fresh-allowed/shadow.py', '.root-shadow.pyi', '[ab] source/shadow.pyd', '-dash/shadow.so', '.hidden/shadow.pth', 'package/shadow.pyc']) {
      f.put(relative); assert.throws(() => capture(old, f), importRefusal, relative);
      assert.throws(() => capture(current, f), importRefusal, relative); f.remove(relative);
    }
    f.put('fresh-allowed/UPPER.PY');
    let oldRejected = false;
    try { capture(old, f); } catch (error) { assert.match(error.message, importRefusal); oldRejected = true; }
    assert.throws(() => capture(current, f), importRefusal);
    t.diagnostic(oldRejected ? 'Actual historical Git query also rejects ignored uppercase imports.'
      : 'Current capture additionally rejects ignored uppercase imports missed by the actual historical Git query.');
  });
