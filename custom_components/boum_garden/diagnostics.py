"""Diagnostics support for Boum Garden."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.diagnostics import async_redact_data

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    DATA_COORDINATOR,
    DOMAIN,
)

TO_REDACT = {CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, "password", "accessToken", "refreshToken"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "user": async_redact_data(getattr(coordinator, "user", {}), TO_REDACT),
        "api_errors": async_redact_data(getattr(coordinator, "last_api_errors", {}), TO_REDACT),
        "devices": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
