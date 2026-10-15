"""Explicit synthetic-size probe. NEVER a native solve or physics acceptance.

Uses cyclic unchanged ASCII payloads from supplied 3 native frames, synthetic
step/increment/time headers, the unmodified 1085-node/502-element model, and
EXACT common ContactFemCalculixAdapter with only its owned process substituted.
No all-frame list is constructed by this generator or the dynamic pipeline.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import threading
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


PRODUCT_FILES = (
    'caelab/dynamic_native_stream.py', 'caelab/dynamic_result_store.py',
    'caelab/dynamic_results.py', 'caelab/dynamic_execution.py',
    'caelab/dynamic_recovery.py', 'caelab/dynamic_recovery_job.py',
    'caelab/dynamic_locations.py', 'caelab/dynamic_post.py',
    'caelab/adapters/dynamic_fem.py', 'caelab/adapters/frozen_fem.py',
    'caelab/contact_steps.py', 'caelab/contact_status.py',
    'caelab/adapters/contact_results.py', 'caelab/adapters/contact_fem.py',
    'caelab/workbench.py', 'caelab/native_inputs.py',
    'apps/desktop_post/external.py', 'caelab/contact_inspection.py',
    'caelab/dynamic_restart.py', 'tools/profile_dynamic_r2.py')


def source_fingerprints():
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in PRODUCT_FILES}


class CountRead:
    """Observe actual bytes returned by Path-based binary reads during queries only."""
    def __init__(self, stream, count): self.stream, self.count = stream, count
    def __getattr__(self, name): return getattr(self.stream, name)
    def __enter__(self): self.stream.__enter__(); return self
    def __exit__(self, *args): return self.stream.__exit__(*args)
    def read(self, *args):
        value=self.stream.read(*args); self.count(len(value)); return value
    def readinto(self, buffer):
        n=self.stream.readinto(buffer); self.count(n or 0); return n
    def readline(self, *args):
        value=self.stream.readline(*args); self.count(len(value)); return value
    def __iter__(self): return self
    def __next__(self):
        value=self.readline()
        if not value: raise StopIteration
        return value


def emit(sample,out,per_step):
    from caelab.adapters.contact_fem import validate_snapshot
    from caelab.contact_steps import compile_program
    from caelab.dynamic_results import _HEADER
    manifest,model,_,_=validate_snapshot(sample/'frozen_input/snapshot.json')
    # Fixed 3-frame public seed only; this list NEVER grows with requested frames.
    lines=(sample/'first-three-frames.frd').read_text(encoding='ascii').splitlines(True)
    at=[i for i,s in enumerate(lines) if s.split()[:1]==['1PSTEP']]
    groups=[];last=None
    for start,end in zip(at,at[1:]+[len(lines)]):
        cols=lines[start].split();key=cols[2],cols[3]
        if key!=last:groups.append([]);last=key
        groups[-1].extend(s for s in lines[start:end] if s.strip()!='9999')
    assert len(groups)==3
    dat=(sample/'first-three-times.dat').read_text(encoding='ascii').splitlines(True)
    starts=[i for i,s in enumerate(dat) if _HEADER.match(s)]
    blocks=[]
    for i in range(3):
        block=dat[starts[i]:starts[i+1]]
        blocks.append([s for s in block if not re.match(r'\s*(S\s+T\s+E\s+P|INCREMENT)\b',s)])
    output_count=0;field_count=0;out.mkdir(parents=True)
    with (out/'contact.frd').open('w',encoding='ascii',newline='\n') as frd, \
         (out/'contact.dat').open('w',encoding='ascii',newline='\n') as d, \
         (out/'contact.sta').open('w',encoding='ascii',newline='\n') as sta:
        frd.writelines(lines[:at[0]]);sta.write('SUMMARY OF JOB INFORMATION\n')
        for stage in compile_program(model['analysis_steps'],model['conditions']):
            last_time=0.
            for inc in range(1,per_step+1):
                local=stage['duration']*inc/per_step;native=stage['start']+local;token=format(native,'.9E')
                output_count+=1
                for s in groups[(inc-1)%3]:
                    if s.split()[:1]==['1PSTEP']:
                        field_count+=1
                        s='    1PSTEP'+' '*14+f'{field_count:12d}{inc:12d}{stage["index"]:12d}'+' '*10+'\n'
                    elif s.split()[:1]==['100CL']:
                        s='  100CL'+f'{100+output_count:5d}{native:12.9f}{len(model["nodes"]):12d}'+' '*21+'1'+f'{output_count:5d}'+' '*11+'1\n'
                    frd.write(s)
                d.write(f'\n S T E P {stage["index"]}\n INCREMENT {inc}\n')
                for block in blocks:
                    d.write(re.sub(r'(and time\s+)\S+',lambda m:m[1]+token,block[0]));d.writelines(block[1:])
                sta.write(f' {stage["index"]} {inc} 1 2 {native:.9E} {local:.9E} {local-last_time:.9E}\n');last_time=local
        frd.write(' 9999\n')
    return model,manifest,output_count


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frames-per-step',type=int,choices=range(3,201),default=3)
    args=p.parse_args();out=args.output.resolve()
    if out.exists():raise ValueError('Use a NEW probe output directory')
    out.mkdir(parents=True);sample=ROOT/'tests/fixtures/dynamic_r2_public_native'
    source_before=source_fingerprints()
    model,manifest,frame_count=emit(sample,out/'synthetic',args.frames_per_step)
    shutil.copytree(sample/'frozen_input',out/'input')
    exe=out/'EXPLICIT_SYNTHETIC_PROCESS_DOUBLE';exe.write_text('NOT A CALCULIX EXECUTABLE')
    from caelab.adapters import contact_fem
    from caelab import dynamic_result_store as store
    from caelab import dynamic_locations as loc
    from caelab.dynamic_native_stream import NativeFrames
    from caelab.dynamic_results import history
    import psutil
    proc=psutil.Process();baseline=proc.memory_info().rss;peak=[baseline];stop=threading.Event()
    def monitor():
        while not stop.wait(.01):peak[0]=max(peak[0],proc.memory_info().rss)
    watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
    native_calls=[];spool_max=[];strict_scans=[]
    original_close=NativeFrames.close
    def close(self):spool_max.append(self.max_resident_frames);return original_close(self)
    NativeFrames.close=close
    contact_fem.shutil.which=lambda _:str(exe)
    def process(arguments,cwd,label):
        native_calls.append('OWNED_PROCESS_DOUBLE_NO_EXECUTABLE')
        for ext in ('frd','dat','sta'):shutil.copyfile(out/'synthetic'/('contact.'+ext),cwd/('contact.'+ext))
        return SimpleNamespace(returncode=0)
    contact_fem.run_owned_command=process
    start=time.perf_counter()
    result=contact_fem.ContactFemCalculixAdapter().run({'snapshot_path':str(out/'input/snapshot.json')},output=out/'attempt')
    elapsed=time.perf_counter()-start;stop.set();watcher.join();peak[0]=max(peak[0],proc.memory_info().rss)
    if result['execution_status']!='SUCCEEDED':
        print(json.dumps({'status':result['execution_status'],'diagnostics':result.get('diagnostics'),'postprocessing':result.get('postprocessing')},ensure_ascii=False),flush=True)
        raise RuntimeError('Synthetic pipeline did not complete')
    arrays=[];hashed=[];original_json=store._json;original_sha=store._sha;original_locsha=loc._sha
    def js(root,pin,*a,**kw):arrays.append({'relative':pin['relative'],'bytes':pin['bytes']});return original_json(root,pin,*a,**kw)
    def sha(path):hashed.append({'name':str(path),'bytes':Path(path).stat().st_size});return original_sha(path)
    def lsha(path):hashed.append({'name':str(path),'bytes':Path(path).stat().st_size});return original_locsha(path)
    store._json=js;store._sha=sha;loc._sha=lsha
    phase=['metadata']; actual_io={}
    original_open=Path.open
    def counted_open(path,*args,**kwargs):
        stream=original_open(path,*args,**kwargs)
        mode=args[0] if args else kwargs.get('mode','r')
        if 'r' not in mode or not Path(path).is_relative_to(out/'attempt'): return stream
        name=Path(path).relative_to(out/'attempt').as_posix()
        def count(n):
            entries=actual_io.setdefault(phase[0],{})
            entries[name]=entries.get(name,0)+n
        return CountRead(stream,count)
    Path.open=counted_open
    start=time.perf_counter();meta=store.read_attempt(out/'attempt',metadata_only=True);metadata_seconds=time.perf_counter()-start
    metadata_arrays=list(arrays);metadata_hashes=list(hashed);arrays.clear();hashed.clear()
    phase[0]='selected_frame'
    start=time.perf_counter();selection=store.select_frame(out/'attempt',frame_count-2);selection_seconds=time.perf_counter()-start
    selected_arrays=list(arrays);selected_hashes=list(hashed);arrays.clear();hashed.clear()
    a=result['dynamic_post_artifacts']['dynamic'];entry=out/'attempt'/a['relative']
    phase[0]='post_metadata'
    start=time.perf_counter();bundle=loc.load(entry,a['native_metadata']);post_open_seconds=time.perf_counter()-start
    post_metadata_hashes=list(hashed);arrays.clear();hashed.clear()
    phase[0]='post_selected'
    start=time.perf_counter();chosen=loc.select(entry,a['native_metadata'],time=bundle['frames'][-2]['timestep']);post_select_seconds=time.perf_counter()-start
    selected_post_hashes=list(hashed);post_arrays=list(arrays)
    Path.open=original_open
    assert len(meta.index['frames'])==frame_count
    assert len(list((out/'attempt').rglob('*.vtu')))==frame_count
    assert metadata_arrays==[] and len(selected_arrays)==2
    assert max(spool_max)<=3
    assert not any(row['name'].endswith(('.frd','.dat','.rout','.vtu','.FCStd')) for row in metadata_hashes+post_metadata_hashes)
    assert len([row for row in selected_post_hashes if row['name'].endswith('.vtu')])==1
    for name in ('metadata','post_metadata'):
        assert not any(key.endswith(('.frd','.dat','.rout','.vtu','.FCStd')) or
                       re.search(r'(?:^|/)frame[0-9]+\.json$',key) for key in actual_io[name])
    source_after=source_fingerprints();assert source_before==source_after
    # Persist only metrics and exact file hashes in the final delivery, not GB-sized doubles.
    report={'source_sha256':source_before,'source_unchanged_during_probe':True,
        'host':{'platform':platform.platform(),'python':sys.version},
        'query_actual_read_bytes':{name:sum(rows.values()) for name,rows in actual_io.items()},
        'query_actual_reads':actual_io,
        'kind':'EXPLICIT_SYNTHETIC_SIZE_DOUBLE_NOT_NATIVE_SOLVE','frames':frame_count,
        'model_nodes':len(model['nodes']),'model_elements':len(model['elements']),
        'input_model_sha256':hashlib.sha256((sample/'frozen_input/mesh.json').read_bytes()).hexdigest(),
        'actual_sample_frames':3,'synthetic_time_headers':True,'cyclic_seed_values':True,
        'native_solver_executions':0,'owned_process_double_calls':len(native_calls),
        'qualification':'UNKNOWN','physical_acceptance':'NOT_RUN','Windows_READ':'NOT_RUN',
        'pipeline_seconds':elapsed,'rss_start_bytes':baseline,'rss_peak_bytes':peak[0],
        'rss_peak_delta_bytes':peak[0]-baseline,'rss_measurement':'psutil RSS sample 10ms, entire adapter, fresh process',
        'native_frame_spool_cache_high_water':max(spool_max),'vtu_count':frame_count,
        'synthetic_source_bytes':{p.name:p.stat().st_size for p in (out/'synthetic').iterdir()},
        'index_bytes':(out/'attempt/dynamic_result.json').stat().st_size,
        'frame_artifact_bytes':sum(p.stat().st_size for p in (out/'attempt/dynamic-frames').iterdir()),
        'attempt_file_bytes':sum(p.stat().st_size for p in (out/'attempt').rglob('*') if p.is_file()),
        'metadata_seconds':metadata_seconds,'metadata_frame_reads':metadata_arrays,
        'metadata_hash_bytes':sum(p['bytes'] for p in metadata_hashes),
        'selected_seconds':selection_seconds,'selected_frame_reads':selected_arrays,
        'post_metadata_seconds':post_open_seconds,'post_metadata_hash_bytes':sum(p['bytes'] for p in post_metadata_hashes),
        'post_select_seconds':post_select_seconds,'post_selected_hash_bytes':sum(p['bytes'] for p in selected_post_hashes),
        'post_selected_array_reads':post_arrays,'post_location':chosen['selected_native'],
        'verification':selection['verification']}
    (out/'probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
