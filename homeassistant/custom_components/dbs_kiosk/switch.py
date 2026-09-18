"""Switch platform for dbsKioskPi screen control."""
from homeassistant.components.switch import SwitchEntity
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
    """Set up the dbsKioskPi switches."""
    coordinator: KioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KioskScreenSwitch(coordinator, entry)])


class KioskScreenSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of the Kiosk HDMI TV Screen switch."""

    def __init__(self, coordinator: KioskCoordinator, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "HDMI TV Bildschirm"
        self._attr_unique_id = f"{entry.entry_id}_screen_switch"
        self._attr_icon = "mdi:television"

    @property
    def is_on(self) -> bool:
        """Return true if the screen is currently powered on."""
        if not self.coordinator.data:
            return False
        power = self.coordinator.data.get("screen_power", "unknown")
        return power == "on"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the TV on via HDMI-CEC."""
        await self.coordinator.async_set_screen("on")

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the TV off (standby) via HDMI-CEC."""
        await self.coordinator.async_set_screen("off")

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": f"dbsKioskPi ({self.coordinator.host})",
            "manufacturer": "dbsKioskPi",
            "model": "Raspberry Pi Kiosk",
            "sw_version": self.coordinator.data.get("version", "1.0.0") if self.coordinator.data else "1.0.0",
        }
