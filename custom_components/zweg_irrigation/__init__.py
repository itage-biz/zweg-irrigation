"""The Zweg Irrigation integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_DEVICE_ID,
    ATTR_ZONE_ID,
    DATA_CONTROLLER,
    DATA_RUNTIME_STORE,
    DOMAIN,
    PLATFORMS,
    SERVICE_PAUSE_WATERING,
    SERVICE_RESUME_WATERING,
    SERVICE_START_WATERING,
    SERVICE_START_ZONE,
    SERVICE_STOP_WATERING,
)
from .controller import IrrigationController
from .runtime import RuntimeStore

type ZwegIrrigationConfigEntry = ConfigEntry[dict[str, object]]


async def async_setup(hass: HomeAssistant, _: dict[str, object]) -> bool:
    """Register controller actions once for all entries."""

    async def action_handler(call: ServiceCall) -> None:
        controller = _controller_for_device(hass, call.data[ATTR_DEVICE_ID])
        if call.service == SERVICE_START_WATERING:
            await controller.async_start_cycle()
            return
        if call.service == SERVICE_STOP_WATERING:
            await controller.async_stop()
            return
        if call.service == SERVICE_PAUSE_WATERING:
            await controller.async_pause()
            return
        if call.service == SERVICE_RESUME_WATERING:
            await controller.async_resume()
            return
        await controller.async_start_zone(call.data[ATTR_ZONE_ID])

    base_schema = vol.Schema({vol.Required(ATTR_DEVICE_ID): str})
    hass.services.async_register(DOMAIN, SERVICE_START_WATERING, action_handler, schema=base_schema)
    hass.services.async_register(DOMAIN, SERVICE_STOP_WATERING, action_handler, schema=base_schema)
    hass.services.async_register(DOMAIN, SERVICE_PAUSE_WATERING, action_handler, schema=base_schema)
    hass.services.async_register(
        DOMAIN, SERVICE_RESUME_WATERING, action_handler, schema=base_schema
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_ZONE,
        action_handler,
        schema=base_schema.extend({vol.Required(ATTR_ZONE_ID): str}),
    )
    return True


def _controller_for_device(hass: HomeAssistant, device_id: str) -> IrrigationController:
    """Resolve an action target to exactly one controller device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise vol.Invalid("Unknown Zweg Irrigation controller device")
    for identifier_domain, entry_id in device.identifiers:
        if identifier_domain == DOMAIN:
            return hass.data[DOMAIN][entry_id][DATA_CONTROLLER]
    raise vol.Invalid("Device is not a Zweg Irrigation controller")


async def async_setup_entry(hass: HomeAssistant, entry: ZwegIrrigationConfigEntry) -> bool:
    """Set up Zweg Irrigation from a config entry."""
    runtime_store = RuntimeStore(hass, entry.entry_id)
    controller = IrrigationController(hass, entry, runtime_store)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_CONTROLLER: controller,
        DATA_RUNTIME_STORE: runtime_store,
    }
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    await controller.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ZwegIrrigationConfigEntry) -> None:
    """Reload platforms so native options immediately update zone entities."""
    controller: IrrigationController = hass.data[DOMAIN][entry.entry_id][DATA_CONTROLLER]
    await controller.async_prepare_options_reload()
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZwegIrrigationConfigEntry) -> bool:
    """Unload a Zweg Irrigation config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    data = hass.data[DOMAIN].pop(entry.entry_id)
    await data[DATA_CONTROLLER].async_stop_listeners()
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    return True
