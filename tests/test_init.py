"""Integrationstests mit Home Assistant: Einrichtung, Sensoren, Stichtag, Meldungen."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.netzentgelte.const import (
    CONF_EPEX_ENTITY,
    DEFAULT_PREISBLATT_SEITE,
    DOMAIN,
    UMLAGE_URLS,
)

from .conftest import fixture_bytes

BERLIN = ZoneInfo("Europe/Berlin")
PDF_2026 = "https://www.mainzer-netze.de/-/media/strom/s_preisblatt_2026.pdf?rev=a"
PDF_2027 = "https://www.mainzer-netze.de/-/media/strom/s_preisblatt_2027_vorlaeufig.pdf?rev=b"
EPEX = "sensor.epex_spot_data_net_price"
NOTIFY = "custom_components.netzentgelte.coordinator.persistent_notification.async_create"


def zustand(hass: HomeAssistant, key: str):
    """Zustand über die unique_id finden (Entity-IDs hängen von der Sprache ab)."""
    registry = er.async_get(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
    return hass.states.get(entity_id)


def quellen_mocken(aioclient_mock: AiohttpClientMocker, pdf_2026: bytes | None = None) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        DEFAULT_PREISBLATT_SEITE,
        text=f'<a href="{PDF_2026.replace("&", "&amp;")}">2026</a><a href="{PDF_2027}">2027</a>',
    )
    aioclient_mock.get(
        PDF_2026, content=pdf_2026 or fixture_bytes("preisblaetter", "synthetisch_s_preisblatt_2026.pdf")
    )
    aioclient_mock.get(PDF_2027, content=fixture_bytes("preisblaetter", "synthetisch_s_preisblatt_2027_vorlaeufig.pdf"))
    dateien = {"kwkg_umlage": "kwkg_2026.html", "offshore_netzumlage": "offshore_2026.html",
               "aufschlag_besondere_netznutzung": "aufschlag_2026.html"}
    for key, muster in UMLAGE_URLS.items():
        aioclient_mock.get(muster.format(jahr=2026), text=fixture_bytes("netztransparenz", dateien[key]).decode())
        aioclient_mock.get(muster.format(jahr=2027), status=404)


@pytest.fixture
async def eingerichtet(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer):
    await hass.config.async_set_time_zone("Europe/Berlin")
    freezer.move_to(datetime(2026, 10, 17, 12, 0, tzinfo=BERLIN))
    quellen_mocken(aioclient_mock)
    hass.states.async_set(EPEX, "0.10", {"unit_of_measurement": "€/kWh", "data": [
        {"start_time": "2026-10-17T23:00:00+02:00", "end_time": "2026-10-17T23:15:00+02:00", "price_per_kwh": 0.08},
    ]})
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_EPEX_ENTITY: EPEX}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    with patch(NOTIFY) as notify:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, notify


async def test_config_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.netzentgelte.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_EPEX_ENTITY: EPEX})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["stromsteuer"] == 2.05


async def test_sensoren_nach_einrichtung(hass: HomeAssistant, eingerichtet) -> None:
    _, notify = eingerichtet
    ap = zustand(hass, "netz_arbeitspreis")
    assert ap.state == "6.72"
    assert ap.attributes["gueltig_ab"] == "2026-01-01"
    assert ap.attributes["quelle"] == PDF_2026
    assert ap.attributes["abgerufen_am"].startswith("2026-10-17T12:00")
    assert ap.attributes["naechster_wert"] == 6.11
    assert ap.attributes["naechster_gueltig_ab"] == "2027-01-01"

    assert zustand(hass, "kwkg_umlage").state == "0.446"
    assert zustand(hass, "stromsteuer").attributes["quelle"] == (
        "Konfiguration der Integration"
    )
    ht = zustand(hass, "modul3_ht")
    assert ht.attributes["modul3_ht_zeitfenster"] == "16:45-20:00"

    # Börse 10 ct + 15,516 ct Aufschläge, × 1,19
    standard = zustand(hass, "gesamtpreis_standard")
    assert float(standard.state) == pytest.approx(0.30364, abs=1e-5)
    m3 = zustand(hass, "gesamtpreis_modul3")
    assert m3.attributes["stufe"] == "ST"
    assert m3.attributes["data"][0]["stufe"] == "NT"
    assert m3.attributes["data"][0]["price_per_kwh"] == pytest.approx((8 + 15.516 - 5.71) * 1.19 / 100, abs=1e-5)

    # Erster Lauf: keine Wechselmeldung, aber Warnung für Modul-3-HT 2027 (+39,9 %)
    titel = [c.kwargs["title"] for c in notify.call_args_list]
    assert titel == ["Netzentgelte & Umlagen: Wert unplausibel"]
    assert "modul3_ht" in notify.call_args.args[1]


async def test_stichtag_meldet_wechsel(hass: HomeAssistant, eingerichtet, freezer) -> None:
    entry, _ = eingerichtet
    freezer.move_to(datetime(2027, 1, 1, 0, 0, 30, tzinfo=BERLIN))
    with patch(NOTIFY) as notify:
        await entry.runtime_data.async_stichtag()
        await hass.async_block_till_done()

    assert zustand(hass, "netz_arbeitspreis").state == "6.11"
    # HT 2027 wurde abgewiesen -> bleibt 7,86
    assert zustand(hass, "modul3_ht").state == "7.86"
    ids = {c.kwargs["notification_id"] for c in notify.call_args_list}
    assert "netzentgelte_wechsel_netz_arbeitspreis_2027-01-01" in ids
    assert "netzentgelte_wechsel_netz_grundpreis_2027-01-01" in ids
    assert not any("modul3_ht_2027" in i for i in ids)
    text = next(c.args[1] for c in notify.call_args_list if "netz_arbeitspreis" in c.kwargs["notification_id"])
    assert "alt: 6,72 ct/kWh" in text and "neu: 6,11 ct/kWh" in text and PDF_2027 in text


async def test_wert_uebernehmen(hass: HomeAssistant, eingerichtet, freezer) -> None:
    freezer.move_to(datetime(2027, 1, 2, 12, 0, tzinfo=BERLIN))
    with patch(NOTIFY):
        await hass.services.async_call(
            DOMAIN, "wert_uebernehmen", {"bestandteil": "modul3_ht", "gueltig_ab": "2027-01-01"}, blocking=True
        )
    assert zustand(hass, "modul3_ht").state == "11.0"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "wert_uebernehmen", {"bestandteil": "modul3_ht", "gueltig_ab": "2027-01-01"}, blocking=True
        )


async def test_unlesbares_pdf_nur_warnung(hass: HomeAssistant, eingerichtet, aioclient_mock) -> None:
    entry, _ = eingerichtet
    quellen_mocken(aioclient_mock, pdf_2026=b"%PDF-1.4 kaputt")
    with patch(NOTIFY) as notify:
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    titel = {c.kwargs["title"] for c in notify.call_args_list}
    assert "Netzentgelte & Umlagen: Quelle unlesbar" in titel
    # Werte bleiben erhalten
    assert zustand(hass, "netz_arbeitspreis").state == "6.72"


async def test_daten_bleiben_nach_neustart(hass: HomeAssistant, eingerichtet, aioclient_mock) -> None:
    entry, _ = eingerichtet
    aioclient_mock.clear_requests()  # alle Quellen offline
    for url in [DEFAULT_PREISBLATT_SEITE] + [m.format(jahr=j) for m in UMLAGE_URLS.values() for j in (2026, 2027)]:
        aioclient_mock.get(url, status=500)
    with patch(NOTIFY):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert zustand(hass, "kwkg_umlage").state == "0.446"
