"""Sensor platform for dbsKioskPi status information."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KioskCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the dbsKioskPi sensors."""
    coordinator: KioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        KioskServiceStatusSensor(coordinator, entry),
        KioskBellStatusSensor(coordinator, entry),
        KioskUrlSensor(coordinator, entry),
    ])


class KioskServiceStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor for Kiosk systemd service status."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Kiosk Dienst-Status"
        self._attr_unique_id = f"{entry.entry_id}_kiosk_service_status"
        self._attr_icon = "mdi:server"

    @property
    def native_value(self) -> str:
        """Return the service status."""
        if not self.coordinator.data:
            return "Unbekannt"
        return self.coordinator.data.get("kiosk_service", "Unbekannt")

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }


class KioskBellStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor for MP3 bell status."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Schulglocke MP3 Datei"
        self._attr_unique_id = f"{entry.entry_id}_bell_status"
        self._attr_icon = "mdi:music-note"

    @property
    def native_value(self) -> str:
        """Return file presence."""
        if not self.coordinator.data:
            return "Unbekannt"
        bell_info = self.coordinator.data.get("bell", {})
        if bell_info.get("sound_exists"):
            size = bell_info.get("sound_size_bytes", 0)
            return f"Vorhanden ({size // 1024} KB)"
        return "Keine MP3 vorhanden"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }


class KioskUrlSensor(CoordinatorEntity, SensorEntity):
    """Sensor displaying current Kiosk URL."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Kiosk URL"
        self._attr_unique_id = f"{entry.entry_id}_kiosk_url"
        self._attr_icon = "mdi:web"

    @property
    def native_value(self) -> str:
        """Return URL."""
        if not self.coordinator.data:
            return ""
        return self.coordinator.data.get("kiosk_url", "")

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }
