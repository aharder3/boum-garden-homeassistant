"""Sensors for Boum Garden."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import BoumGardenDataUpdateCoordinator
from .helpers import (
    as_float,
    as_timestamp,
    compact_attributes,
    desired_state,
    device_id_from_device,
    device_info,
    device_name,
    find_value,
    reported_state,
)


@dataclass(frozen=True, kw_only=True)
class BoumValueSensorDescription(SensorEntityDescription):
    """Boum value sensor description."""

    keys: tuple[str, ...]
    value_type: str = "auto"


SENSOR_DESCRIPTIONS: tuple[BoumValueSensorDescription, ...] = (
    BoumValueSensorDescription(
        key="battery",
        translation_key="battery",
        keys=("battery", "batteryLevel", "batteryPercent", "batteryPercentage", "soc"),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
    ),
    BoumValueSensorDescription(
        key="temperature",
        translation_key="temperature",
        keys=("temperature", "temp", "tC", "t_c"),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
    ),
    BoumValueSensorDescription(
        key="humidity",
        translation_key="humidity",
        keys=("humidity", "airHumidity", "relativeHumidity"),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
    ),
    BoumValueSensorDescription(
        key="moisture",
        translation_key="moisture",
        keys=("moisture", "soilMoisture", "substrateMoisture", "waterContent"),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.MOISTURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
    ),
    BoumValueSensorDescription(
        key="water_level",
        translation_key="water_level",
        keys=("waterLevel", "tankLevel", "reservoirLevel", "waterTankLevel"),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
    ),
    BoumValueSensorDescription(
        key="flow_rate",
        translation_key="flow_rate",
        keys=("flowRate", "waterFlowRate", "minFlowRate"),
        native_unit_of_measurement="L/min",
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
    ),
    BoumValueSensorDescription(
        key="rssi",
        translation_key="rssi",
        keys=("rssi", "wifiRssi", "signalStrength"),
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
    ),
    BoumValueSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        keys=("lastSeen", "last_seen", "updatedAt", "reportedAt", "timestamp"),
        device_class=SensorDeviceClass.TIMESTAMP,
        value_type="timestamp",
    ),
    BoumValueSensorDescription(
        key="last_pumped",
        translation_key="last_pumped",
        keys=("lastPumped", "lastPump", "lastPumpedAt"),
        device_class=SensorDeviceClass.TIMESTAMP,
        value_type="timestamp",
    ),
    BoumValueSensorDescription(
        key="pump_state",
        translation_key="pump_state",
        keys=("pumpState", "pump_state"),
        value_type="string",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Boum Garden sensors."""
    coordinator: BoumGardenDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    entities: list[SensorEntity] = []

    for device_id, device in coordinator.data.items():
        entities.append(BoumDeviceOverviewSensor(coordinator, device_id))
        reported = reported_state(device)
        desired = desired_state(device)
        for description in SENSOR_DESCRIPTIONS:
            if find_value(reported, description.keys) is not None or find_value(desired, description.keys) is not None:
                entities.append(BoumValueSensor(coordinator, device_id, description))

    async_add_entities(entities)


class BoumBaseSensor(CoordinatorEntity[BoumGardenDataUpdateCoordinator], SensorEntity):
    """Base class for Boum sensors."""

    _attr_has_entity_name = True

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


class BoumDeviceOverviewSensor(BoumBaseSensor):
    """One overview sensor per Boum device."""

    _attr_translation_key = "device_status"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_status"

    @property
    def native_value(self) -> str | None:
        if not self._device:
            return None
        reported = reported_state(self._device)
        desired = desired_state(self._device)
        for key in ("status", "deviceStatus", "connectionState", "online", "pumpState"):
            value = reported.get(key, desired.get(key))
            if value not in (None, ""):
                return str(value)
        if reported:
            return "online"
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        return {
            "device_id": device_id_from_device(self._device),
            "name": device_name(self._device),
            "reported": compact_attributes(reported_state(self._device)),
            "desired": compact_attributes(desired_state(self._device)),
        }


class BoumValueSensor(BoumBaseSensor):
    """Sensor for one known reported/desired Boum field."""

    entity_description: BoumValueSensorDescription

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        device_id: str,
        description: BoumValueSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        if not self._device:
            return None
        reported = reported_state(self._device)
        desired = desired_state(self._device)
        value = find_value(reported, self.entity_description.keys)
        if value is None:
            value = find_value(desired, self.entity_description.keys)

        if self.entity_description.value_type == "float":
            return as_float(value)
        if self.entity_description.value_type == "timestamp":
            return as_timestamp(value)
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        reported = reported_state(self._device)
        desired = desired_state(self._device)
        return {
            "source_keys": self.entity_description.keys,
            "raw_reported_value": find_value(reported, self.entity_description.keys),
            "raw_desired_value": find_value(desired, self.entity_description.keys),
        }
