"""Servidores HTTP locales que imitan Regiondo y TuriTop para los tests (sin red ni dependencias)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from catalog.regiondo import sign

PUBLIC, SECRET = "pub-key", "secret-key"

REGIONDO_PRODUCTS = [
    {"product_id": str(100 + i), "name": f"Tour {i}", "variations": [{"variation_id": str(500 + i), "name": "Visita general"}]}
    for i in range(45)  # 45 productos → 2 páginas de 40
]
REGIONDO_OPTIONS = [
    {"option_id": "1", "name": "Adultos (+18)", "regiondo_price": "19.90", "vat_percentage_val": "21.00"},
    {"option_id": "2", "name": "Niños (6-10)", "regiondo_price": "9.95", "vat_percentage_val": "21.00"},
    {"option_id": "3", "name": "Bebé (0-2)", "regiondo_price": "0.00", "vat_percentage_val": "21.00"},
]

TURITOP_TICKETS = {
    "P1": {
        "293126": {"name": "Niños 4-12", "price": "12.50", "currency": "EUR", "order": 2},  # texto en NFD
        "293123": {"name": "Adulto", "price": "25", "currency": "EUR", "order": 1},
        "293130": {"name": "Audioguía", "price": "5", "currency": "EUR", "order": 3, "is_addon": True},
    }
}


class _State:
    def __init__(self):
        self.reset()

    def reset(self):
        self.requests = []
        self.expire_next = False
        self.tokens_issued = 0


state = _State()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencio
        pass

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- Regiondo ----
    def do_GET(self):
        url = urlparse(self.path)
        query = url.query
        state.requests.append(("GET", url.path, query, dict(self.headers)))
        expected = sign(PUBLIC, SECRET, query, self.headers.get("X-API-TIME", ""))
        if self.headers.get("X-API-ID") != PUBLIC or self.headers.get("X-API-HASH") != expected:
            return self._send(401, {"error": "invalid signature"})
        params = {k: v[0] for k, v in parse_qs(query).items()}
        if url.path == "/products":
            off, lim = int(params["offset"]), int(params["limit"])
            return self._send(200, {"data": REGIONDO_PRODUCTS[off:off + lim]})
        if url.path.startswith("/products/availoptions/"):
            return self._send(200, {"data": REGIONDO_OPTIONS})
        return self._send(404, {"error": "not found"})

    # ---- TuriTop ----
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        state.requests.append(("POST", self.path, body, dict(self.headers)))
        if self.path == "/authorization/grant":
            if body.get("secret_key") != SECRET:
                return self._send(401, {"error": "bad credentials"})
            return self._issue()
        if self.path == "/authorization/refresh":
            return self._issue()
        if body.get("access_token") != f"access-{state.tokens_issued}" or state.expire_next:
            state.expire_next = False
            return self._send(401, {"error": "token expired"})
        if self.path == "/tickets/get":
            sid = body["data"]["product_short_id"]
            return self._send(200, {"data": {"tickets": TURITOP_TICKETS.get(sid, {})}})
        return self._send(404, {"error": "not found"})

    def _issue(self):
        state.tokens_issued += 1
        return self._send(200, {"data": {"access_token": f"access-{state.tokens_issued}", "refresh_token": "refresh"}})


def start():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
