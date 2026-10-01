// The local controller prepends its existing repository-pin implementation to
// this module. This guard uses the public OpenScience 2.0.146 plugin hooks; it
// does not observe final offered schemas, individual HTTP retries or responses.
import nativeFs from 'node:fs';
import nativePath from 'node:path';
import nativeCrypto from 'node:crypto';
import { execFile as nativeExecFile } from 'node:child_process';
import { fileURLToPath as nativeFileURLToPath } from 'node:url';

const nativeKnownTools = Object.freeze([
  'caelab_study_create', 'caelab_study_inspect', 'caelab_parameters_discover',
  'caelab_parameters_register', 'caelab_parameters_list', 'caelab_experiment_run',
  'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare',
  'caelab_analysis_run', 'caelab_optimization_plan', 'caelab_optimization_run',
  'caelab_optimization_inspect', 'caelab_pde_run',
]);
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
        settings.allowed.some(tool => !(Object.hasOwn(settings, 'research') ? nativeKnownTools : nativeAcceptanceTools).includes(tool)) ||
        !nativeSha(settings.config_sha256) || !nativeSha(settings.plugin_sha256) || !nativeSha(settings.boot_source_sha256)) nativeRefuse('SETTINGS_INVALID');
    if (Object.hasOwn(settings, 'research')) {
      const research = settings.research;
      exactKeys(research, nativeResearchKeys, 'RESEARCH_DEFINITION_INVALID');
      if (research.schema !== 1 || research.kind !== 'autonomous-cae-lab.openscience-research-definition' ||
          research.agent !== 'research' || nativeCanonical(research.allowed_tools) !== nativeCanonical(nativeKnownTools) ||
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
  const researchArguments = (tool, args) => {
    if (!Object.hasOwn(settings, 'research')) return;
    if (!nativeRecord(args)) nativeRefuse('RESEARCH_ARGUMENTS_REQUIRED');
    const budget = settings.research.budgets;
    if (['caelab_parameters_discover','caelab_parameters_register','caelab_experiment_run','caelab_optimization_plan'].includes(tool) &&
        (args.backend !== 'fixture.cadquery' || args.model !== 'roller_support')) nativeRefuse('RESEARCH_CAPABILITY_NOT_ADMITTED');
    const analysisMesh = value => {
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
