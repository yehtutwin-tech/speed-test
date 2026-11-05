#!/usr/bin/env python3
"""Small, dependency-free HTTP endpoints for the Speed Test page.

For local evaluation only. Vercel deploys app.py instead of this process.
Put this server behind a production web server / reverse proxy, HTTPS,
request-rate controls, and appropriate bandwidth limits before exposing it.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlparse, parse_qs
import os

ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("SPEEDTEST_HOST", "127.0.0.1")
PORT = int(os.environ.get("SPEEDTEST_PORT", "8080"))
ALLOWED_ORIGINS = [x.strip() for x in os.environ.get("SPEEDTEST_ALLOWED_ORIGINS", "*").split(",") if x.strip()]
MAX_UPLOAD = int(os.environ.get("SPEEDTEST_MAX_UPLOAD", str(32 * 1024 * 1024)))
MAX_DOWNLOAD = int(os.environ.get("SPEEDTEST_MAX_DOWNLOAD", str(64 * 1024 * 1024)))
MAX_CONCURRENT = int(os.environ.get("SPEEDTEST_MAX_CONCURRENT", "4"))
slots = BoundedSemaphore(MAX_CONCURRENT)
CHUNK = bytes(range(256)) * 4096  # 1 MiB of non-compressible-enough varied data


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SpeedTest/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.log_date_time_string(), fmt % args))

    def _cors(self):
        origin = self.headers.get("Origin")
        if "*" in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def _headers(self, status=200, length=0, content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self._cors()
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def _reply(self, status, body):
        self._headers(status, len(body))
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._headers(204, 0)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_page()
            return
        if parsed.path == "/ping":
            self._headers(200, 2)
            self.wfile.write(b"ok")
            return
        if parsed.path != "/download":
            self._reply(404, b"not found")
            return
        try:
            size = int(parse_qs(parsed.query).get("bytes", [str(8 * 1024 * 1024)])[0])
        except ValueError:
            size = 0
        if size < 1 or size > MAX_DOWNLOAD:
            self._reply(413, b"invalid byte count")
            return
        if not slots.acquire(blocking=False):
            self._reply(503, b"test capacity busy")
            return
        try:
            self._headers(200, size, "application/octet-stream")
            remaining = size
            while remaining:
                part = CHUNK[:min(remaining, len(CHUNK))]
                self.wfile.write(part)
                remaining -= len(part)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            slots.release()

    def do_POST(self):
        if urlparse(self.path).path != "/upload":
            self._reply(404, b"not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_UPLOAD:
            self._reply(413, b"upload too large")
            return
        if not slots.acquire(blocking=False):
            self._reply(503, b"test capacity busy")
            return
        try:
            remaining = length
            while remaining:
                data = self.rfile.read(min(1024 * 1024, remaining))
                if not data:
                    self._reply(400, b"short upload")
                    return
                remaining -= len(data)
            self._headers(200, 2)
            self.wfile.write(b"ok")
        finally:
            slots.release()

    def _serve_page(self):
        try:
            page = (ROOT / "speed-test.html").read_bytes()
        except OSError:
            page = b"Page missing"
            self._reply(404, page)
            return
        self._headers(200, len(page), "text/html; charset=utf-8")
        self.wfile.write(page)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"Speed test at http://{HOST}:{PORT}/")
    print(f"Limits: download={MAX_DOWNLOAD:,} B, upload={MAX_UPLOAD:,} B, concurrent tests={MAX_CONCURRENT}")
    Server((HOST, PORT), Handler).serve_forever()
