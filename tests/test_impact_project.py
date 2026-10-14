"""Retained user bundles, topology and the existing physical converter contract.

stdlib unittest is also collected by pytest; no solver is started here.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid

from caelab.impact_source import capture,resolve,retain,SourceError,ImportCancelled,export_effective
from caelab.impact_model import model_from_settings,render,default_settings,validate_settings,BACKEND
from caelab import impact_sets as sets
from examples.impact.include_project import settings

ROOT=Path(__file__).resolve().parents[1]


def tetra_pair(quadratic=False):
    nodes={1:[0,0,0],2:[1,0,0],3:[0,1,0],4:[0,0,1],5:[0,0,-1]}
    a,b=[1,2,3,4],[1,3,2,5]
    if quadratic:
        for n,(u,v) in enumerate([(1,2),(2,3),(3,1),(1,4),(2,4),(3,4),(1,5),(3,5),(2,5)],6):nodes[n]=[(x+y)/2 for x,y in zip(nodes[u],nodes[v])]
        a += [6,7,8,9,10,11];b += [8,7,6,12,13,14]
    return {'nodes':nodes,'elements':{1:{'type':'C3D10' if quadratic else 'C3D4','nodes':a},2:{'type':'C3D10' if quadratic else 'C3D4','nodes':b}},'elsets':{'A':{1},'B':{2},'ALL':{1,2}},'nsets':{},'surfaces':{}}


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'입력 작업';shutil.copytree(ROOT/'examples/impact/include-project',self.root)
    def tearDown(self):self.temp.cleanup()
    def test_nested_submission_root_bytes_repetition_windows_separators(self):
        entry=self.root/'model.inp'
        content=entry.read_text().replace('Mesh Parts/Base.inp','Mesh Parts\\Base.inp')
        # Repeated legal NSET declarations remain repeated in flattened input.
        (self.root/'Repeated.inp').write_bytes(b'*NSET,NSET=REPEAT\r\n1,2\r\n')
        entry.write_bytes((content+'*INCLUDE,INPUT=Repeated.inp\n*INCLUDE,INPUT=Repeated.inp\n').replace('\n','\r\n').encode())
        original=entry.read_bytes();source=capture(entry,self.root)
        self.assertEqual(source['bundle']['files'][0]['text'].encode(),original)
        self.assertEqual(source['text'].count('*NSET,NSET=REPEAT'),2)
        self.assertEqual(len([o for o in source['bundle']['order'] if o['file']=='Repeated.inp']),2)
        self.assertIn('Mesh Parts/Base nodes.inp',[f['path'] for f in source['bundle']['files']])
        s=default_settings();s['source']=source;self.assertEqual(model_from_settings(s)['nsets']['REPEAT'],{1,2})
        shutil.rmtree(self.root)
        self.assertEqual(resolve(json.loads(json.dumps(source)))[0],source['text'])
        out=Path(self.temp.name)/'retained';retain(source,out)
        self.assertEqual((out/'files/model.inp').read_bytes(),original)
    def test_cycle_missing_escape_symlink_and_cancel_leave_caller_unchanged(self):
        entry=self.root/'model.inp';original=entry.read_bytes()
        for name in ('missing.inp','../outside.inp','C:\\outside.inp','//server/share.inp','NUL'):
            entry.write_text('*INCLUDE,INPUT='+name+'\n')
            with self.assertRaises(SourceError):capture(entry,self.root)
        entry.write_text('*INCLUDE,INPUT=loop.inp\n');(self.root/'loop.inp').write_text('*INCLUDE,INPUT=model.inp\n')
        with self.assertRaisesRegex(SourceError,'순환'):capture(entry,self.root)
        entry.write_bytes(original)
        with self.assertRaises(ImportCancelled):capture(entry,self.root,cancel=lambda:True)
        self.assertEqual(entry.read_bytes(),original)
        link=self.root/'link.inp'
        try:link.symlink_to(entry)
        except OSError:return
        with self.assertRaises(ValueError):capture(link,self.root)
    def test_original_locations_duplicates_and_untrusted_flatten(self):
        entry=self.root/'model.inp';included=self.root/'Materials/Elastic.inp'
        included.write_text('*PART,NAME=BAD\n')
        source=capture(entry,self.root);s=default_settings();s['source']=source
        with self.assertRaises(SourceError) as failure:model_from_settings(s)
        self.assertEqual(failure.exception.file,'Materials/Elastic.inp');self.assertEqual(failure.exception.line,1)
        self.assertIn('PART',str(failure.exception))
        included.write_text('*NODE\n1,0,0,0\n')
        source=capture(entry,self.root);s['source']=source
        with self.assertRaises(SourceError) as failure:model_from_settings(s)
        self.assertEqual((failure.exception.file,failure.exception.line),('Materials/Elastic.inp',2))
        for key in ('text','bundle'):
            changed=deepcopy(source)
            if key=='text':changed[key]+='** tampered\n'
            else:changed[key]['files'][0]['text']+='** tampered\n'
            with self.assertRaises(ValueError):resolve(changed)
    def test_blank_root_malformed_card_and_original_cross_reference_location(self):
        from caelab.impact_model import parse_inp
        with self.assertRaisesRegex(SourceError,'명시적으로'):capture(self.root/'model.inp','')
        for text in ('*\n','*,\n'):
            with self.assertRaisesRegex(SourceError,'빈 입력 카드'):parse_inp(text)
        member=self.root/'Mesh Parts/Moving.inp'
        content=member.read_text().replace('2,11,12,13,14,15,16,17,18','2,11,12,13,14,15,16,17,999')
        self.assertIn('999',content);member.write_text(content)
        source=capture(self.root/'model.inp',self.root);s=default_settings();s['source']=source
        with self.assertRaises(SourceError) as failure:model_from_settings(s)
        self.assertEqual(failure.exception.file,'Mesh Parts/Moving.inp')
        self.assertEqual(failure.exception.line,next(i for i,row in enumerate(content.splitlines(),1) if '999' in row))
    def test_repeated_set_missing_member_and_empty_surface_keep_own_file_row(self):
        entry=self.root/'model.inp'
        entry.write_text(entry.read_text()+'*INCLUDE,INPUT=bad.inp\n*INCLUDE,INPUT=good.inp\n')
        (self.root/'good.inp').write_text('*NSET,NSET=REPEATED\n1,\n')
        for text,line in (('*NSET,NSET=REPEATED\n999,\n',2),('*NSET,NSET=EMPTY\n',1),('*SURFACE,NAME=EMPTY,TYPE=ELEMENT\n',1)):
            (self.root/'bad.inp').write_text(text)
            s=default_settings();s['source']=capture(entry,self.root)
            with self.assertRaises(SourceError) as failure:model_from_settings(s)
            self.assertEqual((failure.exception.file,failure.exception.line),('bad.inp',line))
    def test_file_replacement_between_validation_and_open_is_rejected(self):
        from unittest.mock import patch
        import os
        entry=self.root/'model.inp';real_open=os.open;replaced=False
        def opening(path,flags,*args,**kwargs):
            nonlocal replaced
            if Path(path)==entry and not replaced:
                replaced=True
                temporary=entry.with_suffix('.replacement');temporary.write_bytes(entry.read_bytes())
                os.replace(temporary,entry)
            return real_open(path,flags,*args,**kwargs)
        with patch('caelab.impact_source.os.open',opening):
            with self.assertRaisesRegex(SourceError,'변경'):capture(entry,self.root)
        self.assertTrue(replaced)
    def test_bounded_expansion_and_case_collision(self):
        from unittest.mock import patch
        entry=self.root/'model.inp'
        with patch('caelab.impact_source.MAX_BYTES',32):
            with self.assertRaises(ValueError):capture(entry,self.root)
        entry.write_text('*INCLUDE,INPUT=A.inp\n*INCLUDE,INPUT=a.inp\n')
        (self.root/'A.inp').write_text('** A\n');(self.root/'a.inp').write_text('** a\n')
        with self.assertRaisesRegex(ValueError,'대소문자'):capture(entry,self.root)


class TargetTests(unittest.TestCase):
    def test_global_exterior_and_exact_quadratic_topology(self):
        for quadratic in (False,True):
            m=tetra_pair(quadratic)
            self.assertEqual(len(sets.candidates(m,'ALL')),6)
            self.assertEqual(len(sets.candidates(m,'A')),3)
            self.assertEqual(sum(f['internal'] for f in sets.candidates(m,'A','explicit')),1)
        m=tetra_pair(True);m['elements'][2]['nodes'][4:6]=m['elements'][2]['nodes'][5:3:-1]
        with self.assertRaisesRegex(ValueError,'중간 절점'):sets.candidates(m,'ALL')
        m=tetra_pair(True);m['nodes'][15]=[.5,0,0];m['elements'][2]['nodes'][6]=15
        with self.assertRaisesRegex(ValueError,'중간 절점'):sets.candidates(m,'ALL')
    def test_nonmanifold_inversion_and_internal_selection(self):
        m=tetra_pair();m['elements'][3]=deepcopy(m['elements'][1])
        with self.assertRaisesRegex(ValueError,'비다양체'):sets.facets(m)
        m=tetra_pair();m['elements'][1]['nodes']=[1,3,2,4]
        with self.assertRaisesRegex(ValueError,'뒤집힌'):sets.facets(m)
        s=settings();m=tetra_pair()
        with self.assertRaisesRegex(ValueError,'내부면'):sets.create_surface(s['source'],m,'INNER','A','explicit',[(1,'S1')])
        d=sets.create_surface(s['source'],m,'INNER','A','explicit',[(1,'S1')],allow_internal=True)
        self.assertTrue(d['allow_internal'])
    def test_cohesive_only_physical_faces_and_all_motion_nodes(self):
        from caelab.impact_model import parse_inp
        m=parse_inp((ROOT/'examples/impact/cohesive-coupon.inp').read_text())
        cohesive={e for e,row in m['elements'].items() if row['type']=='COH3D8'}
        m['elsets']['INTERFACE']=cohesive
        self.assertTrue(all(f['side'] in ('S1','S2') for f in sets.candidates(m,'INTERFACE','explicit')))
        s=settings();m=tetra_pair(True)
        d=sets.create_node_set(s['source'],m,'BODY','A')
        self.assertEqual(len(d['nodes']),10)
    def test_generated_sets_are_separate_retained_bound_and_referenced(self):
        s=settings();original=deepcopy(s['source']);model=model_from_settings(s)
        self.assertEqual(model['nsets']['MOVEMENT'],set(range(11,19)))
        self.assertNotIn('MOVEMENT',s['source']['text'])
        text,initial=render(s);self.assertIn('*NSET,NSET=MOVEMENT',text);self.assertEqual(s['source'],original)
        with self.assertRaisesRegex(ValueError,'사용 중'):sets.delete(s,0)
        bad=deepcopy(s);bad['source']['bundle']['files'][0]['text']+='** changed\n'
        with self.assertRaises(ValueError):model_from_settings(bad)
        other=sets.create_node_set(s['source'],model,'OVERLAP','MOVING');s['generated_sets'].append(other)
        motion=deepcopy(s['motions'][0]);motion['node_set']='OVERLAP';s['motions'].append(motion)
        with self.assertRaisesRegex(ValueError,'겹치지'):validate_settings(s)
    def test_generated_identity_rejects_boolean_and_fractional_aliases(self):
        for value in (True,1.0,'1'):
            s=settings();s['generated_sets'][1]['faces'][0][0]=value
            with self.assertRaisesRegex(ValueError,'정수'):validate_settings(s)
        s=settings();s['generated_sets'][1]['allow_internal']=1
        with self.assertRaisesRegex(ValueError,'내부면'):validate_settings(s)
        s=settings();s['generated_sets'][0]['nodes'][0]=11.0
        with self.assertRaisesRegex(ValueError,'정수'):validate_settings(s)
    def test_actual_converter_and_native_physics_admission_of_generated_targets(self):
        from caelab.adapters.impact import converted_mesh
        from caelab.adapters.impact_admission import global_gravity,normalize_contact_friction,normalize_surfaces,validate_physics
        import caelab.adapters.inp2rad_worker as worker
        s=settings();m=model_from_settings(s);text,initial=render(s)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'impact.inp';export_effective(s,path)
            with self.assertRaises(FileExistsError):export_effective(s,path)
            process=subprocess.run([sys.executable,worker.__file__,str(path)],capture_output=True,text=True,timeout=30)
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)
            deck=root/'impact_0000.rad';self.assertEqual(converted_mesh(deck,m,initial['nodes'])['element_count'],2)
            effective,_=global_gravity(deck.read_text(),s['gravity_mm_s2'])
            effective=normalize_contact_friction(effective,s);effective,_=normalize_surfaces(effective,m)
            validate_physics(effective,m,initial,s)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('filelock','jsonschema')),
                     'Existing Workbench dependencies unavailable; real HTTP/owner check NOT_RUN')
class OwnerTests(unittest.TestCase):
    def test_real_http_large_bundle_invalid_draft_save_cold_reopen_no_jobs(self):
        from apps.lab.server import LabHTTPServer
        from apps.lab.service import LabService
        from caelab.workbench_client import Client
        from caelab.workbench import Workbench
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);bundle=root/'bundle';shutil.copytree(ROOT/'examples/impact/include-project',bundle)
            entry=bundle/'model.inp';entry.write_text('** '+('large original comment '*5000)+'\n'+entry.read_text())
            s=settings(bundle);s['motions'][0]['velocity_mm_s'][2]='1e'
            server=LabHTTPServer(LabService(root/'store'),0);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02});thread.start()
            try:
                client=Client('http://127.0.0.1:'+str(server.server_port))
                doc=client.document_open(kind='simulation',title='보존 입력',draft={'backend':BACKEND,'settings':s})
                saved=client.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)['document']
                self.assertTrue(saved['diagnostics']);self.assertEqual(server.workbench.manager.list(),[])
                from urllib.error import HTTPError
                with self.assertRaises(HTTPError) as refusal:
                    client.request('/api/workbench/jobs',{'padding':'x'*(129*1024)})
                self.assertEqual(refusal.exception.code,413)
                workspace=server.workbench.workspace
            finally:
                server.shutdown();server.server_close();thread.join(3)
            shutil.rmtree(bundle)
            fresh=Workbench(workspace)
            try:
                reopened=fresh.document_open(kind='simulation',document_id=doc['id'])
                self.assertEqual(reopened['draft']['settings'],s)
                fixed=deepcopy(s);fixed['motions'][0]['velocity_mm_s'][2]=-10.
                validate_settings(fixed);self.assertIn('MOVEMENT',render(fixed)[0]);self.assertEqual(fresh.manager.list(),[])
            finally:fresh.shutdown()


@unittest.skipUnless(os.environ.get('CAELAB_RUN_IMPACT_PROJECT')=='1',
                     'Explicit installed OpenCourant run; native execution NOT_RUN by default')
class NativeProjectTests(unittest.TestCase):
    def test_installed_include_model_retention_converter_engine_post(self):
        from caelab.evaluation import run,read_result
        from caelab.research_execution import publish_fields
        from caelab.workbench import Workbench
        # Retain even failed native attempts for integration diagnosis.
        root=Path(tempfile.mkdtemp(prefix='cae-impact-project-'))
        print('Retained native attempt:',root,flush=True)
        s=settings();calculation=root/'attempt'/'calculation'
        result=run(BACKEND,s,output=calculation)
        self.assertEqual(result['execution_status'],'SUCCEEDED',result)
        self.assertTrue(result['post_artifacts']);self.assertGreater(result['diagnostics']['frame_count'],0)
        saved=read_result(calculation,verify='all');self.assertEqual(saved['settings'],s)
        retained=calculation/'source_bundle'
        self.assertEqual((retained/'files/model.inp').read_bytes(),(ROOT/'examples/impact/include-project/model.inp').read_bytes())
        self.assertEqual(json.loads((calculation/'generated_sets.json').read_text(encoding='utf-8')),s['generated_sets'])
        wb=Workbench(root/'store')
        try:
            publish_fields(wb,result,root/'attempt');self.assertEqual(result['post_input']['format'],'pvd')
        finally:wb.shutdown()


if __name__=='__main__':unittest.main()
