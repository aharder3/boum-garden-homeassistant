"""Constants for the Boum Garden integration."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "boum_garden"
NAME = "Boum Garden"
MANUFACTURER = "Boum"
VERSION = "0.1.8"

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

DEFAULT_LOCAL_PLANTS: dict[str, list[dict[str, str]]] = {
    "Pflanztopf 01": [
        {"name": "Zitronenmelisse", "icon": "mdi:leaf"},
        {"name": "Basilikum", "icon": "mdi:sprout"},
    ],
    "Pflanztopf 02": [
        {"name": "Minze", "icon": "mdi:leaf"},
        {"name": "Zitronenverbene", "icon": "mdi:sprout"},
    ],
    "Pflanztopf 03": [
        {"name": "Oregano", "icon": "mdi:sprout"},
        {"name": "Salbei", "icon": "mdi:leaf"},
    ],
    "Pflanztopf 04": [
        {"name": "Rosmarin", "icon": "mdi:sprout"},
        {"name": "Oregano", "icon": "mdi:sprout"},
    ],
    "Pflanztopf 05": [
        {"name": "Thymian", "icon": "mdi:flower"},
        {"name": "Estragon", "icon": "mdi:leaf"},
    ],
    "Pflanztopf 06": [
        {"name": "Garten-Petersilie", "icon": "mdi:sprout"},
        {"name": "Koriander", "icon": "mdi:flower"},
    ],
    "Pflanztopf 07": [
        {"name": "Majoran", "icon": "mdi:sprout"},
    ],
    "Pflanztopf 08": [
        {"name": "Wald-Erdbeere", "icon": "mdi:fruit-cherries"},
    ],
    "Pflanztopf 09": [
        {"name": "Garten-Petersilie", "icon": "mdi:sprout"},
    ],
}

# Fallback mapping from Boum plantContainerId to the visible pot number/name in the app.
# This is used only for naming/grouping plant entities; the actual plants are read from the API
# when the user endpoint exposes them.
DEFAULT_PLANT_CONTAINER_NAMES: dict[str, str] = {
    "8JQCowYT06DET0A0PFbF": "Pflanztopf 01",
    "7chPko8cD05mHlrFzOnX": "Pflanztopf 02",
    "QBI3LML3HmHnoYGKYPNU": "Pflanztopf 03",
    "3MAeoW554uDVkQIboCby": "Pflanztopf 04",
    "kSo6yFh0TMZqNlakkP1M": "Pflanztopf 05",
    "YWek5KKGv7IM7Hx2j8ev": "Pflanztopf 06",
    "lkYEbqIwNOH52SLB6Jxh": "Pflanztopf 07",
    "pMU9Lju87h2d4qDXgFIr": "Pflanztopf 08",
    "cBt849HlRDRWzuJi6G7p": "Pflanztopf 09",
}

DATA_API = "api"
DATA_COORDINATOR = "coordinator"
