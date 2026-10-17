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


class PreisblattFehler(Exception):
    """Preisblatt nicht lesbar oder Pflichtwerte fehlen."""


@dataclass
class PreisblattErgebnis:
    """Ausgelesene Werte eines Preisblatts."""

    gueltig_ab: date
    vorlaeufig: bool
    quelle: str
    werte: dict[str, Any] = field(default_factory=dict)
    # Abweichender Gültigkeitsbeginn einzelner Werte (z. B. Modul 3 "gültig ab 01.04.2025")
    gueltig_ab_je_key: dict[str, date] = field(default_factory=dict)

    def gueltig_ab_fuer(self, key: str) -> date:
        return self.gueltig_ab_je_key.get(key, self.gueltig_ab)


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


def _zahlen(text: str) -> list[float]:
    return [zahl(z) for z in re.findall(ZAHL, text)]


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

    # Die Preisblätter sind Tabellen: Spaltenköpfe ("Grundpreis [€/a]", "Arbeitspreis [ct/kWh]")
    # stehen vor der Wertezeile ("90,00 6,11"). Gelesen wird daher die Reihenfolge der Zahlen
    # im jeweiligen Abschnitt; Abschnitte ohne Zahl (Inhaltsverzeichnis) werden übersprungen.

    # Preisblatt 2: Entnahme ohne Leistungsmessung (Niederspannung) -> Grundpreis, Arbeitspreis
    slp = _abschnitt(t, r"Preisblatt\s*2\b", [r"Preisblatt\s*\d", r"§\s*14\s*a"], pflicht=ZAHL)
    if len(n := _zahlen(slp)) >= 2:
        w["netz_grundpreis"], w["netz_arbeitspreis"] = n[0], n[1]

    # § 14a Modul 1: Grundpreis, Arbeitspreis, Netzentgeltreduzierung [€]
    modul1 = _abschnitt(
        t, r"Modul\s*1\b", [r"Modul\s*2\b", r"mit\s+Leistungsmessung", r"Preisblatt\s*\d"], pflicht=ZAHL
    )
    if len(n := _zahlen(modul1)) >= 3:
        w["modul1_reduzierung"] = n[2]

    # § 14a Modul 2: Grundpreis, Arbeitspreis
    modul2 = _abschnitt(t, r"Modul\s*2\b", [r"Modul\s*3\b", r"Preisblatt\s*\d"], pflicht=ZAHL)
    if len(n := _zahlen(modul2)) >= 2:
        w["modul2_arbeitspreis"] = n[1]

    # § 14a Modul 3: Zeilen "HT-Zeiten 16:45 – 19:45 Uhr [Grundpreis] Arbeitspreis" usw.
    modul3 = _abschnitt(t, r"Modul\s*3\b", [r"Preisblatt\s*\d"], pflicht=r"Hochtarif|\bHT\b")
    zeile = r"\D{0,40}?" + ZEIT + BIS + ZEIT + r"\s*(?:Uhr)?\s*" + ZAHL + r"(?:\s*" + ZAHL + r")?"
    if m := _erster(r"(?:Hochtarif|\bHT\b)" + zeile, modul3):
        w["modul3_ht_zeitfenster"] = f"{_zeit(m.group(1))}-{_zeit(m.group(2))}"
        w["modul3_ht"] = zahl(m.group(4) or m.group(3))
    if m := _erster(r"(?:Niedertarif|\bNT\b)" + zeile, modul3):
        w["modul3_nt_zeitfenster"] = f"{_zeit(m.group(1))}-{_zeit(m.group(2))}"
        w["modul3_nt"] = zahl(m.group(4) or m.group(3))
    if m := _erster(r"(?:Standardtarif|\bST\b)[^,]{0,120}?" + ZAHL, modul3):
        w["modul3_st"] = zahl(m.group(1))
    # Quartale aus den Tabellenzeilen ("Quartal 1 HT-Zeiten …"), nicht aus Fußnoten wie
    # "In Quartal 2 und 3 gilt der Standardtarif"
    quartale = re.findall(r"Quartal\s*([1-4])\s*(?:HT|Hochtarif)", modul3, re.IGNORECASE)
    if not quartale:
        quartale = re.findall(r"(?<!In )(?:Quartal\s*|\bQ)([1-4])\b(?!\s*und\s*\d\s*gilt)", modul3)
    if quartale:
        w["modul3_quartale"] = ",".join(str(q) for q in sorted({int(q) for q in quartale}))
    if m := _erster(r"gültig\s+ab\s+(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})", modul3[:200]):
        beginn = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if beginn != ergebnis.gueltig_ab:
            for key in w:
                if key.startswith("modul3_"):
                    ergebnis.gueltig_ab_je_key[key] = beginn

    if "netz_arbeitspreis" not in w or "netz_grundpreis" not in w:
        raise PreisblattFehler("Grund- oder Arbeitspreis (ohne Leistungsmessung) nicht gefunden")
    return ergebnis


def preisblatt_links(seite_html: str, basis_url: str) -> list[str]:
    """Links auf die Jahres-Preisblätter Strom (PDF) aus der Übersichtsseite.

    Nur Dateien wie "s_preisblatt_2026.pdf" oder "s_preisblatt-2022.pdf": Das Referenzpreisblatt
    und das Preisblatt für Wärmepumpen tragen kein Jahr und enthalten keine SLP-Netzentgelte.
    """
    links: list[str] = []
    for href in re.findall(r'href="([^"]+?\.pdf[^"]*)"', seite_html, re.IGNORECASE):
        href = html.unescape(href)
        dateiname = href.split("?", 1)[0].rsplit("/", 1)[-1].lower()
        if re.match(r"s_preisblatt[_-]?20\d{2}", dateiname):
            url = urljoin(basis_url, href)
            if url not in links:
                links.append(url)
    return links


def jahr_aus_url(url: str) -> int | None:
    m = re.search(r"(20\d{2})", url.split("?", 1)[0].rsplit("/", 1)[-1])
    return int(m.group(1)) if m else None
