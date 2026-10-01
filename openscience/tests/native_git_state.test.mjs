import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import test from 'node:test';

const helper = fs.readFileSync(new URL('../native_git_state.mjs', import.meta.url), 'utf8');
const { captureNativeGitState, assertNativeGitState } = await import(`data:text/javascript;base64,${Buffer.from(helper + '\nexport { captureNativeGitState, assertNativeGitState };').toString('base64')}`);
const gitPath = process.platform === 'win32'
  ? execFileSync('where.exe', ['git.exe'], { encoding: 'utf8' }).trim().split(/\r?\n/)[0]
  : execFileSync('which', ['git'], { encoding: 'utf8' }).trim();
const git = (root, ...args) => execFileSync(gitPath, ['-C', root, '-c', 'core.fsmonitor=false', ...args],
  { encoding: 'utf8', timeout: 10000, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] }).trim();
function fixture(t) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'caelab-git-state-')), root = path.join(base, 'repo');
  fs.mkdirSync(root);
  t.after(() => {
    assert.equal(path.dirname(path.resolve(base)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(base).startsWith('caelab-git-state-'));
    fs.rmSync(base, { recursive: true, force: true });
  });
  git(root, 'init', '-b', 'test-main');
  git(root, 'config', 'user.name', 'Synthetic Test'); git(root, 'config', 'user.email', 'test@example.invalid');
  fs.writeFileSync(path.join(root, 'source.txt'), 'same source bytes\n');
  git(root, 'add', 'source.txt'); git(root, 'commit', '-m', 'synthetic fixture');
  return { base, root, capture: () => captureNativeGitState(root, [], gitPath) };
}

test('real normal checkout captures and synchronously rechecks complete admin state', t => {
  const f = fixture(t), state = f.capture();
  assertNativeGitState(f.root, [], state);
  assert.deepEqual(state.repositories[0].entries.map(entry => entry.slot),
    ['git-pointer', 'HEAD', 'index', 'config', 'config.worktree', 'commondir', 'info/exclude', 'info/sparse-checkout']);
  assert.equal(state.repositories[0].refs[0].ref, 'refs/heads/test-main');
  assert.equal(JSON.stringify(state).includes('test@example.invalid'), false);
});
test('same-byte staged mode/index change is rejected after capture', t => {
  const f = fixture(t), state = f.capture(), before = fs.readFileSync(path.join(f.root, 'source.txt'));
  git(f.root, 'update-index', '--chmod=+x', 'source.txt');
  assert.deepEqual(fs.readFileSync(path.join(f.root, 'source.txt')), before);
  assert.throws(() => assertNativeGitState(f.root, [], state), /Native Git state refused/);
});
test('symbolic HEAD target changes are rejected even though HEAD and source bytes stay identical', t => {
  const f = fixture(t), state = f.capture(), head = fs.readFileSync(path.join(f.root, '.git', 'HEAD'));
  git(f.root, 'commit', '--allow-empty', '-m', 'same tree different source commit');
  assert.deepEqual(fs.readFileSync(path.join(f.root, '.git', 'HEAD')), head);
  assert.throws(() => assertNativeGitState(f.root, [], state), /Native Git state refused/);
});
test('detached managed worktree rejects its own HEAD drift and permits unrelated main commits', t => {
  const f = fixture(t), serving = path.join(f.base, 'serving');
  git(f.root, 'worktree', 'add', '--detach', serving, 'HEAD');
  const state = captureNativeGitState(serving, [], gitPath);
  git(f.root, 'commit', '--allow-empty', '-m', 'unrelated main checkpoint');
  assertNativeGitState(serving, [], state);
  git(serving, 'checkout', '--detach', 'test-main');
  assert.throws(() => assertNativeGitState(serving, [], state), /Native Git state refused/);
});
test('packed own HEAD reference is checked without blocking unrelated packed references', t => {
  const f = fixture(t);
  git(f.root, 'pack-refs', '--all', '--prune');
  const state = f.capture(), packed = path.join(f.root, '.git', 'packed-refs');
  fs.appendFileSync(packed, `${'b'.repeat(40)} refs/heads/unrelated\n`);
  assertNativeGitState(f.root, [], state);
  fs.writeFileSync(packed, fs.readFileSync(packed, 'utf8').replace(/^[0-9a-f]{40} refs\/heads\/test-main$/m, `${'c'.repeat(40)} refs/heads/test-main`));
  assert.throws(() => assertNativeGitState(f.root, [], state), /Native Git state refused/);
});
test('real local submodule pointer/admin state is checked in addition to the parent', t => {
  const f = fixture(t), upstream = path.join(f.base, 'upstream'); fs.mkdirSync(upstream);
  git(upstream, 'init', '-b', 'fixture'); git(upstream, 'config', 'user.name', 'Synthetic Test'); git(upstream, 'config', 'user.email', 'test@example.invalid');
  fs.writeFileSync(path.join(upstream, 'source.txt'), 'fixture source\n');
  git(upstream, 'add', '.'); git(upstream, 'commit', '-m', 'fixture');
  git(f.root, '-c', 'protocol.file.allow=always', 'submodule', 'add', upstream, 'plugins/fixture');
  git(f.root, 'commit', '-am', 'local fixture module');
  const modules = [{ path: 'plugins/fixture' }], state = captureNativeGitState(f.root, modules, gitPath);
  assertNativeGitState(f.root, modules, state);
  const index = state.repositories[1].entries.find(entry => entry.slot === 'index').path;
  fs.appendFileSync(index, 'synthetic admin drift');
  assert.throws(() => assertNativeGitState(f.root, modules, state), /Native Git state refused/);
});
test('split index backing file drift cannot hide behind unchanged index bytes', t => {
  const f = fixture(t); git(f.root, 'update-index', '--split-index');
  const state = f.capture(), shared = state.repositories[0].entries.find(entry => entry.slot === 'shared-index');
  assert.ok(shared); fs.appendFileSync(shared.path, 'synthetic backing drift');
  assert.throws(() => assertNativeGitState(f.root, [], state), /Native Git state refused/);
});
test('missing admin coverage, foreign paths and expired final deadline fail closed', t => {
  const f = fixture(t), state = f.capture();
  const missing = structuredClone(state); missing.repositories[0].entries.pop();
  assert.throws(() => assertNativeGitState(f.root, [], missing));
  const foreign = structuredClone(state); foreign.repositories[0].entries[1].path = path.join(f.base, 'outside');
  assert.throws(() => assertNativeGitState(f.root, [], foreign));
  assert.throws(() => assertNativeGitState(f.root, [], state, () => { throw new Error('bounded deadline'); }), /bounded deadline/);
});
