# Boum Garden for Home Assistant

Custom Home Assistant integration for Boum Garden devices using the Boum IoT REST API directly.

This integration is intentionally **not** a wrapper around the Node.js CLI. It talks directly to the same REST endpoints used by `boum-garden/cli`, which is better suited for Home Assistant OS, Docker and HACS installations.

## Features

- Config Flow setup from the Home Assistant UI
- Token refresh support
- Claimed device discovery
- Device status sensor with raw `reported` and `desired` state as attributes
- Common sensors when the API exposes the matching fields:
  - battery
  - temperature
  - humidity
  - moisture
  - water level
  - flow rate
  - RSSI
  - last seen
  - last pumped
  - pump state
- Pump switch using `state.desired.pumpState`
- Buttons:
  - refresh
  - restart device
  - reset last pumped
- Diagnostics with tokens redacted
- German and English translations

## Installation via HACS custom repository

1. Put this repository on GitHub, for example as `aharder3/home-assistant-boum-garden`.
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

The API expects the raw access token in the `Authorization` header, without a `Bearer` prefix.

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

The public Boum API documentation currently does not define every possible reported telemetry field. For this reason, the integration always creates a status sensor with the complete raw `reported` and `desired` state as attributes and then creates additional friendly sensors when known fields are present.

If a useful value is visible in the status sensor attributes but not exposed as a separate sensor yet, add the field name to `SENSOR_DESCRIPTIONS` in `sensor.py`.
