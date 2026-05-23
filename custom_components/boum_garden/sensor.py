"""Sensors for Boum Garden."""
from __future__ import annotations

from collections.abc import Mapping
import json
from dataclasses import dataclass
import re
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

from .const import (
    CONF_PLANT_ICON,
    CONF_PLANT_LOCATION,
    CONF_PLANT_NAME,
    CONF_PLANTS_JSON,
    DATA_COORDINATOR,
    DEFAULT_LOCAL_PLANTS,
    DEFAULT_PLANT_CONTAINER_NAMES,
    DOMAIN,
)
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
    telemetry_state,
)


@dataclass(frozen=True, kw_only=True)
class BoumValueSensorDescription(SensorEntityDescription):
    """Boum value sensor description."""

    keys: tuple[str, ...]
    value_type: str = "auto"
    source_order: tuple[str, ...] = ("reported", "telemetry", "desired")


PUMP_STATE_KEYS = ("pumpState", "pump_state", "pump", "pumping", "pumpOn", "pump_on", "isPumping")
LAST_WATERING_KEYS = (
    "lastPumped",
    "lastPump",
    "lastPumpedAt",
    "lastWatered",
    "lastWateredAt",
    "lastIrrigated",
    "lastIrrigatedAt",
    "lastRefill",
    "lastRefilled",
    "lastRefilledAt",
)

SENSOR_DESCRIPTIONS: tuple[BoumValueSensorDescription, ...] = (
    BoumValueSensorDescription(
        key="battery",
        translation_key="battery",
        keys=("battery", "batteryLevel", "batteryPercent", "batteryPercentage", "soc"),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
        icon="mdi:battery",
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
        icon="mdi:water-percent",
    ),
    BoumValueSensorDescription(
        key="water_level",
        translation_key="water_level",
        keys=("waterLevel", "tankLevel", "reservoirLevel", "waterTankLevel"),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
        icon="mdi:cup-water",
    ),
    BoumValueSensorDescription(
        key="flow_rate",
        translation_key="flow_rate",
        keys=("flowRate", "waterFlowRate", "minFlowRate"),
        native_unit_of_measurement="L/min",
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
        icon="mdi:waves-arrow-right",
    ),
    BoumValueSensorDescription(
        key="rssi",
        translation_key="rssi",
        keys=("rssi", "wifiRssi", "signalStrength"),
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
        icon="mdi:wifi",
    ),
    BoumValueSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        keys=("lastSeen", "last_seen", "updatedAt", "reportedAt", "timestamp", "time", "createdAt"),
        device_class=SensorDeviceClass.TIMESTAMP,
        value_type="timestamp",
        icon="mdi:clock-outline",
    ),
    BoumValueSensorDescription(
        key="last_pumped",
        translation_key="last_pumped",
        keys=LAST_WATERING_KEYS,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_type="timestamp",
        icon="mdi:pump",
    ),
    BoumValueSensorDescription(
        key="last_pumped_raw",
        translation_key="last_pumped_raw",
        keys=LAST_WATERING_KEYS,
        value_type="string",
        icon="mdi:pump-outline",
    ),
    BoumValueSensorDescription(
        key="pump_state",
        translation_key="pump_state",
        keys=PUMP_STATE_KEYS,
        value_type="string",
        icon="mdi:water-pump",
        # This is the UI/control state. Prefer desired, because Boum devices may
        # report physical state later.
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="pump_state_reported",
        translation_key="pump_state_reported",
        keys=PUMP_STATE_KEYS,
        value_type="string",
        icon="mdi:water-pump-off",
        source_order=("reported",),
    ),
    BoumValueSensorDescription(
        key="pump_state_desired",
        translation_key="pump_state_desired",
        keys=PUMP_STATE_KEYS,
        value_type="string",
        icon="mdi:water-pump",
        source_order=("desired",),
    ),
    BoumValueSensorDescription(
        key="online",
        translation_key="online",
        keys=("online", "isOnline", "connected", "isConnected"),
        value_type="boolean_text",
        icon="mdi:cloud-check-outline",
    ),
    BoumValueSensorDescription(
        key="connection_state",
        translation_key="connection_state",
        keys=("connectionState", "deviceStatus", "status"),
        value_type="string",
        icon="mdi:connection",
    ),
    BoumValueSensorDescription(
        key="firmware",
        translation_key="firmware",
        keys=("firmware", "firmwareVersion", "swVersion", "appVersion", "version"),
        value_type="string",
        icon="mdi:chip",
    ),
    BoumValueSensorDescription(
        key="model",
        translation_key="model",
        keys=("model", "deviceModel", "hardware", "hardwareVersion", "productName", "type"),
        value_type="string",
        icon="mdi:devices",
    ),
    BoumValueSensorDescription(
        key="leakage_detection",
        translation_key="leakage_detection",
        keys=("leakageDetection", "leakage_detection", "leakDetected", "leak"),
        value_type="boolean_text",
        icon="mdi:water-alert",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="min_flow_rate",
        translation_key="min_flow_rate",
        keys=("minFlowRate", "min_flow_rate"),
        native_unit_of_measurement="L/min",
        state_class=SensorStateClass.MEASUREMENT,
        value_type="float",
        icon="mdi:waves-arrow-right",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="max_pump_duration",
        translation_key="max_pump_duration",
        keys=("maxPumpDuration", "max_pump_duration"),
        value_type="string",
        icon="mdi:timer-sand",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="refill_interval",
        translation_key="refill_interval",
        keys=("refillInterval", "refill_interval"),
        value_type="string",
        icon="mdi:calendar-clock",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="max_pub_interval",
        translation_key="max_pub_interval",
        keys=("maxPubInterval", "max_pub_interval"),
        value_type="string",
        icon="mdi:timer-cog-outline",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="high_battery_max_pub_interval",
        translation_key="high_battery_max_pub_interval",
        keys=("hMaxPubInterval", "h_max_pub_interval"),
        value_type="string",
        icon="mdi:timer-cog",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="daily_refill_1",
        translation_key="daily_refill_1",
        keys=("dailyRefill", "daily_refill"),
        value_type="boolean_text",
        icon="mdi:calendar-refresh",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="refill_time_1",
        translation_key="refill_time_1",
        keys=("refillTimeOne", "refill_time_one", "refillTime1", "refill_time_1"),
        value_type="string",
        icon="mdi:clock-time-seven-outline",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="daily_refill_2",
        translation_key="daily_refill_2",
        keys=("dailyRefillTwo", "daily_refill_two", "dailyRefill2", "daily_refill_2"),
        value_type="boolean_text",
        icon="mdi:calendar-refresh",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="refill_time_2",
        translation_key="refill_time_2",
        keys=("refillTimeTwo", "refill_time_two", "refillTime2", "refill_time_2"),
        value_type="string",
        icon="mdi:clock-time-seven-outline",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="daily_refill_3",
        translation_key="daily_refill_3",
        keys=("dailyRefillThree", "daily_refill_three", "dailyRefill3", "daily_refill_3"),
        value_type="boolean_text",
        icon="mdi:calendar-refresh",
        source_order=("desired", "reported", "telemetry"),
    ),
    BoumValueSensorDescription(
        key="refill_time_3",
        translation_key="refill_time_3",
        keys=("refillTimeThree", "refill_time_three", "refillTime3", "refill_time_3"),
        value_type="string",
        icon="mdi:clock-time-seven-outline",
        source_order=("desired", "reported", "telemetry"),
    ),
)


def _normalise_key(text: str) -> str:
    """Normalise API field names for matching/filtering.

This helper is used while module-level constants are created, so it must be
defined before KNOWN_SENSOR_KEYS.
    """
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())

KNOWN_SENSOR_KEYS = {
    _normalise_key(key)
    for description in SENSOR_DESCRIPTIONS
    for key in description.keys
}
TOP_LEVEL_SKIP_KEYS = {
    "state",
    "reported",
    "desired",
    "_claimed_device",
    "_device_detail",
    "_owner",
    "_api_user",
    "_latest_telemetry",
    "_latest_telemetry_last_hour",
    "_latest_telemetry_last_7d",
    "_telemetry_summary",
    "_telemetry_available",
    "_api_errors",
}
DYNAMIC_SKIP_KEYS = {
    "id",
    "deviceid",
    "serialnumber",
    "serial",
    "uuid",
    "name",
    "devicename",
    "displayname",
    "friendlyname",
    "label",
    "nickname",
    "alias",
    "email",
    "owner",
    "user",
    "password",
    "accesstoken",
    "refreshtoken",
    "token",
    "pushtoken",
    "preview",
    "length",
    "truncated",
}
SENSITIVE_PATH_TOKENS = (
    "token",
    "password",
    "secret",
    "auth",
    "credential",
    "push",
    "email",
)
PLANT_CONTEXT_KEYS = {
    "plant",
    "plants",
    "plantdata",
    "plantdetails",
    "pot",
    "pots",
    "garden",
    "gardens",
    "crop",
    "crops",
}
PLANT_NAME_KEYS = {
    "plantname",
    "plant_name",
    "plantlabel",
    "plant_label",
    "cropname",
    "crop_name",
    "species",
    "botanicalname",
    "botanical_name",
}


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
        entities.append(BoumConfiguredPlantSensor(coordinator, device_id))
        entities.append(BoumPlantSummarySensor(coordinator, device_id))
        for plant_entity in _plant_entities_for_device(coordinator, device_id, device):
            entities.append(plant_entity)
        entities.append(BoumDerivedLastWateredSensor(coordinator, device_id))
        entities.append(BoumPumpSyncSensor(coordinator, device_id))
        sources = _sources(device)

        for description in SENSOR_DESCRIPTIONS:
            if _find_known_value(sources, description.keys, description.source_order) is not None:
                entities.append(BoumValueSensor(coordinator, device_id, description))

        for path, source in _dynamic_scalar_paths(device):
            entities.append(BoumDynamicValueSensor(coordinator, device_id, path, source))

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
    _attr_icon = "mdi:sprout"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_status"

    @property
    def native_value(self) -> str | None:
        if not self._device:
            return None
        sources = _sources(self._device)
        for key in ("status", "deviceStatus", "connectionState", "online"):
            value = _find_known_value(sources, (key,), ("reported", "telemetry", "desired"))
            if value not in (None, ""):
                return str(value)
        pump = _find_known_value(sources, PUMP_STATE_KEYS, ("desired", "reported", "telemetry"))
        if pump not in (None, ""):
            return f"pump {pump}"
        if sources["telemetry"]:
            return "telemetry"
        if sources["reported"]:
            return "online"
        return "unavailable"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        plants = _api_plants_for_device(self._device) or _extract_plants(self._device)
        return {
            "device_id": device_id_from_device(self._device),
            "name": device_name(self._device),
            "telemetry_available": bool(self._device.get("_telemetry_available")),
            "api_sections_loaded": [
                key
                for key in (
                    "_claimed_device",
                    "_device_detail",
                    "_owner",
                    "_latest_telemetry",
                    "_latest_telemetry_last_hour",
                    "_latest_telemetry_last_7d",
                    "_telemetry_summary",
                )
                if self._device.get(key)
            ],
            "plant_names": [plant.get("name") for plant in plants if plant.get("name")],
            "plant_count": len(plants),
            "reported": compact_attributes(reported_state(self._device)),
            "desired": compact_attributes(desired_state(self._device)),
            "latest_telemetry": compact_attributes(telemetry_state(self._device)),
            "latest_telemetry_last_hour": compact_attributes(
                self._device.get("_latest_telemetry_last_hour", {})
            ),
            "latest_telemetry_last_7d": compact_attributes(
                self._device.get("_latest_telemetry_last_7d", {})
            ),
            "telemetry_summary": compact_attributes(self._device.get("_telemetry_summary", {})),
            "api_errors": compact_attributes(self._device.get("_api_errors", {})),
        }


class BoumConfiguredPlantSensor(BoumBaseSensor):
    """Locally configured plant name/location when Boum does not expose plants."""

    _attr_translation_key = "configured_plant"
    _attr_icon = "mdi:sprout"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_configured_plant"

    @property
    def icon(self) -> str:
        icon = str(self.coordinator.options.get(CONF_PLANT_ICON) or "").strip()
        return icon if icon.startswith("mdi:") else "mdi:sprout"

    @property
    def native_value(self) -> str | None:
        local_plants = _local_plants_for_device(self.coordinator.options, self._device or {})
        if local_plants:
            names = [str(plant.get("name")) for plant in local_plants if plant.get("name")]
            return ", ".join(names) if names else None
        name = str(self.coordinator.options.get(CONF_PLANT_NAME) or "").strip()
        if name:
            return name
        plants = (_api_plants_for_device(self._device or {}) or _extract_plants(self._device or {})) if self._device else []
        if plants and plants[0].get("name"):
            return str(plants[0]["name"])
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        local_plants = _local_plants_for_device(self.coordinator.options, self._device)
        return {
            "configured_in_home_assistant": bool(
                local_plants or str(self.coordinator.options.get(CONF_PLANT_NAME) or "").strip()
            ),
            "location": str(self.coordinator.options.get(CONF_PLANT_LOCATION) or "").strip() or None,
            "icon": self.icon,
            "local_plants": compact_attributes(local_plants),
            "api_plant_names": [
                plant.get("name")
                for plant in (_api_plants_for_device(self._device) or _extract_plants(self._device))
                if plant.get("name")
            ],
            "note": (
                "If Boum does not expose plant names through the API, this sensor uses "
                "the locally configured Home Assistant options. Multiple plants can be "
                "configured as JSON in the integration options."
            ),
        }


class BoumDerivedLastWateredSensor(BoumBaseSensor):
    """Best-effort last watered timestamp derived from API, telemetry or HA actions."""

    _attr_translation_key = "last_watered_derived"
    _attr_icon = "mdi:watering-can"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_last_watered_derived"

    @property
    def native_value(self) -> Any:
        if not self._device:
            return None
        return self._best_value()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        value, source, confidence, note = self._best_value()
        local = self._device.get("_local", {}) if isinstance(self._device.get("_local"), Mapping) else {}
        derived = self._device.get("_derived", {}) if isinstance(self._device.get("_derived"), Mapping) else {}
        sources = _sources(self._device)
        api_raw = _find_known_value(sources, LAST_WATERING_KEYS, ("reported", "telemetry", "desired"))
        return {
            "source": source,
            "confidence": confidence,
            "note": note,
            "api_raw_value": api_raw,
            "derived_value": derived.get("last_watered"),
            "derived_source": derived.get("last_watered_source"),
            "local_last_watered": local.get("last_watered"),
            "last_pump_command": local.get("last_pump_command"),
            "last_pump_command_at": local.get("last_pump_command_at"),
        }

    def _best_value(self) -> tuple[Any, str | None, str | None, str | None]:
        if not self._device:
            return None, None, None, None
        sources = _sources(self._device)
        api_raw = _find_known_value(sources, LAST_WATERING_KEYS, ("reported", "telemetry", "desired"))
        api_value = as_timestamp(api_raw)
        if api_value is not None:
            return api_value, "api", "direct", "Boum exposed a direct last-watered/last-pumped value."

        derived = self._device.get("_derived", {}) if isinstance(self._device.get("_derived"), Mapping) else {}
        derived_value = as_timestamp(derived.get("last_watered"))
        if derived_value is not None:
            return (
                derived_value,
                str(derived.get("last_watered_source") or "derived"),
                str(derived.get("last_watered_confidence") or "derived"),
                str(derived.get("last_watered_note") or "Derived from telemetry or Home Assistant pump action."),
            )

        local = self._device.get("_local", {}) if isinstance(self._device.get("_local"), Mapping) else {}
        local_value = as_timestamp(local.get("last_watered"))
        if local_value is not None:
            return (
                local_value,
                str(local.get("last_watered_source") or "home_assistant"),
                "local",
                "Home Assistant recorded the pump being switched on.",
            )
        return None, None, None, "No API, telemetry or local pump event is available yet."


class BoumPlantSummarySensor(BoumBaseSensor):
    """Plant summary sensor."""

    _attr_translation_key = "plant_summary"
    _attr_icon = "mdi:sprout"
    _attr_native_unit_of_measurement = "plants"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_plants"

    @property
    def native_value(self) -> int | None:
        if not self._device:
            return None
        api_plants = _api_plants_for_device(self._device)
        extracted_plants = _extract_plants(self._device)
        local_plants = _local_plants_for_device(self.coordinator.options, self._device)
        return len(api_plants or local_plants or extracted_plants)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        api_plants = _api_plants_for_device(self._device)
        extracted_plants = _extract_plants(self._device)
        local_plants = _local_plants_for_device(self.coordinator.options, self._device)
        plants = api_plants or local_plants or extracted_plants
        return {
            "names": [plant.get("name") for plant in plants if plant.get("name")],
            "containers": _plant_container_summary(plants),
            "plants": compact_attributes(plants),
            "source": "api_user_plants" if api_plants else ("local_options" if local_plants else "api_device_payload"),
            "api_names": [plant.get("name") for plant in api_plants if plant.get("name")],
            "note": (
                "Uses Boum app plant assignments from the user API when available. "
                "If the API does not expose plants, the local JSON mapping from the "
                "integration options is used."
            ),
        }



class BoumApiPlantSensor(BoumBaseSensor):
    """One sensor per Boum app plant assignment."""

    _attr_icon = "mdi:sprout"

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        device_id: str,
        plant: Mapping[str, Any],
        index: int,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._plant_uid = str(plant.get("id") or plant.get("plantId") or index)
        self._index = index
        self._attr_unique_id = f"{DOMAIN}_{device_id}_plant_{_slugify(self._plant_uid)}"
        pot = _plant_pot_name(plant)
        name = _plant_display_name(plant) or f"Pflanze {index}"
        self._attr_name = f"{pot} {name}" if pot else name
        self._attr_icon = _plant_icon(plant)

    @property
    def native_value(self) -> str | None:
        plant = _find_current_plant(self._device or {}, self._plant_uid)
        if not plant:
            return None
        return _plant_display_name(plant)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plant = _find_current_plant(self._device or {}, self._plant_uid)
        if not plant:
            return {}
        attrs = _plant_attributes(plant)
        return compact_attributes(attrs)



class BoumPumpSyncSensor(BoumBaseSensor):
    """Shows whether desired and reported pump states match."""

    _attr_translation_key = "pump_sync"
    _attr_icon = "mdi:sync"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_pump_sync"

    @property
    def native_value(self) -> str | None:
        if not self._device:
            return None
        reported = find_value(reported_state(self._device), PUMP_STATE_KEYS)
        desired = find_value(desired_state(self._device), PUMP_STATE_KEYS)
        if reported is None and desired is None:
            return "unknown"
        if desired is None:
            return "reported_only"
        if reported is None:
            return "desired_pending"
        if _normalise_state(reported) == _normalise_state(desired):
            return "synced"
        return "pending"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        return {
            "desired_pump_state": find_value(desired_state(self._device), PUMP_STATE_KEYS),
            "reported_pump_state": find_value(reported_state(self._device), PUMP_STATE_KEYS),
            "explanation": (
                "Boum writes commands to state.desired. The device may update "
                "state.reported only after it has received/executed the command."
            ),
        }


class BoumValueSensor(BoumBaseSensor):
    """Sensor for one known reported/desired/telemetry Boum field."""

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
        sources = _sources(self._device)
        value = _find_known_value(
            sources, self.entity_description.keys, self.entity_description.source_order
        )

        if self.entity_description.value_type == "float":
            return as_float(value)
        if self.entity_description.value_type == "timestamp":
            return as_timestamp(value)
        if self.entity_description.value_type == "boolean_text":
            return _normalise_boolean_text(value)
        if value is None:
            return None
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, (str, int, float)):
            return value
        return str(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        sources = _sources(self._device)
        attrs: dict[str, Any] = {
            "source_keys": self.entity_description.keys,
            "source_order": self.entity_description.source_order,
        }
        for source_name, source_data in sources.items():
            attrs[f"raw_{source_name}_value"] = find_value(source_data, self.entity_description.keys)
        return attrs


class BoumDynamicValueSensor(BoumBaseSensor):
    """Dynamic sensor for useful scalar Boum values not covered by known sensors."""

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        device_id: str,
        path: str,
        source: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._path = path
        self._source = source
        self._attr_unique_id = f"{DOMAIN}_{device_id}_{source}_{_slugify(path)}"
        self._attr_name = _friendly_name(source, path)
        metadata = _metadata_for_path(path)
        self._attr_icon = metadata["icon"]
        self._attr_device_class = metadata.get("device_class")
        self._attr_native_unit_of_measurement = metadata.get("unit")
        self._attr_state_class = metadata.get("state_class")
        self._value_type = metadata.get("value_type", "auto")

    @property
    def native_value(self) -> Any:
        if not self._device:
            return None
        source_data = _source_mapping(self._device, self._source)
        value = _value_at_path(source_data, self._path)
        if self._value_type == "float":
            return as_float(value)
        if self._value_type == "timestamp":
            return as_timestamp(value)
        if isinstance(value, bool):
            return "on" if value else "off"
        if value is None or isinstance(value, (str, int, float)):
            return value
        return str(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"source": self._source, "path": self._path}


def _sources(device: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        "reported": reported_state(device),
        "desired": desired_state(device),
        "telemetry": telemetry_state(device),
        "telemetry_last_hour": device.get("_latest_telemetry_last_hour", {})
        if isinstance(device.get("_latest_telemetry_last_hour"), Mapping)
        else {},
        "telemetry_last_7d": device.get("_latest_telemetry_last_7d", {})
        if isinstance(device.get("_latest_telemetry_last_7d"), Mapping)
        else {},
    }


def _find_known_value(
    sources: Mapping[str, Mapping[str, Any]],
    keys: tuple[str, ...],
    source_order: tuple[str, ...],
) -> Any:
    for source_name in source_order:
        value = find_value(sources.get(source_name, {}), keys)
        if value is not None:
            return value
    return None


def _dynamic_scalar_paths(device: Mapping[str, Any]) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    for source, data in (
        ("reported", reported_state(device)),
        ("desired", desired_state(device)),
        ("telemetry", telemetry_state(device)),
        ("telemetry_last_hour", device.get("_latest_telemetry_last_hour", {})),
        ("telemetry_last_7d", device.get("_latest_telemetry_last_7d", {})),
    ):
        for path, value in _flatten_scalars(data):
            normalised_last_key = _normalise_key(path.split(".")[-1])
            if normalised_last_key in KNOWN_SENSOR_KEYS or normalised_last_key in DYNAMIC_SKIP_KEYS:
                continue
            if _path_is_sensitive(path) or not _value_is_reasonable_dynamic(value):
                continue
            paths.append((path, source))
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for item in paths:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _flatten_scalars(data: Any, prefix: str = "") -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    if isinstance(data, Mapping):
        for key, value in data.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if isinstance(value, (Mapping, list)):
                result.extend(_flatten_scalars(value, path))
            elif isinstance(value, (str, int, float, bool)) or value is None:
                result.append((path, value))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            path = f"{prefix}.{index}" if prefix else str(index)
            if isinstance(value, (Mapping, list)):
                result.extend(_flatten_scalars(value, path))
            elif isinstance(value, (str, int, float, bool)) or value is None:
                result.append((path, value))
    return result


def _value_at_path(data: Any, path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _source_mapping(device: Mapping[str, Any], source: str) -> Any:
    return {
        "reported": reported_state(device),
        "desired": desired_state(device),
        "telemetry": telemetry_state(device),
        "telemetry_last_hour": device.get("_latest_telemetry_last_hour", {}),
        "telemetry_last_7d": device.get("_latest_telemetry_last_7d", {}),
    }.get(source, {})



def _plant_entities_for_device(
    coordinator: BoumGardenDataUpdateCoordinator,
    device_id: str,
    device: Mapping[str, Any],
) -> list[BoumApiPlantSensor]:
    """Create one entity per Boum app plant if the user API exposes plants."""
    plants = _api_plants_for_device(device)
    return [BoumApiPlantSensor(coordinator, device_id, plant, index) for index, plant in enumerate(plants, start=1)]


def _api_plants_for_device(device: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return API plants normalised for Home Assistant attributes."""
    raw = device.get("_api_plants")
    if not isinstance(raw, list):
        return []
    plants: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        plant = _normalise_api_plant(item, index)
        key = str(plant.get("id") or plant.get("plant_id") or plant.get("name") or index)
        if key in seen:
            continue
        seen.add(key)
        plants.append(plant)
    plants.sort(key=lambda plant: (str(plant.get("pot_name") or ""), int(plant.get("index") or 0)))
    return plants


def _normalise_api_plant(plant: Mapping[str, Any], index: int) -> dict[str, Any]:
    """Convert a raw Boum plant object to compact, useful attributes."""
    translated = plant.get("translated") if isinstance(plant.get("translated"), Mapping) else {}
    name_translated = plant.get("nameTranslated") if isinstance(plant.get("nameTranslated"), Mapping) else {}
    name = (
        name_translated.get("de")
        or translated.get("de")
        or plant.get("name")
        or plant.get("latinName")
        or plant.get("plantId")
    )
    container_id = plant.get("plantContainerId")
    pot_name = DEFAULT_PLANT_CONTAINER_NAMES.get(str(container_id), str(container_id or ""))
    result: dict[str, Any] = {
        "name": str(name) if name is not None else None,
        "pot_name": pot_name or None,
        "plant_container_id": str(container_id) if container_id else None,
        "plant_id": plant.get("plantId"),
        "id": plant.get("id") or plant.get("objectID") or plant.get("plantId"),
        "state": plant.get("state"),
        "latin_name": plant.get("latinName"),
        "product_name": plant.get("name"),
        "image_url": plant.get("imageUrl"),
        "water_usage": plant.get("waterUsage"),
        "water_class": plant.get("waterClass"),
        "water": _translated_value(plant, "waterTranslated", plant.get("water")),
        "light": _translated_value(plant, "lightTypeTranslated", plant.get("lightType")),
        "soil": _translated_value(plant, "soilTypeTranslated", plant.get("soilType")),
        "nutrients": _translated_value(plant, "nutrientsTranslated", plant.get("nutrients")),
        "min_temperature": plant.get("minTemperature"),
        "max_temperature": plant.get("maxTemperature"),
        "min_prefered_temperature": plant.get("minPreferedTemperature"),
        "max_prefered_temperature": plant.get("maxPreferedTemperature"),
        "fertilizer_interval_days": plant.get("fertilizerInterval"),
        "height": plant.get("height"),
        "width": plant.get("width"),
        "is_boum_plant": plant.get("isBoumPlant"),
        "is_pot_plant": plant.get("isPotPlant"),
        "is_perennial": plant.get("isPerennial"),
        "source": "api_user_plants",
        "index": index,
    }
    descriptions = {
        "description": _translated_value(plant, "descriptionTranslated", plant.get("description")),
        "general_care": _translated_value(plant, "generalCareDescriptionTranslated", plant.get("generalCareDescription")),
        "water_care": _translated_value(plant, "waterCareDescriptionTranslated", plant.get("waterCareDescription")),
        "light_care": _translated_value(plant, "lightCareDescriptionTranslated", plant.get("lightCareDescription")),
        "temperature_care": _translated_value(plant, "temperatureCareDescriptionTranslated", plant.get("temperatureCareDescription")),
        "fertilizer_care": _translated_value(plant, "fertilizerCareDescriptionTranslated", plant.get("fertilizerCareDescription")),
    }
    for key, value in descriptions.items():
        if isinstance(value, str) and len(value) > 900:
            result[key] = value[:897] + "..."
        elif value not in (None, ""):
            result[key] = value
    return {key: value for key, value in result.items() if value not in (None, "", [], {})}


def _translated_value(plant: Mapping[str, Any], key: str, fallback: Any = None) -> Any:
    value = plant.get(key)
    if isinstance(value, Mapping):
        return value.get("de") or value.get("en") or next((v for v in value.values() if v), fallback)
    return fallback


def _plant_display_name(plant: Mapping[str, Any]) -> str | None:
    return str(plant.get("name")) if plant.get("name") not in (None, "") else None


def _plant_pot_name(plant: Mapping[str, Any]) -> str | None:
    return str(plant.get("pot_name")) if plant.get("pot_name") not in (None, "") else None


def _plant_icon(plant: Mapping[str, Any]) -> str:
    name = _normalise_key(str(plant.get("name") or ""))
    if "erdbeere" in name:
        return "mdi:fruit-cherries"
    if any(token in name for token in ("basilikum", "minze", "zitronenmelisse", "zitronenverbene")):
        return "mdi:leaf"
    if any(token in name for token in ("rosmarin", "oregano", "thymian", "majoran", "salbei", "estragon", "koriander", "petersilie")):
        return "mdi:sprout"
    return "mdi:sprout"


def _plant_attributes(plant: Mapping[str, Any]) -> dict[str, Any]:
    return dict(plant)


def _find_current_plant(device: Mapping[str, Any], plant_uid: str) -> dict[str, Any] | None:
    for plant in _api_plants_for_device(device):
        if str(plant.get("id") or plant.get("plant_id")) == str(plant_uid):
            return plant
    return None


def _plant_container_summary(plants: list[dict[str, Any]]) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {}
    for plant in plants:
        pot = str(plant.get("pot_name") or plant.get("plant_container_id") or "unknown")
        name = plant.get("name")
        if name:
            summary.setdefault(pot, []).append(str(name))
    return summary



def _local_plants_for_device(options: Mapping[str, Any], device: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return locally configured plants for this device from options JSON."""
    raw = str(options.get(CONF_PLANTS_JSON) or "").strip()
    parsed: Any = None
    if raw:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = None

    candidates = [
        str(device_id_from_device(device) or "").strip(),
        str(device_name(device) or "").strip(),
        str(device.get("name") or "").strip(),
        str(device.get("label") or "").strip(),
        str(device.get("deviceName") or "").strip(),
        str(device.get("title") or "").strip(),
        "default",
    ]
    candidates = [item for item in candidates if item]

    value: Any = None
    if isinstance(parsed, Mapping):
        lower_map = {str(key).lower(): val for key, val in parsed.items()}
        for candidate in candidates:
            if candidate in parsed:
                value = parsed[candidate]
                break
            lowered = candidate.lower()
            if lowered in lower_map:
                value = lower_map[lowered]
                break
    elif isinstance(parsed, list):
        value = parsed

    # Fallback: Arthur's known Boum app mapping. This is only used when the
    # Boum API does not expose plant names and no custom JSON option was set.
    if value is None:
        lower_defaults = {str(key).lower(): val for key, val in DEFAULT_LOCAL_PLANTS.items()}
        for candidate in candidates:
            if candidate in DEFAULT_LOCAL_PLANTS:
                value = DEFAULT_LOCAL_PLANTS[candidate]
                break
            lowered = candidate.lower()
            if lowered in lower_defaults:
                value = lower_defaults[lowered]
                break

    plants: list[dict[str, Any]] = []
    if isinstance(value, str):
        value = [name.strip() for name in value.split(",") if name.strip()]
    if isinstance(value, list):
        for index, item in enumerate(value, start=1):
            if isinstance(item, Mapping):
                plant = dict(item)
                if plant.get("name"):
                    plant.setdefault("source", "local_options" if raw else "built_in_mapping")
                    plant.setdefault("index", index)
                    plants.append(plant)
            elif isinstance(item, str) and item.strip():
                plants.append({"name": item.strip(), "source": "local_options" if raw else "built_in_mapping", "index": index})

    if not plants:
        legacy_name = str(options.get(CONF_PLANT_NAME) or "").strip()
        if legacy_name:
            plants.append(
                {
                    "name": legacy_name,
                    "location": str(options.get(CONF_PLANT_LOCATION) or "").strip() or None,
                    "icon": str(options.get(CONF_PLANT_ICON) or "mdi:sprout").strip() or "mdi:sprout",
                    "source": "local_options",
                    "index": 1,
                }
            )
    return plants

def _extract_plants(device: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract plant-like objects from the payloads Boum exposes, if any."""
    plants: list[dict[str, Any]] = []
    for source_name, payload in (
        ("reported", reported_state(device)),
        ("desired", desired_state(device)),
        ("telemetry", telemetry_state(device)),
        ("claimed", device.get("_claimed_device", {})),
        ("detail", device.get("_device_detail", {})),
    ):
        _collect_plants(payload, plants, source_name=source_name, in_context=False)

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for plant in plants:
        key = str(plant.get("name") or plant.get("index") or plant)
        if key in seen:
            continue
        seen.add(key)
        unique.append(plant)
    return unique


def _collect_plants(
    data: Any,
    plants: list[dict[str, Any]],
    *,
    source_name: str,
    in_context: bool,
    index: int | None = None,
) -> None:
    if isinstance(data, Mapping):
        normalised_keys = {_normalise_key(str(key)): key for key in data}
        name = None
        for key in PLANT_NAME_KEYS:
            original = normalised_keys.get(_normalise_key(key))
            if original is not None and data.get(original) not in (None, ""):
                name = str(data.get(original))
                break
        if name is None and in_context:
            for key in ("name", "label", "displayName", "display_name", "friendlyName"):
                if key in data and data.get(key) not in (None, ""):
                    name = str(data.get(key))
                    break
        if name is not None:
            plant: dict[str, Any] = {
                "name": name,
                "source": source_name,
            }
            if index is not None:
                plant["index"] = index + 1
            for key, value in data.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    if not _path_is_sensitive(str(key)):
                        plant[str(key)] = value
            plants.append(plant)

        for key, value in data.items():
            key_norm = _normalise_key(str(key))
            child_context = in_context or key_norm in PLANT_CONTEXT_KEYS
            if isinstance(value, list):
                for idx, item in enumerate(value):
                    if isinstance(item, str) and child_context and item:
                        plants.append({"name": item, "source": source_name, "index": idx + 1})
                    else:
                        _collect_plants(
                            item,
                            plants,
                            source_name=source_name,
                            in_context=child_context,
                            index=idx,
                        )
            elif isinstance(value, Mapping):
                _collect_plants(value, plants, source_name=source_name, in_context=child_context)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            _collect_plants(item, plants, source_name=source_name, in_context=in_context, index=idx)


def _normalise_boolean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "on" if value else "off"
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "online", "connected"}:
        return "on"
    if text in {"0", "false", "no", "off", "offline", "disconnected"}:
        return "off"
    return str(value)


def _normalise_state(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "online", "open", "running"}:
        return "on"
    if text in {"0", "false", "no", "off", "offline", "closed", "stopped"}:
        return "off"
    return text


def _slugify(text: str) -> str:
    text = text.lower().replace(".", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return text.strip("_") or "value"


def _friendly_name(source: str, path: str) -> str:
    parts = []
    for part in path.split("."):
        if part.isdigit():
            parts.append(str(int(part) + 1))
        else:
            parts.append(re.sub(r"(?<!^)(?=[A-Z])", " ", part).replace("_", " ").replace("-", " "))
    source_name = source.replace("_", " ").title()
    return f"{source_name} {' '.join(parts)}".strip().title()


def _metadata_for_path(path: str) -> dict[str, Any]:
    lowered = path.lower()
    metadata: dict[str, Any] = {"icon": "mdi:information-outline"}
    if any(token in lowered for token in ("water", "tank", "reservoir")):
        metadata["icon"] = "mdi:cup-water"
    if "pump" in lowered:
        metadata["icon"] = "mdi:water-pump"
    if any(token in lowered for token in ("plant", "garden", "grow", "crop", "pot")):
        metadata["icon"] = "mdi:sprout"
    if any(token in lowered for token in ("moist", "soil", "humidity")):
        metadata.update(
            {
                "icon": "mdi:water-percent",
                "unit": PERCENTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
                "value_type": "float",
            }
        )
    if "temp" in lowered:
        metadata.update(
            {
                "icon": "mdi:thermometer",
                "unit": UnitOfTemperature.CELSIUS,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
                "value_type": "float",
            }
        )
    if "battery" in lowered or "soc" in lowered:
        metadata.update(
            {
                "icon": "mdi:battery",
                "unit": PERCENTAGE,
                "device_class": SensorDeviceClass.BATTERY,
                "state_class": SensorStateClass.MEASUREMENT,
                "value_type": "float",
            }
        )
    if any(token in lowered for token in ("wifi", "rssi", "signal")):
        metadata.update(
            {
                "icon": "mdi:wifi",
                "unit": "dBm" if "rssi" in lowered else None,
                "device_class": SensorDeviceClass.SIGNAL_STRENGTH if "rssi" in lowered else None,
                "state_class": SensorStateClass.MEASUREMENT if "rssi" in lowered else None,
                "value_type": "float" if "rssi" in lowered else "auto",
            }
        )
    if "leak" in lowered:
        metadata["icon"] = "mdi:water-alert"
    if "firmware" in lowered or "version" in lowered:
        metadata["icon"] = "mdi:chip"
    if any(token in lowered for token in ("time", "date", "timestamp", "createdat", "updatedat", "pumped", "watered")):
        metadata.update(
            {
                "icon": "mdi:clock-outline",
                "device_class": SensorDeviceClass.TIMESTAMP,
                "value_type": "timestamp",
            }
        )
    return {key: value for key, value in metadata.items() if value is not None}


def _path_is_sensitive(path: str) -> bool:
    lowered = _normalise_key(path)
    return any(token in lowered for token in SENSITIVE_PATH_TOKENS)


def _value_is_reasonable_dynamic(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, str) and len(value) > 120:
        return False
    return True

