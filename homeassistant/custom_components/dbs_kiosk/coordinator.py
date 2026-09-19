"""DataUpdateCoordinator for dbsKioskPi."""
import asyncio
from datetime import timedelta
import logging
import aiohttp
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class KioskCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the dbsKioskPi API."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, username: str, password: str) -> None:
        """Initialize the coordinator."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"http://{host}:{port}"
        self.auth = aiohttp.BasicAuth(username, password)
        self.session = aiohttp.ClientSession(auth=self.auth)

        super().__init__(
            hass,
            _LOGGER,
            name=f"dbsKioskPi ({host})",
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self):
        """Fetch status data from dbsKioskPi API."""
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(f"{self.base_url}/api/status") as response:
                    if response.status == 401:
                        raise UpdateFailed("Ungültige Zugangsdaten für dbsKioskPi")
                    if response.status != 200:
                        raise UpdateFailed(f"Fehlerhafte API-Antwort: {response.status}")
                    return await response.json()
        except asyncio.TimeoutError as err:
            raise UpdateFailed(f"Zeitüberschreitung bei Verbindung zu dbsKioskPi: {err}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Netzwerkfehler bei dbsKioskPi: {err}") from err

    async def async_set_screen(self, action: str) -> bool:
        """Turn screen on or off."""
        try:
            async with self.session.post(
                f"{self.base_url}/api/screen",
                json={"action": action}
            ) as response:
                if response.status == 200:
                    await self.async_request_refresh()
                    return True
        except Exception as e:
            _LOGGER.error("Fehler beim Schalten des Bildschirms: %s", e)
        return False

    async def async_play_bell(self, volume: int = None) -> bool:
        """Trigger school bell audio playback."""
        try:
            payload = {}
            if volume is not None:
                payload["volume"] = volume
            async with self.session.post(
                f"{self.base_url}/api/bell/play",
                json=payload
            ) as response:
                return response.status == 200
        except Exception as e:
            _LOGGER.error("Fehler beim Läuten der Schulglocke: %s", e)
            return False

    async def async_set_schedule(self, on_time: str = None, off_time: str = None) -> bool:
        """Update daily TV on/off times."""
        try:
            payload = {}
            if on_time:
                payload["on_time"] = on_time
            if off_time:
                payload["off_time"] = off_time
            async with self.session.post(
                f"{self.base_url}/api/schedule",
                json=payload
            ) as response:
                if response.status == 200:
                    await self.async_request_refresh()
                    return True
        except Exception as e:
            _LOGGER.error("Fehler beim Setzen des Zeitplans: %s", e)
        return False

    async def async_upload_bell(self, file_path: str) -> bool:
        """Upload an MP3 file to the KioskPi."""
        try:
            def read_file():
                with open(file_path, "rb") as f:
                    return f.read()

            file_content = await self.hass.async_add_executor_job(read_file)
            data = aiohttp.FormData()
            data.add_field("file", file_content, filename="bell.mp3", content_type="audio/mpeg")

            async with self.session.post(
                f"{self.base_url}/api/bell/upload",
                data=data
            ) as response:
                if response.status == 200:
                    await self.async_request_refresh()
                    return True
        except Exception as e:
            _LOGGER.error("Fehler beim Hochladen der Schulglocke: %s", e)
        return False

    async def async_restart_kiosk(self) -> bool:
        """Restart the Kiosk service."""
        try:
            async with self.session.post(f"{self.base_url}/api/kiosk/restart") as response:
                return response.status == 200
        except Exception as e:
            _LOGGER.error("Fehler beim Neustart des Kiosks: %s", e)
            return False

    async def async_shutdown_pi(self) -> bool:
        """Shutdown the Raspberry Pi device."""
        try:
            async with self.session.post(f"{self.base_url}/api/system/shutdown") as response:
                return response.status == 200
        except Exception as e:
            _LOGGER.error("Fehler beim Herunterfahren des dbsKioskPi: %s", e)
            return False

    async def async_reboot_pi(self) -> bool:
        """Reboot the Raspberry Pi device."""
        try:
            async with self.session.post(f"{self.base_url}/api/system/reboot") as response:
                return response.status == 200
        except Exception as e:
            _LOGGER.error("Fehler beim Neustart des dbsKioskPi: %s", e)
            return False

    async def async_close(self):
        """Close the client session."""
        if self.session and not self.session.closed:
            await self.session.close()
