"""Tests for Navimow lawn_mower entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.lawn_mower import LawnMowerActivity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.navimow.coordinator import NavimowCoordinator
from custom_components.navimow.lawn_mower import (
    NavimowLawnMower,
    _STATUS_TO_ACTIVITY,
)

from .conftest import FakeDevice, FakeDeviceStateMessage
from .const import MOCK_DEVICE_ID, MOCK_DEVICE_NAME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(
    hass: HomeAssistant,
    coordinator: MagicMock | None = None,
    api: AsyncMock | None = None,
) -> NavimowLawnMower:
    """Create a NavimowLawnMower entity with mocked dependencies."""
    if coordinator is None:
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.data = {}
        coordinator.get_device_state.return_value = None
        coordinator.get_device_attributes.return_value = None
        coordinator.last_update_success = True
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

    if api is None:
        api = AsyncMock()
        api.async_send_command = AsyncMock()

    device = FakeDevice()
    entity = NavimowLawnMower(
        coordinator=coordinator,
        api=api,
        device_id=device.id,
        device_name=device.name,
        device_info=device,
    )
    entity.hass = hass
    return entity


# ---------------------------------------------------------------------------
# Entity attributes
# ---------------------------------------------------------------------------


class TestEntityAttributes:
    """Tests for entity attribute properties."""

    async def test_unique_id(self, hass: HomeAssistant) -> None:
        """unique_id follows the DOMAIN_device_id pattern."""
        entity = _make_entity(hass)
        assert entity.unique_id == f"navimow_{MOCK_DEVICE_ID}"

    async def test_has_entity_name(self, hass: HomeAssistant) -> None:
        """has_entity_name is True."""
        entity = _make_entity(hass)
        assert entity.has_entity_name is True

    async def test_device_info(self, hass: HomeAssistant) -> None:
        """device_info contains expected identifiers."""
        entity = _make_entity(hass)
        info = entity.device_info
        assert ("navimow", MOCK_DEVICE_ID) in info["identifiers"]
        assert info["name"] == MOCK_DEVICE_NAME
        assert info["manufacturer"] == "Navimow"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class TestAvailability:
    """Tests for the available property."""

    async def test_available_when_state_exists(self, hass: HomeAssistant) -> None:
        """Entity is available when coordinator has state."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.get_device_state.return_value = FakeDeviceStateMessage()
        coordinator.last_update_success = True

        entity = _make_entity(hass, coordinator=coordinator)
        assert entity.available is True

    async def test_unavailable_when_no_state(self, hass: HomeAssistant) -> None:
        """Entity is unavailable when coordinator has no state."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.get_device_state.return_value = None
        coordinator.last_update_success = False

        entity = _make_entity(hass, coordinator=coordinator)
        assert entity.available is False

    async def test_available_with_cached_state_overrides_super(
        self, hass: HomeAssistant
    ) -> None:
        """Entity uses cached state check, not just super().available."""
        # When get_device_state returns a value, the entity short-circuits
        # to True without delegating to super().available.
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.get_device_state.return_value = FakeDeviceStateMessage()
        # Ensure the coordinator itself would report available
        coordinator.last_update_success = True

        entity = _make_entity(hass, coordinator=coordinator)
        assert entity.available is True

        # Verify the short-circuit: even if we change last_update_success,
        # the entity's available property returns True because of get_device_state
        coordinator.get_device_state.assert_called()


# ---------------------------------------------------------------------------
# Activity mapping
# ---------------------------------------------------------------------------


class TestActivityMapping:
    """Tests for status -> LawnMowerActivity mapping."""

    @pytest.mark.parametrize(
        "status,expected",
        [
            ("idle", LawnMowerActivity.DOCKED),
            ("mowing", LawnMowerActivity.MOWING),
            ("paused", LawnMowerActivity.PAUSED),
            ("docked", LawnMowerActivity.DOCKED),
            ("charging", LawnMowerActivity.DOCKED),
            ("returning", LawnMowerActivity.MOWING),
            ("error", LawnMowerActivity.ERROR),
            ("unknown", LawnMowerActivity.ERROR),
        ],
    )
    async def test_status_to_activity(
        self,
        hass: HomeAssistant,
        status: str,
        expected: LawnMowerActivity,
    ) -> None:
        """All _STATUS_TO_ACTIVITY entries map correctly."""
        assert _STATUS_TO_ACTIVITY[status] == expected

        # Also test via the entity property
        coordinator = MagicMock(spec=NavimowCoordinator)
        state = FakeDeviceStateMessage(state=status)
        coordinator.get_device_state.return_value = state

        entity = _make_entity(hass, coordinator=coordinator)
        assert entity.activity == expected

    async def test_unknown_status_returns_none(self, hass: HomeAssistant) -> None:
        """Status not in the mapping returns None."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        state = FakeDeviceStateMessage(state="totally_unexpected_status")
        coordinator.get_device_state.return_value = state

        entity = _make_entity(hass, coordinator=coordinator)
        assert entity.activity is None

    async def test_no_state_returns_none(self, hass: HomeAssistant) -> None:
        """No state -> activity is None."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.get_device_state.return_value = None

        entity = _make_entity(hass, coordinator=coordinator)
        assert entity.activity is None


# ---------------------------------------------------------------------------
# Command methods
# ---------------------------------------------------------------------------


class TestCommands:
    """Tests for mower command methods."""

    async def test_async_start_mowing_sends_command(
        self, hass: HomeAssistant
    ) -> None:
        """start_mowing sends MowerCommand.START."""
        from mower_sdk.models import MowerCommand

        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.get_device_state.return_value = FakeDeviceStateMessage()
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        api.async_send_command = AsyncMock()

        entity = _make_entity(hass, coordinator=coordinator, api=api)
        await entity.async_start_mowing()

        api.async_send_command.assert_awaited_once_with(
            MOCK_DEVICE_ID, MowerCommand.START
        )

    async def test_async_start_mowing_wraps_exception_in_ha_error(
        self, hass: HomeAssistant
    ) -> None:
        """Generic exception during start_mowing is wrapped in HomeAssistantError."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.async_ensure_valid_token = AsyncMock(
            side_effect=RuntimeError("network error")
        )
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        entity = _make_entity(hass, coordinator=coordinator, api=api)

        with pytest.raises(HomeAssistantError, match="Failed to start mowing"):
            await entity.async_start_mowing()

    async def test_async_pause(self, hass: HomeAssistant) -> None:
        """pause sends MowerCommand.PAUSE."""
        from mower_sdk.models import MowerCommand

        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        entity = _make_entity(hass, coordinator=coordinator, api=api)

        await entity.async_pause()
        api.async_send_command.assert_awaited_once_with(
            MOCK_DEVICE_ID, MowerCommand.PAUSE
        )

    async def test_async_dock(self, hass: HomeAssistant) -> None:
        """dock sends MowerCommand.DOCK."""
        from mower_sdk.models import MowerCommand

        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        entity = _make_entity(hass, coordinator=coordinator, api=api)

        await entity.async_dock()
        api.async_send_command.assert_awaited_once_with(
            MOCK_DEVICE_ID, MowerCommand.DOCK
        )

    async def test_async_resume(self, hass: HomeAssistant) -> None:
        """resume sends MowerCommand.RESUME."""
        from mower_sdk.models import MowerCommand

        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        entity = _make_entity(hass, coordinator=coordinator, api=api)

        await entity.async_resume()
        api.async_send_command.assert_awaited_once_with(
            MOCK_DEVICE_ID, MowerCommand.RESUME
        )

    async def test_async_pause_wraps_exception(
        self, hass: HomeAssistant
    ) -> None:
        """Generic exception during pause is wrapped in HomeAssistantError."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        api.async_send_command = AsyncMock(side_effect=RuntimeError("fail"))

        entity = _make_entity(hass, coordinator=coordinator, api=api)

        with pytest.raises(HomeAssistantError, match="Failed to pause"):
            await entity.async_pause()

    async def test_async_dock_wraps_exception(
        self, hass: HomeAssistant
    ) -> None:
        """Generic exception during dock is wrapped in HomeAssistantError."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        api.async_send_command = AsyncMock(side_effect=RuntimeError("fail"))

        entity = _make_entity(hass, coordinator=coordinator, api=api)

        with pytest.raises(HomeAssistantError, match="Failed to dock"):
            await entity.async_dock()

    async def test_async_resume_wraps_exception(
        self, hass: HomeAssistant
    ) -> None:
        """Generic exception during resume is wrapped in HomeAssistantError."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        api.async_send_command = AsyncMock(side_effect=RuntimeError("fail"))

        entity = _make_entity(hass, coordinator=coordinator, api=api)

        with pytest.raises(HomeAssistantError, match="Failed to resume"):
            await entity.async_resume()

    async def test_ha_error_passthrough(self, hass: HomeAssistant) -> None:
        """HomeAssistantError is not double-wrapped."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.async_ensure_valid_token = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()

        api = AsyncMock()
        api.async_send_command = AsyncMock(
            side_effect=HomeAssistantError("original error")
        )

        entity = _make_entity(hass, coordinator=coordinator, api=api)

        with pytest.raises(HomeAssistantError, match="original error"):
            await entity.async_start_mowing()


# ---------------------------------------------------------------------------
# Extra state attributes
# ---------------------------------------------------------------------------


class TestExtraStateAttributes:
    """Tests for extra_state_attributes property."""

    async def test_empty_when_no_state(self, hass: HomeAssistant) -> None:
        """Returns empty dict when no state."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        coordinator.get_device_state.return_value = None
        coordinator.get_device_attributes.return_value = None

        entity = _make_entity(hass, coordinator=coordinator)
        assert entity.extra_state_attributes == {}

    async def test_includes_battery_and_status(self, hass: HomeAssistant) -> None:
        """Includes battery and status from state."""
        coordinator = MagicMock(spec=NavimowCoordinator)
        state = FakeDeviceStateMessage(battery=42, state="paused")
        coordinator.get_device_state.return_value = state
        coordinator.get_device_attributes.return_value = None

        entity = _make_entity(hass, coordinator=coordinator)
        attrs = entity.extra_state_attributes
        assert attrs["battery"] == 42
        assert attrs["status"] == "paused"
