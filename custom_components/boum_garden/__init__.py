"""Boum Garden integration for Home Assistant."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BoumApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL_OVERRIDE,
    CONF_ENV,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DATA_API,
    DATA_COORDINATOR,
    DEFAULT_ENV,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import BoumGardenDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Boum Garden from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    async def _save_tokens(access_token: str | None, refresh_token: str | None) -> None:
        new_data = dict(entry.data)
        if access_token:
            new_data[CONF_ACCESS_TOKEN] = access_token
        if refresh_token:
            new_data[CONF_REFRESH_TOKEN] = refresh_token
        hass.config_entries.async_update_entry(entry, data=new_data)

    session = async_get_clientsession(hass)
    api = BoumApiClient(
        session,
        env=entry.data.get(CONF_ENV, DEFAULT_ENV),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        base_url_override=entry.data.get(CONF_BASE_URL_OVERRIDE),
        token_update_callback=_save_tokens,
    )

    scan_interval = int(
        entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
        )
    )
    coordinator = BoumGardenDataUpdateCoordinator(
        hass,
        api,
        update_interval=timedelta(seconds=max(scan_interval, 60)),
        options=entry.options,
    )
    await coordinator.async_load_local_state()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_API: api,
        DATA_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
