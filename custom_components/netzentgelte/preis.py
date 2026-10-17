"""Gesamtpreis-Berechnung und Modul-3-Zeitfenster. Reines Python."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

STANDARD = "standard"
MODUL3 = "modul3"

UMLAGEN = ("kwkg_umlage", "offshore_netzumlage", "aufschlag_besondere_netznutzung")
ABGABEN = ("stromsteuer", "konzessionsabgabe", "lieferant_aufschlag")


def _zeit(text: str) -> time:
    stunde, minute = text.split(":")
    return time(int(stunde) % 24, int(minute))


def im_fenster(zeitpunkt: time, fenster: str) -> bool:
    """Liegt `zeitpunkt` im Fenster "HH:MM-HH:MM" (Ende exklusiv, über Mitternacht möglich)?"""
    start_text, ende_text = fenster.split("-")
    start, ende = _zeit(start_text), _zeit(ende_text)
    if start <= ende:
        return start <= zeitpunkt < ende
    return zeitpunkt >= start or zeitpunkt < ende


def quartal(zeitpunkt: datetime) -> int:
    return (zeitpunkt.month - 1) // 3 + 1


def modul3_stufe(zeitpunkt: datetime, werte: dict) -> str:
    """Tarifstufe HT/ST/NT für den Zeitpunkt (Ortszeit). Außerhalb der Quartale: ST."""
    quartale = {int(q) for q in str(werte.get("modul3_quartale") or "1,4").split(",") if q}
    if quartal(zeitpunkt) not in quartale:
        return "ST"
    uhrzeit = zeitpunkt.time()
    if (fenster := werte.get("modul3_nt_zeitfenster")) and im_fenster(uhrzeit, fenster):
        return "NT"
    if (fenster := werte.get("modul3_ht_zeitfenster")) and im_fenster(uhrzeit, fenster):
        return "HT"
    return "ST"


def modul3_netzpreis(zeitpunkt: datetime, werte: dict) -> float | None:
    """Netz-Arbeitspreis Modul 3 in ct/kWh netto zum Zeitpunkt."""
    stufe = modul3_stufe(zeitpunkt, werte)
    wert = werte.get(f"modul3_{stufe.lower()}")
    if wert is None and stufe == "ST":
        wert = werte.get("netz_arbeitspreis")
    return wert


@dataclass
class Gesamtpreis:
    """Ergebnis einer Gesamtpreis-Berechnung."""

    brutto_eur_kwh: float
    netto_ct_kwh: float
    netzpreis_ct_kwh: float
    stufe: str | None


def gesamtpreis(
    boerse_ct_kwh: float, zeitpunkt: datetime, werte: dict, variante: str
) -> Gesamtpreis | None:
    """(Börse + Netz + Umlagen + Steuern/Abgaben + Lieferantenaufschlag) × (1 + MwSt).

    Gibt None zurück, wenn ein Pflichtbestandteil fehlt.
    """
    if variante == MODUL3:
        netz = modul3_netzpreis(zeitpunkt, werte)
        stufe = modul3_stufe(zeitpunkt, werte)
    else:
        netz = werte.get("netz_arbeitspreis")
        stufe = None
    if netz is None:
        return None
    summe = boerse_ct_kwh + netz
    for key in UMLAGEN + ABGABEN:
        wert = werte.get(key)
        if wert is None:
            return None
        summe += wert
    mwst = werte.get("mwst")
    if mwst is None:
        return None
    brutto = summe * (1 + mwst / 100) / 100
    return Gesamtpreis(round(brutto, 5), round(summe, 4), netz, stufe)


def boersenpreis_ct_kwh(wert: float, einheit: str | None) -> float:
    """Börsenpreis in ct/kWh umrechnen (Einheit des EPEX-Sensors)."""
    einheit = (einheit or "").replace(" ", "").lower()
    if einheit.startswith("ct"):
        return wert
    if "mwh" in einheit:
        return wert / 10
    return wert * 100  # €/kWh oder EUR/kWh
