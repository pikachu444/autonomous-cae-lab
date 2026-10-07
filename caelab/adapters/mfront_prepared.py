"""Prepared two-coefficient MFront Elasticity workbench evaluation.

One owned MGIS child reuses an operator-supplied, hashed library across candidate
histories. This product path does not run the pinned MFront/MTest benchmark or
require its package-directory fingerprints. It does not qualify material.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time
import uuid

from ..evaluation import PreparedEvaluation
from ..execution_control import ExecutionCleanupFailed
from ..storage import save_json
from plugins.material_point import reference as domain
from .mfront_material import _runtime_identity


WORKER = Path(__file__).with_name("mfront_prepared_worker.py")
_COMPONENTS = ("xx", "yy", "zz", "xy", "xz", "yz")
_BOOTSTRAP = ("source /opt/activate.sh; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 "
              "MKL_NUM_THREADS=1; exec python3 -B -I -u /work/mfront_prepared_worker.py")


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _line(process, *, timeout=120):
    from ..execution_control import check_cancelled
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_cancelled()
        if process.poll() is not None:
            raise RuntimeError(f"Prepared MGIS worker exited {process.returncode}; retained worker stderr")
        ready, _, _ = select.select([process.stdout], [], [], min(.2, max(.01, deadline-time.monotonic())))
        if ready:
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("Prepared MGIS worker closed its response pipe")
            return json.loads(line)
    raise TimeoutError("Prepared MGIS worker did not answer within the bounded interval")


def _close(process, stderr):
    try:
        if process.poll() is None:
            try:
                process.stdin.write('{"command":"STOP"}\n')
                process.stdin.flush()
                process.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                from ..execution_control import stop_owned_process
                stop_owned_process(process, isolated_group=True, reap_timeout=5)
    finally:
        for stream in (process.stdin, process.stdout, stderr):
            stream.close()


class MFrontElasticityPreparedAdapter:
    backend = "material.mfront.prepared"

    def describe_inputs(self, settings=None):
        return {'law':'Elasticity','parameters':[
            {'id':'youngs_modulus_mpa','native_property':'YoungModulus','unit':'MPa','lower_exclusive':0,'upper':1e9},
            {'id':'poisson_ratio','native_property':'PoissonRatio','unit':'1','lower_exclusive':-1,'upper_exclusive':.5}],
            'required':['material','temperature_k','history'],
            'history':'2..32 {time_s,strain:[xx,yy,zz,xy,xz,yz]} states; physical tensor shear; initial time and strain zero',
            'outputs':['stress_'+name for name in _COMPONENTS],
            'runtime':'Operator-supplied library and image identities; no benchmark fingerprint requirement',
            'limitations':['Infinitesimal isotropic Elasticity only','Zero initial stress/state','Physical qualification UNKNOWN']}

    def prepare(self, settings, *, runtime=None):
        if runtime and set(runtime) - {"threads", "memory_mb"}:
            raise ValueError("Prepared MFront uses its configured isolated native runtime")
        if not isinstance(settings, dict) or set(settings) != {"output_root", "material", "temperature_k", "history"}:
            raise ValueError("Prepared MFront needs output_root, material, temperature_k and one history")
        root = Path(settings["output_root"]).absolute()
        if any(path.is_symlink() for path in (root, *root.parents)) or root.exists():
            raise ValueError("Prepared MFront output_root must be a new nonlinked directory")
        baseline = {"case": "isotropic_small_strain", "material": deepcopy(settings["material"]),
                    "temperature_k": settings["temperature_k"], "history": deepcopy(settings["history"]),
                    "limits": deepcopy(domain.FIXED_LIMITS)}
        baseline = domain.validate_settings(baseline)
        root.mkdir(parents=True, exist_ok=False)
        configured_library = os.environ.get('CAELAB_MFRONT_PREPARED_LIBRARY')
        if not configured_library:
            raise RuntimeError('Configure an operator-built CAELAB_MFRONT_PREPARED_LIBRARY; the fixed MFront benchmark remains separate')
        source_library = Path(configured_library).resolve(strict=True)
        expected_library = os.environ.get('CAELAB_MFRONT_PREPARED_LIBRARY_SHA256')
        if not expected_library or _sha(source_library) != expected_library:
            raise RuntimeError('Configured material library hash differs')
        library = root / 'libBehaviour.so'
        shutil.copyfile(source_library,library)
        if _sha(library) != expected_library:
            raise RuntimeError('Material library changed while preparing the worker')
        from . import mfront_material_worker
        shutil.copyfile(mfront_material_worker.__file__,root/'mfront_material_worker.py')
        image, image_sha, singularity = _runtime_identity()
        library_sha = _sha(library)
        worker_bytes = WORKER.read_bytes()
        (root / "mfront_prepared_worker.py").write_bytes(worker_bytes)
        worker_sha = _sha(root / "mfront_prepared_worker.py")
        scratch = root / "runtime_tmp"
        scratch.mkdir(exist_ok=False)
        (root / "candidates").mkdir(exist_ok=False)
        command = [singularity, "exec", "--cleanenv", "--containall", "--no-home",
                   "--bind", f"{root.resolve()}:/work:rw", "--bind", f"{scratch.resolve()}:/tmp:rw",
                   "--pwd", "/work", str(image), "/bin/bash", "--noprofile", "--norc", "-c", _BOOTSTRAP]
        save_json(root / "prepared_execution.json", {"argv": command, "image_sha256": image_sha,
                   "library_sha256": library_sha, "worker_sha256": worker_sha,
                   "library_source": str(source_library), "qualification": "UNKNOWN; separately supplied library",
                   "candidate_protocol": "one JSON line per candidate"})
        stderr = (root / "prepared_worker.stderr.log").open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=stderr, text=True, bufsize=1, start_new_session=True)
            ready = _line(process, timeout=45)
            if ready != {"ready": True, "library_sha256": library_sha,
                         "properties": ["YoungModulus", "PoissonRatio"]}:
                raise RuntimeError("Prepared MGIS loaded a different material library or descriptor")
        except BaseException:
            if "process" in locals():
                try:
                    _close(process, stderr)
                except ExecutionCleanupFailed:
                    raise
                except Exception:
                    pass
            else:
                stderr.close()
            raise

        def evaluate(values):
            if not values:
                values=baseline['material']
            if not isinstance(values, dict) or set(values) != {"youngs_modulus_mpa", "poisson_ratio"}:
                raise ValueError("Each prepared material candidate requires E and nu")
            candidate = domain.validate_settings({**baseline, "material": deepcopy(values)})
            if process.poll() is not None:
                raise RuntimeError("Prepared MGIS worker is no longer running")
            if _sha(library) != library_sha or _sha(root / "mfront_prepared_worker.py") != worker_sha:
                raise RuntimeError("Prepared material library or worker source changed")
            identifier = uuid.uuid4().hex
            request = {"candidate_id": identifier, "material": candidate["material"],
                       "temperature_k": candidate["temperature_k"], "history": candidate["history"]}
            process.stdin.write(json.dumps(request, allow_nan=False) + "\n")
            process.stdin.flush()
            receipt = _line(process)
            if receipt.get("candidate_id") != identifier:
                raise RuntimeError("Prepared MGIS candidate receipt differs from request")
            if receipt.get("execution_status") == "FAILED":
                return {"execution_status": "FAILED", "responses": {},
                        "checks": [{"code": "native_material", "status": "FAIL", "observed": receipt.get("reason")}],
                        "diagnostics": {"candidate_id": identifier, "output_root": str(root)}}
            result_path = root / "candidates" / identifier / "result.json"
            if _sha(result_path) != receipt.get("result_sha256"):
                raise RuntimeError("Prepared MGIS candidate result hash differs from receipt")
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if (result.get("candidate_id") != identifier or result.get("library_sha256") != library_sha or
                    result.get("execution_status") != receipt.get("execution_status") or
                    _sha(root / "candidates" / identifier / "input.json") != result.get("input_sha256")):
                raise RuntimeError("Prepared MGIS candidate input/library identity differs")
            rows = result["rows"]
            times = [row["time_s"] for row in rows]
            status = result["execution_status"]
            responses = {}
            if status == "SUCCEEDED":
                if len(rows) != len(candidate["history"]) or times != [row["time_s"] for row in candidate["history"]]:
                    raise RuntimeError("Prepared MGIS history length/clock differs from candidate")
                for index, component in enumerate(_COMPONENTS):
                    responses["stress_" + component] = {
                        "kind": "series", "value": [row["stress_physical_mpa"][index] for row in rows],
                        "unit": "MPa", "component": component, "location": "material point",
                        "reduction": "none", "axes": [{"name": "time", "unit": "s", "values": times}],
                        "stress_measure": "Cauchy infinitesimal strain",
                        "source": {"backend": self.backend, "artifact": f"candidates/{identifier}/result.json",
                                   "sha256": receipt["result_sha256"], "selector": "stress_" + component,
                                   "native_library_sha256": library_sha}}
            return {"execution_status": status, "responses": responses,
                    "checks": [{"code": "native_material", "status": "PASS" if status == "SUCCEEDED" else "FAIL",
                                "observed": "MGIS native stress update" if status == "SUCCEEDED" else result.get("native_rejection")}],
                    "diagnostics": {"candidate_id": identifier, "output_root": str(root),
                                    "qualification": "UNKNOWN; library identity and native update recorded",
                                    "library_sha256": library_sha}}

        return PreparedEvaluation(evaluate, settings, close=lambda: _close(process, stderr))
