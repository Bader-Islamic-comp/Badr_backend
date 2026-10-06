"""A local HTTP server that records what reaches it, for the tests that a private endpoint is called directly.

`HTTP_PROXY` and friends must never route a request meant for a private address (the speech service, the
model and embedding endpoints) through a proxy: a proxy would see the token, the child's audio or the prompt.
The tests run one of these as the endpoint and another as a stand-in proxy, and check which one was reached.
"""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROXY_VARIABLES = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")


@contextmanager
def recording_server(body: dict):
    """Yields (base URL, requests seen as (method, path)); every request is answered 200 with `body` as JSON."""
    seen = []
    payload = json.dumps(body).encode()

    class Handler(BaseHTTPRequestHandler):
        def _answer(self):
            length = int(self.headers.get("content-length") or 0)
            if length:
                self.rfile.read(length)
            seen.append((self.command, self.path))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = _answer

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        server.server_close()


def route_through(monkeypatch, proxy_url: str):
    """Sets every proxy variable to `proxy_url`, with no exception for local addresses."""
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in PROXY_VARIABLES:
        monkeypatch.setenv(name, proxy_url)
