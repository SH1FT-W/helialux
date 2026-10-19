"""Einrichtung: Adresse + Name; die Verbindung wird vor dem Anlegen geprüft."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
import voluptuous as vol

from .api import HeliaLuxClient, HeliaLuxDevice, HeliaLuxError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TANK_HOST,
    CONF_TANK_NAME,
    CONF_TANK_PROTOCOL,
    CONF_WEATHER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

PROTOCOLS = ["http", "https"]


class HeliaLuxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2
    MINOR_VERSION = 2

    async def _probe(self, host: str, protocol: str) -> HeliaLuxDevice:
        client = HeliaLuxClient(async_get_clientsession(self.hass), host, protocol)
        await client.status()
        return await client.device()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_TANK_HOST].strip()
            self._async_abort_entries_match({CONF_TANK_HOST: host})
            try:
                device = await self._probe(host, user_input[CONF_TANK_PROTOCOL])
            except HeliaLuxError:
                errors["base"] = "cannot_connect"
            else:
                if device.mac:
                    await self.async_set_unique_id(format_mac(device.mac))
                    self._abort_if_unique_id_configured(updates={CONF_TANK_HOST: host})
                return self.async_create_entry(
                    title=user_input[CONF_TANK_NAME],
                    data={**user_input, CONF_TANK_HOST: host},
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_TANK_HOST): str,
                vol.Required(CONF_TANK_NAME): str,
                vol.Required(CONF_TANK_PROTOCOL, default="http"): vol.In(PROTOCOLS),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, user_input), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Neue IP-Adresse eintragen (Name bleibt, sonst würden sich die Entity-IDs ändern)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_TANK_HOST].strip()
            try:
                await self._probe(host, user_input[CONF_TANK_PROTOCOL])
            except HeliaLuxError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TANK_HOST: host, CONF_TANK_PROTOCOL: user_input[CONF_TANK_PROTOCOL]}
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_TANK_HOST, default=entry.data[CONF_TANK_HOST]): str,
                vol.Required(CONF_TANK_PROTOCOL, default=entry.data.get(CONF_TANK_PROTOCOL, "http")): vol.In(PROTOCOLS),
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> HeliaLuxOptionsFlow:
        return HeliaLuxOptionsFlow()


class HeliaLuxOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        current = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        weather = options.get(CONF_WEATHER)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
                vol.Optional(CONF_WEATHER, description={"suggested_value": weather}): EntitySelector(
                    EntitySelectorConfig(domain="weather")
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
