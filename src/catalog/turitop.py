"""TuriTop API v1: tickets y precios por producto.

Autenticación OAuth propia: /authorization/grant (short_id + secret) devuelve access y refresh token.
Cuando el access token caduca (401) se renueva con /authorization/refresh y se reintenta UNA vez.
"""

from __future__ import annotations

import unicodedata

from .http import ApiError, HttpClient
from .model import Price, Product, Variation
from .customer_groups import classify

BASE_URL = "https://app.turitop.com/v1"


def _nfc(value):
    """TuriTop devuelve a veces texto en NFD ("Niños"): se normaliza para comparar y exportar."""
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


class TuritopClient:
    def __init__(self, short_id: str, secret: str, *, language: str = "es", http: HttpClient | None = None):
        if not short_id or not secret:
            raise ValueError("Faltan las credenciales de TuriTop (TURITOP_SHORT_ID / TURITOP_SECRET)")
        self.short_id = short_id
        self._secret = secret
        self.language = language
        self.http = http or HttpClient(BASE_URL)
        self._access = None
        self._refresh = None

    def _auth(self, path: str, body: dict):
        status, payload = self.http.request("POST", path, body=body)
        if status != 200 or not isinstance(payload, dict) or "data" not in payload:
            raise ApiError(status, "autenticación rechazada")
        self._access = payload["data"]["access_token"]
        self._refresh = payload["data"]["refresh_token"]

    def _call(self, path: str, data: dict):
        if not self._access:
            self._auth("/authorization/grant", {"short_id": self.short_id, "secret_key": self._secret})
        for attempt in (1, 2):
            status, payload = self.http.request("POST", path, body={"access_token": self._access, "data": data})
            if status == 401 and attempt == 1:
                self._auth("/authorization/refresh", {"refresh_token": self._refresh})
                continue
            if status != 200:
                raise ApiError(status, str(payload)[:200])
            return (payload or {}).get("data") or {}
        raise ApiError(401, "token renovado pero sigue sin autorización")

    def tickets(self, product_short_id: str) -> dict:
        data = self._call("/tickets/get", {"product_short_id": product_short_id, "language_code": self.language})
        return data.get("tickets") or {}

    def catalog(self, product_short_ids: list[str]) -> list[Product]:
        products = []
        for sid in product_short_ids:
            tickets = self.tickets(sid)
            prices = [
                Price(
                    id=str(tid),
                    label=_nfc(t.get("name") or ""),
                    group=classify(_nfc(t.get("name") or "")),
                    amount=str(t.get("price") or "0"),
                    currency=t.get("currency") or "EUR",
                )
                for tid, t in sorted(tickets.items(), key=lambda kv: (kv[1] or {}).get("order") or 0)
                if t and not t.get("is_addon")
            ]
            products.append(Product(platform="turitop", id=sid, name=sid, variations=[Variation(id=sid, name="", prices=prices)]))
        return products
