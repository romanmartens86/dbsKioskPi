"""Time platform for dbsKioskPi CEC scheduling."""
from datetime import time as dt_time
import logging

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KioskCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the dbsKioskPi time entities."""
    coordinator: KioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        KioskOnTimeEntity(coordinator, entry),
        KioskOffTimeEntity(coordinator, entry),
    ])


def parse_hh_mm(val_str: str, default_h: int, default_m: int) -> dt_time:
    """Helper to parse HH:MM into a datetime.time object."""
    try:
        if val_str and ":" in val_str:
            parts = val_str.split(":")
            return dt_time(int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return dt_time(default_h, default_m)


class KioskOnTimeEntity(CoordinatorEntity, TimeEntity):
    """Entity to set the daily TV power-on time."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "TV Einschaltzeit"
        self._attr_unique_id = f"{entry.entry_id}_cec_on_time"
        self._attr_icon = "mdi:clock-start"

    @property
    def native_value(self) -> dt_time:
        """Return the current configured on time."""
        val = self.coordinator.data.get("cec_on_time", "07:00") if self.coordinator.data else "07:00"
        return parse_hh_mm(val, 7, 0)

    async def async_set_value(self, value: dt_time) -> None:
        """Update the on time on the Kiosk Pi."""
        formatted = value.strftime("%H:%M")
        await self.coordinator.async_set_schedule(on_time=formatted)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }


class KioskOffTimeEntity(CoordinatorEntity, TimeEntity):
    """Entity to set the daily TV standby/off time."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "TV Standby-Zeit"
        self._attr_unique_id = f"{entry.entry_id}_cec_off_time"
        self._attr_icon = "mdi:clock-end"

    @property
    def native_value(self) -> dt_time:
        """Return the current configured off time."""
        val = self.coordinator.data.get("cec_off_time", "19:00") if self.coordinator.data else "19:00"
        return parse_hh_mm(val, 19, 0)

    async def async_set_value(self, value: dt_time) -> None:
        """Update the off time on the Kiosk Pi."""
        formatted = value.strftime("%H:%M")
        await self.coordinator.async_set_schedule(off_time=formatted)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }
