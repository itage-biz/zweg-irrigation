# Zweg Irrigation

Zweg Irrigation is a Home Assistant custom integration for ordered, scheduled
irrigation zones. It orchestrates existing Home Assistant `switch` entities; it does
not implement MQTT, HTTP, Zigbee, Z-Wave, flow sensing, weather calculations, or
notification delivery.

> **Safety warning:** Automation cannot prove that water is flowing safely. Use
> compatible valves, fit appropriate physical safety equipment, and test every zone
> while supervised. This integration turns outputs off when it is stopped, paused,
> Home Assistant stops, or an output command fails.

## Requirements

- Home Assistant Core 2026.7.0 or later.
- A `switch` entity for every valve and, optionally, the pump.
- Optionally, a `binary_sensor` or `input_boolean` that enables watering when on.
- Optionally, a `number` or `input_number` entity supplying a finite positive duration multiplier.
- HACS is optional.

## Installation

### HACS

1. Install HACS.
2. Add `https://github.com/itage-biz/zweg-irrigation` as a custom **Integration** repository.
3. Download **Zweg Irrigation**.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration → Zweg Irrigation**.

### Manual

Download the matching GitHub Release asset and extract it into `/config` so it
creates `/config/custom_components/zweg_irrigation/`. Restart Home Assistant and
add the integration from **Settings → Devices & services**.

HACS uses GitHub Releases when they are available and falls back to the default
branch otherwise. Releases are preferred for stable installations.

## Configuration

Create one controller for each irrigation system. Choose a calendar interval, local
start time, optional pump, optional irrigation-enabled entity, optional multiplier, and one or
more zones. Each zone has a stable ID, name, enabled default, duration in seconds,
and one or more valve switches. Zone order is editable in the integration options.

The controller starts the pump before the first enabled zone, keeps it on through
zone handoffs, and turns it off after the final zone. A multiplier is read just
before every zone and applies only to that zone. An irrigation-enabled entity must
be on; off, unavailable, and unknown states block watering.

## Actions

Every action targets the controller device. `start_zone` also needs its configured
zone ID.

```yaml
action: zweg_irrigation.start_watering
target:
  device_id: YOUR_CONTROLLER_DEVICE_ID
```

```yaml
action: zweg_irrigation.start_zone
target:
  device_id: YOUR_CONTROLLER_DEVICE_ID
data:
  zone_id: stable-zone-id
```

Available actions are `start_watering`, `stop_watering`, `pause_watering`,
`resume_watering`, and `start_zone`.

## Events and lifecycle

The integration emits `zweg_irrigation_lifecycle` events. They include a controller
ID, UTC timestamp, remaining seconds, event name, and zone ID/name or reason where
applicable:

```yaml
event_type: zweg_irrigation_lifecycle
data:
  event: zone_started
  controller_id: abc123
  zone_id: front-lawn
  zone_name: Front lawn
  remaining_seconds: 600
```

Schedules use local calendar days. A non-existent spring DST wall time runs at the
first valid instant after the gap; a repeated autumn wall time runs once at its first
occurrence. Due cycles that overlap a run or pause coalesce into one pending cycle.
On Home Assistant shutdown, all outputs are turned off and only unwatered remaining
time is eligible for automatic resume after startup. Manual and output-fault pauses
always require a manual Resume.

## Dashboard and troubleshooting

Add the controller status, current zone, next run, remaining time, watering, and
paused entities to a dashboard; add per-zone enabled, watering, and remaining-time
entities beside their controls. If watering does not start, check global enable,
irrigation-enabled entity state, multiplier value, enabled zones, and switch availability.
Output actions are retried three times at five-second intervals before the controller
enters fault-paused; inspect the lifecycle event and Home Assistant log, repair the
output, then use Resume.

Back up Home Assistant configuration and storage before upgrades. Review release
notes, update through HACS or install the matching release asset, then restart Home
Assistant. Report issues at https://github.com/itage-biz/zweg-irrigation/issues with
Home Assistant version, integration version, relevant lifecycle event, and logs.

## Development and releases

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup and validation. Maintainers
update `manifest.json` and release notes in a reviewed pull request, merge to
`master`, then push a matching `vX.Y.Z` tag. The release workflow verifies the tag,
packages the installable directory, and publishes the GitHub Release.

Compatibility is limited to Home Assistant Core 2026.7.0+ and its supported Python
runtime.
