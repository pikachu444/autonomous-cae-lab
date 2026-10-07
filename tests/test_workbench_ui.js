'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const ui=require('../apps/lab/static/workbench.js');

test('Channel mapping retains physical axis, units, components, locations and transforms',()=>{
 const mapping=ui.serializeMapping([{name:'contact_force',column:'Fz',unit:'N',component:'z',location:'chip_contact',scale:'1000',offset:'0'}],{column:'t',name:'time',unit:'ms'},'tab',2);
 assert.deepEqual(mapping.columns.contact_force,{column:'Fz',unit:'N',component:'z',location:'chip_contact',scale:1000,offset:0,axis:{column:'t',name:'time',unit:'ms'},reduction:'none'});
 assert.equal(mapping.delimiter,'\t');assert.equal(mapping.skip_header,2);
 assert.throws(()=>ui.serializeMapping([{name:'force',column:'1',unit:'N',component:'z',location:'chip'}],{column:'time',name:'time',unit:'s'}),/consistently/);
 assert.throws(()=>ui.serializeMapping([{name:'force',column:'1',unit:'',component:'z',location:'chip'}],{column:'0',name:'time',unit:'s'}),/unit/);
});
test('Editable material histories serialize to actual backend inputs without simulation',()=>{
 const settings=ui.materialSettings('linear_elastic','2000','0.3','MPa','s',[{time:0,f11:1,f22:1,f33:1},{time:1,f11:1.005,f22:1,f33:1}]);
 assert.deepEqual(settings.parameters,{E:2000,nu:0.3});assert.deepEqual(settings.deformation_gradient[1],[[1.005,0,0],[0,1,0],[0,0,1]]);assert.equal(settings.stress_unit,'MPa');
 assert.throws(()=>ui.materialSettings('linear_elastic',2000,0.3,'MPa','s',[{time:1,f11:1,f22:1,f33:1},{time:0,f11:1,f22:1,f33:1}]),/increase/);
});
test('Independent variable bounds reject invalid initial values and logarithms',()=>{
 const rows=[{id:'coefficient-any',unit:'Pa',lower:1,upper:10,value:3,transform:'log'}];assert.equal(ui.serializeVariables(rows)[0].id,'coefficient-any');
 assert.throws(()=>ui.serializeVariables([{...rows[0],value:11}]),/bounds/);assert.throws(()=>ui.serializeVariables([{...rows[0],lower:0}]),/positive/);assert.throws(()=>ui.serializeVariables([rows[0],rows[0]]),/distinct/);
});
test('Comparison selects exact independent recorded jobs and responses',()=>{
 const selection=ui.comparisonSelection('Jpred','stress_xx','Jobs','observed_axial',2,5);
 assert.equal(selection.prediction_response,'stress_xx');assert.equal(selection.observation_response,'observed_axial');assert.deepEqual(selection.options,{weight:2,scale:5});assert.throws(()=>ui.comparisonSelection('Jpred','','Jobs','stress'),/required/);
});
test('Expert plan aligns actual inputs and remains a proposal, not an execution',()=>{
 const action={status:'PLANNED',executed:false,plan:{purpose:'Narrow real influence range',operation:'doe',inputs:{backend:'user.registered',variables:[{id:'contact',unit:'1',lower:.1,upper:.3,value:.2}],settings:{load:50}},budget:{evaluations:12}}};
 const aligned=ui.alignPlan(action);assert.equal(aligned.operation,'doe');assert.deepEqual(aligned.arguments,action.plan.inputs);assert.equal(aligned.budget.evaluations,12);aligned.arguments.settings.load=60;assert.equal(action.plan.inputs.settings.load,50);assert.throws(()=>ui.alignPlan({operation:'arbitrary-code',inputs:{}}),/supported/);
});
test('Plotting accepts only actual scalar-axis numeric series and preserves units',()=>{
 const response={kind:'series',value:[3,7],unit:'N',component:'z',location:'contact',axes:[{name:'time',unit:'ms',values:[0,10]}]};assert.deepEqual(ui.seriesPoints(response).points,[[0,3],[10,7]]);assert.match(ui.seriesPoints(response).yLabel,/N.*contact/);
 assert.equal(ui.seriesPoints({...response,value:[3,NaN]}),null);assert.equal(ui.seriesPoints({...response,kind:'field'}),null);assert.equal(ui.seriesPoints({...response,value:[3]}),null);
});
test('Exported report escapes untrusted labels and excludes raw document/conversation content',()=>{
 const report=ui.reportHTML({responses:{'<img src=x onerror=alert(1)>':{unit:'N',value:4}},diagnostics:{limitations:['sample only']},segments:[{text:'RAW PRIVATE SOURCE'}],answer:'PRIVATE CONVERSATION'},{id:'Jactual',operation:'evaluate',arguments:{backend:'material.felupe',question:'PRIVATE QUESTION',settings:{parameters:{E:2000}}}});
 assert.ok(report.includes('&lt;img'));assert.ok(!report.includes('<img'));assert.ok(report.includes('sample only'));assert.ok(!report.includes('RAW PRIVATE SOURCE'));assert.ok(!report.includes('PRIVATE CONVERSATION'));assert.ok(!report.includes('PRIVATE QUESTION'));assert.ok(report.includes('2000'));
});

test('Masked null observations create separate segments without zero substitution or bridging',()=>{
 const response={kind:'series',value:[1,2,null,4,5],unit:'MPa',component:'xx',location:'material_point',mask:[true,true,false,true,true],axes:[{name:'time',unit:'s',values:[0,1,2,3,4]}]};
 const series=ui.seriesPoints(response);assert.deepEqual(series.segments,[[[0,1],[1,2]],[[3,4],[4,5]]]);assert.equal(series.missingCount,1);assert.equal(series.points.length,4);
 const svg=ui.curveSVG([['Actual',response]]);assert.equal((svg.match(/<polyline/g)||[]).length,2);assert.ok(!svg.includes('NaN'));assert.match(svg,/1 masked\/missing/);
});
test('Fit and holdout report includes actual curves, units and errors while excluding private source content',()=>{
 const observed={kind:'series',value:[0,2,null,6],unit:'MPa',component:'xx',location:'material_point',axes:[{name:'time',unit:'s',values:[0,1,2,3]}]};
 const result={kind:'fit',parameters:{E:1500},parameter_units:{E:'MPa'},curves:[{experiment_id:'fit-test',role:'fit',response:'stress_xx',observations:observed,prediction:[0,2.1,null,5.9],mask:[true,true,false,true],rmse:.08165},{experiment_id:'holdout-test',role:'holdout',response:'stress_xx',observations:observed,prediction:[0,1.9,null,6.2],mask:[true,true,false,true],rmse:.1291}],segments:[{text:'PRIVATE RAW DOCUMENT'}],answer:'PRIVATE QUESTION'};
 const report=ui.reportHTML(result,{operation:'fit',arguments:{question:'PRIVATE INPUT QUESTION'}});
 assert.equal((report.match(/<svg /g)||[]).length,2);assert.match(report,/holdout · holdout-test/);assert.match(report,/RMSE 0.08165 MPa/);assert.match(report,/parameter_units/);assert.ok(report.includes('Predicted'));assert.ok(report.includes('Observed'));assert.ok(!report.includes('PRIVATE RAW DOCUMENT'));assert.ok(!report.includes('PRIVATE INPUT QUESTION'));assert.ok(!report.includes('PRIVATE QUESTION'));
 assert.deepEqual(ui.displayResponses(result)['fit: fit-test predicted'].mask,[true,true,false,true]);
});
