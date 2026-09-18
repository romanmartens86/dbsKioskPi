"""Config flow for dbsKioskPi integration."""
import logging
import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD

from .const import DOMAIN, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_USERNAME, default="pi"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass, data: dict):
    """Validate the user input allows us to connect to dbsKioskPi."""
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    url = f"http://{host}:{port}/api/status"
    auth = aiohttp.BasicAuth(username, password)

    try:
        async with aiohttp.ClientSession(auth=auth) as session:
            async with async_timeout.timeout(10):
                async with session.get(url) as response:
                    if response.status == 401:
                        return "invalid_auth"
                    if response.status != 200:
                        return "cannot_connect"
                    payload = await response.json()
                    return {"title": f"dbsKioskPi ({host})", "info": payload}
    except Exception as err:
        _LOGGER.warning("Verbindungsprüfung fehlgeschlagen für %s: %s", host, err)
        return "cannot_connect"


class KioskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for dbsKioskPi."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()

            result = await validate_input(self.hass, user_input)
            if isinstance(result, dict):
                return self.async_create_entry(title=result["title"], data=user_input)
            elif result == "invalid_auth":
                errors["base"] = "invalid_auth"
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
