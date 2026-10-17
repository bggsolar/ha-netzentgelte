"""Netzentgelte & Umlagen: Strompreisbestandteile für Home Assistant."""

from __future__ import annotations

from datetime import date

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .const import ALLE_BESTANDTEILE, DOMAIN, SERVICE_AKTUALISIEREN, SERVICE_WERT_UEBERNEHMEN
from .coordinator import NetzentgelteCoordinator

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type NetzentgelteConfigEntry = ConfigEntry[NetzentgelteCoordinator]

SCHEMA_UEBERNEHMEN = vol.Schema(
    {
        vol.Required("bestandteil"): vol.In(sorted(ALLE_BESTANDTEILE)),
        vol.Required("gueltig_ab"): cv.date,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Aktionen registrieren."""

    def _coordinators() -> list[NetzentgelteCoordinator]:
        return [
            entry.runtime_data
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        ]

    async def aktualisieren(_: ServiceCall) -> None:
        for coordinator in _coordinators():
            await coordinator.async_refresh()

    async def wert_uebernehmen(call: ServiceCall) -> None:
        key: str = call.data["bestandteil"]
        gueltig_ab: date = call.data["gueltig_ab"]
        if not any([await c.async_wert_uebernehmen(key, gueltig_ab) for c in _coordinators()]):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="kein_abgewiesener_wert",
                translation_placeholders={"bestandteil": key, "gueltig_ab": gueltig_ab.isoformat()},
            )

    hass.services.async_register(DOMAIN, SERVICE_AKTUALISIEREN, aktualisieren)
    hass.services.async_register(DOMAIN, SERVICE_WERT_UEBERNEHMEN, wert_uebernehmen, schema=SCHEMA_UEBERNEHMEN)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NetzentgelteConfigEntry) -> bool:
    coordinator = NetzentgelteCoordinator(hass, entry)
    await coordinator.async_laden()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(async_track_time_change(hass, coordinator.async_stichtag, hour=0, minute=0, second=30))
    entry.async_on_unload(entry.add_update_listener(_optionen_geaendert))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _optionen_geaendert(hass: HomeAssistant, entry: NetzentgelteConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NetzentgelteConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
