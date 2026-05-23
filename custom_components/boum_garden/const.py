"""Constants for the Boum Garden integration."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "boum_garden"
NAME = "Boum Garden"
MANUFACTURER = "Boum"
VERSION = "0.1.3"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]

CONF_ENV = "env"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_BASE_URL_OVERRIDE = "base_url_override"

DEFAULT_ENV = "prod"
DEFAULT_SCAN_INTERVAL_SECONDS = 300
DEFAULT_SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)

ENV_BASE_URLS = {
    "prod": "https://api.boum.us/v1",
    "dev": "https://api-dev.boum.us/v1",
    "local": "http://localhost:3000/dev/v1",
}

DATA_API = "api"
DATA_COORDINATOR = "coordinator"
