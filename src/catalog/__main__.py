"""CLI.

  python -m catalog regiondo --out catalogo
  python -m catalog turitop --products P1,P2,P3 --out catalogo
  python -m catalog regiondo --ttd-landing "https://www.example.com/reservar?p={product_id}&v={variation_id}"

Las credenciales se leen de variables de entorno, nunca de argumentos (quedarían en el historial):
REGIONDO_PUBLIC_KEY, REGIONDO_SECRET, TURITOP_SHORT_ID, TURITOP_SECRET.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .export import to_csv, to_things_to_do
from .http import CallBudgetExceeded, HttpClient
from .regiondo import BASE_URL as REGIONDO_URL, RegiondoClient
from .turitop import BASE_URL as TURITOP_URL, TuritopClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="catalog", description="Exporta catálogo y precios de plataformas de reservas")
    parser.add_argument("platform", choices=["regiondo", "turitop"])
    parser.add_argument("--products", help="TuriTop: short_id de los productos, separados por comas")
    parser.add_argument("--locale", default="es_ES")
    parser.add_argument("--max-calls", type=int, default=500, help="tope de llamadas a la API por ejecución")
    parser.add_argument("--out", default="out", help="carpeta de salida")
    parser.add_argument("--ttd-landing", help="plantilla de landing page para generar el esqueleto de Things To Do")
    args = parser.parse_args(argv)

    try:
        if args.platform == "regiondo":
            client = RegiondoClient(os.environ.get("REGIONDO_PUBLIC_KEY", ""), os.environ.get("REGIONDO_SECRET", ""),
                                    locale=args.locale, http=HttpClient(REGIONDO_URL, max_calls=args.max_calls))
            products = client.catalog()
        else:
            if not args.products:
                parser.error("turitop necesita --products")
            client = TuritopClient(os.environ.get("TURITOP_SHORT_ID", ""), os.environ.get("TURITOP_SECRET", ""),
                                   language=args.locale[:2], http=HttpClient(TURITOP_URL, max_calls=args.max_calls))
            products = client.catalog([s.strip() for s in args.products.split(",") if s.strip()])
    except (ValueError, CallBudgetExceeded) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.platform}_catalog.json").write_text(
        json.dumps([p.to_dict() for p in products], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / f"{args.platform}_prices.csv").write_text(to_csv(products), encoding="utf-8")
    if args.ttd_landing:
        (out / f"{args.platform}_things_to_do.json").write_text(
            json.dumps({"products": to_things_to_do(products, args.ttd_landing)}, ensure_ascii=False, indent=2), encoding="utf-8")
    prices = sum(len(v.prices) for p in products for v in p.variations)
    # Solo ASCII: la consola de Windows (cp1252) no puede imprimir flechas y la CLI fallaría al final
    print(f"{len(products)} productos | {prices} tarifas | {client.http.calls} llamadas -> {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
