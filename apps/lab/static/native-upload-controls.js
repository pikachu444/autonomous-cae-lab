"use strict";

// Prepare one selected file's bytes only; the server/native importer owns admission.
(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.nativeUploadControls = api;
})(typeof window === "undefined" ? globalThis : window, function (root) {
  const minimumBytes = 100, maximumBytes = 25 * 1024 * 1024;
  const getter = (type, name) => type && Object.getOwnPropertyDescriptor(type.prototype, name)?.get;
  const nameGetter = getter(root.File, "name"), modifiedGetter = getter(root.File, "lastModified");
  const sizeGetter = getter(root.Blob, "size"), typeGetter = getter(root.Blob, "type");
  const lengthGetter = getter(root.ArrayBuffer, "byteLength"), resizableGetter = getter(root.ArrayBuffer, "resizable");

  function metadata(file) {
    let selected;
    try {
      // Native getters check the actual File brand, including foreign-realm Files.
      // A duck-typed object, Blob or forged File prototype is not a selection.
      selected = { name: nameGetter.call(file), size: sizeGetter.call(file),
        type: typeGetter.call(file), lastModified: modifiedGetter.call(file), reader: file.arrayBuffer };
      if (selected.name !== file.name || selected.size !== file.size || selected.type !== file.type ||
          selected.lastModified !== file.lastModified || typeof selected.reader !== "function") throw new Error();
    } catch {
      throw new Error("실제 FCStd 파일 하나를 선택하세요. 파일 목록이나 경로는 사용할 수 없습니다.");
    }
    if (typeof selected.name !== "string" || !selected.name.trim() || /[\\/:\u0000-\u001f\u007f]/.test(selected.name) ||
        !/\.fcstd$/i.test(selected.name)) {
      throw new Error("경로가 아닌 .FCStd 파일 이름이 필요합니다. STEP·MSH 등 다른 형식은 변환하지 않습니다.");
    }
    if (!Number.isSafeInteger(selected.size) || selected.size < minimumBytes || selected.size > maximumBytes) {
      throw new Error("FCStd 파일 크기는 100바이트 이상, 25 MiB 이하여야 합니다.");
    }
    if (typeof selected.type !== "string" || !Number.isSafeInteger(selected.lastModified)) {
      throw new Error("선택한 파일 정보를 확인할 수 없습니다. 다시 선택하세요.");
    }
    return selected;
  }

  async function readFile(file) {
    const before = metadata(file);
    let body;
    try { body = await before.reader.call(file); }
    catch { throw new Error("선택한 FCStd 파일을 읽지 못했습니다. 다시 선택하세요."); }
    let after;
    try { after = metadata(file); }
    catch { throw new Error("읽는 동안 선택한 파일 정보가 변경됐거나 확인되지 않았습니다. 다시 선택하세요."); }
    if (["name", "size", "type", "lastModified", "reader"].some(key => before[key] !== after[key])) {
      throw new Error("읽는 동안 선택한 파일 정보가 변경됐습니다. 다시 선택하세요.");
    }
    let bytes;
    try {
      bytes = lengthGetter.call(body);
      if (resizableGetter?.call(body)) throw new Error();
    } catch {
      throw new Error("파일 읽기 결과는 크기가 고정된 ArrayBuffer 바이트여야 합니다.");
    }
    if (!Number.isSafeInteger(bytes) || bytes !== before.size || bytes < minimumBytes || bytes > maximumBytes) {
      throw new Error("실제로 읽은 파일 크기가 선택 정보와 다릅니다. 다시 선택하세요.");
    }
    // No JSON encoding, MIME substitution, source path or upload action.
    return { body, bytes, label: before.name };
  }
  return Object.freeze({ readFile });
});
