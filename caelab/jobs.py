"""One local controller per workspace; transports share owned jobs and results."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import os
import threading
import time
import uuid
from filelock import FileLock, Timeout
from .execution_control import CancellationToken, cancellation_scope, ExecutionCancelled, ExecutionCleanupFailed
from .storage import save_json, load_json, canonical_hash, check_id, utc_now
from .evaluation import save_evaluation, read_result

TERMINAL = {'SUCCEEDED', 'FAILED', 'PARTIAL_FAILURE', 'CANCELLED', 'INTERRUPTED'}


class JobManager:
    def __init__(self, root, execute, *, workers=2, cpu_budget=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._owner = FileLock(self.root / 'controller.lock', timeout=0)
        try:
            self._owner.acquire()
        except Timeout as error:
            raise RuntimeError('Workspace already has a controller; connect to its service') from error
        self._execute = execute
        self.cpu_budget = cpu_budget or max(1, os.cpu_count() or 1)
        if type(workers) is not int or not 1 <= workers <= self.cpu_budget:
            self._owner.release()
            raise ValueError('workers must fit the declared CPU budget')
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='caelab-job')
        # A model turn may submit/poll numerical children. Keep one orchestration
        # thread outside the solver pool so it cannot occupy the last child slot.
        self._assist_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='caelab-expert')
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._reserved_cpus = 0
        self._cleanup_reservations = {}
        self._jobs, self._tokens, self._futures = {}, {}, {}
        self._accepting = True
        (self.root / 'jobs').mkdir(exist_ok=True)
        for path in sorted((self.root / 'jobs').glob('*.json')):
            job = load_json(path)
            check_id(job['id'])
            if job['state'] not in TERMINAL:
                job.update(state='INTERRUPTED', status='INTERRUPTED', phase='REQUIRES_CONFIRMATION',
                           message='Previous controller ended without a terminal receipt; no automatic replay or PID adoption')
                save_json(path, job)
            self._jobs[job['id']] = job

    def _persist(self, job):
        job['status'] = job['state']
        job['updated_utc'] = utc_now()
        save_json(self.root / 'jobs' / (job['id'] + '.json'), job)

    def submit(self, operation, arguments, *, workspace_id='local', request_id=None, resources=None):
        resources = deepcopy(resources or {})
        threads = resources.get('threads', 1)
        if type(threads) is not int or not 1 <= threads <= self.cpu_budget:
            raise ValueError('Requested solver threads exceed the controller CPU budget')
        if set(resources) - {'threads', 'memory_mb'}:
            raise ValueError('Unknown resource field')
        memory = resources.get('memory_mb')
        if memory is not None and (type(memory) not in (int, float) or not 0 < memory < float('inf')):
            raise ValueError('memory_mb must be a finite positive reservation hint')
        if request_id is not None and (not isinstance(request_id,str) or not request_id or len(request_id)>128):
            raise ValueError('request_id must be a nonempty string of at most 128 characters')
        signature = canonical_hash({'operation':operation, 'arguments':arguments, 'resources':resources})
        with self._lock:
            if request_id is not None:
                for job in self._jobs.values():
                    if job.get('request_id') == request_id and job['workspace_id'] == workspace_id:
                        if job['request_hash'] != signature:
                            raise ValueError('request_id conflicts with an earlier request')
                        return deepcopy(job)
            if not self._accepting:
                raise RuntimeError('Controller is shutting down')
            identifier='J'+uuid.uuid4().hex
            job={'id':identifier,'job_id':identifier,'workspace_id':workspace_id,'operation':operation,
                 'arguments':deepcopy(arguments),'request_id':request_id,'request_hash':signature,
                 'state':'QUEUED','phase':'QUEUED','created_utc':utc_now(),'resources':resources,
                 'resource_enforcement':{'cpu':'child_jobs_reserved_separately' if operation=='experts.ask' else 'controller_concurrency_budget','memory':'HINT_ONLY'},
                 'result_refs':[], 'cancel_requested':False}
            self._jobs[identifier]=job
            self._tokens[identifier]=CancellationToken()
            self._persist(job)
            executor=self._assist_pool if operation=='experts.ask' else self._pool
            self._futures[identifier]=executor.submit(self._run,identifier)
            return deepcopy(job)

    def _run(self, identifier):
        token=self._tokens[identifier]
        reserved=0
        cleanup_unconfirmed=False
        try:
            with self._condition:
                job=self._jobs[identifier]
                threads=0 if job['operation']=='experts.ask' else job['resources'].get('threads',1)
                while self._reserved_cpus+threads>self.cpu_budget:
                    token.check()
                    self._condition.wait(.1)
                token.check()
                self._reserved_cpus+=threads
                reserved=threads
                job.update(state='RUNNING',phase='CALCULATING',started_utc=utc_now())
                self._persist(job)
            with cancellation_scope(token):
                token.check()
                result=self._execute(job['operation'],deepcopy(job['arguments']),identifier)
            if token.cleanup_pending:
                raise ExecutionCleanupFailed('Owned native cleanup remains unconfirmed')
            result_path=self.root/'results'/identifier
            if not result_path.exists():
                save_evaluation(result,result_path)
            with self._lock:
                job['result_refs']=[f'results/{identifier}']
                outcome=result.get('execution_status')
                state='CANCELLED' if token.observed or outcome=='CANCELLED' else ('PARTIAL_FAILURE' if outcome=='PARTIAL_FAILURE' else ('FAILED' if outcome in {'FAILED','REJECTED'} else 'SUCCEEDED'))
                job.update(state=state,phase='FINISHED',finished_utc=utc_now())
                self._persist(job)
        except BaseException as error:
            cleanup_unconfirmed=isinstance(error,ExecutionCleanupFailed)
            with self._lock:
                job=self._jobs[identifier]
                state=('CLEANUP_PENDING' if token.cleanup_pending or cleanup_unconfirmed else 'CANCELLED' if token.observed else 'FAILED')
                job.update(state=state,phase='CLEANUP' if state=='CLEANUP_PENDING' else 'FINISHED',
                           error={'code':type(error).__name__,'message':str(error),'retryable':False},
                           cleanup_unconfirmed=cleanup_unconfirmed,finished_utc=utc_now() if state!='CLEANUP_PENDING' else None)
                self._persist(job)
        finally:
            with self._condition:
                if token.cleanup_pending or cleanup_unconfirmed:
                    self._cleanup_reservations[identifier]=reserved
                else:
                    self._reserved_cpus-=reserved
                self._condition.notify_all()

    def status(self, identifier):
        check_id(identifier)
        with self._lock:
            if identifier not in self._jobs:
                raise KeyError('Job not found')
            return deepcopy(self._jobs[identifier])

    def list(self):
        with self._lock:
            return [deepcopy(job) for job in self._jobs.values()]

    def cancel(self, identifier):
        with self._condition:
            job=self._jobs[check_id(identifier)]
            if job['state'] in TERMINAL:
                return deepcopy(job)
            token=self._tokens.get(identifier)
            if token is None:
                return deepcopy(job)
            token.request()
            job['cancel_requested']=True
            if job.get('cleanup_unconfirmed') and not token.cleanup_pending:
                # A lost worker is not an owned live handle that can be retried.
                self._persist(job)
                return deepcopy(job)
            if token.cleanup_pending:
                token.retry_cleanup(timeout=1)
                future=self._futures[identifier]
                if not token.cleanup_pending and future.done():
                    self._reserved_cpus-=self._cleanup_reservations.pop(identifier,0)
                    job.update(state='CANCELLED' if token.observed else 'FAILED',phase='FINISHED',finished_utc=utc_now())
            else:
                job.update(state='CANCEL_REQUESTED',phase='AWAITING_SAFE_STOP')
            self._persist(job)
            self._condition.notify_all()
            return deepcopy(job)

    def result(self, identifier, *, selection=None):
        job=self.status(identifier)
        if not job['result_refs']:
            raise ValueError('This job has no retained result')
        return read_result(self.root/job['result_refs'][0],selection=selection)

    def shutdown(self, timeout=5):
        with self._lock:
            self._accepting=False
            pending=[identifier for identifier,job in self._jobs.items() if job['state'] not in TERMINAL]
        for identifier in pending:
            self.cancel(identifier)
        deadline=time.monotonic()+timeout
        for future in list(self._futures.values()):
            try:
                future.result(timeout=max(0,deadline-time.monotonic()))
            except TimeoutError:
                break
        self._pool.shutdown(wait=False)
        self._assist_pool.shutdown(wait=False)
        pending=[job['id'] for job in self.list() if job['state'] not in TERMINAL]
        if not pending:
            self._owner.release()
        return {'joined':not pending,'pending':pending,'accepting_jobs':False}
