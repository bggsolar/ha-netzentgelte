"""Erzeugt synthetische Test-Preisblätter (Aufbau nachempfunden, keine Originale).

Aufruf: python scripts/synthetische_preisblaetter.py  (benötigt reportlab)
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ZIEL = Path(__file__).parent.parent / "tests" / "fixtures" / "preisblaetter"

JAHRE = {
    "2026": dict(titel="Preisblatt Netzentgelte Strom 2026", gueltig="gültig ab 01.01.2026", gp="75,00", ap="6,72",
                 m1="117,63", m2="2,69", ht="16:45 bis 20:00", ht_p="7,86", st="6:00 bis 16:45 Uhr und 20:00 bis 22:00", nt_p="1,01"),
    "2027_vorlaeufig": dict(titel="Vorläufiges Preisblatt Netzentgelte Strom 2027", gueltig="gültig ab 01.01.2027", gp="90,00",
                            ap="6,11", m1="113,05", m2="2,44", ht="16:45 bis 19:45", ht_p="11,00",
                            st="6:00 bis 16:45 Uhr und 19:45 bis 22:00", nt_p="1,22"),
}


def zeilen(w: dict) -> list[str]:
    return [
        "Mainzer Netze GmbH",
        w["titel"],
        w["gueltig"],
        "Preisblatt 1: Entnahme mit Leistungsmessung",
        "Niederspannung Leistungspreis €/kW*a 25,10 Arbeitspreis ct/kWh 5,90",
        "Preisblatt 2: Entnahme ohne Leistungsmessung",
        "Netzebene Grundpreis Arbeitspreis",
        f"Niederspannung {w['gp']} €/a {w['ap']} ct/kWh",
        "Alle Preise zuzüglich KWKG-Umlage, Offshore-Netzumlage, Aufschlag für besondere Netznutzung und Konzessionsabgabe.",
        "Preisblatt 3: Steuerbare Verbrauchseinrichtungen nach § 14a EnWG",
        "Modul 1: Pauschale Netzentgeltreduzierung",
        f"Grundpreis {w['gp']} €/a Arbeitspreis {w['ap']} ct/kWh Netzentgeltreduzierung {w['m1']} €",
        "Das Gesamtentgelt der Entnahmestelle kann nicht unter 0 sinken.",
        "Modul 2: Prozentuale Arbeitspreisreduzierung",
        f"Grundpreis 0,00 €/a Arbeitspreis {w['m2']} ct/kWh",
        "Modul 3: Zeitvariable Netzentgelte",
        f"Grundpreis {w['gp']} €/a, gültig in Quartal 1 (Januar bis März) und Quartal 4 (Oktober bis Dezember)",
        f"Hochtarif (HT) {w['ht']} Uhr {w['ht_p']} ct/kWh",
        f"Standardtarif (ST) {w['st']} Uhr {w['ap']} ct/kWh",
        f"Niedertarif (NT) 22:00 bis 6:00 Uhr {w['nt_p']} ct/kWh",
        "Preisblatt 5: Messeinrichtungen ohne Leistungsmessung",
        "Eintarifzähler 15,90 €/a Zweirichtungszähler 24,90 €/a",
    ]


def main() -> None:
    ZIEL.mkdir(parents=True, exist_ok=True)
    for name, werte in JAHRE.items():
        pdf = canvas.Canvas(str(ZIEL / f"synthetisch_s_preisblatt_{name}.pdf"), pagesize=A4)
        y = 800
        for zeile in zeilen(werte):
            pdf.setFont("Helvetica", 8)
            pdf.drawString(40, y, zeile)
            y -= 16
        pdf.save()


if __name__ == "__main__":
    main()
