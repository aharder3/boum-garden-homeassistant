"""Config flow for Boum Garden."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import BoumApiClient, BoumApiError, BoumAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BASE_URL_OVERRIDE,
    CONF_ENV,
    CONF_PLANT_ICON,
    CONF_PLANT_LOCATION,
    CONF_PLANT_NAME,
    CONF_PLANTS_JSON,
    CONF_TANK_EMPTY_DISTANCE_CM,
    CONF_TANK_FULL_DISTANCE_CM,
    CONF_TANK_VOLUME_LITERS,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENV,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENV_BASE_URLS,
)

_LOGGER = logging.getLogger(__name__)


class BoumGardenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Boum Garden config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: config_entries.ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return BoumGardenOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            env = user_input[CONF_ENV]
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            scan_interval = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS))
            base_url_override = (user_input.get(CONF_BASE_URL_OVERRIDE) or "").strip() or None

            session = async_get_clientsession(self.hass)
            api = BoumApiClient(
                session,
                env=env,
                base_url_override=base_url_override,
            )
            try:
                await api.sign_in(email, password)
                await api.whoami()
            except BoumAuthError:
                errors["base"] = "invalid_auth"
            except BoumApiError as err:
                _LOGGER.debug("Boum API setup failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Unexpected Boum setup error: %s", err)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"{env}:{email.lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Boum Garden ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_ENV: env,
                        CONF_ACCESS_TOKEN: api.access_token,
                        CONF_REFRESH_TOKEN: api.refresh_token,
                        CONF_SCAN_INTERVAL: scan_interval,
                        **({CONF_BASE_URL_OVERRIDE: base_url_override} if base_url_override else {}),
                    },
                    options={CONF_SCAN_INTERVAL: scan_interval},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Start reauthentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        """Handle reauthentication."""
        errors: dict[str, str] = {}
        if not self._reauth_entry:
            return self.async_abort(reason="reauth_successful")

        email = self._reauth_entry.data.get(CONF_EMAIL, "")
        env = self._reauth_entry.data.get(CONF_ENV, DEFAULT_ENV)
        base_url_override = self._reauth_entry.data.get(CONF_BASE_URL_OVERRIDE)

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = BoumApiClient(session, env=env, base_url_override=base_url_override)
            try:
                await api.sign_in(email, user_input[CONF_PASSWORD])
                await api.whoami()
            except BoumAuthError:
                errors["base"] = "invalid_auth"
            except BoumApiError:
                errors["base"] = "cannot_connect"
            else:
                new_data = dict(self._reauth_entry.data)
                new_data[CONF_ACCESS_TOKEN] = api.access_token
                new_data[CONF_REFRESH_TOKEN] = api.refresh_token
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=new_data)
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }),
            description_placeholders={"email": str(email)},
            errors=errors,
        )


class BoumGardenOptionsFlow(config_entries.OptionsFlow):
    """Handle Boum Garden options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = int(
            self._config_entry.options.get(
                CONF_SCAN_INTERVAL,
                self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
            )
        )
        options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=60, max=86400)
                    ),
                    vol.Optional(
                        CONF_PLANT_NAME,
                        default=options.get(CONF_PLANT_NAME, ""),
                    ): str,
                    vol.Optional(
                        CONF_PLANT_LOCATION,
                        default=options.get(CONF_PLANT_LOCATION, ""),
                    ): str,
                    vol.Optional(
                        CONF_PLANT_ICON,
                        default=options.get(CONF_PLANT_ICON, "mdi:sprout"),
                    ): str,
                    vol.Optional(
                        CONF_PLANTS_JSON,
                        default=options.get(CONF_PLANTS_JSON, ""),
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                    vol.Optional(
                        CONF_TANK_VOLUME_LITERS,
                        default=str(options.get(CONF_TANK_VOLUME_LITERS, "")),
                    ): str,
                    vol.Optional(
                        CONF_TANK_EMPTY_DISTANCE_CM,
                        default=str(options.get(CONF_TANK_EMPTY_DISTANCE_CM, "")),
                    ): str,
                    vol.Optional(
                        CONF_TANK_FULL_DISTANCE_CM,
                        default=str(options.get(CONF_TANK_FULL_DISTANCE_CM, "")),
                    ): str,
                }
            ),
            description_placeholders={
                "tank_help": (
                    "Use the main Boum tank volume, not the 2 L pot reservoir. "
                    "Known Boum tanks are 32 L (small) and 35 L (large). "
                    "Water level is calculated only when Boum exposes a distance in cm."
                )
            },
        )


def _user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    defaults = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): str,
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_ENV, default=defaults.get(CONF_ENV, DEFAULT_ENV)): SelectSelector(
                SelectSelectorConfig(
                    options=list(ENV_BASE_URLS.keys()),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
            ): vol.All(vol.Coerce(int), vol.Range(min=60, max=86400)),
            vol.Optional(
                CONF_BASE_URL_OVERRIDE,
                default=defaults.get(CONF_BASE_URL_OVERRIDE, ""),
            ): str,
        }
    )
