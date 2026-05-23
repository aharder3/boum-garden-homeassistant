"""Constants for the Boum Garden integration."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "boum_garden"
NAME = "Boum Garden"
MANUFACTURER = "Boum"
VERSION = "0.2.2"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]

CONF_ENV = "env"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_BASE_URL_OVERRIDE = "base_url_override"
CONF_PLANT_NAME = "plant_name"
CONF_PLANT_LOCATION = "plant_location"
CONF_PLANT_ICON = "plant_icon"
CONF_PLANTS_JSON = "plants_json"

DEFAULT_ENV = "prod"
DEFAULT_SCAN_INTERVAL_SECONDS = 300
DEFAULT_SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)

ENV_BASE_URLS = {
    "prod": "https://api.boum.us/v1",
    "dev": "https://api-dev.boum.us/v1",
    "local": "http://localhost:3000/dev/v1",
}

# Plant/container names are intentionally not hard-coded.
# The integration derives them from Boum API data or optional user-provided settings.

DATA_API = "api"
DATA_COORDINATOR = "coordinator"
