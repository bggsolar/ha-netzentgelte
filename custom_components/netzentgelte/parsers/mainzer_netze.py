"""Parser für die Strom-Preisblätter der Mainzer Netze GmbH.

Liest Netzentgelte Niederspannung ohne Leistungsmessung (SLP) und § 14a EnWG
Modul 1/2/3 aus dem Text des PDF-Preisblatts. Reines Python, ohne Home Assistant.
"""

from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urljoin

ZAHL = r"(\d{1,4},\d{2,3})"
ZEIT = r"(\d{1,2}[:.]\d{2})"
BIS = r"\s*(?:Uhr)?\s*(?:bis|-|–|—)\s*"
EUR_A = r"(?:€|EUR|Euro)\s*/\s*(?:a|Jahr)\b"
CT_KWH = r"ct\s*/\s*kWh"
EUR = r"(?:€|EUR|Euro)(?!\s*/)"


class PreisblattFehler(Exception):
    """Preisblatt nicht lesbar oder Pflichtwerte fehlen."""


@dataclass
class PreisblattErgebnis:
    """Ausgelesene Werte eines Preisblatts."""

    gueltig_ab: date
    vorlaeufig: bool
    quelle: str
    werte: dict[str, Any] = field(default_factory=dict)


def pdf_text(daten: bytes) -> str:
    """Text aus einem PDF extrahieren (blockierend, im Executor aufrufen)."""
    from pypdf import PdfReader  # noqa: PLC0415 - Import erst bei Bedarf
    from pypdf.errors import PdfReadError  # noqa: PLC0415

    try:
        reader = PdfReader(io.BytesIO(daten))
        text = "\n".join(seite.extract_text() or "" for seite in reader.pages)
    except (PdfReadError, ValueError, KeyError, TypeError) as err:
        raise PreisblattFehler(f"PDF nicht lesbar: {err}") from err
    if not text.strip():
        raise PreisblattFehler("PDF enthält keinen extrahierbaren Text")
    return text


def zahl(text: str) -> float:
    """Deutsche Zahl ("1.234,56") in float wandeln."""
    return float(text.replace(".", "").replace(",", "."))


def _norm(text: str) -> str:
    text = text.replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text)


def _zeit(text: str) -> str:
    stunde, minute = re.split(r"[:.]", text)
    return f"{int(stunde):02d}:{minute}"


def _abschnitt(text: str, start: str, ende: list[str], pflicht: str | None = None) -> str:
    """Text ab dem ersten Treffer von `start` (dem `pflicht` folgt) bis zum nächsten Ende-Muster."""
    for treffer in re.finditer(start, text, re.IGNORECASE):
        rest = text[treffer.end():]
        stopp = len(rest)
        for muster in ende:
            m = re.search(muster, rest, re.IGNORECASE)
            if m:
                stopp = min(stopp, m.start())
        abschnitt = rest[:stopp]
        if pflicht is None or re.search(pflicht, abschnitt, re.IGNORECASE):
            return abschnitt
    return ""


def _erster(muster: str, text: str) -> re.Match[str] | None:
    return re.search(muster, text, re.IGNORECASE)


def _betrag(text: str, einheit: str, nach: str = "") -> float | None:
    """Erste Zahl mit Einheit ("75,00 €/a" oder "€/a 75,00"), optional erst nach Muster `nach`."""
    if nach:
        m = _erster(nach, text)
        if m is None:
            return None
        text = text[m.end():]
    m = _erster(ZAHL + r"\s*" + einheit, text) or _erster(einheit + r"\s*" + ZAHL, text)
    return zahl(m.group(1)) if m else None


def _setzen(werte: dict[str, Any], key: str, wert: float | None) -> None:
    if wert is not None:
        werte[key] = wert


def gueltig_ab_ermitteln(text: str, url: str = "") -> date:
    """Gültigkeitsbeginn aus dem Text, sonst 1.1. des Jahres aus Titel oder URL."""
    m = _erster(r"gültig\s+(?:ab|vom)\s+(?:dem\s+)?(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})", text)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = _erster(r"(?:ab|zum)\s+(?:dem\s+)?0?1\.\s?0?1\.\s?(20\d{2})", text)
    if m:
        return date(int(m.group(1)), 1, 1)
    m = _erster(r"preisblatt[^0-9]{0,40}(20\d{2})", text) or _erster(
        r"netzentgelte[^0-9]{0,20}(20\d{2})", text
    )
    if m:
        return date(int(m.group(1)), 1, 1)
    m = re.search(r"(20\d{2})", url.rsplit("/", 1)[-1])
    if m:
        return date(int(m.group(1)), 1, 1)
    raise PreisblattFehler("Gültigkeitsbeginn nicht erkennbar")


def parse_preisblatt(text: str, quelle: str = "") -> PreisblattErgebnis:
    """Werte aus dem Preisblatt-Text auslesen."""
    t = _norm(text)
    ergebnis = PreisblattErgebnis(
        gueltig_ab=gueltig_ab_ermitteln(t, quelle),
        vorlaeufig=bool(re.search(r"vorläufig", t, re.IGNORECASE) or "vorlaeufig" in quelle),
        quelle=quelle,
    )
    w = ergebnis.werte

    # Standard: Entnahme ohne Leistungsmessung (Niederspannung)
    slp = _abschnitt(
        t,
        r"ohne\s+Leistungsmessung",
        [r"§\s*14\s*a", r"Modul\s*1", r"Preisblatt\s*\d"],
        pflicht=r"Arbeitspreis",
    )
    _setzen(w, "netz_grundpreis", _betrag(slp, EUR_A))
    _setzen(w, "netz_arbeitspreis", _betrag(slp, CT_KWH))

    # § 14a Modul 1: pauschale Netzentgeltreduzierung (Betrag in €, nicht €/a)
    modul1 = _abschnitt(t, r"Modul\s*1", [r"Modul\s*2", r"Preisblatt\s*\d"], pflicht=r"reduzierung")
    _setzen(w, "modul1_reduzierung", _betrag(modul1, EUR, nach=r"reduzierung"))

    # § 14a Modul 2: prozentuale Arbeitspreisreduzierung
    modul2 = _abschnitt(t, r"Modul\s*2", [r"Modul\s*3", r"Preisblatt\s*\d"], pflicht=r"Arbeitspreis")
    _setzen(w, "modul2_arbeitspreis", _betrag(modul2, CT_KWH))

    # § 14a Modul 3: zeitvariable Netzentgelte
    modul3 = _abschnitt(
        t, r"Modul\s*3", [r"Preisblatt\s*\d", r"Messeinrichtung", r"Konzessionsabgabe"], pflicht=r"Hochtarif|\bHT\b"
    )
    if m := _erster(r"(?:Hochtarif|\bHT\b)\D{0,40}?" + ZEIT + BIS + ZEIT + r"\D{0,40}?" + ZAHL, modul3):
        w["modul3_ht_zeitfenster"] = f"{_zeit(m.group(1))}-{_zeit(m.group(2))}"
        w["modul3_ht"] = zahl(m.group(3))
    if m := _erster(r"(?:Niedertarif|\bNT\b)\D{0,40}?" + ZEIT + BIS + ZEIT + r"\D{0,40}?" + ZAHL, modul3):
        w["modul3_nt_zeitfenster"] = f"{_zeit(m.group(1))}-{_zeit(m.group(2))}"
        w["modul3_nt"] = zahl(m.group(3))
    if m := _erster(r"(?:Standardtarif|\bST\b)[^,]{0,120}?" + ZAHL, modul3):
        w["modul3_st"] = zahl(m.group(1))
    quartale = sorted({int(q) for q in re.findall(r"(?:Quartal\s*|\bQ)([1-4])\b", modul3)})
    if quartale:
        w["modul3_quartale"] = ",".join(str(q) for q in quartale)

    if "netz_arbeitspreis" not in w or "netz_grundpreis" not in w:
        raise PreisblattFehler("Grund- oder Arbeitspreis (ohne Leistungsmessung) nicht gefunden")
    return ergebnis


def preisblatt_links(seite_html: str, basis_url: str) -> list[str]:
    """Links auf Strom-Preisblätter (PDF) aus der Übersichtsseite."""
    links: list[str] = []
    for href in re.findall(r'href="([^"]+?\.pdf[^"]*)"', seite_html, re.IGNORECASE):
        href = html.unescape(href)
        dateiname = href.split("?", 1)[0].rsplit("/", 1)[-1].lower()
        if "preisblatt" in dateiname and dateiname.startswith("s_"):
            url = urljoin(basis_url, href)
            if url not in links:
                links.append(url)
    return links


def jahr_aus_url(url: str) -> int | None:
    m = re.search(r"(20\d{2})", url.split("?", 1)[0].rsplit("/", 1)[-1])
    return int(m.group(1)) if m else None
