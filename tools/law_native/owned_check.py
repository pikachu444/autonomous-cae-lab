"""Run one bounded check, retaining exit/timeout and closing ONLY its owned tree."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from caelab.execution_control import wait_for_process,stop_owned_process


def run(command,folder,timeout):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    receipt={'command':list(command),'cwd':str(ROOT),'timeout_s':timeout,'status':'STARTING',
             'platform':sys.platform,'python':sys.version,'pid':None,'cleanup':'NOT_STARTED'}
    process=None;started=time.monotonic();code=1
    try:
        with (folder/'stdout.log').open('wb') as out,(folder/'stderr.log').open('wb') as err:
            env=dict(os.environ, PYTHONPATH=str(ROOT),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
            try:
                if os.name=='nt':
                    from caelab.windows_job import spawn_gated,release_gate
                    process,ready=spawn_gated(command,cwd=ROOT,stdout=out,stderr=err,env=env,label='law-check')
                    receipt['pid']=process.pid
                    release_gate(process,ready,lambda:None)
                else:
                    process=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,env=env,start_new_session=True)
                    receipt['pid']=process.pid
                code=wait_for_process(process,timeout)
                receipt.update(status='PASS' if code==0 else 'FAIL',return_code=code)
            except subprocess.TimeoutExpired:
                receipt.update(status='TIMEOUT',return_code=None);code=124
            except BaseException as error:
                receipt.update(status='ERROR',error_type=type(error).__name__,error=str(error));code=1
            finally:
                if process is not None:
                    # Existing helper owns the Popen/Job, never process-name/PID lookup.
                    try:
                        stop_owned_process(process,isolated_group=os.name=='posix')
                        receipt.update(cleanup='CONFIRMED_REAPED',observed_return_code=process.returncode)
                    except BaseException as error:
                        receipt.update(cleanup='UNKNOWN',cleanup_error=str(error));code=125
    finally:
        receipt['elapsed_s']=time.monotonic()-started
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False));return code


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--timeout',type=float,default=45)
    parser.add_argument('command',nargs=argparse.REMAINDER);a=parser.parse_args()
    command=a.command[1:] if a.command[:1]==['--'] else a.command
    if not command or not 0<a.timeout<=600:parser.error('Provide a command and timeout in (0,600] seconds')
    return run(command,a.output,a.timeout)


if __name__=='__main__':raise SystemExit(main())
