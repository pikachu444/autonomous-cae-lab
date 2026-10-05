"use strict";

// TEST_ONLY binary Files: no ZIP/native CAD qualification, HTTP or provider calls.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const controls = require("../apps/lab/static/native-upload-controls.js");
const maximumBytes = 25 * 1024 * 1024;
const data = () => Uint8Array.from({ length: 100 }, (_value, index) => (index * 73) % 256);
const file = (name = "사용자 모델.FCStd", bytes = data()) => new File([bytes], name,
  { type: "application/octet-stream", lastModified: 123456789 });
const reader = (selected, read) => Object.defineProperty(selected, "arrayBuffer", { configurable: true, value: read });

test("CommonJS/browser API returns exactly original binary body, byte count and selected label without path or actions", async () => {
  assert.deepEqual(Object.keys(controls), ["readFile"]); assert.equal(Object.isFrozen(controls), true);
  const selected = file("  사용자 <모델>.fCsTd"), before = { name: selected.name, size: selected.size,
    type: selected.type, lastModified: selected.lastModified };
  for (const key of ["path", "model", "store_id"]) Object.defineProperty(selected, key, {
    get() { throw new Error("Paths and server identities must not be read"); } });
  const browser = { window: { File, Blob, ArrayBuffer }, fetch() { throw new Error("No HTTP"); } };
  vm.runInNewContext(readFileSync(require.resolve("../apps/lab/static/native-upload-controls.js"), "utf8"), browser);
  const output = await controls.readFile(selected), other = await browser.window.nativeUploadControls.readFile(selected);
  assert.deepEqual(Object.keys(output).sort(), ["body", "bytes", "label"]);
  assert(output.body instanceof ArrayBuffer); assert.equal(output.bytes, 100); assert.equal(output.label, before.name);
  assert.deepEqual(new Uint8Array(output.body), data()); assert.deepEqual(new Uint8Array(other.body), data());
  assert.equal(other.bytes, output.bytes); assert.equal(other.label, output.label);
  assert.deepEqual({ name: selected.name, size: selected.size, type: selected.type, lastModified: selected.lastModified }, before);
});

test("non-Files, empty/multiple selections and forged File brands are refused before any reader runs", async () => {
  let reads = 0;
  const fake = { name: "model.FCStd", size: 100, type: "", lastModified: 1,
    arrayBuffer: async () => { reads++; return new ArrayBuffer(100); } };
  const forged = Object.assign(Object.create(File.prototype), { arrayBuffer: fake.arrayBuffer });
  for (const selected of [undefined, null, [], [file()], [file(), file()], { 0: file(), length: 1 }, fake,
    { ...fake, [Symbol.toStringTag]: "File" }, forged, new Blob([data()]), "C:/model.FCStd"]) {
    await assert.rejects(controls.readFile(selected), /파일 하나/);
  }
  assert.equal(reads, 0);
});

test("unsupported extensions, path-shaped names, empty/undersized Files refuse without replacement or reading", async () => {
  let reads = 0;
  for (const name of ["model.step", "model.msh", "model.FCStd.bak", "model.FCStd ", "model.FCStd\n", "",
    "../model.FCStd", "folder\\model.FCStd", "C:model.FCStd", "nul\u0000.FCStd"]) {
    const selected = reader(file(name), async () => { reads++; throw new Error("must not read"); });
    await assert.rejects(controls.readFile(selected), /FCStd/);
  }
  for (const bytes of [new Uint8Array(0), new Uint8Array(99)]) {
    const selected = reader(file("model.FCStd", bytes), async () => { reads++; throw new Error("must not read"); });
    await assert.rejects(controls.readFile(selected), /100바이트/);
  }
  assert.equal(reads, 0);
  const accepted = await controls.readFile(file("UPPER.FCSTD")); assert.equal(accepted.bytes, 100);
});

test("maximum boundary reads one synthetic 25 MiB File; one byte over refuses before reading and JSON limits do not apply", async () => {
  const maximum = new File([new Uint8Array([17]), new Blob([new ArrayBuffer(maximumBytes - 2)]), new Uint8Array([251])],
    "maximum.FCStd", { lastModified: 1 });
  let reads = 0;
  reader(maximum, async function () { reads++; return Blob.prototype.arrayBuffer.call(this); });
  const output = await controls.readFile(maximum);
  assert.equal(output.bytes, maximumBytes); assert.equal(output.body.byteLength, maximumBytes);
  const bytes = new Uint8Array(output.body); assert.equal(bytes[0], 17); assert.equal(bytes.at(-1), 251); assert.equal(reads, 1);
  const tooLarge = reader(new File([maximum, new Uint8Array([1])], "oversize.FCStd", { lastModified: 1 }),
    async () => { reads++; throw new Error("must not read"); });
  await assert.rejects(controls.readFile(tooLarge), /25 MiB/); assert.equal(reads, 1);
  const aboveJsonLimit = await controls.readFile(file("binary.FCStd", new Uint8Array(128 * 1024 + 1)));
  assert.equal(aboveJsonLimit.bytes, 128 * 1024 + 1);
});

test("read errors are readable without leaking underlying path; non-ArrayBuffer or mismatched bytes never become a request", async () => {
  const broken = reader(file(), async () => { throw new Error("private C:/source/model.FCStd"); });
  await assert.rejects(controls.readFile(broken), error => /읽지 못/.test(error.message) && !error.message.includes("private"));
  for (const result of [undefined, null, {}, new Uint8Array(100), new DataView(new ArrayBuffer(100)),
    new SharedArrayBuffer(100), new ArrayBuffer(99), new ArrayBuffer(101)]) {
    await assert.rejects(controls.readFile(reader(file(), async () => result)), /ArrayBuffer|크기/);
  }
  const resizable = new ArrayBuffer(100, { maxByteLength: 200 });
  await assert.rejects(controls.readFile(reader(file(), async () => resizable)), /크기가 고정/);
  const detached = new ArrayBuffer(100); structuredClone(detached, { transfer: [detached] });
  await assert.rejects(controls.readFile(reader(file(), async () => detached)), /크기/);
});

test("name/size/type/modified time or reader changes during a pending read refuse after the read completes", async () => {
  for (const [key, value] of [["name", "other.FCStd"], ["size", 101], ["type", "application/zip"], ["lastModified", 2],
    ["arrayBuffer", async () => new ArrayBuffer(100)]]) {
    let release, started = false;
    const selected = reader(file(), async () => { started = true; return await new Promise(resolve => { release = resolve; }); });
    const pending = controls.readFile(selected); assert.equal(started, true);
    Object.defineProperty(selected, key, { configurable: true, value }); release(new ArrayBuffer(100));
    await assert.rejects(pending, /정보.*변경/);
  }
  const alteredBefore = file(); Object.defineProperty(alteredBefore, "size", { value: 1000 });
  await assert.rejects(controls.readFile(alteredBefore), /파일 하나/);
});

test("a completed immutable selection is copied faithfully and does not infer MIME, ZIP validity or model eligibility", async () => {
  const selected = new File([data()], "not-a-qualified-document.FCStd", { type: "text/html", lastModified: -1 });
  Object.freeze(selected);
  const output = await controls.readFile(selected);
  assert.equal(output.label, "not-a-qualified-document.FCStd"); assert.equal(output.bytes, 100);
  assert.deepEqual(new Uint8Array(output.body), data());
  assert.equal("type" in output, false); assert.equal("valid" in output, false); assert.equal("backend" in output, false);
});
