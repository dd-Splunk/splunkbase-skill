"""A tiny fake Splunkbase API for offline tests.

Serves the trimmed real responses in tests/fixtures:
    /api/v1/app/<id>           -> app_<id>.json   (a body with "status": 404 is sent as a 404)
    /api/v1/app/<id>/release   -> release_<id>.json
    /api/v1/app/?query=aws     -> search_aws.json  (any other query: no results)

Tests can add per-path behaviour:
    server.static(path, status, body)   permanent override
    server.queue(path, [(status, body), ...])   one-shot responses, consumed in order
    server.delay[path] = seconds
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FIXTURES = Path(__file__).parent / "fixtures"


class FakeSplunkbase:
    def __init__(self):
        self.statics = {}
        self.queues = {}
        self.delay = {}
        self.requests = []
        self.user_agents = []
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output clean
                pass

            def do_GET(self):
                fake.user_agents.append(self.headers.get("User-Agent"))
                status, body = fake._respond(self.path)
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self._httpd.server_address[1]

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()

    def reset(self):
        with self._lock:
            self.statics.clear()
            self.queues.clear()
            self.delay.clear()
            self.requests.clear()
            self.user_agents.clear()

    def static(self, path, status, body):
        self.statics[path] = (status, body)

    def queue(self, path, responses):
        self.queues[path] = list(responses)

    def request_count(self, path):
        with self._lock:
            return sum(1 for p in self.requests if p == path)

    def _respond(self, raw_path):
        parts = urlsplit(raw_path)
        path = parts.path
        with self._lock:
            self.requests.append(path)
            queued = self.queues.get(path)
            if queued:
                return queued.pop(0)
        wait = self.delay.get(path)
        if wait:
            time.sleep(wait)
        if path in self.statics:
            return self.statics[path]
        if path == "/api/v1/app/":
            query = parse_qs(parts.query).get("query", [""])[0]
            name = "search_aws.json" if "aws" in query.lower() else None
            if name:
                return 200, json.loads((FIXTURES / name).read_text())
            return 200, {"offset": 0, "limit": 10, "total": 0, "results": []}
        segments = path.strip("/").split("/")  # api v1 app <id> [release]
        if len(segments) in (4, 5) and segments[:3] == ["api", "v1", "app"]:
            kind = "release" if len(segments) == 5 and segments[4] == "release" else "app"
            fixture = FIXTURES / ("%s_%s.json" % (kind, segments[3]))
            if fixture.exists():
                body = json.loads(fixture.read_text())
                if isinstance(body, dict) and body.get("status") == 404:
                    return 404, body
                return 200, body
        return 404, {"status": 404, "errors": ["not found"]}
