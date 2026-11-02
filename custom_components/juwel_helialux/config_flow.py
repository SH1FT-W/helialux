"""Einrichtung: Adresse + Name; die Verbindung wird vor dem Anlegen geprüft."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
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
from .device import device_macs, is_ip, is_mac, mac_unique_id

PROTOCOLS = ["http", "https"]


class HeliaLuxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2
    MINOR_VERSION = 3

    _discovered_host: str

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
                    # Old entry (URL as unique_id) of this lamp: change its address with "Reconfigure".
                    if self._known_entry(format_mac(device.mac)):
                        return self.async_abort(reason="already_configured")
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

    def _known_entry(self, mac: str) -> ConfigEntry | None:
        """Entry of this lamp: MAC as unique_id first, else an old entry (URL as unique_id) whose
        device reported this MAC and no other one (an older controller's MAC proves nothing)."""
        entries = self._async_current_entries(include_ignore=False)
        for entry in entries:
            if entry.unique_id == mac:
                return entry
        for entry in entries:
            if not is_mac(entry.unique_id) and device_macs(self.hass, entry.entry_id) == {mac}:
                return entry
        return None

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Lamp seen on the network: offer it, or update the address of the entry it belongs to."""
        mac = format_mac(discovery_info.macaddress)
        ip = discovery_info.ip
        if entry := self._known_entry(mac):
            return self._update_discovered_entry(entry, mac, ip)
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()
        self._async_abort_entries_match({CONF_TANK_HOST: ip})
        try:
            device = await self._probe(ip, "http")
        except HeliaLuxError:
            return self.async_abort(reason="cannot_connect")
        if device.mac and format_mac(device.mac) != mac:
            return self.async_abort(reason="cannot_connect")  # the address already moved on to another device
        self._discovered_host = ip
        self.context["title_placeholders"] = {"name": device.model, "host": ip}
        return await self.async_step_discovery_confirm()

    def _update_discovered_entry(self, entry: ConfigEntry, mac: str, ip: str) -> ConfigFlowResult:
        """New IP for a known lamp; an old entry also takes over the MAC as unique_id when that is safe."""
        unique_id = mac if mac_unique_id(self.hass, entry) == mac else entry.unique_id
        if unique_id != entry.unique_id:
            # A discovery of this lamp still waiting for confirmation would otherwise create a second
            # entry with the same unique_id, which makes Home Assistant replace (delete) this one.
            for flow in self._async_in_progress(include_uninitialized=True, match_context={"unique_id": mac}):
                self.hass.config_entries.flow.async_abort(flow["flow_id"])
        host = entry.data[CONF_TANK_HOST]
        # A host name entered by the user stays; only a plain IP follows the lamp.
        data_updates = {CONF_TANK_HOST: ip} if is_ip(host) and host != ip else {}
        return self.async_update_reload_and_abort(
            entry,
            unique_id=unique_id,
            data_updates=data_updates,
            reason="already_configured",
            reload_even_if_entry_is_unchanged=False,
        )

    async def async_step_discovery_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the aquarium name (it determines the entity IDs)."""
        if user_input is not None:
            # The lamp may have been set up (or an old entry taken over its MAC) while this form was open.
            if self.unique_id and self._known_entry(self.unique_id):
                return self.async_abort(reason="already_configured")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_TANK_NAME],
                data={
                    CONF_TANK_HOST: self._discovered_host,
                    CONF_TANK_NAME: user_input[CONF_TANK_NAME],
                    CONF_TANK_PROTOCOL: "http",
                },
                options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
            )
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TANK_NAME): str}),
            description_placeholders={"host": self._discovered_host},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Neue IP-Adresse eintragen (Name bleibt, sonst würden sich die Entity-IDs ändern)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_TANK_HOST].strip()
            try:
                device = await self._probe(host, user_input[CONF_TANK_PROTOCOL])
            except HeliaLuxError:
                errors["base"] = "cannot_connect"
            else:
                if is_mac(entry.unique_id) and device.mac:
                    await self.async_set_unique_id(format_mac(device.mac))
                    self._abort_if_unique_id_mismatch()
                # Entry from the old integration (URL as unique_id): compare with the MAC of its device.
                # A lamp without MAC cannot prove it is the same one once a MAC is known.
                known = {entry.unique_id} if is_mac(entry.unique_id) else device_macs(self.hass, entry.entry_id)
                if known and (not device.mac or format_mac(device.mac) not in known):
                    return self.async_abort(reason="unique_id_mismatch")
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
