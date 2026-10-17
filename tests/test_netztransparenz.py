"""Tests des netztransparenz.de-Parsers."""

import pytest

from custom_components.netzentgelte.parsers.netztransparenz import UmlageFehler, parse_umlage

from .conftest import fixture_bytes


@pytest.mark.parametrize(
    ("key", "datei", "wert"),
    [
        ("kwkg_umlage", "kwkg_2026.html", 0.446),
        ("offshore_netzumlage", "offshore_2026.html", 0.941),
        ("aufschlag_besondere_netznutzung", "aufschlag_2026.html", 1.559),
    ],
)
def test_umlage_2026(key, datei, wert):
    assert parse_umlage(key, fixture_bytes("netztransparenz", datei).decode(), 2026) == wert


def test_falsches_jahr():
    with pytest.raises(UmlageFehler):
        parse_umlage("kwkg_umlage", fixture_bytes("netztransparenz", "kwkg_2026.html").decode(), 2027)


def test_kein_wert():
    with pytest.raises(UmlageFehler):
        parse_umlage("offshore_netzumlage", "<p>2026 folgt</p>", 2026)
