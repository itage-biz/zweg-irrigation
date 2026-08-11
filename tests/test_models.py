"""Tests for durable configuration and runtime models."""

from custom_components.zweg_irrigation.config_flow import validate_config
from custom_components.zweg_irrigation.models import ControllerConfig, RuntimeState


def test_config_round_trip_preserves_zone_order_and_ids() -> None:
    """Configured zones remain ordered and retain their stable IDs."""
    data = {
        "controller_name": "Garden",
        "interval_days": 2,
        "start_time": "06:00:00",
        "transition_delay": 5,
        "zones": [
            {
                "id": "front",
                "name": "Front",
                "duration": 60,
                "enabled": True,
                "valves": ["switch.a"],
            },
            {
                "id": "back",
                "name": "Back",
                "duration": 90,
                "enabled": False,
                "valves": ["switch.b"],
            },
        ],
    }

    config = ControllerConfig.from_dict(data)

    assert [zone.id for zone in config.zones] == ["front", "back"]
    assert config.as_dict() == data | {
        "pump_entity_id": None,
        "pause_entity_id": None,
        "multiplier_entity_id": None,
    }


def test_invalid_zone_configuration_is_rejected() -> None:
    """A controller needs a zone and each zone needs at least one valve."""
    assert validate_config({"zones": []}) == {"base": "zone_required"}
    assert validate_config({"zones": [{"duration": 60, "valves": []}]}) == {
        "base": "valve_required"
    }


def test_runtime_state_round_trip_preserves_pause_causes() -> None:
    """Runtime persistence stores each pause cause separately."""
    runtime = RuntimeState(
        active_zone_id="front",
        remaining_seconds=42,
        pause_reasons={"manual", "restart"},
    )

    restored = RuntimeState.from_dict(runtime.as_dict())

    assert restored.pause_reasons == {"manual", "restart"}
    assert restored.remaining_seconds == 42
