"""Configuration and runtime models for Zweg Irrigation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .const import (
    CONF_CONTROLLER_NAME,
    CONF_INTERVAL_DAYS,
    CONF_MULTIPLIER_ENTITY_ID,
    CONF_PAUSE_ENTITY_ID,
    CONF_PUMP_ENTITY_ID,
    CONF_START_TIME,
    CONF_TRANSITION_DELAY,
    CONF_ZONE_DURATION,
    CONF_ZONE_ENABLED,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    CONF_ZONE_VALVES,
    CONF_ZONES,
    STATE_IDLE,
)


@dataclass(frozen=True, slots=True)
class Zone:
    """A configured irrigation zone."""

    id: str
    name: str
    duration: int
    enabled: bool
    valves: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Zone:
        """Create a zone from config-entry data."""
        return cls(
            id=value[CONF_ZONE_ID],
            name=value[CONF_ZONE_NAME],
            duration=value[CONF_ZONE_DURATION],
            enabled=value[CONF_ZONE_ENABLED],
            valves=tuple(value[CONF_ZONE_VALVES]),
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialize for config-entry data."""
        return {**asdict(self), CONF_ZONE_VALVES: list(self.valves)}


@dataclass(frozen=True, slots=True)
class ControllerConfig:
    """Validated controller configuration."""

    controller_name: str
    interval_days: int
    start_time: str
    transition_delay: int
    pump_entity_id: str | None
    pause_entity_id: str | None
    multiplier_entity_id: str | None
    zones: tuple[Zone, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ControllerConfig:
        """Create a controller config from config-entry data."""
        return cls(
            controller_name=value[CONF_CONTROLLER_NAME],
            interval_days=value[CONF_INTERVAL_DAYS],
            start_time=value[CONF_START_TIME],
            transition_delay=value[CONF_TRANSITION_DELAY],
            pump_entity_id=value.get(CONF_PUMP_ENTITY_ID) or None,
            pause_entity_id=value.get(CONF_PAUSE_ENTITY_ID) or None,
            multiplier_entity_id=value.get(CONF_MULTIPLIER_ENTITY_ID) or None,
            zones=tuple(Zone.from_dict(zone) for zone in value[CONF_ZONES]),
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialize for config-entry data."""
        return {
            CONF_CONTROLLER_NAME: self.controller_name,
            CONF_INTERVAL_DAYS: self.interval_days,
            CONF_START_TIME: self.start_time,
            CONF_TRANSITION_DELAY: self.transition_delay,
            CONF_PUMP_ENTITY_ID: self.pump_entity_id,
            CONF_PAUSE_ENTITY_ID: self.pause_entity_id,
            CONF_MULTIPLIER_ENTITY_ID: self.multiplier_entity_id,
            CONF_ZONES: [zone.as_dict() for zone in self.zones],
        }


@dataclass(slots=True)
class RuntimeState:
    """Durable mutable controller state."""

    schedule_anchor: str | None = None
    enabled: bool = True
    pending_schedule: bool = False
    state: str = STATE_IDLE
    active_zone_id: str | None = None
    active_zone_index: int | None = None
    effective_zone_duration: float | None = None
    elapsed_seconds: float = 0
    remaining_seconds: float = 0
    pause_reasons: set[str] = field(default_factory=set)
    fault: str | None = None
    cycle_kind: str | None = None
    completed_zone_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> RuntimeState:
        """Deserialize persisted runtime state."""
        if not value:
            return cls()
        data = dict(value)
        data["pause_reasons"] = set(data.get("pause_reasons", []))
        return cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})

    def as_dict(self) -> dict[str, Any]:
        """Serialize runtime state."""
        data = asdict(self)
        data["pause_reasons"] = sorted(self.pause_reasons)
        return data

    @property
    def schedule_anchor_datetime(self) -> datetime | None:
        """Return the persisted anchor as an aware datetime."""
        return datetime.fromisoformat(self.schedule_anchor) if self.schedule_anchor else None
