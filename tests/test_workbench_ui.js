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
test('Native settings tree edits nested numeric, string and boolean leaves without fixing a profile',()=>{
 const template={conditions:{duration:2.5,axis:'x',enabled:true},mesh:{cells:[12,8],grading:null}};
 const leaves=ui.nativeLeaves(template);
 assert.deepEqual(leaves.map(row=>row.path),[['conditions','duration'],['conditions','axis'],['conditions','enabled'],['mesh','cells',0],['mesh','cells',1],['mesh','grading']]);
 const edited=ui.nativeSettings(template,[{path:['conditions','duration'],kind:'number',value:'3.25'},
   {path:['conditions','axis'],kind:'string',value:'y'},
   {path:['conditions','enabled'],kind:'boolean',value:'false'},
   {path:['mesh','cells',0],kind:'number',value:'24'}]);
 assert.deepEqual(edited,{conditions:{duration:3.25,axis:'y',enabled:false},mesh:{cells:[24,8],grading:null}});
 assert.equal(template.conditions.duration,2.5);
 assert.throws(()=>ui.nativeSettings(template,[{path:['mesh','cells',0],kind:'number',value:'NaN'}]),/finite/);
 assert.throws(()=>ui.nativeLeaves(JSON.parse('{"__proto__":{"value":1}}')),/Unsafe native setting key/);
});
test('Expert approval sends public discovery, consultation and bounded calculations as distinct scopes',()=>{
 const approved=ui.expertScope({backend:'material.felupe',variables:[{id:'E',unit:'MPa',lower:100,upper:2000,value:900}],
   evaluations:12,threads:2,memory:2048,seconds:90,allowExecution:true,allowPublicSearch:true,allowExternal:true,
   documents:[{document_id:'D1',collection:'materials'}],results:['J1'],consult:['testing']});
 assert.deepEqual(approved.context.selected_document_ids,['D1']);
 assert.deepEqual(approved.context.consult_experts,['testing']);
 assert.equal(approved.context.transmission_scope.allow_public_search,true);
 assert.deepEqual(approved.context.calculation_scope.variables.E,[100,2000]);
 assert.equal(approved.context.calculation_scope.max_evaluations,12);
 assert.equal(approved.context.calculation_scope.resources.threads,2);
 assert.equal(approved.budget.seconds,90);
 const readOnly=ui.expertScope({seconds:120,allowExecution:false,allowPublicSearch:false,documents:[],results:[],consult:[]});
 assert.equal(readOnly.context.calculation_scope,undefined);
 assert.throws(()=>ui.expertScope({backend:'material.felupe',variables:[{id:'E',unit:'MPa',lower:100,upper:2000,value:900}],evaluations:0,threads:1,memory:1024,seconds:10,allowExecution:true,documents:[],results:[],consult:[]}),/positive integers/);
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
test('Large retained curves use bounded row windows and avoid argument-spread limits',()=>{
 assert.deepEqual(ui.resultRows('0','2000'),[0,2000]);
 assert.deepEqual(ui.resultRows('299000','300001'),[299000,300001]);
 for(const [start,stop] of [['','1'],['0',''],['-1','1'],['0','0'],['0','2001'],['2.5','4']])
   assert.throws(()=>ui.resultRows(start,stop),/row|samples/i);
 const count=300001,response={kind:'series',value:Array.from({length:count},(_,i)=>i%7),unit:'N',component:'z',location:'saved',axes:[{name:'time',unit:'s',values:Array.from({length:count},(_,i)=>i)}]};
 const svg=ui.curveSVG([['saved',response]]);
 assert.match(svg,/300001 retained samples/);
 assert.ok(!svg.includes('NaN'));
});
test('Fit and holdout report includes actual curves, units and errors while excluding private source content',()=>{
 const observed={kind:'series',value:[0,2,null,6],unit:'MPa',component:'xx',location:'material_point',axes:[{name:'time',unit:'s',values:[0,1,2,3]}]};
 const result={kind:'fit',parameters:{E:1500},parameter_units:{E:'MPa'},curves:[{experiment_id:'fit-test',role:'fit',response:'stress_xx',observations:observed,prediction:[0,2.1,null,5.9],mask:[true,true,false,true],rmse:.08165},{experiment_id:'holdout-test',role:'holdout',response:'stress_xx',observations:observed,prediction:[0,1.9,null,6.2],mask:[true,true,false,true],rmse:.1291}],segments:[{text:'PRIVATE RAW DOCUMENT'}],answer:'PRIVATE QUESTION'};
 const report=ui.reportHTML(result,{operation:'fit',arguments:{question:'PRIVATE INPUT QUESTION'}});
 assert.equal((report.match(/<svg /g)||[]).length,2);assert.match(report,/holdout · holdout-test/);assert.match(report,/RMSE 0.08165 MPa/);assert.match(report,/parameter_units/);assert.ok(report.includes('Predicted'));assert.ok(report.includes('Observed'));assert.ok(!report.includes('PRIVATE RAW DOCUMENT'));assert.ok(!report.includes('PRIVATE INPUT QUESTION'));assert.ok(!report.includes('PRIVATE QUESTION'));
 assert.deepEqual(ui.displayResponses(result)['fit: fit-test predicted'].mask,[true,true,false,true]);
});
test('Selected saved comparison and fit aliases take precedence over packed originals',()=>{
 const selected={kind:'series',value:[2,4],unit:'N',component:'z',location:'saved',axes:[{name:'time',unit:'s',values:[100,101]}]};
 const packed={data_ref:{path:'packed.npy',sha256:'retained'}};
 const comparison={observation:{...selected,value:packed},prediction:packed,
   responses:{observation:selected,prediction:{...selected,value:[3,5]}},
   display_window:{response:'observation',requested_rows:[100,102],returned_samples:2}};
 assert.equal(ui.displayResponses(comparison).observation,selected);
 assert.match(ui.reportHTML(comparison,{id:'Jcompare',operation:'compare'}),/display_window/);
 assert.match(ui.reportHTML(comparison,{id:'Jcompare',operation:'compare'}),/<svg /);
 const fit={curves:[{role:'fit',experiment_id:'A',response:'force',rmse:1,
   observations:{...selected,value:packed},prediction:packed}],
   responses:{'fit: A observed':selected}};
 assert.equal(ui.displayResponses(fit)['fit: A observed'],selected);
 assert.match(ui.reportHTML(fit,{id:'Jfit',operation:'fit'}),/<svg /);
});

test('Actual candidate analysis exposes recorded statistics, influence, held-out error and conditions',()=>{
 const source={id:'Jdoe',operation:'doe',arguments:{backend:'external.oscillator',settings:{values:{mass_kg:1.2},conditions:{duration_s:2}},variables:[{id:'mass_kg',unit:'kg',lower:1,upper:2}],count:8,seed:41,execution:{max_evaluations:8}}};
 const job={id:'Janalyze',operation:'analyze',arguments:{job_id:'Jdoe',responses:[{response:'peak_force',unit:'N'}]}};
 const result={candidate_count:8,failure_count:0,exclusions:[],qualification:'NUMERICAL_SAMPLE_ANALYSIS_ONLY',decision:'NOT_RELEASED',
  statistics:[{metric:'peak_force',unit:'N',count:8,min:1.25,max:9.75}],
  sensitivity:[{metric:'peak_force',unit:'N',valid:true,coefficients:[{parameter_id:'mass_kg',unit:'1',coefficient:0.6125}]}],
  surrogate:[{metric:'peak_force',unit:'N',valid:true,test_rmse:0.03125,test_ids:['C1','C2'],limitations:['Held-out error is descriptive only.']}],
  limitations:['Conditional association, not causation.']};
 const summary=ui.analysisSummary(result,job,source);
 assert.deepEqual(summary.statistics,[{metric:'peak_force',unit:'N',count:8,min:1.25,max:9.75}]);
 assert.deepEqual(summary.coefficients,[{metric:'peak_force',variable:'mass_kg',coefficient:0.6125,unit:'1',reason:null}]);
 assert.equal(summary.holdout[0].rmse,0.03125);assert.equal(summary.holdout[0].test_count,2);
 assert.equal(summary.decision,'NOT_RELEASED');assert.equal(summary.source_candidate_input.settings.values.mass_kg,1.2);
 assert.equal(summary.source_candidate_input.seed,41);assert.equal(summary.input.job_id,'Jdoe');
 const report=ui.reportHTML(result,job,source);
 assert.match(report,/0\.6125/);assert.match(report,/0\.03125/);assert.match(report,/mass_kg/);assert.match(report,/NOT_RELEASED/);assert.match(report,/duration_s/);
 assert.equal(ui.analysisSummary({kind:'doe'},source),null);
});

test('Explicit session refresh obtains a new token before reloading without resubmission',async()=>{
 const order=[];
 await ui.refreshSession(async()=>{order.push('overview');return {token:'new-session-token'};},
  token=>order.push('token:'+token),async()=>order.push('reload'));
 assert.deepEqual(order,['overview','token:new-session-token','reload']);
 await assert.rejects(ui.refreshSession(async()=>({token:''}),()=>order.push('changed'),async()=>order.push('reload-again')),/Session token/);
 assert.deepEqual(order,['overview','token:new-session-token','reload']);
});
