"""Switches for Boum Garden."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_API, DATA_COORDINATOR, DOMAIN
from .api import BoumApiClient
from .coordinator import BoumGardenDataUpdateCoordinator
from .helpers import desired_state, device_info, find_value, reported_state


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Boum Garden switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    api: BoumApiClient = data[DATA_API]
    coordinator: BoumGardenDataUpdateCoordinator = data[DATA_COORDINATOR]

    async_add_entities(
        [BoumPumpSwitch(coordinator, api, device_id) for device_id in coordinator.data]
    )


class BoumPumpSwitch(CoordinatorEntity[BoumGardenDataUpdateCoordinator], SwitchEntity):
    """Switch for Boum pump state."""

    _attr_has_entity_name = True
    _attr_translation_key = "pump"
    _attr_icon = "mdi:water-pump"

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        api: BoumApiClient,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._api = api
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_pump"

    @property
    def _device(self) -> dict[str, Any] | None:
        return self.coordinator.data.get(self._device_id)

    @property
    def device_info(self):
        if not self._device:
            return None
        return device_info(self._device)

    @property
    def available(self) -> bool:
        return super().available and self._device is not None

    @property
    def is_on(self) -> bool | None:
        if not self._device:
            return None
        reported = reported_state(self._device)
        desired = desired_state(self._device)
        value = find_value(reported, ("pumpState", "pump_state"))
        if value is None:
            value = find_value(desired, ("pumpState", "pump_state"))
        if value is None:
            return None
        return str(value).lower() in {"on", "true", "1", "open", "running"}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn pump on."""
        await self._api.set_pump_state(self._device_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn pump off."""
        await self._api.set_pump_state(self._device_id, False)
        await self.coordinator.async_request_refresh()
