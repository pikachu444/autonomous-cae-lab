"""Local file-backed design review workspace; no product solver or LLM backend."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs


HERE = Path(__file__).resolve().parent
KINDS = {
    "pre": ".caeprep", "runner": ".caerun", "post": ".caepost",
    "opt": ".caestudy", "expert": ".caechat", "workbench": ".caeproject",
}
APP_PATHS = {"/": "workbench", **{f"/{kind}": kind for kind in KINDS}}
STATIC = {"/app.js": "app.js", "/style.css": "style.css"}
LOCK = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}", value))


def semantic_hash(kind: str, data: dict) -> str:
    """Prototype impact marker; presentation-only fields cannot stale a dependency."""
    keys = {
        "pre": ("points", "intervals", "material", "conditions", "mesh", "vertices", "unitX", "unitY"),
        "runner": ("cases", "runs"),
        "post": ("datasets",),
        "opt": ("nodes", "edges", "variables", "objectives", "constraints", "candidates", "sourceId", "sourceRevision", "budget", "method"),
        "expert": ("messages", "issues", "evidence"),
        "workbench": ("nodes", "links"),
    }[kind]
    relevant = {key: data.get(key) for key in keys}
    raw = json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class Handler(BaseHTTPRequestHandler):
    server: "LabServer"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{now()}] {self.address_string()} {fmt % args}", flush=True)

    def _send(self, status: int, data: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, value: object) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 4 * 1024 * 1024:
            raise ValueError("JSON body must be between 1 byte and 4 MiB")
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("Content-Type must be application/json")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _path(self, doc_id: str) -> Path | None:
        if not safe_id(doc_id):
            return None
        for ext in KINDS.values():
            path = self.server.data_dir / f"{doc_id}{ext}"
            if path.exists():
                return path
        return None

    def _read(self, doc_id: str) -> dict | None:
        path = self._path(doc_id)
        if path is None:
            return None
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _read_revision(self, doc_id: str, revision: int) -> dict | None:
        current = self._read(doc_id)
        if current is None:
            return None
        if current["revision"] == revision:
            return current
        archive = self.server.data_dir / "history" / f"{doc_id}-r{revision}.json"
        if not archive.exists():
            return None
        with archive.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write(self, value: dict) -> None:
        path = self.server.data_dir / f"{value['id']}{KINDS[value['kind']]}"
        pending = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        with pending.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(pending, path)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        if path == "/api/health":
            return self._json(200, {"ok": True, "storage": str(self.server.data_dir)})
        if path == "/api/docs":
            kind = parse_qs(url.query).get("kind", [""])[0]
            if kind and kind not in KINDS:
                return self._json(400, {"error": "Unknown program kind"})
            docs = []
            with LOCK:
                paths = [p for p in self.server.data_dir.iterdir() if p.suffix in KINDS.values()]
                for file in paths:
                    try:
                        with file.open("r", encoding="utf-8") as stream:
                            doc = json.load(stream)
                        if not kind or doc.get("kind") == kind:
                            summary = {k: doc.get(k) for k in ("id", "kind", "title", "revision", "updatedAt", "semanticHash")}
                            if not summary["semanticHash"] and doc.get("kind") in KINDS:
                                summary["semanticHash"] = semantic_hash(doc["kind"], doc.get("data", {}))
                            docs.append(summary)
                    except (OSError, ValueError):
                        continue
            docs.sort(key=lambda item: item.get("updatedAt") or "", reverse=True)
            return self._json(200, {"docs": docs})
        match = re.fullmatch(r"/api/docs/([0-9a-f]{32})(/export)?", path)
        if match:
            raw_revision = parse_qs(url.query).get("revision", [None])[0]
            if raw_revision is not None and (not raw_revision.isdigit() or int(raw_revision)<1):
                return self._json(400, {"error": "Invalid revision"})
            with LOCK:
                doc = self._read_revision(match.group(1), int(raw_revision)) if raw_revision else self._read(match.group(1))
            if doc is None:
                return self._json(404, {"error": "Document not found"})
            if match.group(2):
                raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                filename = f"{doc['id']}{KINDS[doc['kind']]}"
                return self._send(200, raw, "application/json; charset=utf-8", {"Content-Disposition": f'attachment; filename="{filename}"'})
            return self._json(200, doc)
        if path in APP_PATHS:
            page = (HERE / "index.html").read_text(encoding="utf-8")
            page = page.replace("__APP_KIND__", APP_PATHS[path])
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if path in STATIC:
            file = HERE / STATIC[path]
            content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            return self._send(200, file.read_bytes(), content_type + "; charset=utf-8")
        return self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/docs":
            return self._json(404, {"error": "Not found"})
        try:
            body = self._body()
            kind, title = body.get("kind"), str(body.get("title", "")).strip()
            data = body.get("data", {})
            if kind not in KINDS or not title or len(title) > 120 or not isinstance(data, dict):
                raise ValueError("A valid program, title and data object are required")
            doc = {"id": uuid.uuid4().hex, "kind": kind, "title": title,
                   "revision": 1, "updatedAt": now(), "semanticHash": semantic_hash(kind, data), "data": data}
            with LOCK:
                self._write(doc)
            return self._json(201, doc)
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json(400, {"error": str(exc)})

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        match = re.fullmatch(r"/api/docs/([0-9a-f]{32})", path)
        if match is None:
            return self._json(404, {"error": "Not found"})
        try:
            body = self._body()
            expected = body.get("expectedRevision")
            if not isinstance(expected, int) or isinstance(expected, bool):
                raise ValueError("expectedRevision integer required")
            title = str(body.get("title", "")).strip()
            data = body.get("data")
            if not title or len(title) > 120 or not isinstance(data, dict):
                raise ValueError("A title and data object are required")
            with LOCK:
                doc = self._read(match.group(1))
                if doc is None:
                    return self._json(404, {"error": "Document not found"})
                if doc["revision"] != expected:
                    return self._json(409, {"error": "A newer version is saved on disk", "current": doc})
                archive = self.server.data_dir / "history" / f"{doc['id']}-r{doc['revision']}.json"
                archive.parent.mkdir(exist_ok=True)
                with archive.open("w", encoding="utf-8", newline="\n") as stream:
                    json.dump(doc, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                doc.update({"title": title, "data": data, "revision": expected + 1,
                            "updatedAt": now(), "semanticHash": semantic_hash(doc["kind"], data)})
                self._write(doc)
            return self._json(200, doc)
        except (ValueError, json.JSONDecodeError) as exc:
            return self._json(400, {"error": str(exc)})


class LabServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], data_dir: Path):
        super().__init__(address, Handler)
        self.data_dir = data_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--data-dir", type=Path, default=HERE / "user-data")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    server = LabServer(("127.0.0.1", args.port), args.data_dir.resolve())
    print(f"Design Lab: http://127.0.0.1:{args.port}/; JSON files: {server.data_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
