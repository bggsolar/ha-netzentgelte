# Kurzdoku: Netzentgelte & Umlagen

Betriebs- und Admin-Notizen zur Integration `netzentgelte`. Bedienung und Installation stehen in der [README](../README.md).

## Aufbau

| Datei | Aufgabe |
|---|---|
| `custom_components/netzentgelte/parsers/mainzer_netze.py` | Liest die PDF-Preisblätter mit `pypdf`, findet die Links auf der Übersichtsseite und liest Werte, Zeitfenster, Quartale, Stichtag und das Kennzeichen „vorläufig“. |
| `parsers/netztransparenz.py` | Liest die Jahresseiten der drei Umlagen (`…/KWKG-Umlage-JJJJ` usw.). |
| `fahrplan.py` | Speichert alle Werte je Bestandteil mit Stichtag. Er prüft die Plausibilität, liefert den wirksamen Wert und meldet Wechsel. Reines Python. |
| `preis.py` | Bestimmt die Modul-3-Stufe zu einem Zeitpunkt und berechnet den Gesamtpreis. Reines Python. |
| `coordinator.py` | Ruft die Quellen ab (alle 12 h und über die Aktion `aktualisieren`), pflegt den Fahrplan und erzeugt die Benachrichtigungen. |
| `sensor.py` | Stellt die Sensoren bereit. Die Modul-3- und Gesamtpreis-Sensoren aktualisieren sich jede Viertelstunde und bei jeder Änderung des EPEX-Sensors. |

## Ablauf je Abruf

1. Konfigurationswerte (Stromsteuer, Konzessionsabgabe, Lieferantenaufschlag, MwSt) werden ohne Plausibilitätsprüfung übernommen und gelten ab dem Tag der Änderung.
2. Die Übersichtsseite wird gelesen. Sie liefert die Links `s_preisblatt_*.pdf`, Preisblätter älter als das Vorjahr werden übersprungen. Danach wird jedes PDF geladen und ausgewertet.
3. Für das laufende Jahr und das Folgejahr werden die Umlageseiten abgerufen. Eine 404 für das Folgejahr ist normal, denn die ÜNB veröffentlichen bis zum 25.10.
4. Jeder gelesene Wert wird in den Fahrplan eingepflegt:
   - Gibt es denselben Wert zum selben Stichtag schon, werden nur die Metadaten aktualisiert, etwa vorläufig → endgültig.
   - Weicht der Wert mehr als die Grenze vom Referenzwert ab, wird er abgewiesen und eine Warnung angelegt. Referenz ist der Wert, der zu diesem Stichtag sonst gälte.
   - Sonst wird der Wert gespeichert.
5. Stichtagsprüfung: Hat sich ein wirksamer Wert geändert, wird eine dauerhafte Benachrichtigung angelegt. Diese Prüfung läuft außerdem täglich um 00:00:30 ohne Abruf.

Beim allerersten Lauf gibt es keine Wechselmeldungen, nur die Ausgangswerte.

## Speicherung, Backup, Restore

- Den Fahrplan speichert Home Assistant unter `/config/.storage/netzentgelte.<entry_id>`. Er enthält alle bekannten Werte, die wirksamen Werte und die abgewiesenen Kandidaten.
- Der Code liegt unter `/config/custom_components/netzentgelte/`.
- Beides ist Teil des normalen HAOS-Backups. Nach einem Restore gelten die gespeicherten Werte sofort, auch wenn eine Quelle nicht erreichbar ist.
- Geht der Speicher verloren, baut der nächste Abruf ihn neu auf. Werte, die nicht mehr online stehen (z. B. alte Preisblätter), fehlen dann.

## Benachrichtigungen

| Titel | ID | Bedeutung |
|---|---|---|
| Preisbestandteil geändert | `netzentgelte_wechsel_<key>_<datum>` | Ein neuer Wert ist wirksam. Die Meldung nennt den alten und den neuen Wert und verlinkt die Quelle. |
| Wert unplausibel | `netzentgelte_plausi_<key>_<datum>` | Der Wert wurde nicht übernommen. Nach Prüfung an der Quelle mit `netzentgelte.wert_uebernehmen` übernehmen. |
| Quelle unlesbar | `netzentgelte_unlesbar_<hash>` | Ein PDF oder eine Seite ist nicht auswertbar, die Werte bleiben unverändert. Die Meldung verschwindet automatisch, sobald die Quelle wieder lesbar ist. |

Nicht erreichbare Quellen (Netzwerk, HTTP-Fehler) erzeugen nur einen Logeintrag mit dem Logger `custom_components.netzentgelte`.

## Bekannte Grenzen

- **±30 % ist für einzelne Bestandteile knapp.** Die Umlagen schwanken von Jahr zu Jahr stark (KWKG 2025 → 2026: +61 %), ebenso Modul 3 HT (2026 → 2027: +40 %). Solche Werte landen als Warnung und müssen einmal bestätigt werden. Wer das nicht möchte, setzt die Grenze höher.
- Der PDF-Parser ist auf den Aufbau der Mainzer-Netze-Preisblätter zugeschnitten. Ändert der Netzbetreiber das Layout, erscheint „Quelle unlesbar“. Abhilfe: neues PDF unter `tests/fixtures/preisblaetter/` ablegen, Erwartungswerte in `erwartet.json` eintragen und den Parser anpassen.
- Die Konzessionsabgabe ist fest konfiguriert. Für Schwachlast-/Nachtstrom gelten nach KAV niedrigere Sätze, und ob ein Lieferant sie bei Modul 3 NT anwendet, ist nicht geklärt.
- Modul 2 wird nur gelesen und nicht in einen Gesamtpreis eingerechnet.

## Update und Rollback

- Updates kommen über HACS. Vor einem Update im Changelog bzw. Release prüfen, ob sich Sensor-Schlüssel oder Einheiten ändern.
- Rollback: in HACS *Neu herunterladen* mit der vorigen Version und Home Assistant neu starten. Der Speicherstand bleibt kompatibel, solange `STORAGE_VERSION` gleich bleibt.
- Nach jedem Update prüfen: Sensoren vorhanden, `abgerufen_am` aktuell, keine neue Meldung „Quelle unlesbar“.

## Tests

```bash
pip install -r requirements_test.txt
pytest -q
```

Die Tests laufen gegen die Preisblätter in `tests/fixtures/preisblaetter/`, und zwar für jede dort vorhandene Datei, die in `erwartet.json` steht. Die Dateien `synthetisch_*` sind nachgebaut und ersetzen die Originale nicht. Die Originale der Mainzer Netze (`s_preisblatt_JJJJ.pdf`) gehören daneben.
