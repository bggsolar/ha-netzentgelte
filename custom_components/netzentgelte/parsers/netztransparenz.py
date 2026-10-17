"""Parser für die Umlagen-Jahresseiten auf netztransparenz.de.

KWKG-Umlage und Offshore-Netzumlage stehen als Fließtext ("… beträgt 0,941 ct/kWh"),
der Aufschlag für besondere Netznutzung als Tabelle je Letztverbrauchergruppe.
Für Haushalte gilt jeweils der Satz für die ersten 1 GWh (Gruppe A bzw. A').
"""

from __future__ import annotations

import html
import re

CT = r"(\d{1,2},\d{2,4})\s*ct\s*/\s*kWh"


class UmlageFehler(Exception):
    """Wert auf der Seite nicht gefunden."""


def _text(seite_html: str) -> str:
    seite_html = re.sub(r"<(script|style|nav|header|footer)\b.*?</\1>", " ", seite_html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", seite_html)
    text = html.unescape(text).replace(" ", " ")
    return re.sub(r"\s+", " ", text)


def _zahl(wert: str) -> float:
    return float(wert.replace(",", "."))


def parse_umlage(key: str, seite_html: str, jahr: int) -> float:
    """Umlage in ct/kWh für Gruppe A/A' aus einer Jahresseite lesen."""
    text = _text(seite_html)
    if str(jahr) not in text:
        raise UmlageFehler(f"Jahr {jahr} nicht auf der Seite")

    if key == "aufschlag_besondere_netznutzung":
        # Tabelle: | Jahr | LV Gruppe A' | LV Gruppe B' | ... -> erste Zahl nach der Jahreszeile
        m = re.search(rf"\b{jahr}\b\s*\|?\s*{CT}", text)
        if m is None:
            m = re.search(r"Gruppe\s*A['’`´]?[^0-9]{0,80}?" + CT, text, re.I)
        if m is None:
            raise UmlageFehler("Aufschlag für Gruppe A' nicht gefunden")
        return _zahl(m.group(1))

    # KWKG / Offshore: Satz im Ergebnistext, bevorzugt nahe "beträgt"/"Umlage von"
    for muster in (
        r"beträgt[^0-9]{0,120}?" + CT,
        r"Umlage\s+von\s+" + CT,
        r"(?:Kategorie|Gruppe)\s*A['’`´]?[^0-9]{0,80}?" + CT,
    ):
        if m := re.search(muster, text, re.I):
            return _zahl(m.group(1))
    werte = re.findall(CT, text)
    if len(set(werte)) == 1:
        return _zahl(werte[0])
    raise UmlageFehler("Umlagesatz nicht eindeutig gefunden")
