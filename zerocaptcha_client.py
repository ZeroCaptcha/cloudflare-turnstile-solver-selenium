"""A small client for the ZeroCaptcha REST API, with the standard library only: solve a Cloudflare
Turnstile widget for its token, or a Cloudflare challenge page for its cf_clearance cookie.

For a maintained client with callbacks and signature checks, use the official SDK:
pip install zerocaptcha.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, Optional

# Answers worth another try after a wait: too many requests, or a server busy or away.
RETRYABLE = {429, 502, 503, 504}
ATTEMPTS = 3


class ZeroCaptchaError(Exception):
    """The API refused a request, the task ended without a result, or the wait ran out."""

    def __init__(self, code: str, message: str, request_id: Optional[str] = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.request_id = request_id


class ZeroCaptcha:
    """The API, as one account's key sees it: ZEROCAPTCHA_API and ZEROCAPTCHA_KEY by default."""

    def __init__(
        self,
        api: Optional[str] = None,
        key: Optional[str] = None,
        interval: float = 2,
        timeout: float = 180,
    ) -> None:
        self.api = (api or os.environ.get("ZEROCAPTCHA_API") or "").rstrip("/")
        self.key = key or os.environ.get("ZEROCAPTCHA_KEY") or ""
        if not self.api or not self.key:
            raise ValueError("Set ZEROCAPTCHA_API and ZEROCAPTCHA_KEY first.")
        self.interval = interval
        self.timeout = timeout

    def solve_turnstile(
        self,
        website_url: str,
        website_key: str,
        action: Optional[str] = None,
        cdata: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> str:
        """A Cloudflare Turnstile token for the widget: it works once, for 300 seconds."""
        task: Dict[str, Any] = {
            "type": "TurnstileTask" if proxy else "TurnstileTaskProxyless",
            "websiteURL": website_url,
            "websiteKey": website_key,
        }
        for field, value in (("action", action), ("cdata", cdata), ("proxy", proxy)):
            if value:
                task[field] = value
        return self._run(task)["solution"]["token"]

    def solve_challenge(self, website_url: str, proxy: str) -> Dict[str, str]:
        """A Cloudflare challenge page's clearance, through your proxy: the cf_clearance cookie
        and the user agent it is bound to. Use both, through the same proxy."""
        done = self._run({"type": "CloudflareChallengeTask", "websiteURL": website_url, "proxy": proxy})
        return {"cf_clearance": done["solution"]["cookie"]["value"], "user_agent": done["solution"]["userAgent"]}

    def _run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a task and waits for it to end; returns it once it succeeded."""
        deadline = time.monotonic() + self.timeout
        # One key per task: a retry after a lost reply returns this task instead of making another.
        current = self._request("POST", "/v1/tasks", deadline, task, str(uuid.uuid4()))
        while current["status"] in ("queued", "running"):
            if time.monotonic() + self.interval >= deadline:
                raise ZeroCaptchaError("timeout", f"Task {current['id']} was still {current['status']}.")
            time.sleep(self.interval)
            current = self._request("GET", f"/v1/tasks/{current['id']}", deadline)
        if current["status"] == "succeeded" and current.get("solution"):
            return current
        raise ZeroCaptchaError(
            current.get("errorCode") or current["status"],
            current.get("errorDescription") or f"The task {current['status']}; nothing was charged.",
        )

    def _request(
        self,
        method: str,
        path: str,
        deadline: float,
        body: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends one request, trying it up to three times with the same Idempotency-Key."""
        headers = {"Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        for attempt in range(1, ATTEMPTS + 1):
            left = deadline - time.monotonic()
            if left <= 0:
                raise ZeroCaptchaError("timeout", f"{method} {path} ran past the deadline.")
            request = urllib.request.Request(self.api + path, data=data, headers=headers, method=method)
            wait = float(attempt)
            try:
                with urllib.request.urlopen(request, timeout=min(30, left)) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as error:
                failure = _refusal(error)
                retryable = error.code in RETRYABLE or (
                    error.code == 409 and failure.code == "idempotency_key_in_use"
                )
                if not retryable:
                    raise failure from None
                asked = (error.headers.get("Retry-After") or "").strip()
                if asked.isdigit():
                    wait = float(asked)
            except (urllib.error.URLError, OSError, ValueError) as error:
                # No answer, or one cut short: the same Idempotency-Key makes a retry safe.
                failure = ZeroCaptchaError("network", str(error))
            if attempt == ATTEMPTS:
                raise failure
            if time.monotonic() + wait >= deadline:
                raise ZeroCaptchaError("timeout", f"{method} {path} ran past the deadline.")
            time.sleep(wait)
        raise AssertionError("unreachable")


def _refusal(error: urllib.error.HTTPError) -> ZeroCaptchaError:
    """The API's problem document (RFC 9457) as an error: its code, detail and request ID."""
    try:
        problem = json.loads(error.read())
    except ValueError:
        problem = {}
    if not isinstance(problem, dict):
        problem = {}
    return ZeroCaptchaError(
        str(problem.get("code") or f"http_{error.code}"),
        str(problem.get("detail") or problem.get("title") or f"HTTP {error.code}"),
        problem.get("request_id") or error.headers.get("x-request-id"),
    )
