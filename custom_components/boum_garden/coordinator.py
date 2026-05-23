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
from .helpers import compact_attributes, desired_state, device_id_from_device

_LOGGER = logging.getLogger(__name__)


class BoumGardenDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch Boum devices, user data, shadows, owners and telemetry."""

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
        self.user: dict[str, Any] = {}
        self.last_api_errors: dict[str, str] = {}

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
                # User/owner data stays available in diagnostics but should not be
                # turned into Home Assistant entities.
                if device_errors:
                    full["_api_errors"] = device_errors
                return device_id_from_device(full), full

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


def _latest_telemetry_row(payload: Any) -> dict[str, Any]:
    """Extract the latest telemetry row from common API response shapes."""
    rows = _find_telemetry_rows(payload)
    if not rows:
        if isinstance(payload, Mapping):
            simple = {k: v for k, v in payload.items() if _is_simple(v)}
            return dict(simple)
        return {}

    def sort_key(row: Mapping[str, Any]) -> str:
        for key in ("timestamp", "time", "createdAt", "created_at", "date", "ts"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    return dict(sorted(rows, key=sort_key)[-1])


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
        summary[name] = {
            "rows": len(rows),
            "latest": compact_attributes(latest),
            "available": bool(rows or payload),
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
