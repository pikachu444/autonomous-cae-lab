// Prepended to the native plugin and its pinned Node reader. Git commands run
// only in the reader; the admission check after the last await uses files only.
import gitStateFs from 'node:fs';
import gitStatePath from 'node:path';
import gitStateCrypto from 'node:crypto';
import { execFileSync as gitStateExec } from 'node:child_process';

const gitStateKind = 'autonomous-cae-lab.native-git-state';
const gitStateSlots = Object.freeze(['HEAD', 'index', 'config', 'config.worktree', 'commondir', 'info/exclude', 'info/sparse-checkout']);
const gitStateKey = value => process.platform === 'win32' ? value.toLowerCase() : value;
const gitStateCanonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const gitStateFail = () => { throw new Error('Native Git state refused'); };
const gitStateExact = (value, keys) => {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      gitStateCanonical(Object.keys(value).sort()) !== gitStateCanonical([...keys].sort())) gitStateFail();
};
function gitStateAbsolute(value) {
  if (typeof value !== 'string' || value.length > 32768 || !gitStatePath.isAbsolute(value) ||
      gitStatePath.resolve(value) !== value || /[\r\n\0]/.test(value)) gitStateFail();
  return value;
}
function gitStateRoots(repoRoot, submodules) {
  repoRoot = gitStateAbsolute(repoRoot);
  if (!Array.isArray(submodules)) gitStateFail();
  const roots = [repoRoot], seen = new Set([gitStateKey(repoRoot)]);
  for (const module of submodules) {
    const relative = module?.path;
    if (typeof relative !== 'string' || !relative || relative.includes('\\') || gitStatePath.isAbsolute(relative) ||
        relative.split('/').some(part => !part || part === '.' || part === '..')) gitStateFail();
    const root = gitStatePath.resolve(repoRoot, relative), local = gitStatePath.relative(repoRoot, root);
    if (!local || gitStatePath.isAbsolute(local) || local === '..' || local.startsWith(`..${gitStatePath.sep}`) || seen.has(gitStateKey(root))) gitStateFail();
    seen.add(gitStateKey(root)); roots.push(root);
  }
  return roots;
}
function gitStateRead(absolute, deadline, limit = 128 * 1024 * 1024) {
  gitStateAbsolute(absolute); deadline();
  const parsed = gitStatePath.parse(absolute);
  let current = parsed.root;
  for (const part of absolute.slice(parsed.root.length).split(gitStatePath.sep).filter(Boolean)) {
    current = gitStatePath.join(current, part); deadline();
    let stat;
    try { stat = gitStateFs.lstatSync(current); } catch (error) {
      if (error.code === 'ENOENT') return { state: 'missing', sha256: null, bytes: null };
      throw error;
    }
    if (stat.isSymbolicLink() || (current !== absolute && !stat.isDirectory())) gitStateFail();
  }
  const stat = gitStateFs.lstatSync(absolute);
  if (stat.isDirectory()) return { state: 'directory', sha256: null, bytes: null };
  if (!stat.isFile() || stat.size > limit) gitStateFail();
  const fd = gitStateFs.openSync(absolute, 'r');
  try {
    const open = gitStateFs.fstatSync(fd);
    if (!open.isFile() || open.size > limit || open.dev !== stat.dev || open.ino !== stat.ino) gitStateFail();
    const bytes = gitStateFs.readFileSync(fd);
    deadline();
    if (bytes.length > limit) gitStateFail();
    return { state: 'file', sha256: gitStateCrypto.createHash('sha256').update(bytes).digest('hex'), bytes };
  } finally { gitStateFs.closeSync(fd); }
}
function gitStateLayout(root, deadline) {
  if (gitStateRead(root, deadline).state !== 'directory') gitStateFail();
  const pointer = gitStatePath.join(root, '.git'), value = gitStateRead(pointer, deadline, 65536);
  let own;
  if (value.state === 'directory') own = pointer;
  else if (value.state === 'file') {
    const match = /^gitdir: ([^\r\n\0]+)\r?\n?$/.exec(value.bytes.toString('utf8'));
    if (!match) gitStateFail();
    own = gitStatePath.resolve(root, match[1]);
  } else gitStateFail();
  if (gitStateRead(own, deadline).state !== 'directory') gitStateFail();
  const commonValue = gitStateRead(gitStatePath.join(own, 'commondir'), deadline, 65536);
  let common = own;
  if (commonValue.state === 'file') {
    const match = /^([^\r\n\0]+)\r?\n?$/.exec(commonValue.bytes.toString('utf8'));
    if (!match) gitStateFail();
    common = gitStatePath.resolve(own, match[1]);
  } else if (commonValue.state !== 'missing') gitStateFail();
  if (gitStateRead(common, deadline).state !== 'directory') gitStateFail();
  const slots = { 'git-pointer': pointer };
  for (const slot of gitStateSlots) slots[slot] = gitStatePath.join(['config', 'info/exclude'].includes(slot) ? common : own, slot);
  return { own, common, slots };
}
function gitStateRef(bytes) {
  const text = bytes?.toString('utf8');
  const symbolic = /^ref: (refs\/[A-Za-z0-9_./-]+)\r?\n?$/.exec(text);
  if (symbolic) {
    const ref = symbolic[1];
    if (ref.includes('..') || ref.endsWith('/') || ref.split('/').some(part => !part || part === '.' || part.endsWith('.lock'))) gitStateFail();
    return ref;
  }
  if (!/^[0-9a-f]{40}(?:[0-9a-f]{24})?\r?\n?$/.test(text)) gitStateFail();
  return null;
}
function gitStatePacked(absolute, ref, deadline) {
  const value = gitStateRead(absolute, deadline, 16 * 1024 * 1024);
  if (value.state === 'missing') return null;
  if (value.state !== 'file') gitStateFail();
  const matches = value.bytes.toString('utf8').split(/\r?\n/).filter(line => line.endsWith(` ${ref}`));
  if (matches.length > 1) gitStateFail();
  if (!matches.length) return null;
  const match = /^([0-9a-f]{40}(?:[0-9a-f]{24})?) (refs\/[A-Za-z0-9_./-]+)$/.exec(matches[0]);
  if (!match || match[2] !== ref) gitStateFail();
  return match[1];
}
function gitStateEntry(slot, absolute, deadline) {
  const { state, sha256 } = gitStateRead(absolute, deadline);
  if (state === 'directory' && slot !== 'git-pointer') gitStateFail();
  return { slot, path: absolute, state, sha256 };
}
function assertNativeGitState(repoRoot, submodules, snapshot, deadline = () => {}) {
  gitStateExact(snapshot, ['schema', 'kind', 'repositories']);
  const roots = gitStateRoots(repoRoot, submodules);
  if (snapshot.schema !== 1 || snapshot.kind !== gitStateKind || !Array.isArray(snapshot.repositories) || snapshot.repositories.length !== roots.length) gitStateFail();
  for (let i = 0; i < roots.length; i++) {
    deadline();
    const repository = snapshot.repositories[i], root = roots[i], layout = gitStateLayout(root, deadline);
    gitStateExact(repository, ['repo_root', 'entries', 'refs', 'packed_ref']);
    if (repository.repo_root !== root || !Array.isArray(repository.entries) || !Array.isArray(repository.refs)) gitStateFail();
    const expectedSlots = ['git-pointer', ...gitStateSlots], seen = new Set();
    for (const entry of repository.entries) {
      gitStateExact(entry, ['slot', 'path', 'state', 'sha256']);
      if (seen.has(entry.slot) || (!expectedSlots.includes(entry.slot) && entry.slot !== 'shared-index')) gitStateFail();
      seen.add(entry.slot);
      const absolute = entry.slot === 'shared-index' ? entry.path : layout.slots[entry.slot];
      if (entry.slot === 'shared-index' && (gitStatePath.dirname(entry.path) !== layout.own || !/^sharedindex\.[0-9a-f]{40}(?:[0-9a-f]{24})?$/.test(gitStatePath.basename(entry.path)))) gitStateFail();
      if (entry.path !== absolute || gitStateCanonical(entry) !== gitStateCanonical(gitStateEntry(entry.slot, absolute, deadline))) gitStateFail();
    }
    if (expectedSlots.some(slot => !seen.has(slot))) gitStateFail();
    let ref = gitStateRef(gitStateRead(layout.slots.HEAD, deadline, 65536).bytes), packed = null;
    const refsSeen = new Set();
    for (const entry of repository.refs) {
      gitStateExact(entry, ['ref', 'path', 'state', 'sha256']);
      if (!ref || refsSeen.has(ref) || refsSeen.size >= 5 || entry.ref !== ref || entry.path !== gitStatePath.join(layout.common, ref)) gitStateFail();
      refsSeen.add(ref);
      const value = gitStateRead(entry.path, deadline, 65536);
      if (entry.state !== value.state || entry.sha256 !== value.sha256 || value.state === 'directory') gitStateFail();
      if (value.state === 'missing') { packed = { path: gitStatePath.join(layout.common, 'packed-refs'), ref, value: gitStatePacked(gitStatePath.join(layout.common, 'packed-refs'), ref, deadline) }; ref = null; }
      else ref = gitStateRef(value.bytes);
    }
    if (ref || gitStateCanonical(repository.packed_ref) !== gitStateCanonical(packed)) gitStateFail();
  }
  deadline();
}
function captureNativeGitState(repoRoot, submodules, gitPath) {
  const started = process.hrtime.bigint(), deadline = () => {
    if (process.hrtime.bigint() - started >= 20_000_000_000n) gitStateFail();
  };
  const env = { ...process.env };
  for (const key of Object.keys(env)) if (/^GIT_/i.test(key)) delete env[key];
  const git = (root, args) => {
    deadline();
    const result = gitStateExec(gitPath, ['-C', root, '-c', 'core.fsmonitor=false', ...args], {
      encoding: 'utf8', timeout: 10000, maxBuffer: 16 * 1024 * 1024, windowsHide: true, env, stdio: ['ignore', 'pipe', 'pipe'],
    }); deadline(); return result;
  };
  const repositories = gitStateRoots(repoRoot, submodules).map(root => {
    const layout = gitStateLayout(root, deadline), resolved = git(root, ['rev-parse', '--path-format=absolute', ...gitStateSlots.flatMap(slot => ['--git-path', slot])]).trim().split(/\r?\n/);
    if (resolved.length !== gitStateSlots.length || resolved.some((absolute, index) => gitStatePath.resolve(absolute) !== layout.slots[gitStateSlots[index]])) gitStateFail();
    const entries = ['git-pointer', ...gitStateSlots].map(slot => gitStateEntry(slot, layout.slots[slot], deadline));
    const shared = git(root, ['rev-parse', '--shared-index-path']).trim();
    if (shared) entries.push(gitStateEntry('shared-index', gitStatePath.resolve(root, shared), deadline));
    const refs = [], refsSeen = new Set();
    let ref = gitStateRef(gitStateRead(layout.slots.HEAD, deadline, 65536).bytes), packed_ref = null;
    while (ref) {
      if (refsSeen.has(ref) || refsSeen.size >= 5) gitStateFail();
      refsSeen.add(ref);
      const absolute = gitStatePath.resolve(git(root, ['rev-parse', '--path-format=absolute', '--git-path', ref]).trim());
      if (absolute !== gitStatePath.join(layout.common, ref)) gitStateFail();
      const value = gitStateRead(absolute, deadline, 65536);
      if (value.state === 'directory') gitStateFail();
      refs.push({ ref, path: absolute, state: value.state, sha256: value.sha256 });
      if (value.state === 'missing') { packed_ref = { path: gitStatePath.join(layout.common, 'packed-refs'), ref, value: gitStatePacked(gitStatePath.join(layout.common, 'packed-refs'), ref, deadline) }; ref = null; }
      else ref = gitStateRef(value.bytes);
    }
    return { repo_root: root, entries, refs, packed_ref };
  });
  const result = { schema: 1, kind: gitStateKind, repositories };
  assertNativeGitState(repoRoot, submodules, result, deadline);
  return result;
}
