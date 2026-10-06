"""Regiondo Supplier API: productos y tarifas por variación (availoptions).

Autenticación: cada petición se firma con HMAC-SHA256(timestamp + clave pública + querystring)
usando la clave privada, enviada en X-API-HASH junto con X-API-TIME y X-API-ID.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Callable, Iterator
from urllib.parse import quote_plus, urlencode

from .http import ApiError, HttpClient
from .model import Price, Product, Variation
from .customer_groups import classify

BASE_URL = "https://api.regiondo.com/v1"


def build_query(params: dict) -> str:
    """Querystring ordenado y codificado igual que lo firma Regiondo (http_build_query de PHP)."""
    return urlencode(sorted(params.items()), quote_via=quote_plus)


def sign(public_key: str, secret: str, query: str, timestamp: str) -> str:
    message = f"{timestamp}{public_key}{query}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _rows(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return list(value.values())
    return []


class RegiondoClient:
    def __init__(self, public_key: str, secret: str, *, locale: str = "es_ES", currency: str = "EUR",
                 http: HttpClient | None = None, clock: Callable[[], float] = time.time):
        if not public_key or not secret:
            raise ValueError("Faltan las claves de Regiondo (REGIONDO_PUBLIC_KEY / REGIONDO_SECRET)")
        self.public_key = public_key
        self._secret = secret
        self.locale = locale
        self.currency = currency
        self.http = http or HttpClient(BASE_URL)
        self._clock = clock

    def _get(self, path: str, params: dict):
        query = build_query(params)
        ts = str(int(self._clock() * 1000))
        headers = {"X-API-ID": self.public_key, "X-API-TIME": ts, "X-API-HASH": sign(self.public_key, self._secret, query, ts)}
        status, payload = self.http.request("GET", path, query=query, headers=headers)
        if status != 200:
            raise ApiError(status, str(payload)[:200])
        return payload

    def iter_products(self, page_size: int = 40) -> Iterator[dict]:
        offset = 0
        while True:
            rows = _rows(self._get("/products", {"limit": page_size, "offset": offset, "store_locale": self.locale}))
            yield from rows
            if len(rows) < page_size:
                return
            offset += page_size

    def availoptions(self, variation_id: str) -> list[dict]:
        return _rows(self._get(f"/products/availoptions/{variation_id}",
                               {"store_locale": self.locale, "currency": self.currency}))

    def catalog(self) -> list[Product]:
        products = []
        for p in self.iter_products():
            variations = []
            for v in p.get("variations") or []:
                vid = str(v.get("variation_id") or "")
                if not vid:
                    continue
                prices = [
                    Price(
                        id=str(o.get("option_id")),
                        label=o.get("name") or "",
                        group=classify(o.get("name") or ""),
                        amount=str(o.get("regiondo_price") or o.get("original_price") or "0"),
                        currency=self.currency,
                        vat_percent=o.get("vat_percentage_val"),
                    )
                    for o in self.availoptions(vid)
                ]
                variations.append(Variation(id=vid, name=v.get("name") or "", prices=prices))
            products.append(Product(platform="regiondo", id=str(p.get("product_id")), name=p.get("name") or "", variations=variations))
        return products
