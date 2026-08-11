"""Action buttons for Zweg Irrigation."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .const import DATA_CONTROLLER, DOMAIN
from .entity import ZwegIrrigationEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up controller and per-zone action buttons."""
    controller = hass.data[DOMAIN][entry.entry_id][DATA_CONTROLLER]
    entities: list[ButtonEntity] = [
        ControllerButton(controller, "start", "Start", controller.async_start_cycle),
        ControllerButton(controller, "stop", "Stop", controller.async_stop),
        ControllerButton(controller, "pause", "Pause", controller.async_pause),
        ControllerButton(controller, "resume", "Resume", controller.async_resume),
    ]
    entities.extend(
        ZoneStartButton(controller, zone.id, zone.name) for zone in controller.config.zones
    )
    async_add_entities(entities)


class ControllerButton(ZwegIrrigationEntity, ButtonEntity):
    def __init__(self, controller, key: str, name: str, action) -> None:
        self._action = action
        super().__init__(controller, key, name)

    async def async_press(self) -> None:
        await self._action()


class ZoneStartButton(ZwegIrrigationEntity, ButtonEntity):
    def __init__(self, controller, zone_id: str, zone_name: str) -> None:
        self._zone_id = zone_id
        super().__init__(controller, f"zone_{zone_id}_start", f"Start {zone_name}")

    async def async_press(self) -> None:
        await self.controller.async_start_zone(self._zone_id)
