"""Serialized irrigation state machine and output safety controls."""

from __future__ import annotations

import asyncio
import logging
import math
import time as time_module
from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.components.logbook import async_log_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_LIFECYCLE,
    PAUSE_CONDITION,
    PAUSE_MANUAL,
    PAUSE_OUTPUT_FAULT,
    PAUSE_RESTART,
    RETRY_COUNT,
    RETRY_DELAY_SECONDS,
    STATE_FAULT_PAUSED,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_RUNNING,
)
from .models import ControllerConfig, RuntimeState, Zone
from .runtime import RuntimeStore
from .schedule import first_anchor_after, next_occurrence

_LOGGER = logging.getLogger(__name__)


class OutputError(RuntimeError):
    """A configured output could not be controlled safely."""


class IrrigationController:
    """Own one serialized watering controller for a config entry."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, runtime_store: RuntimeStore
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.config = ControllerConfig.from_dict({**entry.data, **entry.options})
        self._runtime_store = runtime_store
        self.runtime = RuntimeState()
        self.enabled = True
        self._lock = asyncio.Lock()
        self._schedule_cancel: Callable[[], None] | None = None
        self._zone_task: asyncio.Task[None] | None = None
        self._zone_started_monotonic: float | None = None
        self._zone_remaining_at_start: float = 0
        self._unsubscribers: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = []

    async def async_start(self) -> None:
        """Restore state, subscribe to HA events, and arm the schedule."""
        self.runtime = await self._runtime_store.async_load()
        self.enabled = self.runtime.enabled
        if self.config.pause_entity_id:
            self._unsubscribers.append(
                async_track_state_change_event(
                    self.hass, [self.config.pause_entity_id], self._async_pause_condition_changed
                )
            )
        self._unsubscribers.append(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_hass_stop)
        )
        await self._async_refresh_condition_pause()
        if self.paused and self.runtime.state == STATE_IDLE:
            self.runtime.state = STATE_PAUSED
        await self._async_arm_schedule(reset_anchor=self.runtime.schedule_anchor is None)
        if self.runtime.active_zone_id:
            await self._async_safe_off()
            self.runtime.pause_reasons.add(PAUSE_RESTART)
            self.runtime.state = STATE_PAUSED
            await self._persist()
            if self._can_auto_resume_after_restart():
                self.runtime.pause_reasons.discard(PAUSE_RESTART)
                await self.async_resume()
        self._notify()

    async def async_stop_listeners(self) -> None:
        """Cancel listeners and active timers during entry unload."""
        if self._schedule_cancel:
            self._schedule_cancel()
            self._schedule_cancel = None
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        await self._async_cancel_zone_task()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe an entity to immediate controller changes."""
        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.remove(listener)

        return remove_listener

    @property
    def status(self) -> str:
        """Current controller status."""
        return self.runtime.state

    @property
    def active_zone(self) -> Zone | None:
        """Current active zone, if any."""
        if self.runtime.active_zone_id is None:
            return None
        return next(
            (zone for zone in self.config.zones if zone.id == self.runtime.active_zone_id), None
        )

    @property
    def paused(self) -> bool:
        """Whether any pause cause blocks watering."""
        return bool(self.runtime.pause_reasons)

    @property
    def next_run(self) -> datetime | None:
        """Return the next future calendar occurrence."""
        anchor = self.runtime.schedule_anchor_datetime
        if anchor is None:
            return None
        return next_occurrence(anchor, self.config.interval_days, dt_util.now())

    @property
    def total_remaining_seconds(self) -> float:
        """Return the active and queued cycle estimate, or zero while idle."""
        if self.runtime.state not in (STATE_RUNNING, STATE_PAUSED, STATE_FAULT_PAUSED):
            return 0
        multiplier = self._multiplier()
        queued = (
            sum(
                zone.duration * multiplier
                for zone in self._remaining_zones()
                if zone.id != self.runtime.active_zone_id
            )
            if multiplier is not None
            else 0
        )
        return self._current_remaining() + queued

    def zone_remaining_seconds(self, zone_id: str) -> float:
        """Return the current zone count down or queued estimate."""
        if self.runtime.state == STATE_IDLE or zone_id in self.runtime.completed_zone_ids:
            return 0
        if zone_id == self.runtime.active_zone_id:
            return self._current_remaining()
        zone = next((item for item in self._remaining_zones() if item.id == zone_id), None)
        multiplier = self._multiplier()
        return zone.duration * multiplier if zone and multiplier is not None else 0

    async def async_start_cycle(self, *, scheduled: bool = False) -> bool:
        """Start a full cycle if it is safe to do so."""
        async with self._lock:
            return await self._async_start_cycle_locked(scheduled=scheduled)

    async def _async_start_cycle_locked(self, *, scheduled: bool) -> bool:
        """Start a cycle while the state-machine lock is held."""
        if not self.enabled or self.runtime.state != STATE_IDLE or self.paused:
            return False
        if not self._enabled_zones():
            return False
        if self._multiplier() is None:
            if scheduled:
                await self._async_emit("schedule_skipped", reason="invalid_multiplier")
            return False
        self.runtime.cycle_kind = "scheduled" if scheduled else "manual"
        self.runtime.completed_zone_ids = []
        self.runtime.pending_schedule = False
        await self._async_begin_zone(self._first_pending_zone())
        return True

    async def async_start_zone(self, zone_id: str) -> bool:
        """Start exactly one configured, enabled zone."""
        async with self._lock:
            zone = next((item for item in self.config.zones if item.id == zone_id), None)
            if (
                zone is None
                or not zone.enabled
                or not self.enabled
                or self.runtime.state != STATE_IDLE
                or self.paused
                or self._multiplier() is None
            ):
                return False
            self.runtime.cycle_kind = "single"
            self.runtime.completed_zone_ids = []
            await self._async_begin_zone(zone)
            return True

    async def async_stop(self) -> None:
        """Immediately make every output safe and clear all work."""
        async with self._lock:
            await self._async_cancel_zone_task()
            await self._async_safe_off()
            self.runtime = RuntimeState(
                schedule_anchor=self.runtime.schedule_anchor,
                enabled=self.enabled,
            )
            await self._persist()
            await self._async_emit("stopped", reason="manual")
            self._notify()

    async def async_pause(self, reason: str = PAUSE_MANUAL) -> None:
        """Pause work, preserve remaining duration, and turn outputs off."""
        async with self._lock:
            if self.runtime.state == STATE_IDLE:
                self.runtime.pause_reasons.add(reason)
                self.runtime.state = STATE_PAUSED
            else:
                await self._async_capture_remaining()
                await self._async_cancel_zone_task()
                await self._async_safe_off()
                self.runtime.pause_reasons.add(reason)
                self.runtime.state = (
                    STATE_FAULT_PAUSED if reason == PAUSE_OUTPUT_FAULT else STATE_PAUSED
                )
            await self._persist()
            await self._async_emit("paused", reason=reason)
            self._notify()

    async def async_resume(self) -> bool:
        """Resume retained work only if all safety conditions are clear."""
        async with self._lock:
            if not self.enabled:
                return False
            self.runtime.pause_reasons.discard(PAUSE_MANUAL)
            await self._async_refresh_condition_pause()
            if self.runtime.pause_reasons - {PAUSE_RESTART, PAUSE_OUTPUT_FAULT}:
                return False
            if PAUSE_OUTPUT_FAULT in self.runtime.pause_reasons:
                self.runtime.pause_reasons.remove(PAUSE_OUTPUT_FAULT)
            self.runtime.pause_reasons.discard(PAUSE_RESTART)
            if self.runtime.active_zone_id:
                zone = self.active_zone
                if zone is None:
                    return False
                await self._async_begin_zone(zone, remaining=self.runtime.remaining_seconds)
                await self._async_emit("resumed", reason="retained_work")
                return True
            self.runtime.state = STATE_IDLE
            if self.runtime.pending_schedule:
                return await self._async_start_cycle_locked(scheduled=True)
            await self._persist()
            self._notify()
            return True

    async def async_set_enabled(self, enabled: bool) -> None:
        """Set the global enable state; disable is an immediate safe stop."""
        self.enabled = enabled
        self.runtime.enabled = enabled
        if not enabled:
            await self.async_stop()
        else:
            await self._persist()
        self._notify()

    async def async_set_zone_enabled(self, zone_id: str, enabled: bool) -> None:
        """Persist a zone's enabled default through the config entry."""
        zones = [zone.as_dict() for zone in self.config.zones]
        for zone in zones:
            if zone["id"] == zone_id:
                zone["enabled"] = enabled
                break
        else:
            return
        data = self.config.as_dict()
        data["zones"] = zones
        self.hass.config_entries.async_update_entry(self.entry, options=data)
        self.config = ControllerConfig.from_dict(data)
        self._notify()

    async def async_prepare_options_reload(self) -> None:
        """Reset the schedule anchor only when the saved schedule changed."""
        updated = ControllerConfig.from_dict({**self.entry.data, **self.entry.options})
        if (
            updated.interval_days,
            updated.start_time,
        ) != (
            self.config.interval_days,
            self.config.start_time,
        ):
            self.runtime.schedule_anchor = None
            await self._persist()

    async def _async_begin_zone(self, zone: Zone | None, remaining: float | None = None) -> None:
        if zone is None:
            await self._async_finish_cycle()
            return
        multiplier = self._multiplier()
        if multiplier is None:
            self.runtime.completed_zone_ids.extend(
                item.id
                for item in self._remaining_zones()
                if item.id not in self.runtime.completed_zone_ids
            )
            await self._async_safe_off()
            self.runtime.active_zone_id = None
            self.runtime.state = STATE_IDLE
            await self._async_emit("zones_skipped", reason="invalid_multiplier")
            await self._persist()
            self._notify()
            return
        duration = remaining if remaining is not None else zone.duration * multiplier
        self.runtime.active_zone_id = zone.id
        self.runtime.active_zone_index = self.config.zones.index(zone)
        self.runtime.effective_zone_duration = duration
        self.runtime.remaining_seconds = duration
        self.runtime.elapsed_seconds = 0
        self.runtime.state = STATE_RUNNING
        try:
            if self.config.pump_entity_id:
                await self._async_set_output(self.config.pump_entity_id, True)
            for valve in zone.valves:
                await self._async_set_output(valve, True)
        except OutputError as error:
            await self._async_fault(str(error))
            return
        self._zone_task = self.hass.async_create_task(self._async_run_zone(zone, duration))
        self._zone_started_monotonic = time_module.monotonic()
        self._zone_remaining_at_start = duration
        await self._persist()
        await self._async_emit("zone_started", zone=zone)
        self._notify()

    async def _async_run_zone(self, zone: Zone, duration: float) -> None:
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            return
        async with self._lock:
            if self.runtime.state != STATE_RUNNING or self.runtime.active_zone_id != zone.id:
                return
            try:
                for valve in zone.valves:
                    await self._async_set_output(valve, False)
            except OutputError as error:
                await self._async_fault(str(error))
                return
            self.runtime.completed_zone_ids.append(zone.id)
            self.runtime.active_zone_id = None
            self.runtime.remaining_seconds = 0
            await self._async_emit("zone_completed", zone=zone)
            next_zone = None if self.runtime.cycle_kind == "single" else self._first_pending_zone()
            if next_zone is None:
                await self._async_finish_cycle()
                return
            self._zone_task = self.hass.async_create_task(self._async_after_transition(next_zone))
            await self._persist()
            self._notify()

    async def _async_after_transition(self, zone: Zone) -> None:
        """Wait between zones without preventing a Stop or Pause command."""
        try:
            await asyncio.sleep(self.config.transition_delay)
        except asyncio.CancelledError:
            return
        async with self._lock:
            if self.runtime.state != STATE_RUNNING or self.paused:
                return
            await self._async_begin_zone(zone)

    async def _async_finish_cycle(self) -> None:
        await self._async_safe_off()
        self.runtime.active_zone_id = None
        self.runtime.active_zone_index = None
        self.runtime.effective_zone_duration = None
        self.runtime.elapsed_seconds = 0
        self.runtime.remaining_seconds = 0
        self.runtime.cycle_kind = None
        self.runtime.state = STATE_IDLE
        await self._persist()
        await self._async_emit("cycle_completed")
        self._notify()
        if self.runtime.pending_schedule and not self.paused:
            await self._async_start_cycle_locked(scheduled=True)

    async def _async_set_output(self, entity_id: str, on: bool) -> None:
        service = "turn_on" if on else "turn_off"
        for attempt in range(RETRY_COUNT + 1):
            state = self.hass.states.get(entity_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    await self.hass.services.async_call(
                        "switch", service, target={"entity_id": entity_id}, blocking=True
                    )
                    return
                except (
                    Exception
                ):  # Home Assistant service implementations may raise arbitrary errors.
                    _LOGGER.debug("Output command %s %s failed", service, entity_id, exc_info=True)
            if attempt < RETRY_COUNT:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
        raise OutputError(f"{entity_id} did not accept switch.{service}")

    async def _async_safe_off(self) -> None:
        outputs = [valve for zone in self.config.zones for valve in zone.valves]
        if self.config.pump_entity_id:
            outputs.append(self.config.pump_entity_id)
        for entity_id in dict.fromkeys(outputs):
            try:
                await self._async_set_output(entity_id, False)
            except OutputError:
                _LOGGER.error("Unable to turn off irrigation output %s", entity_id)

    async def _async_fault(self, reason: str) -> None:
        await self._async_cancel_zone_task()
        await self._async_safe_off()
        self.runtime.fault = reason
        self.runtime.pause_reasons.add(PAUSE_OUTPUT_FAULT)
        self.runtime.state = STATE_FAULT_PAUSED
        await self._persist()
        await self._async_emit("output_failure", reason=reason)
        self._notify()

    async def _async_capture_remaining(self) -> None:
        if self.runtime.effective_zone_duration is None:
            return
        elapsed = max(0, self.runtime.effective_zone_duration - self._current_remaining())
        self.runtime.elapsed_seconds = elapsed
        self.runtime.remaining_seconds = max(0, self.runtime.effective_zone_duration - elapsed)
        self._zone_started_monotonic = None
        self._zone_remaining_at_start = self.runtime.remaining_seconds

    async def _async_cancel_zone_task(self) -> None:
        if self._zone_task and self._zone_task is not asyncio.current_task():
            self._zone_task.cancel()
        self._zone_task = None
        self._zone_started_monotonic = None

    async def _async_arm_schedule(self, *, reset_anchor: bool) -> None:
        if self._schedule_cancel:
            self._schedule_cancel()
        now = dt_util.now()
        if reset_anchor:
            start = time.fromisoformat(self.config.start_time)
            self.runtime.schedule_anchor = first_anchor_after(now, start).isoformat()
        anchor = self.runtime.schedule_anchor_datetime
        assert anchor is not None
        due = next_occurrence(anchor, self.config.interval_days, now - timedelta(microseconds=1))
        self._schedule_cancel = async_track_point_in_time(self.hass, self._async_schedule_due, due)
        await self._persist()

    async def _async_schedule_due(self, _: datetime) -> None:
        async with self._lock:
            await self._async_arm_schedule(reset_anchor=False)
            if self.runtime.state == STATE_IDLE and not self.paused:
                await self._async_start_cycle_locked(scheduled=True)
                return
            self.runtime.pending_schedule = True
            await self._persist()
            await self._async_emit("schedule_queued", reason="controller_busy_or_paused")
            self._notify()

    async def _async_pause_condition_changed(self, _: Event[EventStateChangedData]) -> None:
        was_paused = PAUSE_CONDITION in self.runtime.pause_reasons
        await self._async_refresh_condition_pause()
        condition_paused = PAUSE_CONDITION in self.runtime.pause_reasons
        if condition_paused and not was_paused:
            await self.async_pause(PAUSE_CONDITION)
        elif was_paused and not condition_paused and PAUSE_MANUAL not in self.runtime.pause_reasons:
            await self.async_resume()

    async def _async_refresh_condition_pause(self) -> None:
        entity_id = self.config.pause_entity_id
        if not entity_id:
            self.runtime.pause_reasons.discard(PAUSE_CONDITION)
            return
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, "on"):
            self.runtime.pause_reasons.add(PAUSE_CONDITION)
        else:
            self.runtime.pause_reasons.discard(PAUSE_CONDITION)

    async def _async_hass_stop(self, _: Event) -> None:
        async with self._lock:
            if self.runtime.active_zone_id:
                await self._async_capture_remaining()
                await self._async_cancel_zone_task()
                await self._async_safe_off()
                self.runtime.pause_reasons.add(PAUSE_RESTART)
                self.runtime.state = STATE_PAUSED
                await self._persist()

    def _multiplier(self) -> float | None:
        if not self.config.multiplier_entity_id:
            return 1.0
        state = self.hass.states.get(self.config.multiplier_entity_id)
        if state is None:
            return None
        try:
            value = float(state.state)
        except TypeError, ValueError:
            return None
        return value if math.isfinite(value) and value > 0 else None

    def _current_remaining(self) -> float:
        """Calculate the active zone count down without mutating storage."""
        if self._zone_started_monotonic is None:
            return self.runtime.remaining_seconds
        return max(
            0,
            self._zone_remaining_at_start
            - (time_module.monotonic() - self._zone_started_monotonic),
        )

    def _enabled_zones(self) -> list[Zone]:
        return [zone for zone in self.config.zones if zone.enabled]

    def _remaining_zones(self) -> list[Zone]:
        return [
            zone for zone in self._enabled_zones() if zone.id not in self.runtime.completed_zone_ids
        ]

    def _first_pending_zone(self) -> Zone | None:
        return next(iter(self._remaining_zones()), None)

    def _can_auto_resume_after_restart(self) -> bool:
        return (
            self.enabled
            and PAUSE_MANUAL not in self.runtime.pause_reasons
            and PAUSE_OUTPUT_FAULT not in self.runtime.pause_reasons
            and PAUSE_CONDITION not in self.runtime.pause_reasons
        )

    async def _persist(self) -> None:
        await self._runtime_store.async_save(self.runtime)

    async def _async_emit(
        self, event: str, *, zone: Zone | None = None, reason: str | None = None
    ) -> None:
        payload: dict[str, Any] = {
            "event": event,
            "controller_id": self.entry.entry_id,
            "timestamp": dt_util.utcnow().isoformat(),
            "remaining_seconds": self.runtime.remaining_seconds,
        }
        if zone:
            payload.update(zone_id=zone.id, zone_name=zone.name)
        if reason:
            payload["reason"] = reason
        self.hass.bus.async_fire(EVENT_LIFECYCLE, payload)
        message = event.replace("_", " ")
        if zone:
            message = f"{message}: {zone.name}"
        if reason:
            message = f"{message} ({reason})"
        async_log_entry(self.hass, self.config.controller_name, message, DOMAIN)
        _LOGGER.info("%s", payload)

    @callback
    def _notify(self) -> None:
        for listener in self._listeners:
            listener()
