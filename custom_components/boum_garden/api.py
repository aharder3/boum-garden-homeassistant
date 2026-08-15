"""Async Boum Garden REST API client."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import aiohttp
import async_timeout

from .const import ENV_BASE_URLS

TokenUpdateCallback = Callable[[str | None, str | None], Awaitable[None]]


class BoumApiError(Exception):
    """Base error for Boum API failures."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class BoumAuthError(BoumApiError):
    """Authentication error."""


class BoumApiClient:
    """Small aiohttp client for the Boum IoT REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        env: str = "prod",
        access_token: str | None = None,
        refresh_token: str | None = None,
        base_url_override: str | None = None,
        token_update_callback: TokenUpdateCallback | None = None,
        timeout: int = 20,
    ) -> None:
        self._session = session
        self._env = env
        self._base_url_override = base_url_override
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._token_update_callback = token_update_callback
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        """Return the effective base URL."""
        if self._base_url_override:
            return self._base_url_override.rstrip("/")
        return ENV_BASE_URLS.get(self._env, ENV_BASE_URLS["prod"]).rstrip("/")

    async def sign_in(self, email: str, password: str) -> dict[str, Any]:
        """Sign in and store the returned access and refresh tokens."""
        data = await self._request(
            "POST",
            "/auth/signin",
            json={"email": email, "password": password},
            auth=False,
            retry=False,
        )
        self.access_token = _first_str(data, "accessToken", "access_token")
        self.refresh_token = _first_str(data, "refreshToken", "refresh_token")
        if not self.access_token or not self.refresh_token:
            raise BoumAuthError("Boum did not return access and refresh tokens")
        await self._save_tokens()
        return data

    async def refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        if not self.refresh_token:
            raise BoumAuthError("No Boum refresh token available", status=401)

        data = await self._request(
            "POST",
            "/auth/token",
            json={"refreshToken": self.refresh_token},
            auth=False,
            retry=False,
        )
        self.access_token = _first_str(data, "accessToken", "access_token") or self.access_token
        self.refresh_token = _first_str(data, "refreshToken", "refresh_token") or self.refresh_token
        if not self.access_token:
            raise BoumAuthError("Could not refresh Boum access token", status=401)
        await self._save_tokens()

    async def whoami(self) -> dict[str, Any]:
        """Return the current Boum user."""
        return await self._request("GET", "/users")

    async def list_claimed_devices(self) -> list[dict[str, Any]]:
        """Return claimed devices."""
        data = await self._request("GET", "/devices/claimed")
        return _coerce_devices(data)

    async def get_device(self, device_id: str) -> dict[str, Any]:
        """Return the full shadow for a device."""
        return await self._request("GET", f"/devices/{device_id}")

    async def get_device_owner(self, device_id: str) -> dict[str, Any]:
        """Return owner information for a device."""
        return await self._request("GET", f"/devices/{device_id}/owner")

    async def update_device_desired_state(
        self, device_id: str, desired_state: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Patch a device's desired shadow state."""
        return await self._request(
            "PATCH",
            f"/devices/{device_id}",
            json={"state": {"desired": dict(desired_state)}},
        )

    async def set_pump_state(self, device_id: str, enabled: bool) -> dict[str, Any]:
        """Turn the pump on or off."""
        return await self.update_device_desired_state(
            device_id, {"pumpState": "on" if enabled else "off"}
        )

    async def send_device_command(self, device_id: str, command: str) -> dict[str, Any]:
        """Send a Boum device command."""
        if command not in {"restartDevice", "resetLastPumped", "resetWiFiCredentials"}:
            raise BoumApiError(f"Unsupported Boum device command: {command}")
        return await self.update_device_desired_state(
            device_id, {"deviceCommands": [command]}
        )

    async def get_device_data(
        self,
        device_id: str,
        *,
        time_start: str | None = None,
        time_end: str | None = None,
        interval: str | None = None,
    ) -> Any:
        """Return telemetry data for a device."""
        params: dict[str, str] = {}
        if time_start:
            params["timeStart"] = time_start
        if time_end:
            params["timeEnd"] = time_end
        if interval:
            params["interval"] = interval
        return await self._request("GET", f"/devices/{device_id}/data", params=params)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        auth: bool = True,
        retry: bool = True,
    ) -> Any:
        """Perform a request and unwrap the Boum `{data: ...}` envelope."""
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        if json is not None:
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.access_token:
                raise BoumAuthError("No Boum access token available", status=401)
            # Boum expects the raw token in Authorization; no Bearer prefix.
            headers["Authorization"] = self.access_token

        try:
            with async_timeout.timeout(self._timeout):
                response = await self._session.request(
                    method, url, headers=headers, json=json, params=params
                )
                body = await _read_json_or_text(response)
        except TimeoutError as err:
            raise BoumApiError("Timeout while talking to Boum API") from err
        except aiohttp.ClientError as err:
            raise BoumApiError(f"Could not connect to Boum API: {err}") from err

        if response.status == 401 and auth and retry and self.refresh_token:
            await self.refresh_access_token()
            return await self._request(
                method, path, json=json, params=params, auth=auth, retry=False
            )

        if response.status == 401:
            raise BoumAuthError(_error_message(body, "Authentication failed"), status=401)

        if response.status >= 400:
            raise BoumApiError(_error_message(body, "Boum API error"), status=response.status)

        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    async def _save_tokens(self) -> None:
        """Persist updated tokens through Home Assistant."""
        if self._token_update_callback:
            await self._token_update_callback(self.access_token, self.refresh_token)


async def _read_json_or_text(response: aiohttp.ClientResponse) -> Any:
    """Read a response as JSON when possible, otherwise text."""
    try:
        return await response.json(content_type=None)
    except Exception:  # noqa: BLE001 - fallback for non-json error bodies
        return await response.text()


def _error_message(body: Any, fallback: str) -> str:
    """Extract an API error message."""
    if isinstance(body, Mapping):
        for key in ("message", "error", "detail", "title"):
            value = body.get(key)
            if value:
                return str(value)
    if isinstance(body, str) and body.strip():
        return body.strip()
    return fallback


def _first_str(data: Any, *keys: str) -> str | None:
    """Return the first non-empty string from a mapping."""
    if not isinstance(data, Mapping):
        return None
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _coerce_devices(data: Any) -> list[dict[str, Any]]:
    """Coerce common device list response shapes into a list of dictionaries."""
    if isinstance(data, list):
        return [dict(item) for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        for key in ("devices", "items", "results", "claimedDevices", "claimed_devices"):
            value = data.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
        return [dict(data)]
    return []
