"""Fahrplan der Preisbestandteile: Werte mit Stichtag, Plausibilitätsprüfung, Wechsel.

Reines Python ohne Home-Assistant-Abhängigkeit, damit es direkt testbar ist.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class Eintrag:
    """Ein Wert eines Bestandteils mit Gültigkeitsbeginn."""

    key: str
    wert: Any
    gueltig_ab: date
    quelle: str
    abgerufen_am: str
    vorlaeufig: bool = False

    def als_dict(self) -> dict[str, Any]:
        daten = asdict(self)
        daten["gueltig_ab"] = self.gueltig_ab.isoformat()
        return daten

    @classmethod
    def aus_dict(cls, daten: dict[str, Any]) -> Eintrag:
        return cls(
            key=daten["key"],
            wert=daten["wert"],
            gueltig_ab=date.fromisoformat(daten["gueltig_ab"]),
            quelle=daten["quelle"],
            abgerufen_am=daten["abgerufen_am"],
            vorlaeufig=daten.get("vorlaeufig", False),
        )


@dataclass
class Wechsel:
    """Ein Wechsel des wirksamen Werts zum Stichtag."""

    key: str
    alt: Eintrag | None
    neu: Eintrag


@dataclass
class Abweisung:
    """Ein Kandidat, der nicht übernommen wurde."""

    kandidat: Eintrag
    referenz: Eintrag
    abweichung_prozent: float
    neu: bool = True


@dataclass
class Fahrplan:
    """Alle bekannten Werte je Bestandteil, sortiert nach Stichtag."""

    eintraege: dict[str, list[Eintrag]] = field(default_factory=dict)
    wirksam: dict[str, Eintrag] = field(default_factory=dict)
    abgewiesen: list[Eintrag] = field(default_factory=list)

    # ------------------------------------------------------------------ Abfragen

    def wert_am(self, key: str, stichtag: date) -> Eintrag | None:
        """Letzter Eintrag, dessen gueltig_ab <= stichtag ist."""
        passend = [e for e in self.eintraege.get(key, []) if e.gueltig_ab <= stichtag]
        return passend[-1] if passend else None

    def naechster(self, key: str, stichtag: date) -> Eintrag | None:
        """Erster Eintrag mit gueltig_ab > stichtag (angekündigter Wert)."""
        for eintrag in self.eintraege.get(key, []):
            if eintrag.gueltig_ab > stichtag:
                return eintrag
        return None

    # ---------------------------------------------------------------- Änderungen

    def einpflegen(self, kandidat: Eintrag, grenze_prozent: float) -> Abweisung | None:
        """Kandidaten übernehmen oder bei zu großer Abweichung abweisen.

        Referenz für die Plausibilität ist der Wert, der am Stichtag des
        Kandidaten sonst gelten würde (gleicher Stichtag oder Vorgänger).
        """
        liste = self.eintraege.setdefault(kandidat.key, [])
        gleich = next((e for e in liste if e.gueltig_ab == kandidat.gueltig_ab), None)

        if gleich is not None and gleich.wert == kandidat.wert:
            # Nur Metadaten aktualisieren (z. B. vorläufig -> endgültig)
            gleich.vorlaeufig = kandidat.vorlaeufig
            gleich.quelle = kandidat.quelle
            gleich.abgerufen_am = kandidat.abgerufen_am
            return None

        referenz = gleich or self.wert_am(kandidat.key, kandidat.gueltig_ab)
        if referenz is not None:
            abweichung = abweichung_prozent(referenz.wert, kandidat.wert)
            if abweichung is not None and abs(abweichung) > grenze_prozent:
                bekannt = any(_gleicher_kandidat(a, kandidat) for a in self.abgewiesen)
                if not bekannt:
                    self.abgewiesen = [
                        a for a in self.abgewiesen if not _gleicher_stichtag(a, kandidat)
                    ]
                    self.abgewiesen.append(kandidat)
                return Abweisung(kandidat, referenz, abweichung, neu=not bekannt)

        self.setzen(kandidat)
        return None

    def uebernehmen(self, key: str, gueltig_ab: date) -> Eintrag | None:
        """Einen abgewiesenen Kandidaten ohne Plausibilitätsprüfung übernehmen."""
        for kandidat in self.abgewiesen:
            if kandidat.key == key and kandidat.gueltig_ab == gueltig_ab:
                self.abgewiesen.remove(kandidat)
                self.setzen(kandidat)
                return kandidat
        return None

    def setzen(self, eintrag: Eintrag) -> None:
        liste = [e for e in self.eintraege.get(eintrag.key, []) if e.gueltig_ab != eintrag.gueltig_ab]
        liste.append(eintrag)
        liste.sort(key=lambda e: e.gueltig_ab)
        self.eintraege[eintrag.key] = liste
        self.abgewiesen = [a for a in self.abgewiesen if not _gleicher_stichtag(a, eintrag)]

    def stichtag_anwenden(self, heute: date) -> list[Wechsel]:
        """Wirksame Werte für heute bestimmen und Wechsel melden.

        Beim allerersten Lauf (noch kein wirksamer Wert) wird nichts gemeldet.
        """
        wechsel: list[Wechsel] = []
        for key in self.eintraege:
            aktuell = self.wert_am(key, heute)
            if aktuell is None:
                continue
            vorher = self.wirksam.get(key)
            if vorher is not None and vorher.wert != aktuell.wert:
                wechsel.append(Wechsel(key, vorher, aktuell))
            self.wirksam[key] = aktuell
        return wechsel

    # ------------------------------------------------------------- Speicherung

    def als_dict(self) -> dict[str, Any]:
        return {
            "eintraege": {k: [e.als_dict() for e in v] for k, v in self.eintraege.items()},
            "wirksam": {k: e.als_dict() for k, e in self.wirksam.items()},
            "abgewiesen": [e.als_dict() for e in self.abgewiesen],
        }

    @classmethod
    def aus_dict(cls, daten: dict[str, Any] | None) -> Fahrplan:
        if not daten:
            return cls()
        return cls(
            eintraege={
                k: [Eintrag.aus_dict(e) for e in v] for k, v in daten.get("eintraege", {}).items()
            },
            wirksam={k: Eintrag.aus_dict(e) for k, e in daten.get("wirksam", {}).items()},
            abgewiesen=[Eintrag.aus_dict(e) for e in daten.get("abgewiesen", [])],
        )


def abweichung_prozent(alt: Any, neu: Any) -> float | None:
    """Relative Abweichung in Prozent; None, wenn nicht sinnvoll berechenbar."""
    if not isinstance(alt, (int, float)) or not isinstance(neu, (int, float)):
        return None
    if alt == 0:
        return None
    return (neu - alt) / abs(alt) * 100


def _gleicher_stichtag(a: Eintrag, b: Eintrag) -> bool:
    return a.key == b.key and a.gueltig_ab == b.gueltig_ab


def _gleicher_kandidat(a: Eintrag, b: Eintrag) -> bool:
    return _gleicher_stichtag(a, b) and a.wert == b.wert
