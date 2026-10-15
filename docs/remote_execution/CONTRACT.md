# Existing remote runtime and exchange contract

This extends the existing JobManager, file exchange and native input reader. It
does not create a scheduler service, solver, queue framework or document owner.
Windows OpenSSH is a supported local transport; WSL is not required. Nothing is
installed remotely. An operator must already have the host, authentication,
known_hosts, writable canonical POSIX root and selected runtime. Slurm/OpenPBS
compute nodes and the SSH login host must see the same job root and inputs.

The following is a **public synthetic registration**, not a connection to try:

```json
{
  "remote_hosts": {
    "public": {
      "enabled": true,
      "label": "공개 계산 서버",
      "target": "public-fixture.invalid",
      "scheduler": "slurm",
      "root": "/public/jobs",
      "python": "python3",
      "queue": "research",
      "account": "public",
      "runtime": {"id": "public.external", "version": "fixture-1"},
      "command": ["python3", "-m", "caelab.remote_execution", "worker",
                  "--configuration", "/public/external.json",
                  "--runtime-id", "public.external", "--runtime-version", "fixture-1"],
      "responses": {"force": {"kind": "series", "unit": "N"}},
      "max_threads": 4,
      "max_memory_mb": 4096,
      "max_wall_seconds": 3600,
      "transfer_limit": 16777216,
      "files": {},
      "outputs": [],
      "post_outputs": []
    }
  }
}
```

The registered command is a trusted argv. Requests cannot supply commands,
environment values, credentials, executables or arbitrary remote paths. The
external configuration is already present on that host and uses the existing
`ExternalFilesAdapter` variables/templates/files/result mapping. Its commands must
stay in the foreground and honor owned-command cancellation, without daemonizing
or escaping that ownership. The included worker supports the adapter's existing
numeric declarations; it does not invent categorical template substitution.
Other already-installed runtimes may return the same exchange envelope, but their
physical scope and SSH cooperative cleanup must be separately established.

`files` explicitly maps portable relative names to operator-approved local model
inputs. Authentication directories and key bytes are not transferable model
inputs. No SSH configuration or authentication file is inspected or copied.
Inputs and the result transfer each keep the existing **16 MiB maximum**, even if
a larger value is configured. VTU/PVD dependencies must all be explicitly listed
in `outputs`; paths must also be safe on Windows. Existing PVD/native input limits
continue to apply. `post_outputs` entries contain `relative` and `native_metadata`
in the existing native Post vocabulary: coordinate units/frame, explicit static
step/increment/load parameter or clock, and array association/name/components/
units/frame/measure. Registration does not substitute for the native reader's
exact array/time checks. A failed second registration keeps raw files and the
first receipt but does not claim every Post output is ready.

## Explicit commands

Use `Client.submit` with a stable, nonempty request_id. Same ID with changed
arguments remains a conflict under the existing JobManager rule.

| Operation | Inputs | Effect |
|---|---|---|
| `remote.run` | host_id, batch_job, optional remote_resources/label | Retain input; prepare and submit once; monitor. No fetch |
| `remote.reconnect` | source_job, optional label | Query the same retained token/ID once. No submit/fetch |
| `remote.cancel` | source_job, optional label | Explicit remote cancel, then confirm termination. No fetch |
| `remote.collect` | source_job, optional label | Query termination, fetch declared files, admit original candidate results, register Post |

Resources are `threads`, `memory_mb`, `wall_seconds`, bounded by host limits.
The local controller reserves one thread; this is separate from remote resources.
Slurm/PBS memory is a scheduler request. SSH memory is `HINT_ONLY` and OMP threads
depend on the foreground runtime; no hard local/remote memory sandbox is claimed.

`POST /api/workbench/remote` with `{operation, arguments}` accepts `catalog`,
`preview` (host_id/batch_job/resources), or `status` (job_id). These read local
records only and make no remote calls. Catalog exposes the existing remote
JobManager request identities so an unacknowledged GUI request can find the exact
accepted job without another submission. GUI pending requests use the existing
desktop QSettings with a stable workspace key; a first definite pre-admission
HTTP rejection releases editing, while uncertain/recovered requests keep their
original identity. A service/port restart does not turn them into a new submit.

```python
job = client.submit('remote.run', {
    'host_id': 'public', 'batch_job': exported_job_id,
    'remote_resources': {'threads': 2, 'memory_mb': 1024, 'wall_seconds': 600}
}, request_id='my-stable-request')
# Explicit later actions use NEW request IDs but reference the same source job.
client.submit('remote.reconnect', {'source_job': job['id']}, request_id='my-check')
client.submit('remote.collect', {'source_job': job['id']}, request_id='my-collect')
```

The same operations are available via `python -m caelab.remote_execution --service
http://127.0.0.1:PORT run --host public --batch-job J... --request-id ...` and
`reconnect/cancel/collect --job J... --request-id ...`. `catalog/preview/status`
remain read-only. This example uses no supplied live host.

## Durable identity and termination

The original JobManager request, immutable batch bytes, resources, input hashes,
runtime/host binding and `R...` token precede the submit call. The remote token
directory uses an atomic submit claim. A lost sbatch/qsub reply is resolved by
token + job name + comment/environment marker; a missing receipt never triggers
another submission. A cancel that claims first atomically prevents submit.
One SSH command at a time is locally serialized, allowing cancellation between
monitor polls. Saved PIDs are never adopted or signalled after reconnect.

Slurm termination requires parent-job accounting state and exit code; step rows
and a terminal queue row alone are insufficient. OpenPBS requires final history
state F plus Exit_status with the complete scheduler ID and matching token.
Missing accounting/history remains UNKNOWN. SSH requires the owned supervisor's
reaped-child receipt **and** the cooperative worker cleanup receipt bound to the
same token/intent/runtime. The existing CancellationToken/run_owned_command
boundary performs native cleanup. A killed SSH pipe, absent PID or accepted
scancel/qdel is not termination evidence. These live POSIX/scheduler assumptions
still require acceptance on the actual selected host.

Cancelling a reconnect/collect job only stops its local observation/transfer;
it preserves the original remote termination facts and sends no remote cancel.
Only cancelling remote.run or explicitly selecting remote.cancel requests remote
termination. Unconfirmed cleanup remains unresolved under existing JobManager
lifecycle rules.

## Result admission and retention

The existing worker evaluates each candidate through ExternalFilesAdapter and
writes `results.json` incrementally with `input_manifest_sha256`, exact runtime,
and `results`. Each row retains candidate_id/case_id/exchange_id and original
typed `values`. Returned responses carry explicit kind/unit and numeric inline
values; arbitrary remote `data_ref` paths are rejected. JSON/array persistence on
the local side remains `save_evaluation/read_result` (no pickle/new array reader).
The existing `numerical.import_batch` rejects duplicate/stale/changed values and
preserves missing NOT_EVALUATED rows and actual failure states. Raw valid-checksum
files survive semantic admission failures. New attempts use new result folders;
original inputs/results are never overwritten. Direct responses and candidate
rows are shown by the existing Runner; registered spatial outputs use existing
Post navigation and physical reader validation. No engineering release is implied.

Official contracts consulted: [OpenSSH](https://man.openbsd.org/ssh),
[sbatch](https://slurm.schedmd.com/sbatch.html),
[sacct](https://slurm.schedmd.com/sacct.html),
[OpenPBS qstat](https://github.com/openpbs/openpbs/blob/master/doc/man1/qstat.1B).
Submission acceptance, accounting and actual host/runtime acceptance are separate.
