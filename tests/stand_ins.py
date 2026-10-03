"""Stand-ins on this machine for everything the flows talk to, so the tests need no key, make no
real task and reach no real site:

- an API that answers POST /v1/tasks and GET /v1/tasks/{id} as ZeroCaptcha's does, for
  Cloudflare Turnstile and challenge-page tasks;
- a site with a login form behind a Cloudflare Turnstile widget, which accepts only the token the
  stand-in API hands out;
- a proxy that answers for a site behind a Cloudflare challenge, http://site.test/: it serves the
  page only to requests that come through it with the cf_clearance cookie and the user agent the
  stand-in API hands out, and a "Just a moment..." page to every other.
"""

from __future__ import annotations

import json
import threading
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List
from urllib.parse import parse_qs

KEY = "zc_live_test_key"
TOKEN = "0.stand-in-turnstile-token"
CLEARANCE = "stand-in-cf-clearance"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
SITEKEY = "1x00000000000000000000AA"
CHALLENGED_SITE = "http://site.test/"

LOGIN_PAGE = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Log in</title></head>
<body>
  <form method="post" action="/login">
    <label>Email <input name="email" value="me@example.com"></label>
    <div class="cf-turnstile" data-sitekey="{SITEKEY}" data-action="login" data-cdata="session-7f3a9c2e" data-callback="onTurnstile"></div>
    <button type="submit">Log in</button>
  </form>
  <script>
    window.onTurnstile = (token) => {{ document.body.dataset.callback = token; }};
  </script>
</body>
</html>"""


class QuietServer(ThreadingHTTPServer):
    """A browser drops connections it no longer needs; that is no error worth printing."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass


class Server:
    """A server on 127.0.0.1 whose handle(handler, method, body) answers every request."""

    def __init__(self, handle: Callable[[BaseHTTPRequestHandler, str, bytes], None]) -> None:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802 - the name http.server calls
                handle(self, "GET", b"")

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                handle(self, "POST", self.rfile.read(length))

        self.server = QuietServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def send(handler: BaseHTTPRequestHandler, status: int, kind: str, text: str) -> None:
    data = text.encode()
    handler.send_response(status)
    handler.send_header("Content-Type", kind)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class StandInApi(Server):
    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        self.tasks: Dict[str, Dict[str, Any]] = {}
        super().__init__(self.answer)

    def answer(self, handler: BaseHTTPRequestHandler, method: str, raw: bytes) -> None:
        body = json.loads(raw) if raw else None
        self.requests.append({"method": method, "path": handler.path, "body": body})
        if handler.headers.get("Authorization") != f"Bearer {KEY}":
            return send(handler, 401, "application/json", json.dumps({"code": "unauthorized"}))
        if method == "POST" and handler.path == "/v1/tasks":
            task_id = str(uuid.uuid4())
            self.tasks[task_id] = {"body": body, "polls": 0}
            return send(handler, 201, "application/json", json.dumps({"id": task_id, "status": "queued"}))
        task_id = handler.path.replace("/v1/tasks/", "")
        task = self.tasks.get(task_id)
        if method != "GET" or task is None:
            return send(handler, 404, "application/json", json.dumps({"code": "not_found"}))
        task["polls"] += 1
        if task["polls"] == 1:
            return send(handler, 200, "application/json", json.dumps({"id": task_id, "status": "running"}))
        if task["body"]["type"] == "CloudflareChallengeTask":
            solution = {
                "token": CLEARANCE,
                "userAgent": USER_AGENT,
                "cookie": {"name": "cf_clearance", "value": CLEARANCE, "expiresAt": None},
            }
        else:
            solution = {"token": TOKEN}
        reply = {"id": task_id, "status": "succeeded", "solution": solution}
        send(handler, 200, "application/json", json.dumps(reply))


class StandInSite(Server):
    def __init__(self) -> None:
        self.posted: List[Dict[str, str]] = []
        super().__init__(self.answer)

    def answer(self, handler: BaseHTTPRequestHandler, method: str, raw: bytes) -> None:
        if handler.path == "/login" and method == "GET":
            return send(handler, 200, "text/html", LOGIN_PAGE)
        if handler.path == "/login" and method == "POST":
            form = {name: values[0] for name, values in parse_qs(raw.decode()).items()}
            self.posted.append(form)
            accepted = form.get("cf-turnstile-response") == TOKEN
            title = "Logged in" if accepted else "Refused"
            return send(handler, 200 if accepted else 403, "text/html", f"<!doctype html><title>{title}</title><h1>{title}</h1>")
        send(handler, 404, "text/plain", "Not found")


class StandInChallengeProxy(Server):
    def __init__(self) -> None:
        self.seen: List[Dict[str, Any]] = []
        super().__init__(self.answer)

    def answer(self, handler: BaseHTTPRequestHandler, method: str, raw: bytes) -> None:
        # Through a proxy, the request line carries the whole URL.
        cookies = SimpleCookie(handler.headers.get("Cookie") or "")
        user_agent = handler.headers.get("User-Agent")
        self.seen.append({"url": handler.path, "cookies": {k: v.value for k, v in cookies.items()}, "user_agent": user_agent})
        if not handler.path.startswith(CHALLENGED_SITE):
            return send(handler, 502, "text/plain", "Not this site")
        cleared = "cf_clearance" in cookies and cookies["cf_clearance"].value == CLEARANCE and user_agent == USER_AGENT
        if cleared:
            return send(handler, 200, "text/html", "<!doctype html><title>Welcome</title><h1>Welcome</h1>")
        send(handler, 403, "text/html", "<!doctype html><title>Just a moment...</title><h1>Checking your browser</h1>")
