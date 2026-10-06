"""Cliente HTTP mínimo (solo biblioteca estándar) con límite de llamadas y pausa entre peticiones."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class CallBudgetExceeded(RuntimeError):
    """Se alcanzó el máximo de llamadas permitido para la ejecución (protege la cuota de la API)."""


class HttpClient:
    def __init__(self, base_url: str, *, max_calls: int = 500, delay_s: float = 0.25, timeout_s: float = 30,
                 sleep: Callable[[float], None] = time.sleep):
        self.base_url = base_url.rstrip("/")
        self.max_calls = max_calls
        self.delay_s = delay_s
        self.timeout_s = timeout_s
        self.calls = 0
        self._sleep = sleep
        self._last = 0.0

    def request(self, method: str, path: str, *, query: str = "", headers: dict | None = None,
                body: Any = None) -> tuple[int, Any]:
        if self.calls >= self.max_calls:
            raise CallBudgetExceeded(f"límite de {self.max_calls} llamadas alcanzado")
        wait = self.delay_s - (time.monotonic() - self._last)
        if self._last and wait > 0:
            self._sleep(wait)
        self.calls += 1

        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json; charset=utf-8"} if data else {}),
            **(headers or {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as res:
                status, raw = res.status, res.read()
        except urllib.error.HTTPError as err:
            status, raw = err.code, err.read()
        finally:
            self._last = time.monotonic()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            payload = raw.decode("utf-8", "replace")
        return status, payload
