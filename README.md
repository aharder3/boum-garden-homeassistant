# Boum Garden for Home Assistant

A modern custom Home Assistant integration for Boum Garden devices using the Boum REST API directly.

This integration is designed for Home Assistant Container, Home Assistant OS, Docker and HACS installations. It does not wrap the Boum CLI; it talks directly to the same documented API endpoints.

## Highlights

- UI setup through the Home Assistant config flow
- Hidden password field during setup
- Password is not stored after login
- Access and refresh token handling
- Tokens and sensitive fields are redacted from diagnostics
- Claimed Boum device discovery
- Device shadow/state fetching
- Telemetry fetching with compact summaries
- Plant container grouping via `plantContainerId`
- One Home Assistant entity per Boum plant container
- Multiple plants in the same container are shown together
- Plant care metadata as entity attributes
- Pump state, refill schedule and device status sensors
- Pump control through Home Assistant
- Optional tank calculation from API distance values and tank configuration
- Brand assets for Home Assistant 2026.3+
- German and English translations

## What the integration fetches

On every update, the integration attempts to fetch data from the documented Boum API:

- Current user: `GET /users`
- Claimed devices: `GET /devices/claimed`
- Device detail / shadow: `GET /devices/:deviceId`
- Device owner: `GET /devices/:deviceId/owner`
- Telemetry/default data: `GET /devices/:deviceId/data`
- Last-hour telemetry: `GET /devices/:deviceId/data?timeStart=-1h&interval=10s`
- Last-7-days telemetry: `GET /devices/:deviceId/data?timeStart=-7d&interval=1h`

Large telemetry series are not stored as full Home Assistant entity attributes to avoid bloating the recorder database. The full raw payload is available through Home Assistant diagnostics.

## Entity model

### Device-level entities

The integration creates device-level entities when the required API fields are available, for example:

- Status
- Firmware
- Pump state
- Desired pump state
- Reported pump state
- Pump sync status
- Refill time
- Refill interval
- Daily refill
- Maximum pump duration
- Leakage detection
- Battery, when `batteryCapacity` or another explicit battery field is available
- Temperature, when an explicit temperature field is available
- Tank level in litres or percent, when a supported water/tank field or distance field is available

The integration avoids creating guessed or phantom values. Unlabelled telemetry values are not blindly reused as battery, water level or temperature unless they can be clearly mapped.

### Plant container entities

Boum plants are grouped by `plantContainerId`.

This means:

- One plant container entity is created per Boum container.
- If multiple plants are assigned to the same container, they appear together in the same entity.
- Plant names, latin names, image URLs, water needs, light requirements, soil type, temperature range and care descriptions are exposed as attributes when available.

Example entity names may look like:

```text
sensor.garden_plant_container_01
sensor.garden_plant_container_02
sensor.garden_plant_container_03
```

The exact entity IDs depend on Home Assistant's entity naming rules and the device name.

## Water level calculation

Boum may calculate the tank level in the app frontend from a measured distance in centimetres. This integration therefore supports water level calculation only when the relevant API field is available.

Optional tank configuration:

- Tank volume in litres
- Distance when tank is empty, in cm
- Distance when tank is full, in cm

Formula:

```text
level_percent = (empty_distance_cm - current_distance_cm) / (empty_distance_cm - full_distance_cm) * 100
level_liters = level_percent * tank_volume_liters / 100
```

Values are clamped between 0 and 100 percent.

## Installation with HACS

1. Upload this repository to GitHub.
2. In Home Assistant, open **HACS → Integrations → Custom repositories**.
3. Add the repository URL.
4. Category: **Integration**.
5. Install **Boum Garden**.
6. Restart Home Assistant.
7. Go to **Settings → Devices & services → Add integration → Boum Garden**.

## Manual installation

Copy:

```text
custom_components/boum_garden
```

to:

```text
/config/custom_components/boum_garden
```

Then restart Home Assistant and add the integration through the UI.

Example for a Docker setup:

```bash
scp -r custom_components/boum_garden root@YOUR_HOME_ASSISTANT_HOST:/docker/homeassistant/custom_components/
```

Then restart the Home Assistant container.

## Configuration

During setup, enter:

- Boum email
- Boum password
- API environment: `prod`, `dev` or `local`
- Scan interval in seconds
- Optional custom API base URL

The password is only used during setup or reauthentication. It is not stored by the integration.

## API environments

Default base URLs:

```text
prod  → https://api.boum.us/v1
dev   → https://api-dev.boum.us/v1
local → http://localhost:3000/dev/v1
```

The documented local environment is a local development/proxy endpoint. It is not automatic LAN discovery of the Boum device.

## Services and automations

Turn the pump on:

```yaml
service: switch.turn_on
target:
  entity_id: switch.your_boum_pump
```

Restart the device:

```yaml
service: button.press
target:
  entity_id: button.your_boum_restart_device
```

## Dashboard

Example dashboard snippets are included in:

```text
dashboard/boum_garden_dashboard.yaml
dashboard/boum_garden_sections_view.yaml
```

The dashboard examples use Home Assistant Sections and `custom:auto-entities` so that entity IDs do not have to be hardcoded.

## Privacy and diagnostics

Diagnostics include the raw API structure where useful for debugging, but sensitive values are redacted, including:

- Email addresses
- Access tokens
- Refresh tokens
- Push tokens
- Password-like values
- API keys

## Notes

The public Boum API does not document every internal telemetry field. This integration therefore only creates confident sensors from explicit fields or clearly mapped values. Ambiguous telemetry values are exposed only as raw/diagnostic summaries and are not automatically interpreted as battery, tank level or temperature.

Per-container last watering is best-effort. If Boum exposes only global pump/refill timestamps, the integration cannot know the exact watering time for each individual container unless Boum adds per-container watering history in the future.

## Changelog

### 0.2.5

- Use explicit `batteryCapacity` for battery.
- Do not infer battery from unlabelled telemetry.
- Calculate water level only from explicit water/tank/distance fields.
- Add tank configuration for distance-based water level calculation.
- Create temperature only from explicit temperature fields.
- Create power-saving mode only from explicit power-saving fields.
- Avoid phantom values.

### 0.2.4

- Add one entity per Boum `plantContainerId`.
- Group multiple plants in the same container.
- Add plant container table sensor.
- Add pot/container dashboard examples.
- Add derived next watering information.

### 0.2.3

- Avoid mixing unlabelled telemetry with battery and water level.
- Add clearer raw telemetry summaries.

### 0.2.2

- Improve app-style device status sensors.
- Remove local plant fallback when API plants are available.

### 0.2.1

- Add best-effort last watered timestamp per plant container.
- Add derived next watering sensor.
- Suppress low-value telemetry X/Y sensors.

### 0.2.0

- Add pot-based plant container entities.
- Add grouped plant attributes per container.
- Add dashboard examples.

## License

MIT
