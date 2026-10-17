"""Tests der Gesamtpreis-Berechnung und Modul-3-Zeitfenster."""

from datetime import datetime

import pytest

from custom_components.netzentgelte.preis import (
    MODUL3,
    STANDARD,
    boersenpreis_ct_kwh,
    gesamtpreis,
    modul3_stufe,
)

WERTE_2026 = {
    "netz_arbeitspreis": 6.72,
    "modul3_ht": 7.86,
    "modul3_st": 6.72,
    "modul3_nt": 1.01,
    "modul3_ht_zeitfenster": "16:45-20:00",
    "modul3_nt_zeitfenster": "22:00-06:00",
    "modul3_quartale": "1,4",
    "kwkg_umlage": 0.446,
    "offshore_netzumlage": 0.941,
    "aufschlag_besondere_netznutzung": 1.559,
    "stromsteuer": 2.05,
    "konzessionsabgabe": 1.99,
    "lieferant_aufschlag": 1.81,
    "mwst": 19.0,
}


@pytest.mark.parametrize(
    ("zeit", "stufe"),
    [
        ("2026-01-15 23:00", "NT"),
        ("2026-01-15 05:59", "NT"),
        ("2026-01-15 06:00", "ST"),
        ("2026-11-15 16:45", "HT"),
        ("2026-11-15 19:59", "HT"),
        ("2026-11-15 20:00", "ST"),
        ("2026-07-15 23:00", "ST"),  # Q3: Modul 3 nicht aktiv
        ("2026-04-01 02:00", "ST"),
    ],
)
def test_modul3_stufe(zeit, stufe):
    assert modul3_stufe(datetime.fromisoformat(zeit), WERTE_2026) == stufe


def test_gesamtpreis_standard_entspricht_bisherigem_aufschlag():
    # Aufschlag ohne Börse: 6,72 + 2,946 + 2,05 + 1,99 + 1,81 = 15,516 ct (HA bisher 15,6)
    ergebnis = gesamtpreis(10.0, datetime(2026, 1, 15, 12), WERTE_2026, STANDARD)
    assert ergebnis.netto_ct_kwh == pytest.approx(25.516)
    assert ergebnis.brutto_eur_kwh == pytest.approx(0.30364, abs=1e-5)


def test_gesamtpreis_modul3_nacht():
    ergebnis = gesamtpreis(10.0, datetime(2026, 1, 15, 23), WERTE_2026, MODUL3)
    assert ergebnis.stufe == "NT"
    assert ergebnis.netto_ct_kwh == pytest.approx(25.516 - 5.71)


def test_gesamtpreis_fehlender_bestandteil():
    werte = dict(WERTE_2026)
    del werte["kwkg_umlage"]
    assert gesamtpreis(10.0, datetime(2026, 1, 15, 12), werte, STANDARD) is None


@pytest.mark.parametrize(
    ("wert", "einheit", "ct"),
    [(0.1, "€/kWh", 10.0), (10.0, "ct/kWh", 10.0), (100.0, "EUR/MWh", 10.0), (0.1, None, 10.0)],
)
def test_boersenpreis_einheiten(wert, einheit, ct):
    assert boersenpreis_ct_kwh(wert, einheit) == pytest.approx(ct)
