"""Button platform for dbsKioskPi actions."""
from homeassistant.components.button import ButtonEntity
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
    """Set up the dbsKioskPi buttons."""
    coordinator: KioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SchoolBellButton(coordinator, entry),
        KioskRestartButton(coordinator, entry),
        KioskRebootButton(coordinator, entry),
        KioskShutdownButton(coordinator, entry),
    ])


class SchoolBellButton(CoordinatorEntity, ButtonEntity):
    """Button to trigger the school bell playback."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Schulglocke läuten"
        self._attr_unique_id = f"{entry.entry_id}_bell_button"
        self._attr_icon = "mdi:bell-ring"

    async def async_press(self) -> None:
        """Handle button press: play bell sound."""
        await self.coordinator.async_play_bell()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }


class KioskRestartButton(CoordinatorEntity, ButtonEntity):
    """Button to restart the kiosk service."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Kiosk neu starten"
        self._attr_unique_id = f"{entry.entry_id}_restart_button"
        self._attr_icon = "mdi:restart"

    async def async_press(self) -> None:
        """Handle button press: restart service."""
        await self.coordinator.async_restart_kiosk()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }


class KioskRebootButton(CoordinatorEntity, ButtonEntity):
    """Button to reboot the Raspberry Pi device."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "System neu starten (Reboot)"
        self._attr_unique_id = f"{entry.entry_id}_reboot_button"
        self._attr_icon = "mdi:restart-alert"

    async def async_press(self) -> None:
        """Handle button press: reboot device."""
        await self.coordinator.async_reboot_pi()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }


class KioskShutdownButton(CoordinatorEntity, ButtonEntity):
    """Button to safely shut down the Raspberry Pi device."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "System herunterfahren"
        self._attr_unique_id = f"{entry.entry_id}_shutdown_button"
        self._attr_icon = "mdi:power"

    async def async_press(self) -> None:
        """Handle button press: shut down device."""
        await self.coordinator.async_shutdown_pi()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
        }
