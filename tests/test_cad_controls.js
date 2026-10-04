"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { supportsBackend, eligibleParent } = require("../apps/lab/static/cad-controls.js");
const screen = { operation: "analysis_run", backend: "fixture.calculix", parent_backends: ["fixture.cadquery"] };
const parent = { id: "E-cad", backend: "fixture.cadquery", status: "COMPLETED_REVIEW_REQUIRED", solver_status: "NOT_RUN", cad_revision: "a".repeat(64) };

test("the single-support screen offers its declared parent and excludes other native models", () => {
  assert.equal(eligibleParent(screen, parent), true);
  for (const backend of ["fixture.assembly", "fixture.freecad", "fixture.unknown", "fixture.cadquery ", undefined]) {
    assert.equal(eligibleParent(screen, { ...parent, backend }), false);
  }
  assert.equal(parent.status, "COMPLETED_REVIEW_REQUIRED");
});
test("completion and a CAD revision are required even for a declared backend", () => {
  for (const changes of [{ status: "REJECTED" }, { status: "FAILED_EXECUTION" }, { status: "RUNNING" },
    { solver_status: "SUCCESS" }, { solver_status: undefined }, { cad_revision: null }, { cad_revision: "" }, { cad_revision: true }]) {
    assert.equal(eligibleParent(screen, { ...parent, ...changes }), false);
  }
});
test("missing or malformed parent capability fails closed without a backend-name prefix guess", () => {
  for (const changes of [{ parent_backends: undefined }, { parent_backends: [] }, { parent_backends: "fixture.cadquery" },
    { parent_backends: ["fixture.cadquery", null] }, { parent_backends: ["fixture.cadquery", ""] },
    { parent_backends: ["fixture.cadquery", "fixture.cadquery"] }, { operation: "model_analysis_run" }, { operation: "pde_run" }]) {
    assert.equal(supportsBackend({ ...screen, ...changes }, parent.backend), false);
  }
  assert.equal(eligibleParent(undefined, parent), false);
  assert.equal(eligibleParent(screen, null), false);
});
test("a later explicitly declared assembly capability can use the same presentation seam", () => {
  const future = { operation: "analysis_run", parent_backends: ["fixture.assembly"] };
  assert.equal(eligibleParent(future, { ...parent, backend: "fixture.assembly" }), true);
  assert.equal(eligibleParent(future, parent), false);
  assert.equal(supportsBackend(screen, "fixture.assembly"), false);
});
