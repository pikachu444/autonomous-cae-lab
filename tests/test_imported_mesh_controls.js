"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const controls = require("../apps/lab/static/imported-mesh-controls.js");
const contents = (tail = "", newline = "\n") => "$MeshFormat\n2.2 0 8\n$EndMeshFormat\n".replaceAll("\n", newline) + tail;
const file = (name, data) => ({ name, size: Buffer.byteLength(data), arrayBuffer: async () => Uint8Array.from(Buffer.from(data)).buffer });
const files = () => [file("coarse.msh", contents("first")), file("medium.msh", contents("second")), file("fine.msh", contents("third", "\r\n"))];

test("file selection preserves original bytes/order/CRLF and hashes independently", async () => {
  const levels = await controls.fromFiles(files());
  assert.deepEqual(levels.map((level) => level.source), ["coarse.msh", "medium.msh", "fine.msh"]);
  for (let index = 0; index < levels.length; index++) {
    const original = Buffer.from(await files()[index].arrayBuffer());
    assert.equal(levels[index].data, original.toString("utf8"));
    assert.equal(levels[index].sha256, createHash("sha256").update(original).digest("hex"));
  }
  assert.deepEqual(controls.summaries(levels).map((row) => row.size_bytes), files().map((item) => item.size));
});

test("advanced settings exclude mesh bytes and merge immutable selected levels", async () => {
  const levels = await controls.fromFiles(files()), settings = { problem: { untouched: "scientific input" }, mesh: { degree: 1, levels }, validation: { unknown: true } };
  const before = structuredClone(settings), { draft, levels: selected } = controls.splitSettings(settings);
  assert.deepEqual(draft.mesh, { degree: 1 });
  assert.deepEqual(controls.settingsWithLevels(draft, selected), settings);
  selected.reverse();
  assert.deepEqual(settings, before);
  assert.deepEqual(controls.settingsWithLevels(draft, selected).mesh.levels.map((level) => level.source), ["fine.msh", "medium.msh", "coarse.msh"]);
  assert.throws(() => controls.settingsWithLevels(settings, selected), /JSON/);
});

test("file count/size refusal happens before reading any selected file", async () => {
  let reads = 0;
  const huge = { name: "huge.msh", size: 96 * 1024, arrayBuffer: async () => { reads++; throw new Error("must not read"); } };
  await assert.rejects(controls.fromFiles([huge, ...files()]), /96 KiB/);
  await assert.rejects(controls.fromFiles(files().slice(0, 2)), /3~8/);
  assert.equal(reads, 0);
});

test("binary/wrong version/mutable size/unsupported filename refuse", async () => {
  const controls_ = [file("binary.msh", contents("\u0080")), file("msh4.msh", "$MeshFormat\n4.1 0 8\n"), file("unsafe.txt", contents())];
  for (const item of controls_) await assert.rejects(controls.fromFiles([item, ...files().slice(1)]));
  const changed = file("changed.msh", contents()); changed.size++;
  await assert.rejects(controls.fromFiles([changed, ...files().slice(1)]), /크기/);
});

test("whole UTF8 JSON size includes escaping, arguments and scientific settings", async () => {
  const levels = await controls.fromFiles(files());
  const args = { experiment_id: "E-source", backend: "pde.fenicsx.imported", settings: { problem: {}, mesh: { degree: 1, levels } } };
  assert.deepEqual(JSON.parse(controls.requestBody("pde_run", args)), { operation: "pde_run", arguments: args });
  args.settings.problem.expression = "가".repeat(48 * 1024);
  assert.throws(() => controls.requestBody("pde_run", args), /128 KiB/);
});
