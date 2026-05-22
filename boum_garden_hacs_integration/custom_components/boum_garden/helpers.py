"""Shared helpers for Boum Garden entities."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER


def device_id_from_device(device: Mapping[str, Any]) -> str:
    """Return a stable ID for a device."""
    for key in ("id", "deviceId", "device_id", "serialNumber", "serial_number", "uuid"):
        value = device.get(key)
        if value not in (None, ""):
            return str(value)
    reported = reported_state(device)
    for key in ("id", "deviceId", "serialNumber"):
        value = reported.get(key)
        if value not in (None, ""):
            return str(value)
    return "unknown"


def device_name(device: Mapping[str, Any]) -> str:
    """Return a friendly device name."""
    reported = reported_state(device)
    desired = desired_state(device)
    for source in (device, reported, desired):
        for key in ("name", "deviceName", "device_name", "label", "nickname"):
            value = source.get(key) if isinstance(source, Mapping) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f"Boum {device_id_from_device(device)[-6:]}"


def reported_state(device: Mapping[str, Any]) -> dict[str, Any]:
    """Return reported shadow state."""
    state = device.get("state")
    if isinstance(state, Mapping):
        reported = state.get("reported")
        if isinstance(reported, Mapping):
            return dict(reported)
    reported = device.get("reported")
    if isinstance(reported, Mapping):
        return dict(reported)
    return {}


def desired_state(device: Mapping[str, Any]) -> dict[str, Any]:
    """Return desired shadow state."""
    state = device.get("state")
    if isinstance(state, Mapping):
        desired = state.get("desired")
        if isinstance(desired, Mapping):
            return dict(desired)
    desired = device.get("desired")
    if isinstance(desired, Mapping):
        return dict(desired)
    return {}


def device_info(device: Mapping[str, Any]) -> DeviceInfo:
    """Return Home Assistant device registry info."""
    device_id = device_id_from_device(device)
    reported = reported_state(device)
    model = _first_present(device, reported, keys=("model", "deviceModel", "hardware", "type"))
    sw_version = _first_present(
        device, reported, keys=("swVersion", "firmware", "firmwareVersion", "version")
    )
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        manufacturer=MANUFACTURER,
        name=device_name(device),
        model=str(model) if model is not None else None,
        sw_version=str(sw_version) if sw_version is not None else None,
    )


def find_value(data: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    """Find a value by exact or case-insensitive key in a nested mapping."""
    for key in keys:
        if key in data:
            return data[key]
    wanted = {key.lower() for key in keys}
    stack: list[Any] = [data]
    while stack:
        current = stack.pop()
        if not isinstance(current, Mapping):
            continue
        for key, value in current.items():
            if str(key).lower() in wanted:
                return value
            if isinstance(value, Mapping):
                stack.append(value)
    return None


def as_float(value: Any) -> float | None:
    """Return a float if possible."""
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def as_timestamp(value: Any) -> datetime | None:
    """Convert common timestamp values to timezone-aware datetimes."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:  # milliseconds
            seconds = seconds / 1000
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def compact_attributes(value: Any, *, max_length: int = 8000) -> Any:
    """Keep entity attributes from becoming extremely large."""
    text = str(value)
    if len(text) <= max_length:
        return value
    return {"truncated": True, "length": len(text), "preview": text[:max_length]}


def _first_present(*sources: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return value
    return None
