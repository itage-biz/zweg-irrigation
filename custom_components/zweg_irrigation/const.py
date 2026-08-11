"""Constants for Zweg Irrigation."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "zweg_irrigation"
NAME: Final = "Zweg Irrigation"
VERSION: Final = 1

PLATFORMS: Final = ["binary_sensor", "button", "sensor", "switch"]

CONF_CONTROLLER_NAME: Final = "controller_name"
CONF_INTERVAL_DAYS: Final = "interval_days"
CONF_START_TIME: Final = "start_time"
CONF_TRANSITION_DELAY: Final = "transition_delay"
CONF_PUMP_ENTITY_ID: Final = "pump_entity_id"
CONF_PAUSE_ENTITY_ID: Final = "pause_entity_id"
CONF_MULTIPLIER_ENTITY_ID: Final = "multiplier_entity_id"
CONF_ZONES: Final = "zones"
CONF_ZONE_ID: Final = "id"
CONF_ZONE_NAME: Final = "name"
CONF_ZONE_DURATION: Final = "duration"
CONF_ZONE_ENABLED: Final = "enabled"
CONF_ZONE_VALVES: Final = "valves"

DATA_CONTROLLER: Final = "controller"
DATA_RUNTIME_STORE: Final = "runtime_store"

EVENT_LIFECYCLE: Final = f"{DOMAIN}_lifecycle"

SERVICE_START_WATERING: Final = "start_watering"
SERVICE_STOP_WATERING: Final = "stop_watering"
SERVICE_PAUSE_WATERING: Final = "pause_watering"
SERVICE_RESUME_WATERING: Final = "resume_watering"
SERVICE_START_ZONE: Final = "start_zone"

ATTR_DEVICE_ID: Final = "device_id"
ATTR_ZONE_ID: Final = "zone_id"

STATE_IDLE: Final = "idle"
STATE_RUNNING: Final = "running"
STATE_PAUSED: Final = "paused"
STATE_FAULT_PAUSED: Final = "fault_paused"

PAUSE_MANUAL: Final = "manual"
PAUSE_CONDITION: Final = "condition"
PAUSE_RESTART: Final = "restart"
PAUSE_OUTPUT_FAULT: Final = "output_fault"

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.runtime"
RETRY_COUNT: Final = 3
RETRY_DELAY_SECONDS: Final = 5
