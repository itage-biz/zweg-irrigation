"""Config and options flows for Zweg Irrigation."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

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
    DATA_CONTROLLER,
    DOMAIN,
)
from .models import ControllerConfig


def _entity_selector(domains: list[str], *, multiple: bool = False) -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter=cast(Any, [{"domain": domain} for domain in domains]),
            multiple=multiple,
        )
    )


GLOBAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONTROLLER_NAME, default="Irrigation"): str,
        vol.Required(CONF_INTERVAL_DAYS, default=1): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Required(CONF_START_TIME, default="06:00:00"): selector.TimeSelector(),
        vol.Required(CONF_TRANSITION_DELAY, default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(CONF_PUMP_ENTITY_ID): _entity_selector(["switch"]),
        vol.Optional(CONF_PAUSE_ENTITY_ID): _entity_selector(["binary_sensor", "input_boolean"]),
        vol.Optional(CONF_MULTIPLIER_ENTITY_ID): _entity_selector(["number"]),
    }
)

ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ZONE_NAME): str,
        vol.Required(CONF_ZONE_DURATION, default=60): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Required(CONF_ZONE_ENABLED, default=True): bool,
        vol.Required(CONF_ZONE_VALVES): _entity_selector(["switch"], multiple=True),
    }
)


def validate_config(data: Mapping[str, Any]) -> dict[str, str]:
    """Return errors that must block a config-entry update."""
    errors: dict[str, str] = {}
    zones = data.get(CONF_ZONES, [])
    if not zones:
        errors["base"] = "zone_required"
    for zone in zones:
        if not zone.get(CONF_ZONE_VALVES):
            errors["base"] = "valve_required"
        if int(zone.get(CONF_ZONE_DURATION, 0)) <= 0:
            errors["base"] = "duration_positive"
    return errors


class ZwegIrrigationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle initial controller setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect global controller settings."""
        if user_input is not None:
            self._data = dict(user_input)
            self._data[CONF_ZONES] = []
            await self.async_set_unique_id(uuid.uuid4().hex)
            return await self.async_step_add_zone()
        return self.async_show_form(step_id="user", data_schema=GLOBAL_SCHEMA)

    async def async_step_add_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add zones during initial configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_ZONE_VALVES]:
                errors["base"] = "valve_required"
            else:
                zone = dict(user_input)
                zone[CONF_ZONE_ID] = uuid.uuid4().hex
                self._data[CONF_ZONES].append(zone)
                return await self.async_step_add_another_zone()
        return self.async_show_form(step_id="add_zone", data_schema=ZONE_SCHEMA, errors=errors)

    async def async_step_add_another_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether to add another zone or create the entry."""
        if user_input is not None:
            if user_input["add_another"]:
                return await self.async_step_add_zone()
            errors = validate_config(self._data)
            if errors:
                return self.async_show_form(step_id="add_another_zone", errors=errors)
            return self.async_create_entry(title=self._data[CONF_CONTROLLER_NAME], data=self._data)
        return self.async_show_form(
            step_id="add_another_zone",
            data_schema=vol.Schema({vol.Required("add_another", default=False): bool}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ZwegIrrigationOptionsFlow(config_entry)


class ZwegIrrigationOptionsFlow(OptionsFlow):
    """Manage controller settings and ordered zones."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry
        self._data = {**config_entry.data, **config_entry.options}
        self._selected_zone_id: str | None = None

    def _controller_active(self) -> bool:
        controller = (
            self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {}).get(DATA_CONTROLLER)
        )
        return controller is not None and controller.status != "idle"

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Select an options operation, refusing edits while watering."""
        if self._controller_active():
            return self.async_abort(reason="controller_active")
        return self.async_show_menu(
            step_id="init",
            menu_options=["global", "add_zone", "edit_zone", "delete_zone", "reorder_zones"],
        )

    async def async_step_global(self, user_input: dict[str, Any] | None = None) -> Any:
        """Edit global settings."""
        if user_input is not None:
            self._data.update(user_input)
            return self._finish_or_error()
        defaults = {key: self._data.get(key) for key in GLOBAL_SCHEMA.schema}
        return self.async_show_form(
            step_id="global",
            data_schema=self.add_suggested_values_to_schema(GLOBAL_SCHEMA, defaults),
        )

    async def async_step_add_zone(self, user_input: dict[str, Any] | None = None) -> Any:
        """Append a zone."""
        if user_input is not None:
            if not user_input[CONF_ZONE_VALVES]:
                return self.async_show_form(
                    step_id="add_zone", data_schema=ZONE_SCHEMA, errors={"base": "valve_required"}
                )
            zone = dict(user_input)
            zone[CONF_ZONE_ID] = uuid.uuid4().hex
            self._data[CONF_ZONES].append(zone)
            return self._finish_or_error()
        return self.async_show_form(step_id="add_zone", data_schema=ZONE_SCHEMA)

    async def async_step_edit_zone(self, user_input: dict[str, Any] | None = None) -> Any:
        """Select a zone to edit."""
        if user_input is not None:
            self._selected_zone_id = user_input[CONF_ZONE_ID]
            return await self.async_step_edit_zone_detail()
        return self.async_show_form(step_id="edit_zone", data_schema=self._zone_choice_schema())

    async def async_step_edit_zone_detail(self, user_input: dict[str, Any] | None = None) -> Any:
        """Edit the selected zone without changing its stable ID."""
        zone = self._find_zone(self._selected_zone_id)
        if zone is None:
            return self.async_abort(reason="zone_not_found")
        if user_input is not None:
            if not user_input[CONF_ZONE_VALVES]:
                return self.async_show_form(
                    step_id="edit_zone_detail",
                    data_schema=ZONE_SCHEMA,
                    errors={"base": "valve_required"},
                )
            zone.update(user_input)
            return self._finish_or_error()
        return self.async_show_form(
            step_id="edit_zone_detail",
            data_schema=self.add_suggested_values_to_schema(ZONE_SCHEMA, zone),
        )

    async def async_step_delete_zone(self, user_input: dict[str, Any] | None = None) -> Any:
        """Delete a zone only if at least one remains."""
        if user_input is not None:
            self._data[CONF_ZONES] = [
                zone
                for zone in self._data[CONF_ZONES]
                if zone[CONF_ZONE_ID] != user_input[CONF_ZONE_ID]
            ]
            return self._finish_or_error()
        return self.async_show_form(step_id="delete_zone", data_schema=self._zone_choice_schema())

    async def async_step_reorder_zones(self, user_input: dict[str, Any] | None = None) -> Any:
        """Set the entire order using stable zone IDs."""
        zone_ids = [zone[CONF_ZONE_ID] for zone in self._data[CONF_ZONES]]
        if user_input is not None:
            order = user_input["zone_order"]
            if set(order) != set(zone_ids) or len(order) != len(zone_ids):
                return self.async_show_form(
                    step_id="reorder_zones",
                    data_schema=self._order_schema(),
                    errors={"base": "invalid_order"},
                )
            by_id = {zone[CONF_ZONE_ID]: zone for zone in self._data[CONF_ZONES]}
            self._data[CONF_ZONES] = [by_id[zone_id] for zone_id in order]
            return self._finish_or_error()
        return self.async_show_form(step_id="reorder_zones", data_schema=self._order_schema())

    def _finish_or_error(self) -> Any:
        errors = validate_config(self._data)
        if errors:
            return self.async_show_form(step_id="init", errors=errors)
        ControllerConfig.from_dict(self._data)
        return self.async_create_entry(title="", data=self._data)

    def _find_zone(self, zone_id: str | None) -> dict[str, Any] | None:
        return next(
            (zone for zone in self._data[CONF_ZONES] if zone[CONF_ZONE_ID] == zone_id), None
        )

    def _zone_choice_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_ZONE_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=zone[CONF_ZONE_ID], label=zone[CONF_ZONE_NAME]
                            )
                            for zone in self._data[CONF_ZONES]
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

    def _order_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    "zone_order", default=[zone[CONF_ZONE_ID] for zone in self._data[CONF_ZONES]]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=zone[CONF_ZONE_ID], label=zone[CONF_ZONE_NAME]
                            )
                            for zone in self._data[CONF_ZONES]
                        ],
                        multiple=True,
                    )
                )
            }
        )
