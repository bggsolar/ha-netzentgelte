# Netzentgelte & Umlagen für Home Assistant

Custom Integration (HACS), die die Bestandteile des Strompreises als einzelne Sensoren bereitstellt und daraus mit einem EPEX-Spot-Börsenpreis den Brutto-Gesamtpreis berechnet. Ausgelegt auf das Netzgebiet der **Mainzer Netze GmbH** (z. B. PLZ 55130), inklusive **§ 14a EnWG Modul 1, 2 und 3**.

| Bestandteil | Quelle |
|---|---|
| Netzentgelt Arbeits- und Grundpreis (Niederspannung ohne Leistungsmessung) | PDF-Preisblatt Mainzer Netze |
| § 14a Modul 1 (Pauschale), Modul 2 (Arbeitspreis), Modul 3 (HT/ST/NT, Zeitfenster, Quartale) | PDF-Preisblatt Mainzer Netze |
| KWKG-Umlage, Offshore-Netzumlage, Aufschlag für besondere Netznutzung (Gruppe A') | netztransparenz.de |
| Stromsteuer, Konzessionsabgabe, Lieferantenaufschlag, Mehrwertsteuer | Konfiguration |

## Was die Integration macht

- **Ein Sensor je Bestandteil** mit den Attributen `gueltig_ab`, `quelle`, `abgerufen_am` und `vorlaeufig`. Ist schon ein künftiger Wert bekannt, stehen zusätzlich `naechster_wert` und `naechster_gueltig_ab` im Sensor.
- **Übernahme erst zum Stichtag.** Ein im Oktober veröffentlichtes Preisblatt für das Folgejahr wird gespeichert, aber erst am 1.1. wirksam.
- **Dauerhafte Benachrichtigung bei Änderung.** Sie nennt den alten und den neuen Wert, den Stichtag und verlinkt die Quelle.
- **Plausibilitätsgrenze (Standard ±30 %).** Weicht ein neu gelesener Wert stärker vom bisherigen ab, wird er nicht übernommen. Stattdessen erscheint eine Warnung. Ist der Wert richtig, übernimmst du ihn mit der Aktion `netzentgelte.wert_uebernehmen`.
- **Unlesbare Quelle.** Ist ein PDF oder eine Seite unlesbar, erscheint nur eine Warnung, und die bisherigen Werte bleiben unverändert.
- **Gesamtpreis-Sensoren „Standard“ und „Modul 3“** in €/kWh brutto. Liefert der EPEX-Sensor ein `data`-Attribut mit Prognosen, wird es je Zeitscheibe umgerechnet. Das Format ist kompatibel zur EPEX-Spot-Integration.

Gesamtpreis = (Börse + Netz-Arbeitspreis bzw. Modul-3-Stufe + Umlagen + Stromsteuer + Konzessionsabgabe + Lieferantenaufschlag) × (1 + MwSt).

Die Grundpreise (€/a) und die Modul-1-Pauschale stehen als eigene Sensoren bereit. In den Arbeitspreis werden sie nicht eingerechnet.

## Installation (HACS)

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/bggsolar/ha-netzentgelte`, Typ *Integration*.
2. „Netzentgelte & Umlagen“ installieren und Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Netzentgelte & Umlagen*.

## Einrichtung

| Feld | Standard | Hinweis |
|---|---|---|
| EPEX-Spot-Sensor | – | **Reiner Börsenpreis ohne Aufschläge.** Die Einheit wird erkannt (€/kWh, ct/kWh, €/MWh). Ohne Angabe entstehen keine Gesamtpreis-Sensoren. |
| Stromsteuer | 2,05 ct/kWh | Regelsatz |
| Konzessionsabgabe | 1,99 ct/kWh | KAV-Höchstsatz für Tarifkunden in Gemeinden mit 100.000–500.000 Einwohnern (Mainz) |
| Lieferantenaufschlag | 1,81 ct/kWh netto | z. B. Tibber 2,15 ct brutto |
| Mehrwertsteuer | 19 % | |
| Plausibilitätsgrenze | 30 % | |
| Übersichtsseite | mainzer-netze.de/strom/netzzugang/netzentgelte | Dort verlinkte `s_preisblatt_*.pdf` werden gelesen. |
| Preisblatt-URLs | leer | Optional, eine URL je Zeile. Ersetzt die Suche auf der Übersichtsseite. |

Alle Werte lassen sich später unter *Konfigurieren* ändern. Geänderte Konfigurationswerte gelten ab dem Tag der Änderung.

## Sensoren

`netz_arbeitspreis`, `netz_grundpreis`, `modul1_reduzierung`, `modul2_arbeitspreis`, `modul3_ht`, `modul3_st`, `modul3_nt`, `modul3_aktuell` (Attribut `stufe`), `kwkg_umlage`, `offshore_netzumlage`, `aufschlag_besondere_netznutzung`, `stromsteuer`, `konzessionsabgabe`, `lieferant_aufschlag`, `mwst`, `gesamtpreis_standard`, `gesamtpreis_modul3`.

Die Bestandteile werden in ct/kWh netto bzw. €/a netto angegeben, die Gesamtpreise in €/kWh brutto.

## Aktionen

- `netzentgelte.aktualisieren` ruft alle Quellen sofort ab (sonst alle 12 Stunden).
- `netzentgelte.wert_uebernehmen` übernimmt einen wegen der Plausibilitätsgrenze abgewiesenen Wert (`bestandteil`, `gueltig_ab`).

Weitere Details stehen in der [Kurzdoku](docs/KURZDOKU.md).

## Haftung

Die Werte werden automatisch aus öffentlichen Dokumenten gelesen. Verbindlich sind allein die Preisblätter des Netzbetreibers und die Veröffentlichungen der Übertragungsnetzbetreiber.
