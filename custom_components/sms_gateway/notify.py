"""Notify platform for the SMS Gateway integration — send SMS messages."""
from __future__ import annotations

import logging

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_NAME, DOMAIN
from .coordinator import (
    SmsGatewayClient,
    SmsGatewayClientError,
    SmsGatewayConnectionError,
    SmsGatewayCoordinator,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the notify platform from a config entry."""
    coordinator: SmsGatewayCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    client: SmsGatewayClient = hass.data[DOMAIN][entry.entry_id]["client"]
    async_add_entities([SmsGatewayNotifyEntity(coordinator, client, entry)])


class SmsGatewayNotifyEntity(NotifyEntity):
    """Notification service for sending SMS via the SIM7600 gateway."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: SmsGatewayCoordinator,
        client: SmsGatewayClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the notify entity."""
        self._coordinator = coordinator
        self._client = client
        self._entry = entry

        gateway_name = entry.options.get(CONF_NAME, entry.title)
        self._attr_name = gateway_name
        self._attr_unique_id = f"{entry.entry_id}_notify"
        self._attr_device_info = None

    async def async_send_message(self, message: str, **kwargs: object) -> None:
        """Send an SMS message."""
        target = kwargs.get("target")

        if target is None:
            raise HomeAssistantError(
                "No recipient specified. "
                "Provide a 'target' with the phone number."
            )

        if isinstance(target, list):
            if not target:
                raise HomeAssistantError("Target list is empty")
            if len(target) > 1:
                raise HomeAssistantError(
                    "Multiple recipients are not supported in a single call."
                )
            target = str(target[0])
        else:
            target = str(target)

        if not target.startswith("+") or len(target) < 8:
            raise HomeAssistantError(
                f"Invalid recipient '{target}'. "
                "Must be international format starting with '+' (e.g., +4512345678)."
            )

        try:
            result = await self._client.send_sms(target, message)
            if result.get("ok"):
                _LOGGER.info(
                    "SMS sent to %s (ref: %s)",
                    target,
                    result.get("message_reference", "N/A"),
                )
            else:
                raise HomeAssistantError(
                    f"Gateway reported failure: {result}"
                )
        except SmsGatewayConnectionError as ex:
            raise HomeAssistantError(
                f"Could not send SMS: gateway unreachable — {ex}"
            ) from ex
        except SmsGatewayClientError as ex:
            raise HomeAssistantError(
                f"Gateway error: {ex}"
            ) from ex
