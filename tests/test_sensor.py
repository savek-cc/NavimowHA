"""Tests for Navimow sensor platform."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant

from custom_components.navimow.coordinator import NavimowCoordinator
from custom_components.navimow.sensor import (
    SENSOR_DESCRIPTIONS,
    NavimowSensor,
)

from .conftest import FakeDevice, FakeDeviceStateMessage
from .const import MOCK_DEVICE_ID


# ---------------------------------------------------------------------------
# Battery sensor description
# ---------------------------------------------------------------------------


class TestBatterySensorDescription:
    """Tests for the battery sensor entity description."""

    def test_sensor_descriptions_not_empty(self) -> None:
        """At least one sensor description exists."""
        assert len(SENSOR_DESCRIPTIONS) >= 1

    def test_battery_description_properties(self) -> None:
        """Battery description has correct device class and entity category."""
        battery_desc = SENSOR_DESCRIPTIONS[0]
        assert battery_desc.key == "battery"
        assert battery_desc.device_class == SensorDeviceClass.BATTERY
        assert battery_desc.entity_category == EntityCategory.DIAGNOSTIC
        assert battery_desc.native_unit_of_measurement == PERCENTAGE
        assert battery_desc.state_class == SensorStateClass.MEASUREMENT


# ---------------------------------------------------------------------------
# Battery sensor value
# ---------------------------------------------------------------------------


class TestBatterySensorValue:
    """Tests for the battery sensor value_fn."""

    async def test_battery_sensor_value(self, hass: HomeAssistant) -> None:
        """Battery sensor returns battery percentage from state."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.device = FakeDevice()
        state = FakeDeviceStateMessage(battery=87)
        coordinator.get_device_state.return_value = state
        coordinator.last_update_success = True

        battery_desc = SENSOR_DESCRIPTIONS[0]
        value = battery_desc.value_fn(coordinator)
        assert value == 87

    async def test_battery_sensor_value_none_when_no_state(
        self, hass: HomeAssistant
    ) -> None:
        """Battery sensor returns None when no state."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.device = FakeDevice()
        coordinator.get_device_state.return_value = None

        battery_desc = SENSOR_DESCRIPTIONS[0]
        value = battery_desc.value_fn(coordinator)
        assert value is None


# ---------------------------------------------------------------------------
# Sensor entity
# ---------------------------------------------------------------------------


class TestNavimowSensor:
    """Tests for the NavimowSensor entity."""

    async def test_unique_id(self, hass: HomeAssistant) -> None:
        """unique_id follows the DOMAIN_device_id_key pattern."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.device = FakeDevice()
        coordinator.get_device_state.return_value = None
        coordinator.last_update_success = True

        sensor = NavimowSensor(
            coordinator=coordinator,
            entity_description=SENSOR_DESCRIPTIONS[0],
        )
        assert sensor.unique_id == f"navimow_{MOCK_DEVICE_ID}_battery"

    async def test_has_entity_name(self, hass: HomeAssistant) -> None:
        """has_entity_name is True."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.device = FakeDevice()
        coordinator.get_device_state.return_value = None

        sensor = NavimowSensor(
            coordinator=coordinator,
            entity_description=SENSOR_DESCRIPTIONS[0],
        )
        assert sensor.has_entity_name is True

    async def test_native_value(self, hass: HomeAssistant) -> None:
        """native_value delegates to value_fn."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.device = FakeDevice()
        state = FakeDeviceStateMessage(battery=63)
        coordinator.get_device_state.return_value = state

        sensor = NavimowSensor(
            coordinator=coordinator,
            entity_description=SENSOR_DESCRIPTIONS[0],
        )
        sensor.hass = hass
        assert sensor.native_value == 63

    async def test_available_with_state(self, hass: HomeAssistant) -> None:
        """Sensor is available when state exists."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.device = FakeDevice()
        coordinator.get_device_state.return_value = FakeDeviceStateMessage()
        coordinator.last_update_success = True

        sensor = NavimowSensor(
            coordinator=coordinator,
            entity_description=SENSOR_DESCRIPTIONS[0],
        )
        assert sensor.available is True

    async def test_unavailable_without_state(self, hass: HomeAssistant) -> None:
        """Sensor is unavailable when no state and last update failed."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.device = FakeDevice()
        coordinator.get_device_state.return_value = None
        coordinator.last_update_success = False

        sensor = NavimowSensor(
            coordinator=coordinator,
            entity_description=SENSOR_DESCRIPTIONS[0],
        )
        assert sensor.available is False

    async def test_device_info(self, hass: HomeAssistant) -> None:
        """device_info contains correct identifiers."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.device = FakeDevice()

        sensor = NavimowSensor(
            coordinator=coordinator,
            entity_description=SENSOR_DESCRIPTIONS[0],
        )
        info = sensor.device_info
        assert ("navimow", MOCK_DEVICE_ID) in info["identifiers"]
        assert info["manufacturer"] == "Navimow"
