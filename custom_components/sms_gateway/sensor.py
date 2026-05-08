"""Sensor platform for the SMS Gateway integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DOMAIN
from .coordinator import SmsGatewayCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SmsGatewaySensorEntityDescription(SensorEntityDescription):
    """Description for SMS Gateway sensor entities."""

    value_fn: callable[[dict], str | int | float | None]
    available_fn: callable[[dict], bool] | None = None


SENSOR_DESCRIPTIONS: tuple[SmsGatewaySensorEntityDescription, ...] = (
    SmsGatewaySensorEntityDescription(
        key="signal_dbm",
        translation_key="signal_dbm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            (d or {}).get("status", {}).get("signal_dbm")
        ),
    ),
    SmsGatewaySensorEntityDescription(
        key="signal_rssi",
        translation_key="signal_rssi",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal-cellular-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            (d or {}).get("status", {}).get("signal_strength")
        ),
    ),
    SmsGatewaySensorEntityDescription(
        key="network",
        translation_key="network",
        icon="mdi:cellphone-wireless",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            (d or {}).get("status", {}).get("network_registration_text")
        ),
    ),
    SmsGatewaySensorEntityDescription(
        key="smsc",
        translation_key="smsc",
        icon="mdi:message-processing-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            (d or {}).get("status", {}).get("smsc")
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: SmsGatewayCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    entities = [
        SmsGatewaySensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class SmsGatewaySensor(CoordinatorEntity[SmsGatewayCoordinator], SensorEntity):
    """Sensor entity representing a value from the SMS Gateway."""

    entity_description: SmsGatewaySensorEntityDescription

    def __init__(
        self,
        coordinator: SmsGatewayCoordinator,
        entry: ConfigEntry,
        description: SmsGatewaySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry

        gateway_name = entry.options.get(CONF_NAME, entry.title)
        self._attr_name = f"{gateway_name} {description.key.replace('_', ' ').title()}"
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> str | int | float | None:
        """Return the sensor value from coordinator data."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available:
            return False
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("health", {}).get("status") == "ok"
