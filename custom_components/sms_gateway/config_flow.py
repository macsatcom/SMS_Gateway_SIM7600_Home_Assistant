"""Config flow for the SMS Gateway integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_API_PORT,
    CONF_AUTO_DELETE,
    CONF_HOST,
    CONF_NAME,
    CONF_POLL_INTERVAL,
    DEFAULT_API_PORT,
    DEFAULT_AUTO_DELETE,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .coordinator import SmsGatewayClient, SmsGatewayClientError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_API_PORT, default=DEFAULT_API_PORT): int,
        vol.Required(CONF_API_KEY): str,
    }
)


class SmsGatewayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the SMS Gateway integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — user enters host, port, and API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip().rstrip("/")
            port = user_input[CONF_API_PORT]
            api_key = user_input[CONF_API_KEY].strip()

            # Basic validation
            if not host.startswith(("http://", "https://")):
                errors[CONF_HOST] = "invalid_host"
            elif not api_key:
                errors[CONF_API_KEY] = "empty_api_key"
            else:
                # Warn if the host is a loopback address
                parsed = urlparse(host)
                if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
                    _LOGGER.warning(
                        "Gateway configured with loopback address '%s'. "
                        "This only works if HA and the gateway are on the same host.",
                        host,
                    )
                # Test connection
                session = async_get_clientsession(self.hass)
                client = SmsGatewayClient(host, port, api_key, session, timeout=DEFAULT_TIMEOUT)

                try:
                    # Step 1: Health check (no auth)
                    health = await client.get_health()
                    if health.get("status") != "ok":
                        errors["base"] = "modem_not_ready"
                    else:
                        try:
                            # Step 2: Verify auth and modem
                            await client.get_status()
                            _LOGGER.debug(
                                "Successfully connected to SMS Gateway at %s:%d",
                                host,
                                port,
                            )
                        except SmsGatewayClientError:
                            errors[CONF_API_KEY] = "invalid_api_key"
                except SmsGatewayClientError:
                    errors[CONF_HOST] = "cannot_connect"

            if not errors:
                # Create a unique ID based on host:port
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=DEFAULT_NAME,
                    data={
                        CONF_HOST: host,
                        CONF_API_PORT: port,
                        CONF_API_KEY: api_key,
                    },
                    options={
                        CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                        CONF_AUTO_DELETE: DEFAULT_AUTO_DELETE,
                        CONF_NAME: DEFAULT_NAME,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler."""
        return SmsGatewayOptionsFlow(config_entry)


class SmsGatewayOptionsFlow(OptionsFlow):
    """Handle options for the SMS Gateway integration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self._entry.options

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NAME,
                    default=options.get(CONF_NAME, DEFAULT_NAME),
                ): str,
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=options.get(
                        CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Optional(
                    CONF_AUTO_DELETE,
                    default=options.get(
                        CONF_AUTO_DELETE, DEFAULT_AUTO_DELETE
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "note": (
                    "Incoming SMS arrive in real-time via SSE stream. "
                    "Poll interval only affects health and status updates."
                ),
            },
        )
