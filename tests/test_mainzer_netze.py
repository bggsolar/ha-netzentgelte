"""Tests des Preisblatt-Parsers gegen gespeicherte Preisblätter."""

import json
from datetime import date

import pytest

from custom_components.netzentgelte.parsers.mainzer_netze import (
    PreisblattFehler,
    gueltig_ab_ermitteln,
    jahr_aus_url,
    parse_preisblatt,
    pdf_text,
    preisblatt_links,
)

from .conftest import FIXTURES

ORDNER = FIXTURES / "preisblaetter"
ERWARTET = {k: v for k, v in json.loads((ORDNER / "erwartet.json").read_text()).items() if not k.startswith("_")}
VORHANDEN = sorted(n for n in ERWARTET if (ORDNER / n).exists())


def test_mindestens_ein_preisblatt_vorhanden():
    assert VORHANDEN


@pytest.mark.parametrize("datei", VORHANDEN)
def test_preisblatt(datei):
    erwartet = ERWARTET[datei]
    ergebnis = parse_preisblatt(pdf_text((ORDNER / datei).read_bytes()), f"https://example.org/{datei}")
    assert ergebnis.gueltig_ab == date.fromisoformat(erwartet["gueltig_ab"])
    assert ergebnis.vorlaeufig is erwartet["vorlaeufig"]
    for key, wert in erwartet["werte"].items():
        assert ergebnis.werte.get(key) == wert, key
    modul3_ab = date.fromisoformat(erwartet.get("modul3_gueltig_ab", erwartet["gueltig_ab"]))
    assert ergebnis.gueltig_ab_fuer("modul3_nt") == modul3_ab
    assert ergebnis.gueltig_ab_fuer("netz_arbeitspreis") == ergebnis.gueltig_ab


@pytest.mark.parametrize("datei", sorted(set(p.name for p in ORDNER.glob("*.pdf")) - set(ERWARTET)))
def test_unbekanntes_preisblatt_ist_lesbar(datei):
    """Neu abgelegte Preisblätter ohne Erwartungswerte müssen zumindest parsebar sein."""
    ergebnis = parse_preisblatt(pdf_text((ORDNER / datei).read_bytes()), datei)
    assert ergebnis.werte["netz_arbeitspreis"] > 0


def test_kaputtes_pdf():
    with pytest.raises(PreisblattFehler):
        pdf_text(b"%PDF-1.4 kaputt")


def test_pflichtwerte_fehlen():
    with pytest.raises(PreisblattFehler):
        parse_preisblatt("Preisblatt 2026 gültig ab 01.01.2026 ohne Inhalt", "x")


def test_gueltig_ab_varianten():
    assert gueltig_ab_ermitteln("gültig ab 1.4.2026") == date(2026, 4, 1)
    assert gueltig_ab_ermitteln("Preise ab dem 01.01.2027") == date(2027, 1, 1)
    assert gueltig_ab_ermitteln("nichts", "https://x/s_preisblatt_2025.pdf?rev=1") == date(2025, 1, 1)


def test_preisblatt_links():
    seite = (
        '<a href="/-/media/strom/s_preisblatt_2026.pdf?rev=abc&amp;x=1">2026</a>'
        '<a href="/-/media/strom/s_preisblatt_2027_vorlaeufig.pdf?rev=def">2027</a>'
        '<a href="/-/media/gas/g_preisblatt_2026.pdf">Gas</a>'
        '<a href="/-/media/strom/s_preisblatt_2026.pdf?rev=abc&amp;x=1">doppelt</a>'
    )
    links = preisblatt_links(seite, "https://www.mainzer-netze.de/strom/netzzugang/netzentgelte")
    assert links == [
        "https://www.mainzer-netze.de/-/media/strom/s_preisblatt_2026.pdf?rev=abc&x=1",
        "https://www.mainzer-netze.de/-/media/strom/s_preisblatt_2027_vorlaeufig.pdf?rev=def",
    ]
    assert jahr_aus_url(links[1]) == 2027
