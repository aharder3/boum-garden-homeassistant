"""Data coordinator for Boum Garden."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BoumApiClient, BoumApiError
from .const import DOMAIN
from .helpers import as_float, as_timestamp, compact_attributes, desired_state, device_id_from_device

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_local_state"

PUMP_STATE_KEYS = ("pumpState", "pump_state", "pump", "pumping", "pumpOn", "pump_on", "isPumping")
FLOW_KEYS = ("flowRate", "waterFlowRate", "minFlowRate", "flow", "waterFlow")
TIME_KEYS = ("timestamp", "time", "createdAt", "created_at", "date", "ts")



class BoumGardenDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch Boum devices, user data, shadows, owners and telemetry."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: BoumApiClient,
        *,
        update_interval: timedelta,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.api = api
        self.options = dict(options or {})
        self.user: dict[str, Any] = {}
        self.last_api_errors: dict[str, str] = {}
        self.local_state: dict[str, dict[str, Any]] = {}
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_load_local_state(self) -> None:
        """Load locally derived Boum data from Home Assistant storage."""
        stored = await self._store.async_load()
        devices = stored.get("devices") if isinstance(stored, Mapping) else None
        self.local_state = {
            str(device_id): dict(values)
            for device_id, values in (devices or {}).items()
            if isinstance(values, Mapping)
        }

    async def async_record_manual_watering(self, device_id: str, *, source: str) -> None:
        """Persist that Home Assistant triggered the pump, used as derived last watering."""
        now = datetime.now(timezone.utc).isoformat()
        local = dict(self.local_state.get(device_id, {}))
        local.update(
            {
                "last_watered": now,
                "last_watered_source": source,
                "last_pump_command": "on",
                "last_pump_command_at": now,
            }
        )
        self.local_state[device_id] = local
        await self._store.async_save({"devices": self.local_state})
        self._apply_local_to_current_data(device_id)

    async def async_record_pump_command(self, device_id: str, command: str) -> None:
        """Persist the latest Home Assistant pump command."""
        now = datetime.now(timezone.utc).isoformat()
        local = dict(self.local_state.get(device_id, {}))
        local.update({"last_pump_command": command, "last_pump_command_at": now})
        self.local_state[device_id] = local
        await self._store.async_save({"devices": self.local_state})
        self._apply_local_to_current_data(device_id)

    def _apply_local_to_current_data(self, device_id: str) -> None:
        """Merge local data into coordinator data for immediate UI updates."""
        if not self.data or device_id not in self.data:
            return
        data = dict(self.data)
        device = dict(data[device_id])
        local = self.local_state.get(device_id)
        if local:
            device["_local"] = dict(local)
        data[device_id] = device
        self.async_set_updated_data(data)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        errors: dict[str, str] = {}
        try:
            try:
                user = await self.api.whoami()
                self.user = dict(user) if isinstance(user, Mapping) else {"value": user}
            except BoumApiError as err:
                errors["users"] = str(err)
                _LOGGER.debug("Could not fetch Boum user information: %s", err)

            claimed = await self.api.list_claimed_devices()
            user_plants = _extract_user_plants(self.user)

            async def fetch_full_device(device: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
                device_id = device_id_from_device(device)
                full: dict[str, Any] = dict(device)
                full["_claimed_device"] = dict(device)
                device_errors: dict[str, str] = {}

                try:
                    detail = await self.api.get_device(device_id)
                    if isinstance(detail, Mapping):
                        full = _deep_merge(full, dict(detail))
                        full["_device_detail"] = dict(detail)
                        device_id = device_id_from_device(full)
                    else:
                        full["_device_detail"] = {"value": detail}
                except BoumApiError as err:
                    device_errors["device_detail"] = str(err)
                    _LOGGER.debug("Could not fetch Boum device detail for %s: %s", device_id, err)

                try:
                    owner = await self.api.get_device_owner(device_id)
                    if isinstance(owner, Mapping):
                        full["_owner"] = dict(owner)
                    else:
                        full["_owner"] = {"value": owner}
                except BoumApiError as err:
                    device_errors["owner"] = str(err)
                    _LOGGER.debug("Could not fetch Boum owner for %s: %s", device_id, err)

                telemetry_payloads: dict[str, Any] = {}
                telemetry_specs = {
                    "last_24h": {},
                    "last_hour": {"time_start": "-1h", "interval": "10s"},
                    "last_7d": {"time_start": "-7d", "interval": "1h"},
                }
                for name, kwargs in telemetry_specs.items():
                    try:
                        telemetry_payloads[name] = await self.api.get_device_data(device_id, **kwargs)
                    except BoumApiError as err:
                        device_errors[f"telemetry_{name}"] = str(err)
                        _LOGGER.debug("Could not fetch Boum telemetry %s for %s: %s", name, device_id, err)

                latest_24h = _latest_telemetry_row(telemetry_payloads.get("last_24h"))
                latest_hour = _latest_telemetry_row(telemetry_payloads.get("last_hour"))
                latest_7d = _latest_telemetry_row(telemetry_payloads.get("last_7d"))

                if latest_24h:
                    full["_latest_telemetry"] = latest_24h
                elif latest_hour:
                    full["_latest_telemetry"] = latest_hour
                elif latest_7d:
                    full["_latest_telemetry"] = latest_7d

                full["_latest_telemetry_last_hour"] = latest_hour
                full["_latest_telemetry_last_7d"] = latest_7d
                full["_telemetry_summary"] = _telemetry_summary(telemetry_payloads)
                full["_telemetry_available"] = any(
                    bool(_find_telemetry_rows(payload)) or isinstance(payload, Mapping)
                    for payload in telemetry_payloads.values()
                    if payload is not None
                )
                final_device_id = device_id_from_device(full)
                local = self.local_state.get(final_device_id)
                if local:
                    full["_local"] = dict(local)

                derived = _derive_values_from_payloads(full, telemetry_payloads, local or {})
                if derived:
                    full["_derived"] = derived

                # Plants returned by /users are real Boum app plant assignments.
                # They are stored on the device payload so sensor.py can create useful entities.
                if user_plants:
                    full["_api_plants"] = user_plants
                    full["_api_plant_containers"] = _group_plants_by_container(user_plants)

                # User/owner data stays available in diagnostics but should not be
                # turned into Home Assistant entities.
                if device_errors:
                    full["_api_errors"] = device_errors
                return final_device_id, full

            pairs = await asyncio.gather(*(fetch_full_device(device) for device in claimed))
            self.last_api_errors = errors
            return {device_id: device for device_id, device in pairs if device_id}
        except BoumApiError as err:
            raise UpdateFailed(str(err)) from err

    def apply_local_desired_state(self, device_id: str, desired_patch: Mapping[str, Any]) -> None:
        """Optimistically update state.desired so UI reflects commands immediately."""
        if not self.data or device_id not in self.data:
            return
        data = dict(self.data)
        device = dict(data[device_id])
        state = dict(device.get("state") or {})
        desired = dict(state.get("desired") or desired_state(device))
        desired.update(dict(desired_patch))
        state["desired"] = desired
        device["state"] = state
        data[device_id] = device
        self.async_set_updated_data(data)



def _extract_user_plants(user: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract plant assignments returned by the Boum user endpoint."""
    plants = user.get("plants") if isinstance(user, Mapping) else None
    if not isinstance(plants, list):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(plants, start=1):
        if not isinstance(item, Mapping):
            continue
        if item.get("isArchived") is True:
            continue
        plant = dict(item)
        plant.setdefault("_index", index)
        result.append(plant)
    return result


def _group_plants_by_container(plants: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group plants by Boum plantContainerId."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for plant in plants:
        container_id = plant.get("plantContainerId")
        if not container_id:
            continue
        grouped.setdefault(str(container_id), []).append(plant)
    return grouped

def _latest_telemetry_row(payload: Any) -> dict[str, Any]:
    """Extract latest telemetry values.

    Boum's /devices/:id/data endpoint can return a shape like:

        {"data": {"timeSeries": {"batteryCapacity": [{"x": "...", "y": 88.1}], ...}}}

    Earlier versions treated the first list of x/y points as an anonymous row,
    which lost the series name and made it impossible to distinguish battery,
    temperature and water distance. This function keeps the time-series names as
    keys, e.g. batteryCapacity=88.1, temperature=22.0, waterTableRange=15.1.
    """
    named = _latest_named_timeseries_values(payload)
    if named:
        return named

    rows = _find_telemetry_rows(payload)
    if not rows:
        if isinstance(payload, Mapping):
            simple = {k: v for k, v in payload.items() if _is_simple(v)}
            return dict(simple)
        return {}

    def sort_key(row: Mapping[str, Any]) -> str:
        for key in ("timestamp", "time", "createdAt", "created_at", "date", "ts", "x"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    return dict(sorted(rows, key=sort_key)[-1])


def _latest_named_timeseries_values(payload: Any) -> dict[str, Any]:
    """Return the latest non-null y value for every named Boum time series."""
    time_series = _find_time_series_mapping(payload)
    if not time_series:
        return {}

    latest: dict[str, Any] = {}
    timestamps: dict[str, Any] = {}

    for name, points in time_series.items():
        if not isinstance(points, list):
            continue
        latest_point: Mapping[str, Any] | None = None
        for point in points:
            if not isinstance(point, Mapping):
                continue
            if point.get("y") is None:
                continue
            latest_point = point
        if latest_point is None:
            continue

        key = str(name)
        latest[key] = latest_point.get("y")
        if latest_point.get("x") not in (None, ""):
            timestamps[f"{key}_timestamp"] = latest_point.get("x")

    latest.update(timestamps)
    return latest


def _find_time_series_mapping(payload: Any) -> Mapping[str, Any] | None:
    """Find a named timeSeries mapping recursively."""
    if not isinstance(payload, Mapping):
        return None

    data = payload.get("data")
    if isinstance(data, Mapping):
        ts = data.get("timeSeries") or data.get("timeseries") or data.get("time_series")
        if isinstance(ts, Mapping):
            return ts

    ts = payload.get("timeSeries") or payload.get("timeseries") or payload.get("time_series")
    if isinstance(ts, Mapping):
        return ts

    for value in payload.values():
        if isinstance(value, Mapping):
            found = _find_time_series_mapping(value)
            if found:
                return found
    return None


def _find_telemetry_rows(payload: Any) -> list[Mapping[str, Any]]:
    """Find list-like telemetry rows recursively."""
    rows: list[Mapping[str, Any]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, Mapping):
                rows.append(item)
        return rows
    if not isinstance(payload, Mapping):
        return rows

    for key in ("data", "items", "results", "values", "measurements", "series", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
        if isinstance(value, Mapping):
            nested = _find_telemetry_rows(value)
            if nested:
                return nested

    for value in payload.values():
        if isinstance(value, (Mapping, list)):
            nested = _find_telemetry_rows(value)
            if nested:
                return nested
    return rows


def _telemetry_summary(payloads: Mapping[str, Any]) -> dict[str, Any]:
    """Return compact telemetry metadata without storing large series in entity attributes."""
    summary: dict[str, Any] = {}
    for name, payload in payloads.items():
        rows = _find_telemetry_rows(payload)
        latest = _latest_telemetry_row(payload)
        time_series = _find_time_series_mapping(payload)
        series_counts: dict[str, int] = {}
        if time_series:
            for series_name, points in time_series.items():
                if isinstance(points, list):
                    series_counts[str(series_name)] = len(points)
        summary[name] = {
            "rows": len(rows),
            "series": series_counts,
            "latest": compact_attributes(latest),
            "available": bool(rows or time_series or payload),
        }
    return summary


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge nested dictionaries, preserving existing helper keys."""
    merged = dict(base)
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(dict(merged[key]), dict(value))
        else:
            merged[key] = value
    return merged


def _is_simple(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _derive_values_from_payloads(
    device: Mapping[str, Any], telemetry_payloads: Mapping[str, Any], local: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive user-facing values when Boum does not expose them directly."""
    derived: dict[str, Any] = {}
    telemetry_last = _derive_last_watering_from_telemetry(telemetry_payloads)
    local_last = as_timestamp(local.get("last_watered")) if local else None

    candidates: list[tuple[datetime, str, str]] = []
    if telemetry_last:
        candidates.append((telemetry_last, "telemetry", "Pump activity/flow found in Boum telemetry."))
    if local_last:
        candidates.append((local_last, str(local.get("last_watered_source") or "home_assistant"), "Pump was switched on through Home Assistant."))

    if candidates:
        when, source, note = sorted(candidates, key=lambda item: item[0])[-1]
        derived["last_watered"] = when.isoformat()
        derived["last_watered_source"] = source
        derived["last_watered_note"] = note
        derived["last_watered_confidence"] = "derived"

    return derived


def _derive_last_watering_from_telemetry(payloads: Mapping[str, Any]) -> datetime | None:
    """Find the latest telemetry row that looks like watering/pumping."""
    latest: datetime | None = None
    for payload in payloads.values():
        for row in _find_telemetry_rows(payload):
            if not _telemetry_row_indicates_watering(row):
                continue
            when = _row_timestamp(row)
            if when is None:
                continue
            if latest is None or when > latest:
                latest = when
    return latest


def _telemetry_row_indicates_watering(row: Mapping[str, Any]) -> bool:
    """Return true if a telemetry row likely represents active watering."""
    for key in PUMP_STATE_KEYS:
        value = _get_case_insensitive(row, key)
        if value is not None and _value_is_on(value):
            return True

    for key in FLOW_KEYS:
        value = _get_case_insensitive(row, key)
        numeric = as_float(value)
        if numeric is not None and numeric > 0:
            return True

    return False


def _row_timestamp(row: Mapping[str, Any]) -> datetime | None:
    for key in TIME_KEYS:
        value = _get_case_insensitive(row, key)
        timestamp = as_timestamp(value)
        if timestamp is not None:
            return timestamp
    return None


def _get_case_insensitive(data: Mapping[str, Any], wanted_key: str) -> Any:
    wanted = wanted_key.lower()
    for key, value in data.items():
        if str(key).lower() == wanted:
            return value
    return None


def _value_is_on(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) > 0
    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "open",
        "running",
        "active",
        "pumping",
    }
