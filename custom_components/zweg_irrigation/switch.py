"""Enable switches for Zweg Irrigation."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .const import DATA_CONTROLLER, DOMAIN
from .entity import ZwegIrrigationEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up global and per-zone enabled switches."""
    controller = hass.data[DOMAIN][entry.entry_id][DATA_CONTROLLER]
    async_add_entities(
        [GlobalEnableSwitch(controller)]
        + [ZoneEnableSwitch(controller, zone.id, zone.name) for zone in controller.config.zones]
    )


class GlobalEnableSwitch(ZwegIrrigationEntity, SwitchEntity):
    def __init__(self, controller) -> None:
        super().__init__(controller, "enabled", "Enabled")

    @property
    def is_on(self) -> bool:
        return self.controller.enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.controller.async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.controller.async_set_enabled(False)


class ZoneEnableSwitch(ZwegIrrigationEntity, SwitchEntity):
    def __init__(self, controller, zone_id: str, zone_name: str) -> None:
        self._zone_id = zone_id
        super().__init__(controller, f"zone_{zone_id}_enabled", f"{zone_name} enabled")

    @property
    def is_on(self) -> bool:
        return next(
            zone.enabled for zone in self.controller.config.zones if zone.id == self._zone_id
        )

    async def async_turn_on(self, **kwargs) -> None:
        await self.controller.async_set_zone_enabled(self._zone_id, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.controller.async_set_zone_enabled(self._zone_id, False)
