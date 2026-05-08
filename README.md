# SMS Gateway SIM7600 — Home Assistant Integration

Send and receive SMS messages directly from Home Assistant automations using a SIM7600E cellular modem — no cloud service required.

## Features

- **`notify.sms_gateway`** — Send SMS from any automation, script, or dashboard
- **`sms_gateway_incoming_message` event** — Trigger automations when an SMS arrives (real-time via SSE push)
- **Sensor entities** — Signal strength (dBm & RSSI), network registration, SMSC
- **UI config flow** — Set up entirely from the Home Assistant interface, no YAML needed
- **Auto-delete** — Optionally clear processed messages from the SIM card
- **Multi-gateway support** — Connect multiple SIM7600 modems

## Requirements

- Home Assistant 2024.1+
- A running [SMS Gateway SIM7600](https://github.com/macsatcom/sms-gateway-sim7600) Docker container on your network

## Installation via HACS

1. Make sure [HACS](https://hacs.xyz) is installed in your Home Assistant instance
2. Go to **HACS → Integrations → Custom repositories**
3. Add this repository URL as a custom repository (category: Integration)
4. Click **Explore & Add Integrations**, search for **SMS Gateway**
5. Click **Install**
6. Restart Home Assistant

## Manual installation

Copy the `custom_components/sms_gateway/` directory to your HA config's `custom_components/` directory, then restart Home Assistant.

## Configuration

1. In Home Assistant, go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **SMS Gateway**
4. Enter your gateway's connection details:
   - **Host URL** — e.g. `http://192.168.1.100`
   - **API Port** — default `8000`
   - **API Key** — from the gateway's `.env` file

## Usage

### Sending SMS

```yaml
service: notify.send_message
target:
  entity_id: notify.sms_gateway
data:
  message: "Motion detected in the garage"
  target: "+4512345678"
```

### Receiving SMS

Received SMS fire the `sms_gateway_incoming_message` event on the HA event bus:

```yaml
automation:
  - alias: "Handle incoming SMS"
    trigger:
      - platform: event
        event_type: sms_gateway_incoming_message
    action:
      - service: notify.send_message
        target:
          entity_id: notify.sms_gateway
        data:
          message: "I got your message!"
          target: "{{ trigger.event.data.sender }}"
```

## API Reference

See [api-full.md](api-full.md) for the complete REST API documentation for the underlying gateway.

Gateway Docker container: [macsatcom/sms-gateway-sim7600](https://github.com/macsatcom/sms-gateway-sim7600)

## License

MIT
