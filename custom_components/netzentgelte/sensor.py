"""Sensoren je Preisbestandteil und Gesamtpreis-Sensoren."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ALLE_BESTANDTEILE,
    ATTR_ABGERUFEN_AM,
    ATTR_GUELTIG_AB,
    ATTR_NAECHSTER_GUELTIG_AB,
    ATTR_NAECHSTER_WERT,
    ATTR_QUELLE,
    ATTR_VORLAEUFIG,
    CONF_EPEX_ENTITY,
    DOMAIN,
    EINHEIT_CT_KWH,
    EINHEIT_EUR_KWH,
    NAME,
)
from .coordinator import NetzentgelteCoordinator
from .preis import MODUL3, STANDARD, boersenpreis_ct_kwh, gesamtpreis, modul3_netzpreis, modul3_stufe

ZUSATZ_ATTRIBUTE = {
    "modul3_ht": ("modul3_ht_zeitfenster", "modul3_quartale"),
    "modul3_nt": ("modul3_nt_zeitfenster", "modul3_quartale"),
    "modul3_st": ("modul3_quartale",),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator: NetzentgelteCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        BestandteilSensor(coordinator, b.key) for b in ALLE_BESTANDTEILE.values() if b.numerisch
    ]
    entities.append(Modul3AktuellSensor(coordinator))
    if coordinator.optionen.get(CONF_EPEX_ENTITY):
        entities += [GesamtpreisSensor(coordinator, STANDARD), GesamtpreisSensor(coordinator, MODUL3)]
    async_add_entities(entities)


class NetzentgelteEntity(CoordinatorEntity[NetzentgelteCoordinator]):
    """Gemeinsame Basis."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NetzentgelteCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=NAME,
            manufacturer="Mainzer Netze / netztransparenz.de",
            entry_type=DeviceEntryType.SERVICE,
        )


class BestandteilSensor(NetzentgelteEntity, SensorEntity):
    """Ein Preisbestandteil mit Gültigkeit und Quelle."""

    def __init__(self, coordinator: NetzentgelteCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._key = key
        self._attr_native_unit_of_measurement = ALLE_BESTANDTEILE[key].einheit
        self._attr_suggested_display_precision = 3 if self._attr_native_unit_of_measurement == EINHEIT_CT_KWH else 2

    @property
    def native_value(self) -> float | None:
        eintrag = self.coordinator.fahrplan.wert_am(self._key, dt_util.now().date())
        return eintrag.wert if eintrag else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        heute = dt_util.now().date()
        fahrplan = self.coordinator.fahrplan
        attribute: dict[str, Any] = {}
        if eintrag := fahrplan.wert_am(self._key, heute):
            attribute = {
                ATTR_GUELTIG_AB: eintrag.gueltig_ab.isoformat(),
                ATTR_QUELLE: eintrag.quelle,
                ATTR_ABGERUFEN_AM: eintrag.abgerufen_am,
                ATTR_VORLAEUFIG: eintrag.vorlaeufig,
            }
        if naechster := fahrplan.naechster(self._key, heute):
            attribute[ATTR_NAECHSTER_WERT] = naechster.wert
            attribute[ATTR_NAECHSTER_GUELTIG_AB] = naechster.gueltig_ab.isoformat()
        for zusatz in ZUSATZ_ATTRIBUTE.get(self._key, ()):
            if z := fahrplan.wert_am(zusatz, heute):
                attribute[zusatz] = z.wert
        return attribute


class _ZeitabhaengigerSensor(NetzentgelteEntity, SensorEntity):
    """Aktualisiert sich zur Viertelstunde (Modul-3-Fenster beginnen auf :00/:15/:30/:45)."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._zeit_tick, minute=(0, 15, 30, 45), second=1)
        )

    @callback
    def _zeit_tick(self, _: datetime) -> None:
        self.async_write_ha_state()


class Modul3AktuellSensor(_ZeitabhaengigerSensor):
    """Aktuell gültiger Netz-Arbeitspreis nach § 14a Modul 3."""

    _attr_native_unit_of_measurement = EINHEIT_CT_KWH
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: NetzentgelteCoordinator) -> None:
        super().__init__(coordinator, "modul3_aktuell")

    @property
    def native_value(self) -> float | None:
        jetzt = dt_util.now()
        return modul3_netzpreis(jetzt, self.coordinator.werte_am(jetzt.date()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        jetzt = dt_util.now()
        werte = self.coordinator.werte_am(jetzt.date())
        return {
            "stufe": modul3_stufe(jetzt, werte),
            "modul3_ht_zeitfenster": werte.get("modul3_ht_zeitfenster"),
            "modul3_nt_zeitfenster": werte.get("modul3_nt_zeitfenster"),
            "modul3_quartale": werte.get("modul3_quartale"),
        }


class GesamtpreisSensor(_ZeitabhaengigerSensor):
    """Brutto-Gesamtpreis auf Basis des EPEX-Spot-Börsenpreises."""

    _attr_native_unit_of_measurement = EINHEIT_EUR_KWH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4
    _unrecorded_attributes = frozenset({"data", "bestandteile"})

    def __init__(self, coordinator: NetzentgelteCoordinator, variante: str) -> None:
        super().__init__(coordinator, f"gesamtpreis_{variante}")
        self._variante = variante
        self._epex = coordinator.optionen[CONF_EPEX_ENTITY]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_state_change_event(self.hass, [self._epex], self._epex_geaendert))

    @callback
    def _epex_geaendert(self, _: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    def _boerse(self) -> tuple[float, str | None] | None:
        state = self.hass.states.get(self._epex)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            wert = float(state.state)
        except ValueError:
            return None
        einheit = state.attributes.get("unit_of_measurement")
        return boersenpreis_ct_kwh(wert, einheit), einheit

    @property
    def available(self) -> bool:
        return super().available and self._boerse() is not None

    @property
    def native_value(self) -> float | None:
        boerse = self._boerse()
        if boerse is None:
            return None
        jetzt = dt_util.now()
        ergebnis = gesamtpreis(boerse[0], jetzt, self.coordinator.werte_am(jetzt.date()), self._variante)
        return ergebnis.brutto_eur_kwh if ergebnis else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        boerse = self._boerse()
        if boerse is None:
            return {}
        jetzt = dt_util.now()
        werte = self.coordinator.werte_am(jetzt.date())
        ergebnis = gesamtpreis(boerse[0], jetzt, werte, self._variante)
        attribute: dict[str, Any] = {
            "boersenpreis_ct_kwh": round(boerse[0], 4),
            "quelle_boersenpreis": self._epex,
            "bestandteile": {k: v for k, v in werte.items() if isinstance(v, (int, float))},
        }
        if ergebnis:
            attribute["netto_ct_kwh"] = ergebnis.netto_ct_kwh
            attribute["netzpreis_ct_kwh"] = ergebnis.netzpreis_ct_kwh
            if ergebnis.stufe:
                attribute["stufe"] = ergebnis.stufe
        if prognose := self._prognose(boerse[1]):
            attribute["data"] = prognose
        return attribute

    def _prognose(self, einheit: str | None) -> list[dict[str, Any]]:
        """Preis je Zeitscheibe aus dem `data`-Attribut der EPEX-Spot-Integration."""
        state = self.hass.states.get(self._epex)
        daten = state.attributes.get("data") if state else None
        if not isinstance(daten, list):
            return []
        prognose = []
        for slot in daten:
            start = dt_util.parse_datetime(str(slot.get("start_time", "")))
            if start is None:
                continue
            if "price_ct_per_kwh" in slot:
                boerse = float(slot["price_ct_per_kwh"])
            elif "price_eur_per_mwh" in slot:
                boerse = float(slot["price_eur_per_mwh"]) / 10
            elif "price_per_kwh" in slot:
                boerse = boersenpreis_ct_kwh(float(slot["price_per_kwh"]), einheit)
            else:
                continue
            lokal = dt_util.as_local(start)
            ergebnis = gesamtpreis(boerse, lokal, self.coordinator.werte_am(lokal.date()), self._variante)
            if ergebnis is None:
                continue
            eintrag = {
                "start_time": slot.get("start_time"),
                "end_time": slot.get("end_time"),
                "price_per_kwh": ergebnis.brutto_eur_kwh,
            }
            if ergebnis.stufe:
                eintrag["stufe"] = ergebnis.stufe
            prognose.append(eintrag)
        return prognose
