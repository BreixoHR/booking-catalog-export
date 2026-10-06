"""Exportaciones: CSV plano para revisar precios y esqueleto de producto para Google Things To Do."""

from __future__ import annotations

import csv
import io

from .model import Product

CSV_FIELDS = ["platform", "product_id", "product_name", "variation_id", "variation_name",
              "price_id", "label", "group", "amount", "currency", "vat_percent"]


def to_csv(products: list[Product]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for p in products:
        for v in p.variations:
            for price in v.prices:
                writer.writerow({
                    "platform": p.platform, "product_id": p.id, "product_name": p.name,
                    "variation_id": v.id, "variation_name": v.name,
                    "price_id": price.id, "label": price.label, "group": price.group,
                    "amount": price.amount, "currency": price.currency, "vat_percent": price.vat_percent or "",
                })
    return buf.getvalue()


def to_things_to_do(products: list[Product], landing_page: str) -> list[dict]:
    """Un producto de Things To Do por producto y una opción por variación, con sus precios.

    Es un esqueleto: textos traducidos, fotos y ubicaciones se completan después en el editor
    (things-to-do-feed-builder), que además valida el feed antes de exportarlo.
    """
    out = []
    for p in products:
        options = []
        for v in p.variations:
            prices = [
                {"id": f"{price.group}-{price.id}", "title": price.label, "price": price.money()}
                for price in v.prices
                if price.group != "other" or len(v.prices) == 1
            ]
            if not prices:
                continue
            options.append({
                "id": f"{p.platform}-{p.id}-{v.id}",
                "title": {"localized_texts": [{"language_code": "es", "text": v.name or p.name}]},
                "landing_page": {"url": landing_page.format(platform=p.platform, product_id=p.id, variation_id=v.id)},
                "price_options": prices,
            })
        if options:
            out.append({
                "id": f"{p.platform}-{p.id}",
                "title": {"localized_texts": [{"language_code": "es", "text": p.name}]},
                "options": options,
            })
    return out
