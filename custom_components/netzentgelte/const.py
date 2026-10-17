"""Konstanten der Integration Netzentgelte & Umlagen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final

DOMAIN: Final = "netzentgelte"
NAME: Final = "Netzentgelte & Umlagen"

STORAGE_VERSION: Final = 1
UPDATE_INTERVAL: Final = timedelta(hours=12)

# Konfiguration
CONF_EPEX_ENTITY: Final = "epex_entity"
CONF_PREISBLATT_SEITE: Final = "preisblatt_seite"
CONF_PREISBLATT_URLS: Final = "preisblatt_urls"
CONF_STROMSTEUER: Final = "stromsteuer"
CONF_KONZESSIONSABGABE: Final = "konzessionsabgabe"
CONF_MWST: Final = "mwst"
CONF_LIEFERANT_AUFSCHLAG: Final = "lieferant_aufschlag"
CONF_PLAUSI_GRENZE: Final = "plausi_grenze"

DEFAULT_PREISBLATT_SEITE: Final = "https://www.mainzer-netze.de/strom/netzzugang/netzentgelte"
DEFAULT_STROMSTEUER: Final = 2.05  # ct/kWh netto, Regelsatz § 3 StromStG
DEFAULT_KONZESSIONSABGABE: Final = 1.99  # ct/kWh, KAV-Höchstsatz Tarifkunden 100.000–500.000 EW
DEFAULT_MWST: Final = 19.0  # %
DEFAULT_LIEFERANT_AUFSCHLAG: Final = 1.81  # ct/kWh netto (Tibber 2,15 brutto)
DEFAULT_PLAUSI_GRENZE: Final = 30.0  # %

NETZTRANSPARENZ_BASIS: Final = "https://www.netztransparenz.de/de-de/Erneuerbare-Energien-und-Umlagen"
UMLAGE_URLS: Final = {
    "kwkg_umlage": NETZTRANSPARENZ_BASIS
    + "/KWKG/KWKG-Umlage/KWKG-Umlagen-Übersicht/KWKG-Umlage-{jahr}",
    "offshore_netzumlage": NETZTRANSPARENZ_BASIS
    + "/Sonstige-Umlagen/Offshore-Netzumlage/Offshore-Netzumlagen-Übersicht/Offshore-Netzumlage-{jahr}",
    "aufschlag_besondere_netznutzung": NETZTRANSPARENZ_BASIS
    + "/Sonstige-Umlagen/Aufschlag-für-besondere-Netznutzung-19-StromNEV-Umlage"
    + "/Übersicht-Aufschlag-für-besondere-Netznutzung/Aufschlag-für-besondere-Netznutzung-{jahr}",
}

QUELLE_KONFIGURATION: Final = "Konfiguration der Integration"

EINHEIT_CT_KWH: Final = "ct/kWh"
EINHEIT_EUR_A: Final = "€/a"
EINHEIT_EUR_KWH: Final = "€/kWh"
EINHEIT_PROZENT: Final = "%"


@dataclass(frozen=True)
class Bestandteil:
    """Beschreibung eines Preisbestandteils."""

    key: str
    einheit: str | None
    numerisch: bool = True


# Bestandteile aus dem Preisblatt des Netzbetreibers
NETZ_BESTANDTEILE: Final = (
    Bestandteil("netz_arbeitspreis", EINHEIT_CT_KWH),
    Bestandteil("netz_grundpreis", EINHEIT_EUR_A),
    Bestandteil("modul1_reduzierung", EINHEIT_EUR_A),
    Bestandteil("modul2_arbeitspreis", EINHEIT_CT_KWH),
    Bestandteil("modul3_ht", EINHEIT_CT_KWH),
    Bestandteil("modul3_st", EINHEIT_CT_KWH),
    Bestandteil("modul3_nt", EINHEIT_CT_KWH),
    Bestandteil("modul3_ht_zeitfenster", None, numerisch=False),
    Bestandteil("modul3_nt_zeitfenster", None, numerisch=False),
    Bestandteil("modul3_quartale", None, numerisch=False),
)

# Bestandteile von netztransparenz.de
UMLAGE_BESTANDTEILE: Final = tuple(Bestandteil(k, EINHEIT_CT_KWH) for k in UMLAGE_URLS)

# Bestandteile aus der Konfiguration
KONFIG_BESTANDTEILE: Final = (
    Bestandteil(CONF_STROMSTEUER, EINHEIT_CT_KWH),
    Bestandteil(CONF_KONZESSIONSABGABE, EINHEIT_CT_KWH),
    Bestandteil(CONF_LIEFERANT_AUFSCHLAG, EINHEIT_CT_KWH),
    Bestandteil(CONF_MWST, EINHEIT_PROZENT),
)

ALLE_BESTANDTEILE: Final = {b.key: b for b in NETZ_BESTANDTEILE + UMLAGE_BESTANDTEILE + KONFIG_BESTANDTEILE}

ATTR_GUELTIG_AB: Final = "gueltig_ab"
ATTR_QUELLE: Final = "quelle"
ATTR_ABGERUFEN_AM: Final = "abgerufen_am"
ATTR_VORLAEUFIG: Final = "vorlaeufig"
ATTR_NAECHSTER_WERT: Final = "naechster_wert"
ATTR_NAECHSTER_GUELTIG_AB: Final = "naechster_gueltig_ab"

SERVICE_AKTUALISIEREN: Final = "aktualisieren"
SERVICE_WERT_UEBERNEHMEN: Final = "wert_uebernehmen"
