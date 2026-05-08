# SMS Gateway — Home Assistant Integration

A Home Assistant custom integration for the [SMS Gateway SIM7600](https://github.com/macsatcom/sms-gateway-sim7600).
Send and receive SMS messages directly from your automations — no cloud service required.

## Features

- **`notify.sms_gateway`** — Send SMS from any automation, script, or dashboard
- **`sms_gateway_incoming_message` event** — Trigger automations when an SMS is received
- **Sensor entities** — Signal strength (dBm), network registration, SMSC, unread message count
- **UI config flow** — No YAML editing required, set up entirely from the HA interface
- **Auto-delete** — Automatically clears processed messages from the SIM card (configurable)
- **Multi-gateway support** — Connect multiple SIM7600 modems

## Requirements

- Home Assistant 2024.1 or later
- A running [SMS Gateway SIM7600](https://github.com/macsatcom/sms-gateway-sim7600) Docker container on your network
- The gateway's full API port (default 8000) must be reachable from Home Assistant

## Installation

### Manual installation

```bash
# Copy the integration to your custom_components directory
cp -r sms_gateway /path/to/your/ha/config/custom_components/

# Restart Home Assistant
ha core restart
```

### Via HACS (coming soon)

Add this repository as a custom repository in HACS.

## Configuration

1. In Home Assistant, go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **SMS Gateway**
4. Enter your gateway's connection details:

| Field | Description |
|-------|-------------|
| **Host URL** | Full URL to your gateway, e.g. `http://192.168.1.100` |
| **API Port** | The full API port (default `8000`) |
| **API Key** | Your configured API token from the gateway's `.env` |

5. Click **Submit**. The integration will validate the connection.
6. (Optional) Configure options:
   - **Poll interval** — How often to check for new SMS (default: 30 seconds)
   - **Auto-delete** — Delete messages from SIM after processing (default: ON)

## Usage

### Sending SMS

Use the `notify.sms_gateway` service from any automation:

```yaml
service: notify.sms_gateway
data:
  message: "Motion detected in the garage"
  target: "+4512345678"
```

Or from a script:

```yaml
alias: "Send garage alert"
sequence:
  - service: notify.sms_gateway
    data:
      message: "Garage door has been open for 10 minutes"
      target: "+4512345678"
```

Multiple recipients are not supported in a single call — use multiple service calls.

### Receiving SMS

When a new SMS arrives, the integration fires a `sms_gateway_incoming_message` event on the Home Assistant event bus.

**Automation example — respond to a keyword:**

```yaml
alias: "SMS: Garage door command"
description: "Open or close the garage door via SMS"
trigger:
  - platform: event
    event_type: sms_gateway_incoming_message
condition:
  - condition: template
    value_template: >
      {{ trigger.event.data.sender == "+4512345678" }}
action:
  - choose:
      - conditions:
          - condition: template
            value_template: >
              {{ trigger.event.data.message | lower == "garage open" }}
        sequence:
          - service: cover.open_cover
            target:
              entity_id: cover.garage_door
          - service: notify.sms_gateway
            data:
              message: "Garage opened"
              target: "{{ trigger.event.data.sender }}"
      - conditions:
          - condition: template
            value_template: >
              {{ trigger.event.data.message | lower == "garage close" }}
        sequence:
          - service: cover.close_cover
            target:
              entity_id: cover.garage_door
          - service: notify.sms_gateway
            data:
              message: "Garage closed"
              target: "{{ trigger.event.data.sender }}"
```

**Event data structure:**

```json
{
  "gateway_id": "01J...",
  "gateway_name": "SMS Gateway",
  "sender": "+4512345678",
  "message": "garage open",
  "timestamp": "26/05/07,10:23:15+08",
  "index": 3
}
```

### Dashboards

Add sensor cards to your dashboard to monitor the gateway:

```yaml
type: entities
entities:
  - entity: sensor.sms_gateway_signal_strength
  - entity: sensor.sms_gateway_network
```

## Options

The following options can be changed after setup via the integration's **Configure** button:

| Option | Default | Description |
|--------|---------|-------------|
| **Display name** | SMS Gateway | Name shown in HA (also used for entity names) |
| **Poll interval** | 30 | Seconds between inbox checks (5–300) |
| **Auto-delete** | ON | Delete SMS from SIM card after processing. Turn OFF to keep messages on the SIM (e.g., for debugging). |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "Cannot connect" during setup | Wrong host/port or Docker network issue | Verify `docker compose ps`, check host IP and port. The gateway must be on the same network. |
| "Invalid API key" during setup | Wrong or expired token | Check `API_KEYS` in the gateway's `.env` file |
| "Modem not ready" during setup | SIM7600E not responding | Check USB connection, verify `/dev/ttyUSB2` is passed through to Docker |
| Entities show "unavailable" | Gateway container stopped or network issue | Check `docker compose logs sms-gateway` |
| Not receiving SMS events | SSE stream disconnected, or auto_delete removed the message before processing | Check gateway logs for SSE errors. SMS arrives in real-time via push — polling interval does not affect event delivery, only sensor health updates. |
| Events fire multiple times | Message not deleted from SIM and arrives again on next read | Enable `auto_delete` in options, or the gateway may re-deliver the message. |

## Target Gateway Configuration

For this integration to work, your SMS Gateway container needs the full API port exposed (8000 by default). Example `docker-compose.yml` snippet:

```yaml
services:
  sms-gateway:
    image: ghcr.io/macsatcom/sms-gateway-sim7600:latest
    ports:
      - "8000:8000"   # Full API — required for this integration
    # ...
```

Make sure `API_KEYS` is set in your `.env`:

```env
API_KEYS=homeassistant:your-generated-token-here
```

## License

MIT
