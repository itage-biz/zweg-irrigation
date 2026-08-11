"""Sensor entities for Zweg Irrigation."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime

from .const import DATA_CONTROLLER, DOMAIN
from .entity import ZwegIrrigationEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up controller and per-zone sensors."""
    controller = hass.data[DOMAIN][entry.entry_id][DATA_CONTROLLER]
    entities = [
        ControllerStatusSensor(controller),
        CurrentZoneSensor(controller),
        NextRunSensor(controller),
        RemainingSensor(controller),
    ]
    entities.extend(
        ZoneRemainingSensor(controller, zone.id, zone.name) for zone in controller.config.zones
    )
    async_add_entities(entities)


class ControllerStatusSensor(ZwegIrrigationEntity, SensorEntity):
    def __init__(self, controller) -> None:
        super().__init__(controller, "status", "Status")

    @property
    def native_value(self) -> str:
        return self.controller.status


class CurrentZoneSensor(ZwegIrrigationEntity, SensorEntity):
    def __init__(self, controller) -> None:
        super().__init__(controller, "current_zone", "Current zone")

    @property
    def native_value(self) -> str | None:
        return self.controller.active_zone.name if self.controller.active_zone else None


class NextRunSensor(ZwegIrrigationEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, controller) -> None:
        super().__init__(controller, "next_run", "Next run")

    @property
    def native_value(self) -> datetime | None:
        return self.controller.next_run


class RemainingSensor(ZwegIrrigationEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, controller) -> None:
        super().__init__(controller, "remaining", "Remaining time")

    @property
    def native_value(self) -> int:
        return round(self.controller.total_remaining_seconds)


class ZoneRemainingSensor(ZwegIrrigationEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS

    def __init__(self, controller, zone_id: str, zone_name: str) -> None:
        self._zone_id = zone_id
        super().__init__(controller, f"zone_{zone_id}_remaining", f"{zone_name} remaining")

    @property
    def native_value(self) -> int:
        return round(self.controller.zone_remaining_seconds(self._zone_id))
