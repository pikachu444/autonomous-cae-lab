"use strict";
const test = require("node:test"), assert = require("node:assert/strict");
const controls = require("../apps/lab/static/pde-controls.js");
const settings = () => ({mode:"selected_mesh", problem:{domain:{type:"rectangle",lengths:[2,1]},
  weak_form:{diffusion:1,reaction:0,rhs:"1"}, boundaries:{xmin:{type:"dirichlet",value:"0"},xmax:{type:"dirichlet",value:"0"},
    ymin:{type:"neumann",value:"0"},ymax:{type:"neumann",value:"0"}}, reference:null},
  mesh:{cell_counts:[16],degree:1},validation:{max_residual_relative:1e-10}});
test("general PDE input retains exact signed source and outward boundary data without creating a reference", () => {
  const original = settings(), snapshot = structuredClone(original), fields = controls.toFields(original);
  Object.assign(fields,{rhs:"-2 + x[0] * x[1]",diffusion:"2.5",reaction:"0.2",cells:"24",xmax_type:"neumann",xmax_value:"-3"});
  const result = controls.fromFields(fields, original);
  assert.equal(result.problem.weak_form.rhs,"-2 + x[0] * x[1]");
  assert.deepEqual(result.problem.boundaries.xmax,{type:"neumann",value:"-3"});
  assert.deepEqual(result.mesh.cell_counts,[24]); assert.equal(result.problem.reference,null);
  assert.deepEqual(original,snapshot); assert.deepEqual(controls.toFields(result).xmax_value,"-3");
});
for (const [key,value] of [["diffusion",""],["reaction","NaN"],["length_x","0x10"],["cells","1.5"],["cells","129"],["residual","0"]]) {
  test(`invalid PDE ${key}=${value} cannot silently reuse the last valid settings`, () => {
    const original=settings(), fields=controls.toFields(original); fields[key]=value;
    assert.throws(()=>controls.fromFields(fields,original)); assert.deepEqual(original,settings());
  });
}
test("benchmark/reference or sweep input cannot pass through the single-mesh editor", () => {
  const reference=settings(); reference.problem.reference={solution:"x[0]",source:"TEST ONLY"};
  assert.throws(()=>controls.toFields(reference));
  const sweep=settings(); sweep.mesh.cell_counts=[8,16,32]; assert.throws(()=>controls.toFields(sweep));
});
test("all-Neumann and unknown boundary or settings keys remain rejected", () => {
  const input=settings(), fields=controls.toFields(input); fields.xmin_type=fields.xmax_type="neumann";
  assert.throws(()=>controls.fromFields(fields,input),/Dirichlet/);
  fields.xmin_type="robin"; assert.throws(()=>controls.fromFields(fields,input));
  input.validation.max_l2_error=.03; assert.throws(()=>controls.toFields(input));
});
