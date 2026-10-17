"""Einrichtung und Optionen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EPEX_ENTITY,
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
)


def _ct(maximum: float = 50) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=maximum, step=0.001, unit_of_measurement="ct/kWh", mode=selector.NumberSelectorMode.BOX
        )
    )


def _prozent(maximum: float) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=maximum, step=0.1, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
        )
    )


def _schema(werte: dict[str, Any]) -> vol.Schema:
    epex = werte.get(CONF_EPEX_ENTITY)
    return vol.Schema(
        {
            vol.Optional(
                CONF_EPEX_ENTITY, **({"description": {"suggested_value": epex}} if epex else {})
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_STROMSTEUER, default=werte.get(CONF_STROMSTEUER, DEFAULT_STROMSTEUER)): _ct(),
            vol.Required(
                CONF_KONZESSIONSABGABE, default=werte.get(CONF_KONZESSIONSABGABE, DEFAULT_KONZESSIONSABGABE)
            ): _ct(),
            vol.Required(
                CONF_LIEFERANT_AUFSCHLAG, default=werte.get(CONF_LIEFERANT_AUFSCHLAG, DEFAULT_LIEFERANT_AUFSCHLAG)
            ): _ct(),
            vol.Required(CONF_MWST, default=werte.get(CONF_MWST, DEFAULT_MWST)): _prozent(30),
            vol.Required(
                CONF_PLAUSI_GRENZE, default=werte.get(CONF_PLAUSI_GRENZE, DEFAULT_PLAUSI_GRENZE)
            ): _prozent(500),
            vol.Required(
                CONF_PREISBLATT_SEITE, default=werte.get(CONF_PREISBLATT_SEITE, DEFAULT_PREISBLATT_SEITE)
            ): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.URL)),
            vol.Optional(
                CONF_PREISBLATT_URLS, default=werte.get(CONF_PREISBLATT_URLS, "")
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        }
    )


class NetzentgelteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung über die Oberfläche."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return NetzentgelteOptionsFlow()


class NetzentgelteOptionsFlow(OptionsFlow):
    """Werte nachträglich ändern."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input.setdefault(CONF_EPEX_ENTITY, "")
            user_input.setdefault(CONF_PREISBLATT_URLS, "")
            return self.async_create_entry(data=user_input)
        aktuell = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(aktuell))
