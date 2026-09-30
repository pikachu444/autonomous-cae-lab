// The local controller prepends its existing repository-pin implementation to
// this module. This guard uses the public OpenScience 2.0.146 plugin hooks; it
// does not observe final offered schemas, individual HTTP retries or responses.
import nativeFs from 'node:fs';
import nativePath from 'node:path';
import nativeCrypto from 'node:crypto';
import { fileURLToPath as nativeFileURLToPath } from 'node:url';

const nativeKnownTools = Object.freeze([
  'caelab_study_create', 'caelab_study_inspect', 'caelab_parameters_discover',
  'caelab_parameters_register', 'caelab_parameters_list', 'caelab_experiment_run',
  'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare',
]);
const nativeSettingsKeys = Object.freeze([
  'schema', 'kind', 'repo_root', 'run_name', 'profile_root', 'model', 'allowed',
  'guardPath', 'configPath', 'config_sha256', 'pluginPath', 'plugin_sha256',
  'receipts', 'boot_source', 'boot_source_sha256',
]);
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
    super(`CAE native guard refused: ${code}`);
    this.name = 'CaeLabNativeGuardRefusal';
    this.code = code;
  }
}
const nativeRefuse = code => { throw new NativeGuardRefusal(code); };

// Internal factory: test code may append an export to its temporary module.
// Production exports only the actual plugin, so the upstream loader cannot
// mistakenly invoke a second exported function as another plugin.
function createNativeHooks(suppliedSettings, dependencies = {}) {
  const io = dependencies.fs ?? nativeFs;
  const paths = dependencies.path ?? nativePath;
  const digest = dependencies.digest ?? (bytes => nativeCrypto.createHash('sha256').update(bytes).digest('hex'));
  const capture = dependencies.capture ?? captureRepositorySourcePin;
  const assertPin = dependencies.assertPin ?? assertRepositorySourcePin;
  const pinSha = dependencies.pinSha ?? sourcePinSha;
  const settingsPath = dependencies.settingsPath;
  const loadedPluginPath = dependencies.pluginPath ?? suppliedSettings?.pluginPath;
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
    exactKeys(settings, nativeSettingsKeys, 'SETTINGS_INVALID');
    if (settings.schema !== 1 || settings.kind !== 'autonomous-cae-lab.openscience-native-guard' ||
        typeof settings.run_name !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(settings.run_name) ||
        typeof settings.model !== 'string' || !/^openai-codex\/[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(settings.model) ||
        !Array.isArray(settings.allowed) || !settings.allowed.length || new Set(settings.allowed).size !== settings.allowed.length ||
        settings.allowed.some(tool => !nativeKnownTools.includes(tool)) ||
        !nativeSha(settings.config_sha256) || !nativeSha(settings.plugin_sha256) || !nativeSha(settings.boot_source_sha256)) nativeRefuse('SETTINGS_INVALID');
    noLinks(settings.profile_root, 'directory');
    noLinks(settings.repo_root, 'directory');
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
  };
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
  const sourceFor = () => {
    const boot = settings.boot_source;
    if (digest(read(boot.git_path, 128 * 1024 * 1024)) !== boot.git_sha256) nativeRefuse('GIT_EXECUTABLE_CHANGED');
    try { assertPin(boot, capture(settings.repo_root, boot.git_path)); }
    catch { nativeRefuse('SOURCE_CHANGED_OR_UNAVAILABLE'); }
    return settings.boot_source_sha256;
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
      session_id: metadataId(input?.sessionID),
      tool: nativeKnownTools.includes(input?.tool) ? input.tool : null,
      status, accepted: status === 'accepted', code, boot_source_sha256: hashes.source ?? null,
      guard_sha256: hashes.guard ?? null, settings_sha256: settingsSha,
      config_sha256: settings.config_sha256, plugin_sha256: settings.plugin_sha256,
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
  const evaluate = async (hook, input) => {
    const hashes = {};
    try {
      stableFiles();
      const parsed = guardFor();
      hashes.guard = parsed.sha256;
      if (parsed.guard.stopping) nativeRefuse('RUNTIME_STOPPING');
      hashes.source = sourceFor();
      if (hook === 'chat.params') {
        const model = input?.model;
        if (!nativeRecord(model) || model.providerID !== 'openai-codex' ||
            `${model.providerID}/${model.id}` !== settings.model) nativeRefuse('MODEL_CHANGED');
        const agent = typeof input?.agent === 'string' ? input.agent : input?.agent?.name;
        if (!['research', 'caelab-acceptance'].includes(agent)) nativeRefuse('AGENT_NOT_ALLOWED');
      } else {
        if (parsed.guard.no_tools) nativeRefuse('NO_TOOLS_STAGE');
        if (!settings.allowed.includes(input?.tool)) nativeRefuse('TOOL_NOT_ALLOWED');
        if (parsed.guard.required !== null && input.tool !== parsed.guard.required) nativeRefuse('REQUIRED_TOOL_MISMATCH');
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
  receipt('plugin.loaded', null, 'accepted', 'PLUGIN_LOADED', { source: sourceFor(), guard: initialGuard.sha256 });
  return {
    'chat.params': async (input, _output) => evaluate('chat.params', input),
    'tool.execute.before': async (input, _output) => evaluate('tool.execute.before', input),
  };
}

export async function CaeLabNativeGuard(_input) {
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
  return createNativeHooks(settings, { settingsPath, pluginPath });
}
