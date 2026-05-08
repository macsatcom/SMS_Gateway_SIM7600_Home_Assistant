"""Constants for the SMS Gateway integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "sms_gateway"

# Config flow keys
CONF_HOST: Final = "host"
CONF_API_PORT: Final = "api_port"
CONF_API_KEY: Final = "api_key"

# Options flow keys
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_AUTO_DELETE: Final = "auto_delete"
CONF_NAME: Final = "name"

# Default values
DEFAULT_API_PORT: Final = 8000
DEFAULT_POLL_INTERVAL: Final = 30  # seconds
DEFAULT_AUTO_DELETE: Final = True
DEFAULT_NAME: Final = "SMS Gateway"
DEFAULT_TIMEOUT: Final = 30  # seconds for HTTP requests

# Event
EVENT_INCOMING_SMS: Final = "sms_gateway_incoming_message"

# SSE stream
STREAM_RECONNECT_DELAY: Final = 5  # base seconds for reconnect backoff
