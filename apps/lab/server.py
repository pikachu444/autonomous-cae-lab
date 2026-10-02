"""Loopback-only standard-library HTTP transport for the integrated Lab."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import parse_qs, unquote, urlsplit

from .service import LabService, ServiceError, contained


MAX_BODY = 128 * 1024
STATIC = Path(__file__).resolve().parent / "static"
UPSTREAM_VIEWER = (Path(__file__).resolve().parents[2] /
                   "plugins/fixture_design/upstream/fixturelab/surface_viewer.js")


class LabHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, service: LabService, port: int = 8766):
        self.service = service
        super().__init__(("127.0.0.1", port), LabHandler)


class LabHandler(BaseHTTPRequestHandler):
    server_version = "AutonomousCAELab/1"

    def log_message(self, format, *args):
        # Request bodies and authentication tokens are never logged.
        super().log_message(format, *args)

    def _guard(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host_values = self.headers.get_all("Host", [])
        if len(host_values) != 1 or host_values[0].lower() not in hosts:
            raise ServiceError(403, "Host must identify this loopback server and port")
        origin_values = self.headers.get_all("Origin", [])
        if origin_values and (len(origin_values) != 1 or origin_values[0].lower() not in
                              {"http://" + host for host in hosts}):
            raise ServiceError(403, "Foreign Origin is not allowed")
        # Modern browsers identify cross-site reads, including same-origin-less requests.
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            raise ServiceError(403, "Cross-site requests are not allowed")

    def _json_body(self) -> dict:
        values = self.headers.get_all("X-CAE-Token", [])
        if len(values) != 1 or not secrets.compare_digest(values[0], self.server.service.token):
            raise ServiceError(403, "A valid X-CAE-Token is required")
        types = self.headers.get_all("Content-Type", [])
        if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
            raise ServiceError(415, "POST requires application/json")
        sizes = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding", []) or len(sizes) != 1 or not sizes[0].isdigit():
            raise ServiceError(400, "One explicit Content-Length is required")
        length = int(sizes[0])
        if length > MAX_BODY:
            raise ServiceError(413, "JSON body exceeds 128 KiB")
        self.connection.settimeout(15)
        payload = self.rfile.read(length)
        if len(payload) != length:
            raise ServiceError(400, "Incomplete JSON body")

        def object_pairs(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("Duplicate JSON key")
                value[key] = item
            return value

        def invalid_constant(value):
            raise ValueError("Non-finite JSON number")

        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("Non-finite JSON number")
            return number

        try:
            body = json.loads(payload.decode("utf-8"), object_pairs_hook=object_pairs,
                              parse_constant=invalid_constant, parse_float=finite_float)
        except (UnicodeError, ValueError) as exc:
            raise ServiceError(400, f"Invalid JSON: {exc}") from exc
        if not isinstance(body, dict):
            raise ServiceError(400, "Request body must be a JSON object")
        return body

    def _send(self, status: int, payload: bytes, mime: str, *, disposition: str | None = None,
              filename: str | None = None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if disposition:
            self.send_header("Content-Disposition", disposition + (f'; filename="{filename}"' if filename else ""))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, value):
        self._send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _request(self, method: str):
        try:
            self._guard()
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                raise ServiceError(400, "A local request target is required")
            path = unquote(parsed.path, errors="strict")
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True,
                             max_num_fields=16)
            if method == "POST":
                body = self._json_body()
                if query:
                    raise ServiceError(400, "POST does not accept query arguments")
                if path == "/api/store":
                    if set(body) != {"id"}:
                        raise ServiceError(400, "Store selection requires only id")
                    return self._json(200, self.server.service.select_store(body["id"]))
                if path == "/api/jobs":
                    if set(body) != {"operation", "arguments"}:
                        raise ServiceError(400, "Job requires operation and arguments")
                    return self._json(202, self.server.service.submit(body["operation"], body["arguments"]))
                cancellation = re.fullmatch(r"/api/jobs/([^/]+)/cancel", path)
                if cancellation:
                    if body:
                        raise ServiceError(400, "Cancellation requires an empty JSON object")
                    job = self.server.service.cancel(cancellation.group(1))
                    return self._json(202 if job["status"] in {"CANCEL_REQUESTED", "CLEANUP_PENDING"}
                                      else 200, job)
                raise ServiceError(404, "Unknown POST route")
            return self._get(path, query)
        except ServiceError as exc:
            self._json(exc.status, {"error": str(exc)})
        except FileNotFoundError as exc:
            self._json(404, {"error": f"{type(exc).__name__}: {exc}"})
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            self._json(400, {"error": f"{type(exc).__name__}: {exc}"})
        except Exception as exc:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def do_GET(self):
        self._request("GET")

    def do_POST(self):
        self._request("POST")

    def _get(self, path: str, query: dict):
        service = self.server.service
        if path == "/api/compare":
            if set(query) != {"ids"} or len(query["ids"]) != 1:
                raise ServiceError(400, "Compare requires one ids query argument")
            return self._json(200, service.compare(query["ids"][0].split(",")))
        if path.startswith("/api/artifacts/"):
            if set(query) != {"path"} or len(query["path"]) != 1:
                raise ServiceError(400, "Artifact requires one relative path argument")
            relative = query["path"][0]
            payload, mime, disposition = service.artifact(path.removeprefix("/api/artifacts/"), relative)
            # A conservative ASCII filename avoids untrusted header text.
            suffix = Path(relative).suffix
            filename = "artifact" + (suffix if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix) else "")
            return self._send(200, payload, mime, disposition=disposition, filename=filename)
        if query:
            raise ServiceError(400, "This route does not accept query arguments")
        if path == "/api/overview":
            return self._json(200, service.overview())
        if path == "/api/presets":
            return self._json(200, service.presets())
        for prefix, operation in (("/api/studies/", service.study), ("/api/experiments/", service.experiment),
                                  ("/api/campaigns/", service.campaign), ("/api/jobs/", service.job)):
            if path.startswith(prefix):
                return self._json(200, operation(path.removeprefix(prefix)))
        if path.startswith("/api/report/"):
            identifier, separator, format = path.removeprefix("/api/report/").rpartition(".")
            types = {"html": "text/html; charset=utf-8", "json": "application/json; charset=utf-8",
                     "zip": "application/zip"}
            if not separator or format not in types:
                raise ServiceError(404, "Unknown report format")
            payload = service.report(identifier, format)
            return self._send(200, payload, types[format], disposition="attachment" if format == "zip" else None,
                              filename=f"{identifier}-evidence.zip" if format == "zip" else None)
        if path == "/upstream/surface_viewer.js":
            return self._send(200, UPSTREAM_VIEWER.read_bytes(), "text/javascript; charset=utf-8")
        if path in {"/", "/index.html"}:
            target = contained(STATIC, "index.html")
        elif path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            if any(part.startswith(".") for part in relative.split("/")):
                raise ServiceError(404, "Static file not found")
            target = contained(STATIC, relative)
        else:
            raise ServiceError(404, "Route not found")
        if not target.is_file():
            raise ServiceError(404, "Static file not found")
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return self._send(200, target.read_bytes(), mime)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Autonomous CAE Lab loopback human interface")
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--library", action="append", default=[], metavar="ID=PATH")
    args = parser.parse_args(argv)
    libraries = {}
    for item in args.library:
        identifier, separator, path = item.partition("=")
        if not separator or not path or identifier in libraries:
            parser.error("Each --library must be a distinct ID=PATH")
        libraries[identifier] = Path(path)
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535")
    server = LabHTTPServer(LabService(args.store, libraries=libraries), args.port)
    print(f"Autonomous CAE Lab: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            announced = False
            while True:
                try:
                    shutdown = server.service.shutdown(timeout=1.0)
                except KeyboardInterrupt:
                    # Another cooperative interruption is not proof that a
                    # daemon worker or its owned native children have stopped.
                    continue
                if shutdown["joined"] and not shutdown["pending"]:
                    break
                if not announced:
                    print("Waiting for cooperative Lab worker shutdown; new jobs are closed. "
                          "Native termination is not yet confirmed.", file=sys.stderr, flush=True)
                    announced = True
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
