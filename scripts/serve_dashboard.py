#!/usr/bin/env python3
"""
Serve the dashboard and accept local browser uploads.

Uploaded files are written to inbox/uploads/<timestamp>/, then imported through
the same dedupe/organize pipeline used for SD cards.
"""

from __future__ import annotations

import argparse
import datetime as dt
from email import policy
from email.parser import BytesParser
import json
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "dashboard"
INBOX_DIR = ROOT / "inbox" / "uploads"
MAX_UPLOAD_BYTES = 512 * 1024 * 1024

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_wardrive  # noqa: E402


def json_bytes(payload: dict, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(payload, indent=2).encode("utf-8"), "application/json; charset=utf-8"


def clean_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "upload.bin"


def parse_content_disposition(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in value.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        result[key.lower()] = raw.strip().strip('"')
    return result


def split_multipart(body: bytes, content_type: str) -> list[tuple[dict[str, str], bytes]]:
    match = re.search(r"boundary=(?P<boundary>[^;]+)", content_type)
    if not match:
        raise ValueError("Missing multipart boundary")

    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    if not message.is_multipart():
        raise ValueError("Upload body is not multipart")

    parts = []
    for part in message.iter_parts():
        headers = {key.lower(): value for key, value in part.items()}
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""
        parts.append((headers, payload))
    return parts


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "WarDriveDashboard/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {fmt % args}")

    def send_payload(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            payload = {
                "ok": True,
                "upload_limit_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
                "dashboard_data": "dashboard/data/wardrive-data.json",
            }
            self.send_payload(*json_bytes(payload))
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/clean-duplicates":
            result = import_wardrive.clean_duplicates()
            data = import_wardrive.build_dashboard_data()
            self.send_payload(*json_bytes({"ok": True, **result, "summary": data["summary"]}))
            return

        if parsed.path != "/api/upload":
            self.send_payload(*json_bytes({"ok": False, "error": "Unknown endpoint"}, 404))
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            self.send_payload(*json_bytes({"ok": False, "error": "No upload body"}, 400))
            return
        if content_length > MAX_UPLOAD_BYTES:
            self.send_payload(*json_bytes({"ok": False, "error": "Upload is too large"}, 413))
            return

        content_type = self.headers.get("Content-Type", "")
        body = self.rfile.read(content_length)
        try:
            parts = split_multipart(body, content_type)
        except ValueError as exc:
            self.send_payload(*json_bytes({"ok": False, "error": str(exc)}, 400))
            return

        batch = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        upload_dir = INBOX_DIR / batch
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved = []
        for headers, payload in parts:
            disposition = parse_content_disposition(headers.get("content-disposition", ""))
            filename = disposition.get("filename")
            if not filename:
                continue
            target = upload_dir / clean_filename(filename)
            if target.exists():
                target = upload_dir / f"{target.stem}-{len(saved) + 1}{target.suffix}"
            target.write_bytes(payload)
            saved.append(target.name)

        if not saved:
            self.send_payload(*json_bytes({"ok": False, "error": "No files found in upload"}, 400))
            return

        result = import_wardrive.import_files(upload_dir, move=True)
        duplicate_cleanup = import_wardrive.clean_duplicates()
        data = import_wardrive.build_dashboard_data()
        response = {
            "ok": True,
            "saved": len(saved),
            "batch": batch,
            **result,
            "duplicate_cleanup": duplicate_cleanup,
            "summary": data["summary"],
        }
        self.send_payload(*json_bytes(response))

    def serve_static(self, request_path: str) -> None:
        raw_path = unquote(request_path).lstrip("/")
        if raw_path in {"", "/"}:
            raw_path = "index.html"
        candidate = (DASHBOARD_DIR / raw_path).resolve()
        try:
            candidate.relative_to(DASHBOARD_DIR.resolve())
        except ValueError:
            self.send_payload(*json_bytes({"ok": False, "error": "Forbidden"}, 403))
            return
        if not candidate.exists() or not candidate.is_file():
            self.send_payload(*json_bytes({"ok": False, "error": "Not found"}, 404))
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_payload(200, candidate.read_bytes(), content_type)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve WDGWars Local Grid with upload support.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Serving dashboard with uploads at http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping dashboard server")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
