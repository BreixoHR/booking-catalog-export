"""Clasificación de tipos de cliente a partir del nombre de la tarifa.

Las plataformas devuelven nombres libres y multilingües: "Adultos (+18)", "Niños (6-10)",
"Child 4-12", "Kinder bis 5 Jahre", "Senior 65+", "Bebé (0-2)". El precio por grupo (adulto, niño,
bebé...) es lo que necesita el feed de Google Things To Do.

Primero se interpreta el rango de edad si lo hay; si no, palabras clave en varios idiomas.
(La versión anterior buscaba "0" o "18" como subcadena: "Niños (6-10)" acababa como bebé y
"Jóvenes (12-18)" como adulto.)
"""

from __future__ import annotations

import re
import unicodedata

ADULT, YOUTH, CHILD, INFANT, SENIOR, OTHER = "adult", "youth", "child", "infant", "senior", "other"

_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (INFANT, ("bebe", "baby", "infant", "nourrisson", "neonato", "kleinkind")),
    (SENIOR, ("senior", "jubilad", "pensionist", "mayores de 65", "rentner", "anziani")),
    (YOUTH, ("joven", "jovenes", "youth", "junior", "student", "estudiante", "teen", "jugend")),
    (CHILD, ("nino", "nina", "ninos", "infantil", "child", "children", "kid", "kind", "enfant", "bambin")),
    (ADULT, ("adult", "adulto", "adulte", "erwachsen", "general", "standard", "estandar")),
]


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def age_range(name: str) -> tuple[int | None, int | None]:
    """Rango de edad expresado en el nombre: "(6-10)" → (6, 10); "+18" / "18+" → (18, None); "bis 5" / "hasta 5" → (0, 5)."""
    text = _plain(name)
    m = re.search(r"(\d{1,2})\s*(?:-|–|a|to|bis)\s*(\d{1,2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(?:\+\s*(\d{1,2})|(\d{1,2})\s*\+|(?:mayores de|over|ab|des)\s*(\d{1,2}))", text)
    if m:
        return int(next(g for g in m.groups() if g)), None
    m = re.search(r"(?:hasta|menores de|under|up to|bis|jusqu'a|moins de)\s*(\d{1,2})", text)
    if m:
        return 0, int(m.group(1))
    return None, None


def classify(name: str) -> str:
    low, high = age_range(name)
    if low is not None or high is not None:
        if high is not None and high <= 3:
            return INFANT
        if low is not None and low >= 65:
            return SENIOR
        if low is not None and low >= 18:
            return ADULT
        if high is not None and high <= 12:
            return CHILD
        if high is not None and high <= 25:
            return YOUTH
    text = _plain(name)
    for group, words in _KEYWORDS:
        if any(re.search(rf"\b{re.escape(w)}", text) for w in words):
            return group
    return OTHER
