"""Actual HTTP research/CAD/PDE and verified-report integration acceptance.

The browser layer uses this same API. Browser rendering is a separate check.
This script creates a fresh append-only store and stops only its own server.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

from caelab.storage import check_id, save_json, source_identity, utc_now


def application_source_sha256(repository):
    digest = hashlib.sha256()
    for path in sorted((repository / "apps/lab").rglob("*")):
        if path.is_file() and path.suffix in {".py", ".js", ".html", ".css"}:
            digest.update(path.relative_to(repository).as_posix().encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


class Client:
    def __init__(self, base):
        self.base, self.token = base, None

    def request(self, path, body=None, *, expected=200, raw=False):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body, allow_nan=False).encode()
            headers = {"Content-Type": "application/json", "X-CAE-Token": self.token or ""}
        request = Request(self.base + path, data=data, headers=headers)
        try:
            with urlopen(request, timeout=180) as response:
                status, payload = response.status, response.read()
        except HTTPError as exc:
            status, payload = exc.code, exc.read()
        if status != expected:
            raise AssertionError(f"HTTP {path}: expected {expected}, got {status}: {payload[:2000]!r}")
        return payload if raw else json.loads(payload)

    def job(self, operation, arguments, *, timeout=300):
        job = self.request("/api/jobs", {"operation": operation, "arguments": arguments}, expected=202)
        deadline = time.monotonic() + timeout
        while job["status"] == "RUNNING":
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Job {job['id']} ({operation}) exceeded acceptance deadline")
            time.sleep(.25)
            job = self.request("/api/jobs/" + job["id"])
        if job["status"] != "COMPLETED":
            raise AssertionError(f"{operation} failed: {job.get('error')}")
        return job["result"]


def check_bundle(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), "Duplicate archive paths"
        assert "bundle_manifest.json" in names
        manifest = json.loads(archive.read("bundle_manifest.json"))
        rows = manifest["files"]
        assert len(rows) == len({r["path"] for r in rows})
        assert set(names) == {r["path"] for r in rows} | {"bundle_manifest.json"}
        for row in rows:
            path = PurePosixPath(row["path"])
            assert not path.is_absolute() and ".." not in path.parts and "\\" not in row["path"]
            value = archive.read(row["path"])
            assert len(value) == row["size_bytes"]
            assert hashlib.sha256(value).hexdigest() == row["sha256"]
        assert any(name.endswith("result.json") for name in names)
        assert any(name.endswith("thread.json") for name in names)
        assert any(name.endswith("report.html") for name in names)
        return {"sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload),
                "files": len(rows), "manifest": manifest}


def retain_library_bundle(store, library_id, experiment_id, payload):
    """Keep distinct library/experiment identities without replacing old bytes."""
    check_id(library_id)
    check_id(experiment_id)
    checked = check_bundle(payload)
    relative = Path("library_exports") / library_id / f"{experiment_id}-evidence.zip"
    target = Path(store) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output:
        output.write(payload)
    return {"store": library_id, "experiment_id": experiment_id,
            "retained_zip": relative.as_posix(),
            **{key: value for key, value in checked.items() if key != "manifest"}}


def run(store, *, libraries=None, skip_pde=False):
    store = Path(store).resolve()
    if store.exists():
        raise ValueError("HTTP acceptance needs a new store; historical records are never overwritten")
    store.mkdir(parents=True)
    repository = Path(__file__).resolve().parents[1]
    before = {**source_identity(repository), "application_source_sha256": application_source_sha256(repository)}
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    command = [sys.executable, "-m", "apps.lab", "--store", str(store), "--port", str(port)]
    for identifier, path in (libraries or {}).items():
        command.extend(["--library", f"{identifier}={Path(path).resolve()}"])
    client = Client(f"http://127.0.0.1:{port}")
    evidence = {"started_utc": utc_now(), "source": before, "decision": "NOT_RELEASED",
                "browser_rendering": "NOT_CHECKED", "stages": [], "bundles": [], "libraries": []}
    with (store / "http.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=repository, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 45
            while True:
                try:
                    overview = client.request("/api/overview")
                    break
                except (URLError, OSError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Local HTTP server did not become ready; see http.log")
                    time.sleep(.2)
            client.token = overview["token"]
            assert overview["active_store"] == "local"
            print("HTTP Core: study and parameter discovery/registration", flush=True)
            study = client.job("study_create", {"study_id": "S-http", "name": "로컬 Lab 연계 검증",
                "research_question": "같은 Core에서 형상 거부와 수치 증거를 확인할 수 있는가?",
                "hypothesis": "폭 38 mm는 형상이 유효하며 볼트 간격 30 mm는 계산 전에 거부된다.",
                "objective": "사람 화면과 API의 기록을 연결하고 미검증 항목을 보존한다."})
            assert study["id"] == "S-http"
            candidates = client.job("parameter_discover", {"backend": "fixture.cadquery", "model": "roller_support"})
            assert {"support_width_mm", "bolt_pitch_x_mm"} <= {c["native"]["path"] for c in candidates}
            for path, identifier, label, lower, upper in (
                ("support_width_mm", "support_width", "지지대 폭", 28, 60),
                ("bolt_pitch_x_mm", "bolt_pitch", "볼트 간격", 18, 40)):
                registered = client.job("parameter_register", {"study_id": "S-http", "backend": "fixture.cadquery",
                    "model": "roller_support", "native_path": path, "parameter_id": identifier,
                    "display_name": label, "lower": lower, "upper": upper})
                assert registered["geometry_effect"]["status"] == "PASS"
            print("HTTP Core: actual CAD valid/rejected cases", flush=True)
            cad = client.job("cad_run", {"study_id": "S-http", "experiment_id": "E-http-width38",
                "backend": "fixture.cadquery", "model": "roller_support", "values": {"support_width": 38}})
            rejected = client.job("cad_run", {"study_id": "S-http", "experiment_id": "E-http-clearance-reject",
                "backend": "fixture.cadquery", "model": "roller_support", "values": {"bolt_pitch": 30}})
            assert cad["status"] == "COMPLETED_REVIEW_REQUIRED"
            assert rejected["status"] == "REJECTED"
            assert not (store / "experiments/E-http-clearance-reject/cad/assembly.step").exists()
            for row in (cad, rejected):
                assert row["decision"] == "NOT_RELEASED"
                inspected = client.request("/api/experiments/" + row["experiment_id"])
                assert inspected["integrity"] == "VERIFIED" and inspected["result"] == row
                assert inspected["summary"]["unknown"]
            comparison = client.request("/api/compare?ids=E-http-width38,E-http-clearance-reject")
            assert [row["status"] for row in comparison] == ["COMPLETED_REVIEW_REQUIRED", "REJECTED"]
            evidence["stages"].append({"stage": "study_registry_cad_rejection", "status": "PASS",
                                        "experiment_ids": [cad["experiment_id"], rejected["experiment_id"]]})
            if not skip_pde:
                print("HTTP Core: actual canonical FEniCSx PDE", flush=True)
                preset = client.request("/api/presets")["pde_canonical"]
                pde = client.job("pde_run", {"study_id": "S-http", "experiment_id": "E-http-poisson",
                    "backend": preset["backend"], "settings": preset["settings"]})
                assert pde["status"] == "COMPLETED_REVIEW_REQUIRED" and pde["solver_status"] == "COMPLETED"
                assert pde["cad_revision"] is None and pde["decision"] == "NOT_RELEASED"
                assert pde["metrics"]["l2_error"]["valid"] and pde["metrics"]["l2_error"]["value"] <= .003
                evidence["stages"].append({"stage": "canonical_pde", "status": "PASS", "metrics": pde["metrics"]})
            print("HTTP results: verified reports and portable bundles", flush=True)
            for identifier in ["E-http-width38", "E-http-clearance-reject"] + ([] if skip_pde else ["E-http-poisson"]):
                html = client.request(f"/api/report/{identifier}.html", raw=True)
                assert b"NOT_RELEASED" in html and b"UNKNOWN" in html
                report = client.request(f"/api/report/{identifier}.json")
                assert report["result"]["experiment_id"] == identifier
                bundle = client.request(f"/api/report/{identifier}.zip", raw=True)
                checked = check_bundle(bundle)
                (store / f"{identifier}-evidence.zip").write_bytes(bundle)
                evidence["bundles"].append({"experiment_id": identifier, **{k:v for k,v in checked.items() if k != "manifest"}})
            for library_id in libraries or {}:
                print(f"HTTP existing library: {library_id}", flush=True)
                selected = client.request("/api/store", {"id": library_id})
                assert selected["active_store"] == library_id
                client.request("/api/jobs", {"operation": "study_create", "arguments": {"study_id": "S-forbidden",
                    "name": "forbidden", "research_question": "forbidden", "hypothesis": "forbidden", "objective": "forbidden"}}, expected=403)
                verified = []
                for row in selected["experiments"]:
                    if row.get("error"):
                        continue
                    data = client.request("/api/experiments/" + row["id"])
                    assert data["integrity"] == "VERIFIED" and data["result"]["decision"] == "NOT_RELEASED"
                    verified.append(row["id"])
                campaigns = []
                for row in selected["campaigns"]:
                    client.request("/api/campaigns/" + row["id"])
                    campaigns.append(row["id"])
                if verified:
                    bundle = client.request(f"/api/report/{verified[-1]}.zip", raw=True)
                    evidence["bundles"].append(retain_library_bundle(store, library_id, verified[-1], bundle))
                evidence["libraries"].append({"id": library_id, "verified_experiments": verified,
                                               "inspected_campaigns": campaigns, "mutation_denied": True})
            assert source_identity(repository)["core_source_sha256"] == before["core_source_sha256"], "Core changed during acceptance"
            assert application_source_sha256(repository) == before["application_source_sha256"], "Application changed during acceptance"
            evidence.update(status="PASS", finished_utc=utc_now(), limitations=[
                "HTTP integration is separate from browser rendering and live OpenScience agent acceptance.",
                "Local ZIP export does not establish remote durability, a signature or engineering release.",
                "Existing library numerical results retain their own original source/run identities."])
            save_json(store / "http_acceptance.json", evidence)
            print(json.dumps({k:v for k,v in evidence.items() if k not in ("source", "stages")}, ensure_ascii=False), flush=True)
            return evidence
        except Exception as exc:
            evidence.update(status="FAILED", error=f"{type(exc).__name__}: {exc}", finished_utc=utc_now())
            save_json(store / "http_acceptance.json", evidence)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--skip-pde", action="store_true")
    parser.add_argument("--library", action="append", default=[], metavar="ID=PATH")
    args = parser.parse_args()
    libraries = dict(item.split("=", 1) for item in args.library)
    run(args.store, libraries=libraries, skip_pde=args.skip_pde)
