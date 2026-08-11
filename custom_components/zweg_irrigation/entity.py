"""Shared entity helpers."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import IrrigationController


class ZwegIrrigationEntity(Entity):
    """Base entity attached to one synthetic controller device."""

    _attr_has_entity_name = True

    def __init__(self, controller: IrrigationController, key: str, name: str) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_name = name
        self._unsub: Callable[[], None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the controller's synthetic device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.controller.entry.entry_id)},
            name=self.controller.config.controller_name,
            manufacturer="Zweg Irrigation",
            model="Irrigation controller",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to immediate controller state changes."""
        self._unsub = self.controller.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove controller listener."""
        if self._unsub:
            self._unsub()
