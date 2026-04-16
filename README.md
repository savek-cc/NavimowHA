# Navimow Integration for Home Assistant

Cloud integration for Segway Navimow robotic mowers. Exposes each mower as a
native `lawn_mower` entity in Home Assistant, with a diagnostic battery sensor
and real-time state updates via MQTT push.

## Features

- Native `lawn_mower` entity per device with `start_mowing`, `pause`, `dock`,
  and `resume` actions
- Diagnostic `sensor.*_battery` entity (battery percentage, `SensorDeviceClass.BATTERY`)
- Real-time state updates via MQTT push from the Segway cloud
- Automatic HTTP polling fallback (every 60 s) when MQTT is stale for more
  than 5 minutes
- Extra state attributes: status, signal strength, position, error code,
  device metrics
- Diagnostics download (`last_data_source`, MQTT staleness, HTTP fallback
  activity) from the integration's "Download Diagnostics" menu
- OAuth2 config flow — no manual credentials entered in the UI
- Multi-device support (all mowers bound to the Segway account appear as
  separate devices)

## Supported Devices

- Segway Navimow **i-Series** (i105E, i108E, i110N, i115N, etc.)
- Segway Navimow **H-Series** (H800E, H1500E, H3000E, etc.)
- Segway Navimow **X-Series** (X3, X315, X330, X350, etc.)

Any mower that the official Segway Navimow app exposes through the Segway
cloud API should work. Firmware restrictions are enforced by the cloud, not
by this integration — if the app can talk to it, the integration can too.

The integration currently targets the **EU server** of the Segway API
(`navimow-fra.ninebot.com`). Accounts registered on other regional servers
(US, APAC, CN) are not supported at this time.

## Installation

### HACS (recommended)

1. Open HACS → Integrations → top-right menu → **Custom repositories**
2. Add the repository:
   - Repository URL: `https://github.com/segwaynavimow/NavimowHA`
   - Category: **Integration**
3. Search for **Navimow** in HACS and install
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** and search
   for **Navimow**

### Manual

```bash
cd /config
git clone https://github.com/segwaynavimow/NavimowHA.git /tmp/NavimowHA
mkdir -p custom_components
cp -r /tmp/NavimowHA/custom_components/navimow custom_components/
```

Restart Home Assistant, then add the integration from **Settings → Devices
& Services**.

### Prerequisites

- Home Assistant **2026.1.0** or newer
- Outbound internet access from HA to `*.ninebot.com` and
  `*.willand.com` (HTTPS and WebSocket)
- A Segway Navimow account that works in the official mobile app
- The Python package `navimow-sdk==0.1.2` (installed automatically from
  `manifest.json` requirements)

## Configuration

Configuration is performed entirely through the Home Assistant UI. There are
no YAML options and no manual parameters.

When you add the integration:

1. Click **Add Integration** → **Navimow**
2. HA opens a browser window pointing at the Segway login page
3. Sign in with your Segway Navimow account
4. The browser redirects back to Home Assistant and the config entry is
   created; all devices bound to the account are discovered automatically

OAuth2 client credentials are currently shipped inside `const.py`. A future
release will migrate to the standard `application_credentials` helper so users
can override them if Segway rotates the values.

### Configuration options (Options Flow)

No runtime options are currently exposed in the Options Flow. The following
values are defined as constants in `custom_components/navimow/const.py` and
can only be changed by editing the source:

| Constant                     | Default           | Purpose                                                   |
|------------------------------|-------------------|-----------------------------------------------------------|
| `UPDATE_INTERVAL`            | `30` s            | Coordinator tick — how often cached MQTT state is pushed  |
| `MQTT_STALE_SECONDS`         | `300` s           | After this long without MQTT traffic, HTTP fallback runs  |
| `HTTP_FALLBACK_MIN_INTERVAL` | `3600` s          | Minimum gap between HTTP fallback fetches (rate limiting) |
| `API_BASE_URL`               | EU server         | Segway cloud endpoint                                     |

## How data is updated

The integration prefers MQTT push and only falls back to HTTP polling when
push is stale.

- **MQTT push (primary).** On startup, the integration calls
  `/mqtt/userInfo/get/v2` to obtain WebSocket MQTT credentials and connects
  to the Segway broker. State (`DeviceStateMessage`) and attribute
  (`DeviceAttributesMessage`) updates are delivered in near real time and
  pushed straight into the coordinator via `async_set_updated_data`.
- **HTTP fallback.** The coordinator ticks every 30 s. If no MQTT message
  has been received for more than `MQTT_STALE_SECONDS` (default 300 s), it
  calls `GET /device/status` — rate-limited to at most once every
  `HTTP_FALLBACK_MIN_INTERVAL` (default 3600 s) to avoid hammering the API.
- **Circuit breaker handling.** The Segway API applies a circuit breaker to
  `/mqtt/userInfo/get/v2`. If that endpoint fails during setup, the
  integration falls back to MQTT credentials cached in the config entry from
  the previous successful run. Real-time updates may be delayed until the
  Segway API recovers, but the entity stays available via HTTP fallback.
- **OAuth token refresh.** The token is refreshed on every coordinator tick
  and before each outbound command. On MQTT disconnect, MQTT credentials
  are re-fetched (they are tied to the OAuth token and become invalid when
  the token rotates).
- **Data source reporting.** The coordinator exposes `last_data_source`
  (`mqtt_push`, `mqtt_cache`, or `http_fallback`) via the Diagnostics
  download.

## Supported Actions

The `lawn_mower` entity implements the standard HA actions:

```yaml
# Start mowing
action: lawn_mower.start_mowing
target:
  entity_id: lawn_mower.navimow

# Pause an active mow
action: lawn_mower.pause
target:
  entity_id: lawn_mower.navimow

# Send back to the charging dock
action: lawn_mower.dock
target:
  entity_id: lawn_mower.navimow
```

The integration also implements `async_resume`, which can be called via
`lawn_mower.start_mowing` from a paused state (HA maps START to resume when
the current activity is `paused`).

## Example automations

Start mowing in the morning if the weather is dry:

```yaml
alias: Navimow - mow when dry
triggers:
  - trigger: time
    at: "09:00:00"
conditions:
  - condition: numeric_state
    entity_id: sensor.openweathermap_forecast_precipitation_probability
    below: 30
  - condition: state
    entity_id: lawn_mower.navimow
    state: docked
actions:
  - action: lawn_mower.start_mowing
    target:
      entity_id: lawn_mower.navimow
```

Send the mower home when rain is detected:

```yaml
alias: Navimow - dock on rain
triggers:
  - trigger: state
    entity_id: binary_sensor.rain_detected
    to: "on"
actions:
  - action: lawn_mower.dock
    target:
      entity_id: lawn_mower.navimow
```

Notify when battery drops below 20 %:

```yaml
alias: Navimow - low battery alert
triggers:
  - trigger: numeric_state
    entity_id: sensor.navimow_battery
    below: 20
actions:
  - action: notify.mobile_app
    data:
      message: "Navimow battery at {{ states('sensor.navimow_battery') }} %"
```

## Known limitations

- **Cloud-only.** There is no local control path. Any outage of the Segway
  cloud API or MQTT broker will affect the integration.
- **Circuit breaker on MQTT credentials.** The Segway API applies a circuit
  breaker to `/mqtt/userInfo/get/v2`. When it trips, the integration falls
  back to cached MQTT credentials; real-time updates may be unavailable
  until the API recovers.
- **Cutting-height control is not exposed.** The Segway cloud API does not
  offer a REST endpoint for blade height — only the mobile app can set it.
- **Map and zone management is not supported.** Mowing zones, no-go areas,
  and map editing remain in the Segway Navimow app.
- **EU server only.** The integration hard-codes the Frankfurt
  (`navimow-fra.ninebot.com`) endpoint; US / APAC / CN accounts are not
  supported.
- **Client credentials hard-coded.** `CLIENT_ID` and `CLIENT_SECRET` live in
  `const.py`. A future release will migrate to `application_credentials`.

## Troubleshooting

Enable debug logging before reproducing an issue by adding this to
`configuration.yaml` and restarting Home Assistant:

```yaml
logger:
  default: info
  logs:
    custom_components.navimow: debug
    mower_sdk: debug
```

**OAuth login fails or the browser returns an error.**
Make sure your HA instance can reach `navimow-h5-fra.willand.com` and
`navimow-fra.ninebot.com`. If you use DNS filtering or ad-blocking,
temporarily disable it — some lists block `*.ninebot.com`. Re-trigger the
flow from **Settings → Devices & Services → Navimow → Reconfigure**.

**Entity is available but state never changes (no real-time updates).**
MQTT push is probably not connected. Enable debug logging (above), restart
HA, and grep the log for `MQTT connected callback` / `MQTT status probe`.
If MQTT is down, the entity still updates via HTTP fallback every hour; a
full recovery typically happens automatically once the Segway API's
circuit breaker closes again. Check diagnostics
(**Download Diagnostics** on the device page) — `last_data_source` should
eventually read `mqtt_push`.

**Device shows as unavailable.**
This means neither MQTT nor the HTTP fallback produced any state. Verify
that the mower is online in the official Navimow app. If the app shows it
online but HA does not, capture a debug log covering a full HA restart and
file an issue.

## Removing the integration

1. **Settings → Devices & Services** → open the Navimow entry → three-dot
   menu → **Delete**. HA removes the config entry, all entities, and the
   device registry records.
2. Remove the custom component:
   - **HACS**: HACS → Integrations → Navimow → three-dot menu → **Remove**
   - **Manual install**: delete `config/custom_components/navimow/`
3. Restart Home Assistant.
4. Optionally revoke the authorization in the Segway Navimow app (Account
   → Third-party authorizations).

## Contributing / Issues

Issues and pull requests are welcome at
<https://github.com/segwaynavimow/NavimowHA/issues>. Development happens on
the `quality_improvements` branch; please target PRs there.

## License

See the `LICENSE` file in the repository root. Absent a `LICENSE` file, refer
to the upstream repository.
