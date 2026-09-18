"""The dbsKioskPi Home Assistant Integration."""
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_PLAY_BELL,
    SERVICE_UPLOAD_BELL,
    SERVICE_SET_SCHEDULE,
    ATTR_VOLUME,
    ATTR_FILE_PATH,
    ATTR_ON_TIME,
    ATTR_OFF_TIME,
)
from .coordinator import KioskCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "button", "time", "sensor"]

PLAY_BELL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_VOLUME, default=100): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    }
)

UPLOAD_BELL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_FILE_PATH): cv.string,
    }
)

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ON_TIME): cv.string,
        vol.Optional(ATTR_OFF_TIME): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up dbsKioskPi from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = KioskCoordinator(
        hass=hass,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --------------------------------------------------------------------------
    # Register Home Assistant Services
    # --------------------------------------------------------------------------
    async def handle_play_bell(call: ServiceCall):
        volume = call.data.get(ATTR_VOLUME, 100)
        await coordinator.async_play_bell(volume=volume)

    async def handle_upload_bell(call: ServiceCall):
        file_path = call.data.get(ATTR_FILE_PATH)
        success = await coordinator.async_upload_bell(file_path=file_path)
        if success:
            _LOGGER.info("Schulglocke MP3 erfolgreich an %s übertragen", entry.data[CONF_HOST])
        else:
            _LOGGER.error("Fehler beim Übertragen der Schulglocke an %s", entry.data[CONF_HOST])

    async def handle_set_schedule(call: ServiceCall):
        on_time = call.data.get(ATTR_ON_TIME)
        off_time = call.data.get(ATTR_OFF_TIME)
        await coordinator.async_set_schedule(on_time=on_time, off_time=off_time)

    hass.services.async_register(DOMAIN, SERVICE_PLAY_BELL, handle_play_bell, schema=PLAY_BELL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPLOAD_BELL, handle_upload_bell, schema=UPLOAD_BELL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE, handle_set_schedule, schema=SET_SCHEDULE_SCHEMA)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: KioskCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()
    return unload_ok
