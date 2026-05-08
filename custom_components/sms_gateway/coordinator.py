"""DataUpdateCoordinator for the SMS Gateway integration."""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_API_KEY,
    CONF_API_PORT,
    CONF_AUTO_DELETE,
    CONF_HOST,
    CONF_NAME,
    CONF_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    EVENT_INCOMING_SMS,
    STREAM_RECONNECT_DELAY,
)

_LOGGER = logging.getLogger(__name__)


class SmsGatewayClientError(Exception):
    """Base error for SMS Gateway client."""


class SmsGatewayAuthError(SmsGatewayClientError):
    """Authentication error (HTTP 401)."""


class SmsGatewayConnectionError(SmsGatewayClientError):
    """Connection error."""


class SmsGatewayClient:
    """Async HTTP client for the SIM7600 SMS Gateway API."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        session: aiohttp.ClientSession,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self._base_url = f"{host.rstrip('/')}:{port}"
        self._api_key = api_key
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def base_url(self) -> str:
        """Return the base URL."""
        return self._base_url

    @property
    def api_key(self) -> str:
        """Return the API key."""
        return self._api_key

    @property
    def _headers(self) -> dict[str, str]:
        """Return request headers with API key."""
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Make an HTTP request to the SMS Gateway."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers if path != "/health" else {},
                json=json_data,
                params=params,
                timeout=self._timeout,
            ) as resp:
                if resp.status == 401:
                    raise SmsGatewayAuthError(
                        f"Invalid API key for {self._base_url}"
                    )
                data = await resp.json()
                if resp.status >= 500:
                    detail = data.get("detail", "Unknown error")
                    raise SmsGatewayClientError(
                        f"Gateway error ({resp.status}): {detail}"
                    )
                if resp.status == 404:
                    raise SmsGatewayClientError(
                        f"Resource not found: {path}"
                    )
                if resp.status == 422:
                    detail = data.get("detail", "Validation error")
                    raise SmsGatewayClientError(
                        f"Validation error: {detail}"
                    )
                return data
        except SmsGatewayAuthError:
            raise
        except SmsGatewayClientError:
            raise
        except aiohttp.ClientConnectorError as ex:
            raise SmsGatewayConnectionError(
                f"Cannot connect to {self._base_url}: {ex}"
            ) from ex
        except asyncio.TimeoutError as ex:
            raise SmsGatewayConnectionError(
                f"Timeout connecting to {self._base_url}"
            ) from ex
        except Exception as ex:
            raise SmsGatewayConnectionError(
                f"Unexpected error: {ex}"
            ) from ex

    async def get_health(self) -> dict:
        """GET /health — no auth required."""
        return await self._request("GET", "/health")

    async def get_status(self) -> dict:
        """GET /status — modem and SIM status."""
        return await self._request("GET", "/status")

    async def send_sms(self, to: str, message: str) -> dict:
        """POST /sms/send — send an SMS."""
        return await self._request(
            "POST", "/sms/send", json_data={"to": to, "message": message}
        )

    async def delete_sms(self, index: int) -> None:
        """DELETE /sms/{index} — delete one SMS from SIM."""
        await self._request("DELETE", f"/sms/{index}")


class SmsGatewayCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator that polls health/status and manages the SSE stream for incoming SMS."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SmsGatewayClient,
    ) -> None:
        """Initialize the coordinator."""
        poll_interval = entry.options.get(
            CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL, 30)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._entry = entry
        self._client = client
        self._stream_task: asyncio.Task | None = None

    @property
    def client(self) -> SmsGatewayClient:
        """Return the HTTP client (used by notify platform)."""
        return self._client

    @property
    def entry_id(self) -> str:
        """Return the config entry ID."""
        return self._entry.entry_id

    def update_poll_interval(self, seconds: int) -> None:
        """Update the polling interval."""
        self.update_interval = timedelta(seconds=seconds)

    async def async_start_stream(self) -> None:
        """Start the SSE stream background task."""
        if self._stream_task is not None and not self._stream_task.done():
            _LOGGER.debug("SSE stream task already running")
            return
        self._stream_task = self.hass.async_create_background_task(
            self._async_stream_reader(),
            "sms_gateway_sse_stream",
        )
        _LOGGER.debug("SSE stream task started")

    async def async_stop_stream(self) -> None:
        """Stop the SSE stream background task."""
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
            _LOGGER.debug("SSE stream task stopped")

    async def _async_stream_reader(self) -> None:
        """Connect to /sms/stream and fire events for incoming SMS."""
        gateway_id = self._entry.entry_id
        gateway_name = self._entry.options.get(CONF_NAME, self._entry.title)
        delay = STREAM_RECONNECT_DELAY

        while True:
            try:
                url = f"{self._client.base_url}/sms/stream"
                headers = {"X-API-Key": self._client.api_key}
                _LOGGER.debug("Connecting to SSE stream at %s", url)

                async with self._client._session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=None, sock_read=300)
                ) as resp:
                    if resp.status == 401:
                        raise SmsGatewayAuthError("Invalid API key for SSE stream")
                    if resp.status != 200:
                        _LOGGER.error(
                            "SSE stream returned HTTP %d, retrying", resp.status
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * 2 * (0.8 + 0.4 * random.random()), 120)
                        continue

                    delay = STREAM_RECONNECT_DELAY
                    _LOGGER.info("SSE stream connected")
                    # Dismiss any previous auth-failure notification
                    try:
                        await self.hass.services.async_call(
                            "persistent_notification",
                            "dismiss",
                            {"notification_id": f"sms_gateway_sse_auth_{gateway_id}"},
                            blocking=False,
                        )
                    except Exception:
                        pass
                    buf = ""

                    async for line_bytes in resp.content:
                        line = line_bytes.decode("utf-8", errors="replace")

                        if line == "\n" and buf:
                            # Empty line = end of event
                            self._process_sse_event(
                                buf, gateway_id, gateway_name
                            )
                            buf = ""
                        elif line.startswith("data:"):
                            if buf:
                                buf += "\n"
                            buf += line[5:].strip()
                        elif line.startswith(":") or line == "\n":
                            continue
                        else:
                            buf += line

            except asyncio.CancelledError:
                _LOGGER.debug("SSE stream task cancelled")
                return
            except SmsGatewayAuthError as ex:
                _LOGGER.error("SSE stream auth failed: %s — not retrying", ex)
                try:
                    await self.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": "SMS Gateway: SSE stream failed",
                            "message": (
                                f"Authentication failed for SSE stream on "
                                f"{self._client.base_url}. "
                                f"Check the API key and reload the integration."
                            ),
                            "notification_id": f"sms_gateway_sse_auth_{gateway_id}",
                        },
                        blocking=False,
                    )
                except Exception:
                    pass
                return
            except Exception as ex:
                _LOGGER.warning(
                    "SSE stream error: %s — reconnecting in %ds", ex, delay
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2 * (0.8 + 0.4 * random.random()), 120)

    def _process_sse_event(
        self,
        payload: str,
        gateway_id: str,
        gateway_name: str,
    ) -> None:
        """Parse and fire an event for a single SSE data payload."""
        try:
            msg = json.loads(payload)
        except json.JSONDecodeError:
            _LOGGER.warning("SSE stream: invalid JSON payload: %s", payload)
            return

        index = msg.get("index")
        sender = msg.get("sender", "")
        message = msg.get("message", "")
        timestamp = msg.get("timestamp", "")

        _LOGGER.info("Incoming SMS from %s (index %d)", sender, index)
        _LOGGER.debug("SMS body: %s", message[:200])

        event_data = {
            "gateway_id": gateway_id,
            "gateway_name": gateway_name,
            "sender": sender,
            "message": message,
            "timestamp": timestamp,
            "index": index,
        }
        self.hass.bus.async_fire(EVENT_INCOMING_SMS, event_data)

        # Read auto_delete dynamically so option changes take effect immediately
        auto_delete = self._entry.options.get(
            CONF_AUTO_DELETE, self._entry.data.get(CONF_AUTO_DELETE, True)
        )
        if auto_delete and index is not None:
            self.hass.async_create_background_task(
                self._async_auto_delete(index),
                f"sms_gateway_delete_{index}",
            )

    async def _async_auto_delete(self, index: int) -> None:
        """Delete a message from SIM after processing."""
        try:
            await self._client.delete_sms(index)
            _LOGGER.debug("Auto-deleted SMS index %d", index)
        except Exception as ex:
            _LOGGER.warning("Failed to auto-delete SMS index %d: %s", index, ex)

    async def _async_update_data(self) -> dict:
        """Fetch health and status from the gateway."""
        data: dict = {
            "health": None,
            "status": None,
        }

        try:
            health = await self._client.get_health()
            data["health"] = health
        except SmsGatewayAuthError as ex:
            raise ConfigEntryAuthFailed(str(ex)) from ex
        except SmsGatewayConnectionError as ex:
            _LOGGER.error("Gateway unreachable: %s", ex)
            raise UpdateFailed(f"Gateway unreachable: {ex}") from ex
        except SmsGatewayClientError as ex:
            _LOGGER.error("Health check failed: %s", ex)
            raise UpdateFailed(f"Health check failed: {ex}") from ex

        if data["health"]["status"] != "ok":
            raise UpdateFailed(
                f"Gateway unhealthy: {data['health'].get('message', 'Unknown')}"
            )

        try:
            data["status"] = await self._client.get_status()
        except Exception as ex:
            _LOGGER.warning("Status fetch failed: %s", ex)
            if self.data and self.data.get("status"):
                data["status"] = self.data["status"]

        return data
