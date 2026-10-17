"""Tests der Stichtag- und Plausibilitätslogik."""

from datetime import date

from custom_components.netzentgelte.fahrplan import Eintrag, Fahrplan


def e(wert, tag, key="netz_arbeitspreis", vorlaeufig=False):
    return Eintrag(key, wert, date.fromisoformat(tag), "https://quelle", "2026-10-17T12:00:00", vorlaeufig)


def test_neuer_wert_erst_zum_stichtag():
    f = Fahrplan()
    assert f.einpflegen(e(6.72, "2026-01-01"), 30) is None
    assert f.stichtag_anwenden(date(2026, 10, 17)) == []  # erster Lauf meldet nichts
    assert f.einpflegen(e(6.11, "2027-01-01", vorlaeufig=True), 30) is None

    assert f.stichtag_anwenden(date(2026, 12, 31)) == []
    assert f.wirksam["netz_arbeitspreis"].wert == 6.72
    assert f.naechster("netz_arbeitspreis", date(2026, 12, 31)).wert == 6.11

    wechsel = f.stichtag_anwenden(date(2027, 1, 1))
    assert len(wechsel) == 1
    assert (wechsel[0].alt.wert, wechsel[0].neu.wert) == (6.72, 6.11)
    assert f.stichtag_anwenden(date(2027, 1, 2)) == []


def test_plausibilitaet_weist_ab_und_meldet_einmal():
    f = Fahrplan()
    f.einpflegen(e(7.86, "2026-01-01", "modul3_ht"), 30)
    abweisung = f.einpflegen(e(11.0, "2027-01-01", "modul3_ht"), 30)
    assert abweisung is not None and abweisung.neu
    assert round(abweisung.abweichung_prozent, 1) == 39.9
    assert f.wert_am("modul3_ht", date(2027, 6, 1)).wert == 7.86
    # Wiederholter Abruf: keine neue Meldung
    assert f.einpflegen(e(11.0, "2027-01-01", "modul3_ht"), 30).neu is False
    assert len(f.abgewiesen) == 1


def test_abgewiesenen_wert_uebernehmen():
    f = Fahrplan()
    f.einpflegen(e(7.86, "2026-01-01", "modul3_ht"), 30)
    f.einpflegen(e(11.0, "2027-01-01", "modul3_ht"), 30)
    assert f.uebernehmen("modul3_ht", date(2027, 1, 1)).wert == 11.0
    assert f.abgewiesen == []
    assert f.wert_am("modul3_ht", date(2027, 1, 1)).wert == 11.0
    assert f.uebernehmen("modul3_ht", date(2027, 1, 1)) is None


def test_vorlaeufig_wird_endgueltig():
    f = Fahrplan()
    f.einpflegen(e(6.11, "2027-01-01", vorlaeufig=True), 30)
    f.einpflegen(e(6.11, "2027-01-01", vorlaeufig=False), 30)
    assert f.eintraege["netz_arbeitspreis"][0].vorlaeufig is False


def test_korrektur_am_gleichen_stichtag_wird_geprueft():
    f = Fahrplan()
    f.einpflegen(e(6.11, "2027-01-01", vorlaeufig=True), 30)
    assert f.einpflegen(e(6.30, "2027-01-01"), 30) is None
    assert f.wert_am("netz_arbeitspreis", date(2027, 1, 1)).wert == 6.30
    assert f.einpflegen(e(12.0, "2027-01-01"), 30) is not None


def test_nicht_numerische_werte_ohne_grenze():
    f = Fahrplan()
    f.einpflegen(e("16:45-20:00", "2026-01-01", "modul3_ht_zeitfenster"), 30)
    assert f.einpflegen(e("16:45-19:45", "2027-01-01", "modul3_ht_zeitfenster"), 30) is None


def test_speichern_und_laden():
    f = Fahrplan()
    f.einpflegen(e(6.72, "2026-01-01"), 30)
    f.einpflegen(e(20.0, "2027-01-01"), 30)
    f.stichtag_anwenden(date(2026, 10, 17))
    g = Fahrplan.aus_dict(f.als_dict())
    assert g.als_dict() == f.als_dict()
    assert g.abgewiesen[0].wert == 20.0
