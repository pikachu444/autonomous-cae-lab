"use strict";
const test = require('node:test'), assert = require('node:assert/strict');
const controls=require('../apps/lab/static/campaign-controls.js');
const digest='a'.repeat(64);
const context={backend:'test.model',settings:{inputs:{x:1},load:{source:'fixed'}},entries:[{parameter_id:'x',target:'model_analysis',mode:'free',kind:'continuous',
  input_effect:{status:'PASS'},unit:'1',source_sha256:digest,model_template_revision:digest,current_value:1,lower_bound:0,upper_bound:2,
  native:{backend:'test.model',document:digest,object:'declared_inputs',path:'input_x',alias:''}}]};
const fields={study_id:'S-doe',campaign_id:'C-doe',parameter_ids:['x'],seed:13,sample_count:8,engine:'scipy.latin_hypercube'};
test('model DOE uses a deep copy of frozen source and LHS metadata without DE objective',()=>{
 const result=controls.modelDoeArguments(fields,context);assert.equal(result.engine,'scipy.latin_hypercube');assert.equal(result.objective,undefined);
 result.settings.load.source='changed';assert.equal(context.settings.load.source,'fixed');assert.deepEqual(fields.parameter_ids,['x']);
});
for(const change of [{sample_count:true},{sample_count:1},{sample_count:33},{seed:-1},{engine:'LLM'},{parameter_ids:['x','x']},{parameter_ids:['other']},{objective:{}}])
 test(`invalid DOE declaration ${JSON.stringify(change)}`,()=>assert.throws(()=>controls.modelDoeArguments({...fields,...change},context)));
test('unregistered model effects are refused',()=>{
 const invalid=structuredClone(context);invalid.entries[0].input_effect.status='UNKNOWN';assert.throws(()=>controls.modelDoeArguments(fields,invalid));
});
