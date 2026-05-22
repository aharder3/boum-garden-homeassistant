"""Data coordinator for Boum Garden."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BoumApiClient, BoumApiError
from .const import DOMAIN
from .helpers import device_id_from_device

_LOGGER = logging.getLogger(__name__)


class BoumGardenDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch Boum devices and their current shadows."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: BoumApiClient,
        *,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            claimed = await self.api.list_claimed_devices()
            device_ids = [_safe_device_id(device) for device in claimed]
            device_ids = [device_id for device_id in device_ids if device_id]

            async def fetch_or_fallback(device: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
                device_id = device_id_from_device(device)
                try:
                    full = await self.api.get_device(device_id)
                    if isinstance(full, Mapping):
                        return device_id_from_device(full), dict(full)
                except BoumApiError:
                    # Keep the list entry when the detail endpoint is temporarily unavailable.
                    return device_id, dict(device)
                return device_id, dict(device)

            pairs = await asyncio.gather(*(fetch_or_fallback(device) for device in claimed))
            return {device_id: device for device_id, device in pairs if device_id}
        except BoumApiError as err:
            raise UpdateFailed(str(err)) from err


def _safe_device_id(device: Mapping[str, Any]) -> str | None:
    try:
        return device_id_from_device(device)
    except Exception:  # noqa: BLE001
        return None
