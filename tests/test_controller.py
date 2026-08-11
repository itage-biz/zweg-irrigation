"""State-machine tests using Home Assistant's test fixture."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

from custom_components.zweg_irrigation.const import STATE_RUNNING
from custom_components.zweg_irrigation.controller import IrrigationController
from custom_components.zweg_irrigation.models import RuntimeState


class MemoryRuntimeStore:
    """Test-only runtime storage."""

    def __init__(self) -> None:
        self.state = RuntimeState()

    async def async_load(self) -> RuntimeState:
        return self.state

    async def async_save(self, state: RuntimeState) -> None:
        self.state = RuntimeState.from_dict(state.as_dict())


@dataclass
class Entry:
    """Minimal config-entry shape required by the controller."""

    data: dict[str, object]
    options: dict[str, object] = field(default_factory=dict)
    entry_id: str = "entry-id"


def controller_entry(
    *,
    duration: int = 1,
    multiplier: str | None = None,
    irrigation_enabled: str | None = None,
) -> Entry:
    """Build a compact controller configuration for safety tests."""
    data: dict[str, object] = {
        "controller_name": "Garden",
        "interval_days": 1,
        "start_time": "06:00:00",
        "transition_delay": 0,
        "zones": [
            {
                "id": "front",
                "name": "Front",
                "duration": duration,
                "enabled": True,
                "valves": ["switch.a"],
            }
        ],
    }
    if multiplier:
        data["multiplier_entity_id"] = multiplier
    if irrigation_enabled:
        data["pause_entity_id"] = irrigation_enabled
    return Entry(data=data)


@pytest.mark.asyncio
async def test_multi_valve_zone_runs_with_pump_and_turns_everything_off(tmp_path: Path) -> None:
    """The pump starts before zone outputs and safely ends after one zone."""
    hass = HomeAssistant(str(tmp_path))
    calls: list[tuple[str, str]] = []

    async def turn_on(call) -> None:
        entity_id = call.data["entity_id"]
        calls.append(("on", entity_id))
        hass.states.async_set(entity_id, "on")

    async def turn_off(call) -> None:
        entity_id = call.data["entity_id"]
        calls.append(("off", entity_id))
        hass.states.async_set(entity_id, "off")

    hass.services.async_register("switch", "turn_on", turn_on)
    hass.services.async_register("switch", "turn_off", turn_off)
    for entity_id in ("switch.pump", "switch.a", "switch.b"):
        hass.states.async_set(entity_id, "off")
    entry = Entry(
        data={
            "controller_name": "Garden",
            "interval_days": 1,
            "start_time": "06:00:00",
            "transition_delay": 0,
            "pump_entity_id": "switch.pump",
            "zones": [
                {
                    "id": "front",
                    "name": "Front",
                    "duration": 0.01,
                    "enabled": True,
                    "valves": ["switch.a", "switch.b"],
                }
            ],
        },
    )
    try:
        controller = IrrigationController(hass, entry, MemoryRuntimeStore())

        assert await controller.async_start_cycle()
        await asyncio.sleep(0.05)
        await hass.async_block_till_done()

        assert calls[:3] == [("on", "switch.pump"), ("on", "switch.a"), ("on", "switch.b")]
        assert hass.states.get("switch.pump").state == "off"
        assert hass.states.get("switch.a").state == "off"
        assert hass.states.get("switch.b").state == "off"
        assert controller.status == "idle"
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_manual_pause_retains_work_and_resume_restarts_only_the_remainder(
    tmp_path: Path,
) -> None:
    """Manual pause safely closes outputs and Resume clears only that pause cause."""
    hass = HomeAssistant(str(tmp_path))
    calls: list[str] = []

    async def set_switch(call) -> None:
        entity_id = call.data["entity_id"]
        calls.append(call.service)
        hass.states.async_set(entity_id, "on" if call.service == "turn_on" else "off")

    hass.services.async_register("switch", "turn_on", set_switch)
    hass.services.async_register("switch", "turn_off", set_switch)
    hass.states.async_set("switch.a", "off")
    try:
        controller = IrrigationController(hass, controller_entry(), MemoryRuntimeStore())
        assert await controller.async_start_cycle()
        await asyncio.sleep(0.02)

        await controller.async_pause()

        assert controller.status == "paused"
        assert controller.runtime.remaining_seconds > 0
        assert hass.states.get("switch.a").state == "off"
        assert "manual" in controller.runtime.pause_reasons

        assert await controller.async_resume()
        assert controller.status == "running"
        assert "manual" not in controller.runtime.pause_reasons
        await controller.async_stop()
        assert calls[-1] == "turn_off"
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_invalid_multiplier_and_global_disable_never_leave_output_on(tmp_path: Path) -> None:
    """Invalid multipliers block starts; disabling uses the same safe shutdown as Stop."""
    hass = HomeAssistant(str(tmp_path))

    async def set_switch(call) -> None:
        entity_id = call.data["entity_id"]
        hass.states.async_set(entity_id, "on" if call.service == "turn_on" else "off")

    hass.services.async_register("switch", "turn_on", set_switch)
    hass.services.async_register("switch", "turn_off", set_switch)
    hass.states.async_set("switch.a", "off")
    hass.states.async_set("input_number.multiplier", "unknown")
    try:
        controller = IrrigationController(
            hass, controller_entry(multiplier="input_number.multiplier"), MemoryRuntimeStore()
        )
        assert not await controller.async_start_cycle()
        assert controller.status == "idle"

        hass.states.async_set("input_number.multiplier", "1")
        assert await controller.async_start_cycle()
        assert hass.states.get("switch.a").state == "on"
        await controller.async_set_enabled(False)

        assert not controller.enabled
        assert controller.status == "idle"
        assert hass.states.get("switch.a").state == "off"
        assert not controller.runtime.pending_schedule
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_irrigation_enabled_entity_pauses_when_off_and_resumes_when_on(
    tmp_path: Path,
) -> None:
    """An enabled entity permits watering only while its state is on."""
    hass = HomeAssistant(str(tmp_path))

    async def set_switch(call) -> None:
        entity_id = call.data["entity_id"]
        hass.states.async_set(entity_id, "on" if call.service == "turn_on" else "off")

    hass.services.async_register("switch", "turn_on", set_switch)
    hass.services.async_register("switch", "turn_off", set_switch)
    hass.states.async_set("switch.a", "off")
    hass.states.async_set("switch.pump", "off")
    hass.states.async_set("input_boolean.irrigation_enabled", "on")
    try:
        entry = controller_entry(
            duration=30,
            irrigation_enabled="input_boolean.irrigation_enabled",
        )
        entry.data["pump_entity_id"] = "switch.pump"
        controller = IrrigationController(
            hass,
            entry,
            MemoryRuntimeStore(),
        )
        await controller.async_start()

        assert await controller.async_start_cycle()
        assert hass.states.get("switch.a").state == "on"
        assert hass.states.get("switch.pump").state == "on"

        hass.states.async_set("input_boolean.irrigation_enabled", "off")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert controller.status == "paused"
        assert hass.states.get("switch.a").state == "off"
        assert hass.states.get("switch.pump").state == "off"

        hass.states.async_set("input_boolean.irrigation_enabled", "on")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert controller.status == "running"
        assert hass.states.get("switch.a").state == "on"
        assert hass.states.get("switch.pump").state == "on"
        await controller.async_stop()
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_remaining_tick_notifies_only_while_watering(tmp_path: Path) -> None:
    """The real-time refresh avoids writes while the controller is idle."""
    hass = HomeAssistant(str(tmp_path))
    try:
        controller = IrrigationController(hass, controller_entry(), MemoryRuntimeStore())
        notifications: list[None] = []
        controller.add_listener(lambda: notifications.append(None))

        controller._async_remaining_tick(datetime.now())
        assert notifications == []

        controller.runtime.state = STATE_RUNNING
        controller._async_remaining_tick(datetime.now())
        assert notifications == [None]
    finally:
        await hass.async_stop()
