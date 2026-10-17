"""Coordinator: Quellen abrufen, Fahrplan pflegen, Benachrichtigungen erzeugen."""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Any

import aiohttp
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ALLE_BESTANDTEILE,
    CONF_KONZESSIONSABGABE,
    CONF_LIEFERANT_AUFSCHLAG,
    CONF_MWST,
    CONF_PLAUSI_GRENZE,
    CONF_PREISBLATT_SEITE,
    CONF_PREISBLATT_URLS,
    CONF_STROMSTEUER,
    DEFAULT_KONZESSIONSABGABE,
    DEFAULT_LIEFERANT_AUFSCHLAG,
    DEFAULT_MWST,
    DEFAULT_PLAUSI_GRENZE,
    DEFAULT_PREISBLATT_SEITE,
    DEFAULT_STROMSTEUER,
    DOMAIN,
    NAME,
    QUELLE_KONFIGURATION,
    STORAGE_VERSION,
    UMLAGE_URLS,
    UPDATE_INTERVAL,
)
from .fahrplan import Abweisung, Eintrag, Fahrplan, Wechsel
from .parsers.mainzer_netze import (
    PreisblattFehler,
    jahr_aus_url,
    parse_preisblatt,
    pdf_text,
    preisblatt_links,
)
from .parsers.netztransparenz import UmlageFehler, parse_umlage

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=60)

KONFIG_DEFAULTS = {
    CONF_STROMSTEUER: DEFAULT_STROMSTEUER,
    CONF_KONZESSIONSABGABE: DEFAULT_KONZESSIONSABGABE,
    CONF_LIEFERANT_AUFSCHLAG: DEFAULT_LIEFERANT_AUFSCHLAG,
    CONF_MWST: DEFAULT_MWST,
}


class NetzentgelteCoordinator(DataUpdateCoordinator[Fahrplan]):
    """Ruft Preisblätter und Umlagen ab und hält den Fahrplan."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.fahrplan = Fahrplan()
        self.fehler: dict[str, str] = {}

    @property
    def optionen(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def grenze(self) -> float:
        return float(self.optionen.get(CONF_PLAUSI_GRENZE, DEFAULT_PLAUSI_GRENZE))

    async def async_laden(self) -> None:
        self.fahrplan = Fahrplan.aus_dict(await self._store.async_load())

    async def _speichern(self) -> None:
        await self._store.async_save(self.fahrplan.als_dict())

    # ----------------------------------------------------------------- Abruf

    async def _async_update_data(self) -> Fahrplan:
        jetzt = dt_util.now()
        abgerufen = jetzt.isoformat(timespec="seconds")
        self._konfig_uebernehmen(abgerufen)
        kandidaten: list[Eintrag] = []
        kandidaten += await self._preisblatt_kandidaten(jetzt.year, abgerufen)
        kandidaten += await self._umlage_kandidaten(jetzt.year, abgerufen)

        for kandidat in kandidaten:
            abweisung = self.fahrplan.einpflegen(kandidat, self.grenze)
            if abweisung is not None and abweisung.neu:
                self._warnung_plausibilitaet(abweisung)

        self.stichtag_pruefen(jetzt.date())
        await self._speichern()
        return self.fahrplan

    def stichtag_pruefen(self, heute: date) -> None:
        """Wirksame Werte bestimmen und bei Wechsel benachrichtigen."""
        for wechsel in self.fahrplan.stichtag_anwenden(heute):
            self._benachrichtigung_wechsel(wechsel)

    async def async_stichtag(self, *_: Any) -> None:
        """Täglich nach Mitternacht: neue Werte ohne Abruf wirksam schalten."""
        self.stichtag_pruefen(dt_util.now().date())
        await self._speichern()
        self.async_update_listeners()

    def _konfig_uebernehmen(self, abgerufen: str) -> None:
        """Konfigurationswerte gelten sofort (Stichtag = Tag der Änderung), ohne Plausibilitätsgrenze."""
        heute = dt_util.now().date()
        for key, default in KONFIG_DEFAULTS.items():
            wert = float(self.optionen.get(key, default))
            vorher = self.fahrplan.wert_am(key, heute)
            if vorher is not None and vorher.wert == wert:
                continue
            gueltig_ab = heute if vorher is not None else date(2000, 1, 1)
            self.fahrplan.setzen(Eintrag(key, wert, gueltig_ab, QUELLE_KONFIGURATION, abgerufen))

    async def _abrufen(self, url: str, erlaube_404: bool = False) -> tuple[str, bytes] | None:
        """URL laden; liefert (End-URL, Inhalt) oder None bei 404 (wenn erlaubt)."""
        session = async_get_clientsession(self.hass)
        async with session.get(url, timeout=TIMEOUT, headers={"User-Agent": "HomeAssistant-netzentgelte"}) as antwort:
            if antwort.status == 404 and erlaube_404:
                return None
            if antwort.status >= 400:
                raise aiohttp.ClientError(f"HTTP {antwort.status}")
            return str(antwort.url), await antwort.read()

    async def _preisblatt_kandidaten(self, jahr: int, abgerufen: str) -> list[Eintrag]:
        urls = [u.strip() for u in str(self.optionen.get(CONF_PREISBLATT_URLS, "")).splitlines() if u.strip()]
        seite = self.optionen.get(CONF_PREISBLATT_SEITE, DEFAULT_PREISBLATT_SEITE)
        if not urls and seite:
            try:
                end_url, inhalt = await self._abrufen(seite)
                urls = preisblatt_links(inhalt.decode("utf-8", "replace"), end_url)
            except (aiohttp.ClientError, TimeoutError) as err:
                self._fehler("preisblatt_seite", f"Übersichtsseite {seite} nicht erreichbar: {err}")
                return []
            if not urls:
                self._fehler("preisblatt_seite", f"Keine Preisblatt-PDFs auf {seite} gefunden")
                return []
        self._fehler_ok("preisblatt_seite")

        kandidaten: list[Eintrag] = []
        for url in urls:
            url_jahr = jahr_aus_url(url)
            if url_jahr is not None and url_jahr < jahr - 1:
                continue
            try:
                _, daten = await self._abrufen(url)
                text = await self.hass.async_add_executor_job(pdf_text, daten)
                ergebnis = parse_preisblatt(text, url)
            except (aiohttp.ClientError, TimeoutError) as err:
                self._fehler(url, f"Preisblatt nicht abrufbar: {url} ({err})")
                continue
            except PreisblattFehler as err:
                self._warnung_unlesbar(url, str(err))
                continue
            except Exception as err:  # noqa: BLE001 - eine defekte Quelle darf die übrigen nicht blockieren
                self._fehler(url, f"Unerwarteter Fehler bei {url}: {err!r}")
                continue
            self._fehler_ok(url)
            kandidaten += [
                Eintrag(key, wert, ergebnis.gueltig_ab_fuer(key), url, abgerufen, ergebnis.vorlaeufig)
                for key, wert in ergebnis.werte.items()
            ]
        return kandidaten

    async def _umlage_kandidaten(self, jahr: int, abgerufen: str) -> list[Eintrag]:
        kandidaten: list[Eintrag] = []
        for key, muster in UMLAGE_URLS.items():
            for j in (jahr, jahr + 1):
                url = muster.format(jahr=j)
                try:
                    geladen = await self._abrufen(url, erlaube_404=True)
                    if geladen is None:
                        continue  # Folgejahr noch nicht veröffentlicht
                    wert = parse_umlage(key, geladen[1].decode("utf-8", "replace"), j)
                except (aiohttp.ClientError, TimeoutError) as err:
                    if j == jahr:
                        self._fehler(url, f"Umlageseite nicht abrufbar: {url} ({err})")
                    continue
                except UmlageFehler as err:
                    if j == jahr:
                        self._warnung_unlesbar(url, str(err))
                    continue
                except Exception as err:  # noqa: BLE001
                    self._fehler(url, f"Unerwarteter Fehler bei {url}: {err!r}")
                    continue
                self._fehler_ok(url)
                kandidaten.append(Eintrag(key, wert, date(j, 1, 1), url, abgerufen))
        return kandidaten

    # -------------------------------------------------------- Benachrichtigungen

    def _fehler(self, schluessel: str, text: str) -> None:
        _LOGGER.warning(text)
        self.fehler[schluessel] = text

    def _fehler_ok(self, schluessel: str) -> None:
        if self.fehler.pop(schluessel, None) is not None:
            persistent_notification.async_dismiss(self.hass, _unlesbar_id(schluessel))

    def _warnung_unlesbar(self, url: str, grund: str) -> None:
        self._fehler(url, f"Quelle nicht auswertbar: {url} ({grund})")
        persistent_notification.async_create(
            self.hass,
            f"Die Quelle konnte nicht ausgewertet werden, es wurden **keine Werte übernommen**.\n\n"
            f"Grund: {grund}\n\n[Quelle öffnen]({url})",
            title=f"{NAME}: Quelle unlesbar",
            notification_id=_unlesbar_id(url),
        )

    def _warnung_plausibilitaet(self, abweisung: Abweisung) -> None:
        k, r = abweisung.kandidat, abweisung.referenz
        einheit = ALLE_BESTANDTEILE[k.key].einheit or ""
        _LOGGER.warning(
            "%s: neuer Wert %s weicht %.1f %% von %s ab, nicht übernommen",
            k.key,
            k.wert,
            abweisung.abweichung_prozent,
            r.wert,
        )
        persistent_notification.async_create(
            self.hass,
            f"**{k.key}** ab {k.gueltig_ab:%d.%m.%Y}: gelesen {_fmt(k.wert)} {einheit}, "
            f"bisher {_fmt(r.wert)} {einheit} (Abweichung {abweisung.abweichung_prozent:+.1f} %, "
            f"Grenze ±{self.grenze:.0f} %).\n\n"
            f"Der Wert wurde **nicht übernommen**. Bitte an der Quelle prüfen. Ist er richtig, "
            f"mit der Aktion `{DOMAIN}.wert_uebernehmen` (bestandteil: `{k.key}`, "
            f"gueltig_ab: `{k.gueltig_ab.isoformat()}`) übernehmen.\n\n[Quelle öffnen]({k.quelle})",
            title=f"{NAME}: Wert unplausibel",
            notification_id=f"{DOMAIN}_plausi_{k.key}_{k.gueltig_ab.isoformat()}",
        )

    def _benachrichtigung_wechsel(self, wechsel: Wechsel) -> None:
        alt, neu = wechsel.alt, wechsel.neu
        einheit = ALLE_BESTANDTEILE.get(wechsel.key)
        einheit_text = f" {einheit.einheit}" if einheit and einheit.einheit else ""
        alt_text = f"{_fmt(alt.wert)}{einheit_text} (gültig ab {alt.gueltig_ab:%d.%m.%Y})" if alt else "–"
        quelle = f"[Quelle öffnen]({neu.quelle})" if neu.quelle.startswith("http") else f"Quelle: {neu.quelle}"
        persistent_notification.async_create(
            self.hass,
            f"**{wechsel.key}** hat sich geändert.\n\n"
            f"- alt: {alt_text}\n"
            f"- neu: {_fmt(neu.wert)}{einheit_text} (gültig ab {neu.gueltig_ab:%d.%m.%Y}"
            f"{', vorläufig' if neu.vorlaeufig else ''})\n\n{quelle}",
            title=f"{NAME}: Preisbestandteil geändert",
            notification_id=f"{DOMAIN}_wechsel_{wechsel.key}_{neu.gueltig_ab.isoformat()}",
        )

    # ------------------------------------------------------------- Aktionen

    async def async_wert_uebernehmen(self, key: str, gueltig_ab: date) -> bool:
        eintrag = self.fahrplan.uebernehmen(key, gueltig_ab)
        if eintrag is None:
            return False
        persistent_notification.async_dismiss(
            self.hass, f"{DOMAIN}_plausi_{key}_{gueltig_ab.isoformat()}"
        )
        self.stichtag_pruefen(dt_util.now().date())
        await self._speichern()
        self.async_update_listeners()
        return True

    def werte_am(self, stichtag: date) -> dict[str, Any]:
        """Alle wirksamen Werte zu einem Tag als dict key -> wert."""
        werte = {}
        for key in self.fahrplan.eintraege:
            if eintrag := self.fahrplan.wert_am(key, stichtag):
                werte[key] = eintrag.wert
        return werte


def _unlesbar_id(url: str) -> str:
    return f"{DOMAIN}_unlesbar_{hashlib.sha1(url.encode()).hexdigest()[:10]}"


def _fmt(wert: Any) -> str:
    if isinstance(wert, float):
        return f"{wert:.3f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(wert)
