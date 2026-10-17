"""Gemeinsame Test-Fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Custom Integrations in jedem Test erlauben."""
    return


def fixture_bytes(*teile: str) -> bytes:
    return FIXTURES.joinpath(*teile).read_bytes()
