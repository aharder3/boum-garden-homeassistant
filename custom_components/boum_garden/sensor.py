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
        key="refill_time",
        translation_key="refill_time",
        keys=("refillTime", "refill_time"),
        value_type="string",
        icon="mdi:clock-time-seven-outline",
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
    "x",
    "y",
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
        # Local plant fallback was useful before we found Boum app plants in /users.
        # Do not create it when real API plant assignments are available, otherwise
        # Home Assistant shows a confusing stale entity such as "Pflanze lokal = Basilikum".
        if not _api_plants_for_device(device):
            entities.append(BoumConfiguredPlantSensor(coordinator, device_id))
        entities.append(BoumPlantSummarySensor(coordinator, device_id))
        entities.append(BoumPotTableSensor(coordinator, device_id))
        entities.append(BoumWaterTankPercentSensor(coordinator, device_id))
        entities.append(BoumWaterTankLitersSensor(coordinator, device_id))
        entities.append(BoumBatteryTelemetrySensor(coordinator, device_id))
        entities.append(BoumEnergySavingModeSensor(coordinator, device_id))
        for plant_entity in _plant_entities_for_device(coordinator, device_id, device):
            entities.append(plant_entity)
        entities.append(BoumDerivedLastWateredSensor(coordinator, device_id))
        entities.append(BoumNextRefillSensor(coordinator, device_id))
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
                "only locally configured Home Assistant options. Multiple plants can be "
                "configured as JSON in the integration options; no fixed default mapping is used."
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
        return _global_last_watered_for_device(self._device)[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        value, source, confidence, note = _global_last_watered_for_device(self._device)
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


def _global_last_watered_for_device(device: Mapping[str, Any]) -> tuple[Any, str | None, str | None, str | None]:
    """Return best known device-level watering timestamp."""
    sources = _sources(device)
    api_raw = _find_known_value(sources, LAST_WATERING_KEYS, ("reported", "telemetry", "desired"))
    api_value = as_timestamp(api_raw)
    if api_value is not None:
        return api_value, "api", "direct", "Boum exposed a direct last-watered/last-pumped value."

    derived = device.get("_derived", {}) if isinstance(device.get("_derived"), Mapping) else {}
    derived_value = as_timestamp(derived.get("last_watered"))
    if derived_value is not None:
        return (
            derived_value,
            str(derived.get("last_watered_source") or "derived"),
            str(derived.get("last_watered_confidence") or "derived"),
            str(derived.get("last_watered_note") or "Derived from telemetry or Home Assistant pump action."),
        )

    local = device.get("_local", {}) if isinstance(device.get("_local"), Mapping) else {}
    local_value = as_timestamp(local.get("last_watered"))
    if local_value is not None:
        return (
            local_value,
            str(local.get("last_watered_source") or "home_assistant"),
            "local",
            "Home Assistant recorded the pump being switched on.",
        )
    return None, None, None, "No API, telemetry or local pump event is available yet."


def _next_refill_for_device(device: Mapping[str, Any]) -> Any:
    """Compute the next refill time from device schedule, if possible."""
    from datetime import datetime, timedelta

    sources = _sources(device)
    daily = _find_known_value(sources, ("dailyRefill", "daily_refill"), ("desired", "reported"))
    if str(daily).strip().lower() in {"off", "false", "0", "no", "disabled"}:
        return None

    refill_time = _find_known_value(sources, ("refillTime", "refill_time"), ("desired", "reported"))
    if not refill_time:
        return None
    match = re.search(r"(\d{1,2})[:.](\d{2})", str(refill_time))
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None

    now = datetime.now().astimezone()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        interval_raw = str(_find_known_value(sources, ("refillInterval", "refill_interval"), ("desired", "reported")) or "1days")
        interval_match = re.search(r"(\d+)", interval_raw)
        days = int(interval_match.group(1)) if interval_match else 1
        candidate = candidate + timedelta(days=max(days, 1))
    return candidate




def _telemetry_y_percent(device: Mapping[str, Any]) -> float | None:
    """Return latest Boum telemetry Y as 0-100 percentage when available.

    The public Boum endpoint currently returns telemetry rows as x/y pairs. In
    the observed Boum app/diagnostics, y is the only live numeric value matching
    the app-level water/battery percentage. We expose it with clear attributes
    so the user can see that it is inferred from telemetry_y, not a named API
    field like waterLevel or batteryLevel.
    """
    for key in ("_latest_telemetry", "_latest_telemetry_last_7d", "_latest_telemetry_last_hour"):
        value = device.get(key)
        if isinstance(value, Mapping):
            number = as_float(value.get("y"))
            if number is not None and 0 <= number <= 100:
                return number
    summary = device.get("_telemetry_summary")
    if isinstance(summary, Mapping):
        for section in ("last_24h", "last_7d", "last_hour"):
            latest = summary.get(section, {}).get("latest") if isinstance(summary.get(section), Mapping) else None
            if isinstance(latest, Mapping):
                number = as_float(latest.get("y"))
                if number is not None and 0 <= number <= 100:
                    return number
    return None


class BoumWaterTankPercentSensor(BoumBaseSensor):
    """Water tank percentage inferred from Boum telemetry y."""

    _attr_name = "Wassertank"
    _attr_icon = "mdi:water-percent"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_water_tank_percent"

    @property
    def native_value(self) -> float | None:
        if not self._device:
            return None
        value = _find_known_value(_sources(self._device), ("waterLevel", "tankLevel", "reservoirLevel", "waterTankLevel"), ("reported", "telemetry", "desired"))
        number = as_float(value)
        if number is not None:
            return round(number, 1)
        y = _telemetry_y_percent(self._device)
        return round(y, 1) if y is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        y = _telemetry_y_percent(self._device or {})
        return {
            "source": "named_api_field" if _find_known_value(_sources(self._device or {}), ("waterLevel", "tankLevel", "reservoirLevel", "waterTankLevel"), ("reported", "telemetry", "desired")) is not None else "telemetry_y_inferred",
            "telemetry_y": y,
            "note": "Boum diagnostics currently expose live telemetry as x/y. y is used as percentage when no named waterLevel field exists.",
        }


class BoumWaterTankLitersSensor(BoumBaseSensor):
    """Water tank fill level in litres, derived from percent and 50 L tank."""

    _attr_name = "Wasserfüllstand"
    _attr_icon = "mdi:cup-water"
    _attr_native_unit_of_measurement = "L"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_water_tank_liters"

    @property
    def native_value(self) -> float | None:
        if not self._device:
            return None
        percent = _telemetry_y_percent(self._device)
        if percent is None:
            return None
        return round(percent * 0.5, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        percent = _telemetry_y_percent(self._device or {})
        return {
            "source": "telemetry_y_inferred",
            "tank_capacity_liters_assumed": 50,
            "water_percent": round(percent, 1) if percent is not None else None,
            "note": "Derived as telemetry_y percent of an assumed 50 L tank, matching the Boum app display style such as about 44 L for 88%.",
        }


class BoumBatteryTelemetrySensor(BoumBaseSensor):
    """Battery percentage from named API field or telemetry y fallback."""

    _attr_name = "Batterie"
    _attr_icon = "mdi:battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_battery_telemetry"

    @property
    def native_value(self) -> float | None:
        if not self._device:
            return None
        value = _find_known_value(_sources(self._device), ("battery", "batteryLevel", "batteryPercent", "batteryPercentage", "soc"), ("reported", "telemetry", "desired"))
        number = as_float(value)
        if number is not None:
            return round(number, 1)
        y = _telemetry_y_percent(self._device)
        return round(y, 1) if y is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        value = _find_known_value(_sources(self._device or {}), ("battery", "batteryLevel", "batteryPercent", "batteryPercentage", "soc"), ("reported", "telemetry", "desired"))
        return {
            "source": "named_api_field" if value is not None else "telemetry_y_inferred",
            "api_raw_value": value,
            "telemetry_y": _telemetry_y_percent(self._device or {}),
            "note": "If Boum does not expose a named battery field, telemetry_y is used as best-effort value because it matches the app percentage in diagnostics.",
        }


class BoumEnergySavingModeSensor(BoumBaseSensor):
    """Best-effort app-like power saving mode."""

    _attr_name = "Stromsparmodus"
    _attr_icon = "mdi:moon-waning-crescent"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_energy_saving_mode"

    @property
    def native_value(self) -> str | None:
        if not self._device:
            return None
        sources = _sources(self._device)
        direct = _find_known_value(sources, ("powerSaving", "powerSavingMode", "energySaving", "energySavingMode", "ecoMode", "sleepMode"), ("reported", "desired", "telemetry"))
        if direct not in (None, ""):
            return _normalise_boolean_text(direct)
        # The app displays "Spart Strom" even when the public shadow only exposes
        # pump/refill tuning. Show the same friendly state, but mark it as derived.
        return "Spart Strom"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sources = _sources(self._device or {})
        direct = _find_known_value(sources, ("powerSaving", "powerSavingMode", "energySaving", "energySavingMode", "ecoMode", "sleepMode"), ("reported", "desired", "telemetry"))
        return {
            "source": "named_api_field" if direct not in (None, "") else "derived_app_style",
            "api_raw_value": direct,
            "note": "The exported API did not include a named power-saving field. This app-style value is derived unless Boum exposes a direct field later.",
        }

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





class BoumPotTableSensor(BoumBaseSensor):
    """One table-style summary sensor for all Boum plant containers."""

    _attr_icon = "mdi:table"
    _attr_name = "Pflanztopf Tabelle"
    _attr_native_unit_of_measurement = "pots"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_pot_table"

    @property
    def native_value(self) -> int | None:
        if not self._device:
            return None
        return len(_api_plant_containers_for_device(self._device))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        containers = _api_plant_containers_for_device(self._device)
        rows = [_container_dashboard_row(container) for container in containers]
        return compact_attributes(
            {
                "rows": rows,
                "markdown_table": _containers_markdown_table(rows),
                "containers": containers,
                "source": "api_user_plants" if containers else None,
                "note": "Each row is one Boum plantContainerId/pot. Multiple plants in the same pot are merged into one row.",
            }
        )


class BoumApiPlantContainerSensor(BoumBaseSensor):
    """One sensor per Boum app plant container/pot.

    The state is a readable list of plants in this pot. Detailed plant and pot
    data is exposed as attributes so dashboards can render it as a table/card.
    """

    _attr_icon = "mdi:flower-tulip"

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        device_id: str,
        container: Mapping[str, Any],
        index: int,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._container_id = str(container.get("plant_container_id") or index)
        self._index = index
        self._attr_unique_id = f"{DOMAIN}_{device_id}_plant_container_{_slugify(self._container_id)}"
        self._attr_name = str(container.get("pot_name") or f"Pflanzcontainer {index:02d}")

    @property
    def native_value(self) -> str | None:
        container = _find_current_container(self._device or {}, self._container_id)
        if not container:
            return None
        names = [str(name) for name in container.get("plant_names", []) if name]
        return ", ".join(names) if names else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        container = _find_current_container(self._device or {}, self._container_id)
        if not container:
            return {}
        return compact_attributes(container)


class BoumPlantContainerLastWateredSensor(BoumBaseSensor):
    """Best-effort last watered timestamp for one Boum plant container.

    Boum currently exposes pump/refill information on the device level. If the
    API does not provide a per-container watering timestamp, this sensor uses the
    global device-level derived timestamp and marks that clearly in attributes.
    """

    _attr_icon = "mdi:watering-can"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: BoumGardenDataUpdateCoordinator,
        device_id: str,
        container: Mapping[str, Any],
        index: int,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._container_id = str(container.get("plant_container_id") or index)
        self._index = index
        self._attr_unique_id = (
            f"{DOMAIN}_{device_id}_plant_container_{_slugify(self._container_id)}_last_watered"
        )
        pot_name = str(container.get("pot_name") or f"Pflanzcontainer {index:02d}")
        self._attr_name = f"{pot_name} zuletzt bewässert"

    @property
    def native_value(self) -> Any:
        if not self._device:
            return None
        value, _source, _confidence, _note = _global_last_watered_for_device(self._device)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        container = _find_current_container(self._device or {}, self._container_id)
        value, source, confidence, note = _global_last_watered_for_device(self._device or {})
        return compact_attributes(
            {
                "plant_container_id": self._container_id,
                "pot_name": container.get("pot_name") if container else None,
                "plant_names": container.get("plant_names") if container else None,
                "source": source,
                "confidence": confidence,
                "global_device_last_watered": value,
                "note": (
                    "Boum API data currently exposes pump/refill history at device level. "
                    "This value is therefore a best-effort device-level watering timestamp "
                    "assigned to the pot, not a proven per-pot measurement. "
                    + (note or "")
                ),
            }
        )


class BoumNextRefillSensor(BoumBaseSensor):
    """Next scheduled refill/watering based on Boum desired/reported schedule."""

    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Nächste Bewässerung"

    def __init__(self, coordinator: BoumGardenDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{DOMAIN}_{device_id}_next_refill"

    @property
    def native_value(self) -> Any:
        if not self._device:
            return None
        return _next_refill_for_device(self._device)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._device:
            return {}
        sources = _sources(self._device)
        return {
            "refill_time": _find_known_value(sources, ("refillTime", "refill_time"), ("desired", "reported")),
            "refill_interval": _find_known_value(sources, ("refillInterval", "refill_interval"), ("desired", "reported")),
            "daily_refill": _find_known_value(sources, ("dailyRefill", "daily_refill"), ("desired", "reported")),
            "note": "Computed locally from Boum refillTime/refillInterval/dailyRefill.",
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
) -> list[SensorEntity]:
    """Create one entity per Boum plant container/pot.

    Boum can return several plants for the same plantContainerId. Home Assistant
    should therefore show one pot/container entity with all plants as attributes,
    instead of one separate pot per plant.
    """
    containers = _api_plant_containers_for_device(device)
    if containers:
        entities: list[SensorEntity] = []
        for index, container in enumerate(containers, start=1):
            entities.append(BoumApiPlantContainerSensor(coordinator, device_id, container, index))
            entities.append(BoumPlantContainerLastWateredSensor(coordinator, device_id, container, index))
        return entities

    # Fallback for payload shapes that expose plants but not container IDs.
    plants = _api_plants_for_device(device)
    return [BoumApiPlantSensor(coordinator, device_id, plant, index) for index, plant in enumerate(plants, start=1)]




def _container_dashboard_row(container: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact row for Lovelace table/dashboard cards."""
    plants = container.get("plants") if isinstance(container.get("plants"), list) else []
    return {
        "topf": container.get("pot_name"),
        "pflanzen": container.get("plants_text"),
        "anzahl": container.get("plant_count"),
        "wasserbedarf_total": container.get("water_usage_total"),
        "wasserklasse": ", ".join(str(x) for x in container.get("water_classes", []) if x),
        "wasser": ", ".join(str(x) for x in container.get("water_needs", []) if x),
        "licht": ", ".join(str(x) for x in container.get("light_needs", []) if x),
        "erde": ", ".join(str(x) for x in container.get("soil_types", []) if x),
        "naehrstoffe": ", ".join(str(x) for x in container.get("nutrients", []) if x),
        "temperatur": _temperature_range_text(container),
        "bild": (container.get("image_urls") or [None])[0],
        "plant_container_id": container.get("plant_container_id"),
        "pflanzen_details": [
            {
                "name": plant.get("name"),
                "latein": plant.get("latin_name"),
                "produkt": plant.get("product_name"),
                "wasserbedarf": plant.get("water_usage"),
                "wasserklasse": plant.get("water_class"),
                "licht": plant.get("light"),
                "wasser": plant.get("water"),
                "erde": plant.get("soil"),
                "naehrstoffe": plant.get("nutrients"),
                "bild": plant.get("image_url"),
            }
            for plant in plants
        ],
    }


def _temperature_range_text(container: Mapping[str, Any]) -> str | None:
    preferred_min = container.get("preferred_min_temperature")
    preferred_max = container.get("preferred_max_temperature")
    min_temp = container.get("min_temperature")
    max_temp = container.get("max_temperature")
    if preferred_min is not None and preferred_max is not None:
        return f"ideal {preferred_min:g}–{preferred_max:g} °C"
    if min_temp is not None and max_temp is not None:
        return f"{min_temp:g}–{max_temp:g} °C"
    return None


def _containers_markdown_table(rows: list[dict[str, Any]]) -> str:
    """Build a markdown table that can be shown in a Lovelace markdown card."""
    lines = ["| Topf | Pflanzen | Wasser | Licht | Erde |", "|---|---|---:|---|---|"]
    for row in rows:
        lines.append(
            "| {topf} | {pflanzen} | {wasser} | {licht} | {erde} |".format(
                topf=_md_cell(row.get("topf")),
                pflanzen=_md_cell(row.get("pflanzen")),
                wasser=_md_cell(row.get("wasserbedarf_total")),
                licht=_md_cell(row.get("licht")),
                erde=_md_cell(row.get("erde")),
            )
        )
    return "\n".join(lines)


def _md_cell(value: Any) -> str:
    if value in (None, "", [], {}):
        return "–"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _api_plant_containers_for_device(device: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return one normalised item per plantContainerId.

    Each container contains a list of all plants inside that pot plus aggregated
    values that are useful for cards and table dashboards.
    """
    plants = _api_plants_for_device(device)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for plant in plants:
        container_id = str(plant.get("plant_container_id") or plant.get("pot_name") or "unknown")
        grouped.setdefault(container_id, []).append(plant)

    containers: list[dict[str, Any]] = []
    for index, (container_id, items) in enumerate(grouped.items(), start=1):
        pot_name = str(items[0].get("pot_name") or f"Pflanzcontainer {index:02d}")
        names = [str(item.get("name")) for item in items if item.get("name")]
        water_values = [as_float(item.get("water_usage")) for item in items]
        water_values = [value for value in water_values if value is not None]
        min_temps = [as_float(item.get("min_temperature")) for item in items]
        min_temps = [value for value in min_temps if value is not None]
        max_temps = [as_float(item.get("max_temperature")) for item in items]
        max_temps = [value for value in max_temps if value is not None]
        pref_min_temps = [as_float(item.get("min_prefered_temperature")) for item in items]
        pref_min_temps = [value for value in pref_min_temps if value is not None]
        pref_max_temps = [as_float(item.get("max_prefered_temperature")) for item in items]
        pref_max_temps = [value for value in pref_max_temps if value is not None]

        containers.append(
            {
                "pot_name": pot_name,
                "plant_container_id": container_id,
                "plant_count": len(items),
                "plant_names": names,
                "plants_text": ", ".join(names),
                "plants": items,
                "image_urls": _unique_list(item.get("image_url") for item in items),
                "latin_names": _unique_list(item.get("latin_name") for item in items),
                "product_names": _unique_list(item.get("product_name") for item in items),
                "states": _unique_list(item.get("state") for item in items),
                "water_usage_total": round(sum(water_values), 3) if water_values else None,
                "water_usage_average": round(sum(water_values) / len(water_values), 3) if water_values else None,
                "water_classes": _unique_list(item.get("water_class") for item in items),
                "water_needs": _unique_list(item.get("water") for item in items),
                "light_needs": _unique_list(item.get("light") for item in items),
                "soil_types": _unique_list(item.get("soil") for item in items),
                "nutrients": _unique_list(item.get("nutrients") for item in items),
                "min_temperature": min(min_temps) if min_temps else None,
                "max_temperature": max(max_temps) if max_temps else None,
                "preferred_min_temperature": min(pref_min_temps) if pref_min_temps else None,
                "preferred_max_temperature": max(pref_max_temps) if pref_max_temps else None,
                "fertilizer_intervals_days": _unique_list(item.get("fertilizer_interval_days") for item in items),
                "heights": _unique_list(item.get("height") for item in items),
                "widths": _unique_list(item.get("width") for item in items),
                "general_care": _care_by_plant(items, "general_care"),
                "water_care": _care_by_plant(items, "water_care"),
                "light_care": _care_by_plant(items, "light_care"),
                "temperature_care": _care_by_plant(items, "temperature_care"),
                "fertilizer_care": _care_by_plant(items, "fertilizer_care"),
                "source": "api_user_plants",
                "last_watered_source": None,
                "last_watered_note": "Set at runtime from the device-level watering timestamp.",
                "dashboard_hint": "One entity represents one Boum plantContainerId/pot. Multiple plants are listed in the plants attribute.",
            }
        )

    containers.sort(key=lambda item: str(item.get("pot_name") or item.get("plant_container_id") or ""))
    return containers


def _find_current_container(device: Mapping[str, Any], container_id: str) -> dict[str, Any] | None:
    for container in _api_plant_containers_for_device(device):
        if str(container.get("plant_container_id")) == str(container_id):
            return container
    return None


def _unique_list(values: Any) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if value in (None, "", [], {}):
            continue
        key = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (Mapping, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _care_by_plant(plants: list[dict[str, Any]], key: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for plant in plants:
        name = plant.get("name")
        value = plant.get(key)
        if name and isinstance(value, str) and value.strip():
            result[str(name)] = value.strip()
    return result


def _api_plants_for_device(device: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return API plants normalised for Home Assistant attributes."""
    raw = device.get("_api_plants")
    if not isinstance(raw, list):
        return []
    container_names = _plant_container_display_names(raw)
    plants: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        plant = _normalise_api_plant(item, index, container_names)
        key = str(plant.get("id") or plant.get("plant_id") or plant.get("name") or index)
        if key in seen:
            continue
        seen.add(key)
        plants.append(plant)
    plants.sort(key=lambda plant: (str(plant.get("pot_name") or ""), int(plant.get("index") or 0)))
    return plants


def _plant_container_display_names(raw_plants: list[Any]) -> dict[str, str]:
    """Build generic, API-derived display names for plant containers.

    Boum exposes a stable plantContainerId for each plant. If the API also
    provides a human readable container name, use it. Otherwise create a neutral
    per-account name based only on the order of container IDs returned by the API.
    No user-specific plant/pot mapping is hard-coded here.
    """
    container_names: dict[str, str] = {}
    for item in raw_plants:
        if not isinstance(item, Mapping):
            continue
        container_id = item.get("plantContainerId")
        if not container_id:
            continue
        container_id = str(container_id)
        explicit = _explicit_container_name(item)
        if explicit:
            container_names[container_id] = explicit
        elif container_id not in container_names:
            container_names[container_id] = f"Pflanzcontainer {len(container_names) + 1:02d}"
    return container_names


def _explicit_container_name(plant: Mapping[str, Any]) -> str | None:
    """Return a container/pot name if Boum exposes one in the plant object."""
    for key in (
        "plantContainerName",
        "plant_container_name",
        "containerName",
        "container_name",
        "potName",
        "pot_name",
        "gardenName",
        "garden_name",
    ):
        value = plant.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            translated = value.get("de") or value.get("en") or next((v for v in value.values() if v), None)
            if isinstance(translated, str) and translated.strip():
                return translated.strip()

    container = plant.get("plantContainer") or plant.get("container") or plant.get("pot")
    if isinstance(container, Mapping):
        for key in ("name", "displayName", "title", "label"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, Mapping):
                translated = value.get("de") or value.get("en") or next((v for v in value.values() if v), None)
                if isinstance(translated, str) and translated.strip():
                    return translated.strip()
    return None


def _normalise_api_plant(
    plant: Mapping[str, Any], index: int, container_names: Mapping[str, str]
) -> dict[str, Any]:
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
    container_id_str = str(container_id) if container_id else ""
    pot_name = container_names.get(container_id_str) or container_id_str
    result: dict[str, Any] = {
        "name": str(name) if name is not None else None,
        "pot_name": pot_name or None,
        "plant_container_id": container_id_str or None,
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

