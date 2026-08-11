"""Binary sensor entities for Zweg Irrigation."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .const import DATA_CONTROLLER, DOMAIN
from .entity import ZwegIrrigationEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up controller and per-zone binary sensors."""
    controller = hass.data[DOMAIN][entry.entry_id][DATA_CONTROLLER]
    entities = [WateringBinarySensor(controller), PausedBinarySensor(controller)]
    entities.extend(
        ZoneWateringBinarySensor(controller, zone.id, zone.name) for zone in controller.config.zones
    )
    async_add_entities(entities)


class WateringBinarySensor(ZwegIrrigationEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, controller) -> None:
        super().__init__(controller, "watering", "Watering")

    @property
    def is_on(self) -> bool:
        return self.controller.status == "running"


class PausedBinarySensor(ZwegIrrigationEntity, BinarySensorEntity):
    def __init__(self, controller) -> None:
        super().__init__(controller, "paused", "Paused")

    @property
    def is_on(self) -> bool:
        return self.controller.paused


class ZoneWateringBinarySensor(ZwegIrrigationEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, controller, zone_id: str, zone_name: str) -> None:
        self._zone_id = zone_id
        super().__init__(controller, f"zone_{zone_id}_watering", f"{zone_name} watering")

    @property
    def is_on(self) -> bool:
        return (
            self.controller.active_zone is not None
            and self.controller.active_zone.id == self._zone_id
        )
