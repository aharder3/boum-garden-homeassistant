<p align="center">
  <img src="images/boum_garden_logo.png" width="180" alt="Boum Garden">
</p>

# Boum Garden for Home Assistant

Custom Home Assistant integration for Boum Garden devices using the Boum IoT REST API directly.

This integration is intentionally **not** a wrapper around the Node.js CLI. It talks directly to the same REST endpoints used by `boum-garden/cli`, which is better suited for Home Assistant OS, Docker and HACS installations.

## What it fetches

On every update the integration tries to fetch the data that is documented in the public Boum CLI/API reference:

- current Boum user: `GET /users`
- claimed devices: `GET /devices/claimed`
- full device shadow: `GET /devices/:deviceId`
- device owner: `GET /devices/:deviceId/owner`
- telemetry/default data: `GET /devices/:deviceId/data`
- last-hour telemetry: `GET /devices/:deviceId/data?timeStart=-1h&interval=10s`
- last-7-days telemetry: `GET /devices/:deviceId/data?timeStart=-7d&interval=1h`

Large telemetry series are **not** stored as full entity attributes to avoid bloating the Home Assistant recorder database. Instead, the integration stores compact summaries and exposes the latest values as entities/attributes. The full raw API payload is available in Home Assistant diagnostics.

## Features

- Config Flow setup from the Home Assistant UI
- Password field is hidden during setup
- Password is not stored after login
- Token refresh support
- Tokens are redacted from diagnostics
- Claimed device discovery
- Device detail/shadow fetching
- Owner fetching
- Telemetry fetching for default/24h, last hour and last 7 days
- Status sensor with compact raw `reported`, `desired`, latest telemetry and API section attributes
- Plant summary sensor that extracts plant objects/names when the API exposes them
- Pump desired/reported/sync sensors so it is visible when a command is pending
- Dynamic sensors for useful scalar values returned by `reported`, `desired` and latest telemetry
- Owner/user/token-like API fields are not exposed as normal entities to avoid nonsense values and privacy leaks
- Common friendly sensors when matching fields are present:
  - battery
  - temperature
  - humidity
  - moisture / soil moisture
  - water level
  - flow rate
  - RSSI
  - last seen
  - last pumped
  - pump state
  - firmware
  - model
  - online / connection status
  - refill schedule and tuning values
  - leakage detection
- Pump switch using `state.desired.pumpState`
- Buttons:
  - refresh
  - restart device
  - reset last pumped
  - reset Wi-Fi credentials, disabled by default because it is disruptive
- Local brand assets for Home Assistant 2026.3+:
  - `custom_components/boum_garden/brand/icon.png`
  - `custom_components/boum_garden/brand/logo.png`
  - dark and 2x variants
- German and English translations

## Installation via HACS custom repository

1. Put this repository on GitHub, for example as `aharder3/boum-garden-homeassistant`.
2. In Home Assistant open **HACS → Integrations → ⋮ → Custom repositories**.
3. Add the repository URL.
4. Category: **Integration**.
5. Install **Boum Garden**.
6. Restart Home Assistant.
7. Go to **Settings → Devices & services → Add integration → Boum Garden**.

## Manual installation

Copy this folder:

```text
custom_components/boum_garden
```

to:

```text
/config/custom_components/boum_garden
```

Then restart Home Assistant and add the integration from the UI.

Example for a Docker setup where Home Assistant config lives under `/docker/homeassistant`:

```bash
scp -r custom_components/boum_garden root@192.168.45.30:/docker/homeassistant/custom_components/
```

Then restart the Home Assistant container.

## Configuration

During setup, enter:

- Boum email
- Boum password
- API environment: `prod`, `dev`, or `local`
- Scan interval in seconds; default is `300`
- Optional custom API base URL

The integration stores the access and refresh token in Home Assistant's config entry storage. The password is used only during setup or reauthentication and is not stored by the integration.

## API behaviour

The Boum API uses these base URLs:

- `prod`: `https://api.boum.us/v1`
- `dev`: `https://api-dev.boum.us/v1`
- `local`: `http://localhost:3000/dev/v1`

The API expects the raw access token in the `Authorization` header, without a `Bearer` prefix. Successful responses are normally wrapped in a `{ "data": ... }` envelope.

The documented `local` environment is a local API development/proxy endpoint. It is **not** automatic LAN discovery of the Boum device IP. If you build or run your own local proxy, enter that proxy URL as custom API base URL.

## Automation examples

Turn the Boum pump on:

```yaml
service: switch.turn_on
target:
  entity_id: switch.boum_xxxxxx_pump
```

Restart a Boum device:

```yaml
service: button.press
target:
  entity_id: button.boum_xxxxxx_restart_device
```

## Notes

The public Boum API documentation does not define every possible reported telemetry field and does not document a separate plant catalogue endpoint. For this reason, the integration creates friendly known sensors where possible and extracts plant objects/names only when they appear in `reported`, `desired`, device detail or telemetry payloads.

The full raw payload is available via Home Assistant diagnostics. If the plant names are not in diagnostics either, the public API currently does not expose them to this integration.

If Boum exposes plant objects such as `plants[0].moisture`, they should appear in the plant summary and as dynamic sensors after a Home Assistant restart/reload. If a new field only appears later, reload the integration so Home Assistant can create the new entity.
