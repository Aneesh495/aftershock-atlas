"""Bounded local static/API server over the exact exported public data boundary."""
from __future__ import annotations

import csv
import io
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .io import ROOT, canonical, read_json
from .privacy import Disclosure

ALLOWED = {"employment", "gdp", "school", "mortality", "population", "immunization", "life_expectancy", "surveillance"}


class AtlasHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path in {"/api/observations", "/api/export"}:
            try:
                query = parse_qs(url.query, max_num_fields=10)
                metric = query.get("metric", ["employment"])[0]
                if metric not in ALLOWED:
                    raise ValueError("Unknown export metric")
                regions = set(query.get("regions", [""])[0].split(",")) - {""}
                if len(regions) > 250:
                    raise ValueError("Too many regions")
                start = int(query.get("start", [2000])[0])
                end = int(query.get("end", [2026])[0])
                if not 2000 <= start <= end <= 2026:
                    raise ValueError("Invalid calendar interval")
                data = read_json(ROOT / f"client/public/data/{metric}.json")
                result = [Disclosure().apply(r) for r in data if (not regions or r["region"] in regions) and start <= r["yr"] <= end]
                if url.path == "/api/export":
                    stream = io.StringIO()
                    if result:
                        writer = csv.DictWriter(stream, fieldnames=list(result[0]))
                        writer.writeheader()
                        writer.writerows(result)
                    content, mime = stream.getvalue().encode(), "text/csv; charset=utf-8"
                else:
                    content, mime = canonical({"rows": result, "count": len(result), "measurement": metric}), "application/json"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)
            except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
                self.send_error(400, str(e))
            return
        if url.path.startswith("/api/"):
            self.send_error(404, "Unknown API path")
            return
        # The static document root excludes raw data, checkpoints and local ledgers.
        super().do_GET()

    def list_directory(self, path):
        self.send_error(403, "Directory listing disabled")
        return None


class BoundedHTTPServer(ThreadingHTTPServer):
    request_queue_size = 16
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address


def serve(port: int = 8765) -> None:
    if not (ROOT / "dist/index.html").exists():
        raise RuntimeError("Run make atlas before make demo")
    server = BoundedHTTPServer(("127.0.0.1", port), partial(AtlasHandler, directory=str(ROOT / "dist")))
    print(f"Aftershock Atlas: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
