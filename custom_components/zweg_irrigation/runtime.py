"""Versioned Home Assistant storage for mutable irrigation state."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import RuntimeState


class RuntimeStore:
    """Persist per-entry runtime state independently of config-entry data."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, object]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}"
        )

    async def async_load(self) -> RuntimeState:
        """Load state or return a clean state."""
        return RuntimeState.from_dict(await self._store.async_load())

    async def async_save(self, state: RuntimeState) -> None:
        """Persist current state immediately for safe recovery."""
        await self._store.async_save(state.as_dict())
