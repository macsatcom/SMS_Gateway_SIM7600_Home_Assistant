"""SMS Gateway integration for Home Assistant.

Provides:
- sms_gateway.send_sms service for sending SMS messages
- sms_gateway_incoming_message events for received SMS (via SSE stream)
- Sensor entities for signal strength and network status
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_API_PORT,
    CONF_HOST,
    CONF_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .coordinator import (
    SmsGatewayAuthError,
    SmsGatewayClient,
    SmsGatewayClientError,
    SmsGatewayConnectionError,
    SmsGatewayCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SEND_SMS_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Required("target"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the SMS Gateway integration from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_API_PORT]
    api_key = entry.data[CONF_API_KEY]

    session = async_get_clientsession(hass)
    client = SmsGatewayClient(host, port, api_key, session, timeout=DEFAULT_TIMEOUT)

    # Validate connection on setup
    try:
        health = await client.get_health()
        if health.get("status") != "ok":
            raise ConfigEntryNotReady(
                f"Gateway modem not ready: {health.get('message', 'Unknown')}"
            )
    except SmsGatewayConnectionError as ex:
        raise ConfigEntryNotReady(str(ex)) from ex
    except SmsGatewayAuthError as ex:
        _LOGGER.error("Authentication failed: %s", ex)
        return False

    # Create coordinator
    coordinator = SmsGatewayCoordinator(hass, entry, client)

    # Do an initial refresh for health/status
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        raise
    except Exception as ex:
        _LOGGER.error("Initial poll failed: %s", ex)
        raise ConfigEntryNotReady(str(ex)) from ex

    # Start the SSE stream for incoming SMS
    await coordinator.async_start_stream()

    # Store coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register send_sms service (first entry only — one service for all gateways)
    if not hass.services.has_service(DOMAIN, "send_sms"):
        async def _send_sms(call: ServiceCall) -> None:
            target = call.data["target"]
            message = call.data["message"]

            if not target.startswith("+") or len(target) < 8:
                raise HomeAssistantError(
                    f"Invalid recipient '{target}'. "
                    "Must be international format starting with '+' (e.g., +4512345678)."
                )

            # Use the first configured gateway
            entry_data = next(iter(hass.data[DOMAIN].values()))
            client: SmsGatewayClient = entry_data["client"]

            try:
                result = await client.send_sms(target, message)
                if not result.get("ok"):
                    raise HomeAssistantError(f"Gateway reported failure: {result}")
                _LOGGER.info("SMS sent to %s (ref: %s)", target, result.get("message_reference", "N/A"))
            except SmsGatewayConnectionError as ex:
                raise HomeAssistantError(f"Could not send SMS: gateway unreachable — {ex}") from ex
            except SmsGatewayClientError as ex:
                raise HomeAssistantError(f"Gateway error: {ex}") from ex

        hass.services.async_register(
            DOMAIN, "send_sms", _send_sms, schema=SEND_SMS_SCHEMA
        )

    # Listen for option changes (reloads the entry to apply all changes)
    entry.async_on_unload(
        entry.add_update_listener(_async_options_updated)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: SmsGatewayCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    await coordinator.async_stop_stream()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    # Remove service when last gateway is removed
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, "send_sms")
    return unload_ok


async def _async_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options flow update — reload to apply name, poll, and auto_delete."""
    _LOGGER.debug("Options changed for %s, reloading entry", entry.title)
    await hass.config_entries.async_reload(entry.entry_id)
