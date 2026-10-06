"""Modelo común del catálogo, independiente de la plataforma de origen."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation


@dataclass
class Price:
    id: str
    label: str
    group: str
    amount: str  # texto decimal exacto ("19.90"): nada de float para importes
    currency: str = "EUR"
    vat_percent: str | None = None

    def money(self) -> dict:
        """Formato google.type.Money que usa Things To Do: {currency_code, units, nanos}."""
        try:
            value = Decimal(str(self.amount).replace(",", "."))
        except InvalidOperation as err:
            raise ValueError(f"importe no válido en la tarifa {self.id}: {self.amount!r}") from err
        units = int(value)  # trunca hacia cero
        nanos = int(((value - units) * 1_000_000_000).to_integral_value())
        money = {"currency_code": (self.currency or "EUR").upper(), "units": str(units)}
        if nanos:
            money["nanos"] = nanos
        return money


@dataclass
class Variation:
    id: str
    name: str
    prices: list[Price] = field(default_factory=list)


@dataclass
class Product:
    platform: str
    id: str
    name: str
    variations: list[Variation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
