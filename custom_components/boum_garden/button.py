"""Buttons for Boum Garden."""
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import BoumApiClient
from .const import DATA_API, DATA_COORDINATOR, DOMAIN
from .coordinator import BoumGardenDataUpdateCoordinator
from .helpers import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Boum Garden buttons."""
    data = hass.data[DOMAIN][entry.entry_id]
    api: BoumApiClient = data[DATA_API]
    coordinator: BoumGardenDataUpdateCoordinator = data[DATA_COORDINATOR]

    entities: list[ButtonEntity] = []
    for device_id in coordinator.data:
        entities.append(BoumRefreshButton(coordinator, device_id))
        entities.append(BoumRestartButton(coordinator, api, device_id))
        entities.append(BoumResetLastPumpedButton(coordinator, api, device_id))
        entities.append(BoumResetWifiCredentialsButton(coordinator, api, device_id))
    async_add_entities(entities)


class BoumBaseButton(CoordinatorEntity[BoumGardenDataUpdateCoordinator], ButtonEntity):
    """Base Boum button."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id

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


class BoumRefreshButton(BoumBaseButton):
    """Manual refresh button."""

    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_refresh"

    async def async_press(self) -> None:
        """Refresh coordinator data."""
        await self.coordinator.async_request_refresh()


class BoumRestartButton(BoumBaseButton):
    """Restart device button."""

    _attr_translation_key = "restart_device"
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        api: BoumApiClient,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._api = api
        self._attr_unique_id = f"{DOMAIN}_{device_id}_restart_device"

    async def async_press(self) -> None:
        """Restart the Boum device."""
        await self._api.send_device_command(self._device_id, "restartDevice")
        await self.coordinator.async_request_refresh()


class BoumResetLastPumpedButton(BoumBaseButton):
    """Reset last pumped button."""

    _attr_translation_key = "reset_last_pumped"
    _attr_icon = "mdi:pump-off"

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        api: BoumApiClient,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._api = api
        self._attr_unique_id = f"{DOMAIN}_{device_id}_reset_last_pumped"

    async def async_press(self) -> None:
        """Reset last pumped value on the device."""
        await self._api.send_device_command(self._device_id, "resetLastPumped")
        await self.coordinator.async_request_refresh()



class BoumResetWifiCredentialsButton(BoumBaseButton):
    """Reset Wi-Fi credentials button. The entity is disabled by default because it is disruptive."""

    _attr_translation_key = "reset_wifi_credentials"
    _attr_icon = "mdi:wifi-remove"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        api: BoumApiClient,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._api = api
        self._attr_unique_id = f"{DOMAIN}_{device_id}_reset_wifi_credentials"

    async def async_press(self) -> None:
        """Reset Wi-Fi credentials on the device."""
        await self._api.send_device_command(self._device_id, "resetWiFiCredentials")
        await self.coordinator.async_request_refresh()
