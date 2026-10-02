"use strict";

// Browser bytes are immutable model inputs; adapter/Domain own final admission.
(function (root) {
  const rawLimit = 96 * 1024, requestLimit = 128 * 1024;
  const bytes = (data) => new TextEncoder().encode(data);
  const clone = (value) => JSON.parse(JSON.stringify(value));
  function levelsCheck(levels) {
    if (!Array.isArray(levels) || levels.length < 3 || levels.length > 8) throw new Error("성긴 메시부터 촘촘한 메시까지 3~8개를 선택하세요.");
    let total = 0;
    for (const level of levels) {
      if (!level || Object.keys(level).sort().join(",") !== "data,format,sha256,source" ||
          level.format !== "gmsh_msh2_ascii" || typeof level.data !== "string" ||
          /[^\x00-\x7f]/.test(level.data) || !/^\$MeshFormat\r?\n2\.2 0 8\r?\n/.test(level.data) ||
          typeof level.source !== "string" || !level.source.trim() || level.source.length > 256 ||
          typeof level.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(level.sha256)) {
        throw new Error("원본 이름·해시가 있는 Gmsh MSH2.2 ASCII 파일이 필요합니다.");
      }
      total += bytes(level.data).byteLength;
    }
    if (total > rawLimit) throw new Error("메시 파일 합계는 96 KiB 이하여야 합니다.");
    return levels;
  }
  async function fromFiles(files) {
    const selected = Array.from(files);
    if (selected.length < 3 || selected.length > 8) throw new Error("메시 파일 3~8개를 선택하세요.");
    let total = 0;
    for (const file of selected) {
      if (typeof file.name !== "string" || !/\.msh$/i.test(file.name) || file.name.length > 256 ||
          !Number.isSafeInteger(file.size) || file.size <= 0) throw new Error("작은 .msh 파일을 선택하세요.");
      total += file.size;
    }
    if (total > rawLimit) throw new Error("메시 파일 합계는 96 KiB 이하여야 합니다.");
    const levels = [];
    for (const file of selected) {
      const buffer = await file.arrayBuffer();
      if (buffer.byteLength !== file.size) throw new Error("선택한 파일 크기가 달라졌습니다. 다시 선택하세요.");
      const original = new Uint8Array(buffer);
      if (original.some((value) => value > 127)) throw new Error("MSH2.2 ASCII 파일만 지원합니다.");
      const data = new TextDecoder("utf-8", { fatal: true }).decode(original);
      const digest = await root.crypto.subtle.digest("SHA-256", original);
      const sha256 = Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
      levels.push({ format: "gmsh_msh2_ascii", data, sha256, source: file.name });
    }
    return clone(levelsCheck(levels));
  }
  function splitSettings(settings) {
    if (!settings?.mesh || settings.mesh.degree !== 1 || Object.keys(settings.mesh).sort().join(",") !== "degree,levels") {
      throw new Error("1차 삼각형 메시 설정이 필요합니다.");
    }
    const levels = clone(levelsCheck(settings.mesh.levels)), draft = clone(settings);
    draft.mesh = { degree: 1 };
    return { draft, levels };
  }
  function settingsWithLevels(draft, levels) {
    if (!draft?.mesh || draft.mesh.degree !== 1 || Object.keys(draft.mesh).join(",") !== "degree") {
      throw new Error("메시는 파일 선택 목록에서 관리합니다. 설정 JSON에는 mesh.degree만 남겨 두세요.");
    }
    const settings = clone(draft);
    settings.mesh.levels = clone(levelsCheck(levels));
    return settings;
  }
  function requestBody(operation, arguments_) {
    const body = JSON.stringify({ operation, arguments: arguments_ });
    if (bytes(body).byteLength > requestLimit) throw new Error("설정을 포함한 요청이 128 KiB를 넘습니다. 메시 파일을 줄이세요.");
    return body;
  }
  function summaries(levels) {
    return levelsCheck(levels).map((level) => ({ source: level.source, size_bytes: bytes(level.data).byteLength, sha256: level.sha256 }));
  }
  const api = { fromFiles, splitSettings, settingsWithLevels, requestBody, summaries };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.importedMeshControls = api;
})(typeof window !== "undefined" ? window : globalThis);
