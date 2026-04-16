"""Tests for NavimowCoordinator."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.navimow.coordinator import NavimowCoordinator

from .conftest import (
    FakeDevice,
    FakeDeviceAttributesMessage,
    FakeDeviceStateMessage,
    FakeDeviceStatus,
)
from .const import MOCK_ACCESS_TOKEN, MOCK_TOKEN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(
    hass: HomeAssistant,
    sdk: MagicMock | None = None,
    api: AsyncMock | None = None,
    device: FakeDevice | None = None,
    oauth_session: MagicMock | None = None,
) -> NavimowCoordinator:
    """Create a NavimowCoordinator with sensible defaults."""
    if sdk is None:
        sdk = MagicMock()
        sdk.on_state = MagicMock()
        sdk.on_attributes = MagicMock()
        sdk.get_cached_state = MagicMock(return_value=None)
        sdk.get_cached_attributes = MagicMock(return_value=None)
    if api is None:
        api = AsyncMock()
        api.set_token = MagicMock()
    if device is None:
        device = FakeDevice()

    return NavimowCoordinator(
        hass=hass,
        sdk=sdk,
        api=api,
        device=device,
        oauth_session=oauth_session,
    )


# ---------------------------------------------------------------------------
# Token refresh tests
# ---------------------------------------------------------------------------


class TestAsyncEnsureValidToken:
    """Tests for async_ensure_valid_token."""

    async def test_success(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """Token is fetched and set on API."""
        session = MagicMock()
        session.async_ensure_token_valid = AsyncMock()
        session.token = dict(MOCK_TOKEN)

        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api, oauth_session=session
        )

        result = await coord.async_ensure_valid_token()
        assert result == MOCK_ACCESS_TOKEN
        mock_mower_api.set_token.assert_called_once_with(MOCK_ACCESS_TOKEN)

    async def test_auth_failure_propagates(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """ConfigEntryAuthFailed from token refresh is re-raised."""
        session = MagicMock()
        session.async_ensure_token_valid = AsyncMock(
            side_effect=ConfigEntryAuthFailed("expired")
        )
        session.token = None

        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api, oauth_session=session
        )

        with pytest.raises(ConfigEntryAuthFailed):
            await coord.async_ensure_valid_token()

    async def test_transient_error_uses_cache(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """Transient error + cached token -> uses cached token."""
        session = MagicMock()
        session.async_ensure_token_valid = AsyncMock(
            side_effect=ConnectionError("DNS timeout")
        )
        session.token = dict(MOCK_TOKEN)

        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api, oauth_session=session
        )

        result = await coord.async_ensure_valid_token()
        assert result == MOCK_ACCESS_TOKEN
        mock_mower_api.set_token.assert_called_once_with(MOCK_ACCESS_TOKEN)

    async def test_transient_error_no_cache_raises(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """Transient error + no cached token -> ConfigEntryAuthFailed."""
        session = MagicMock()
        session.async_ensure_token_valid = AsyncMock(
            side_effect=ConnectionError("DNS timeout")
        )
        session.token = None

        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api, oauth_session=session
        )

        with pytest.raises(ConfigEntryAuthFailed, match="no cached token"):
            await coord.async_ensure_valid_token()

    async def test_no_oauth_session_returns_none(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """No oauth_session -> returns None."""
        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api, oauth_session=None
        )

        result = await coord.async_ensure_valid_token()
        assert result is None

    async def test_no_access_token_after_refresh(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """Token dict present but no access_token key -> ConfigEntryAuthFailed."""
        session = MagicMock()
        session.async_ensure_token_valid = AsyncMock()
        session.token = {"token_type": "Bearer"}  # no access_token

        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api, oauth_session=session
        )

        with pytest.raises(ConfigEntryAuthFailed, match="No access token"):
            await coord.async_ensure_valid_token()


# ---------------------------------------------------------------------------
# Data update tests
# ---------------------------------------------------------------------------


class TestUpdateData:
    """Tests for _async_update_data."""

    async def test_uses_cached_mqtt_state(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
    ) -> None:
        """Coordinator picks up state from SDK cache."""
        sdk = MagicMock()
        sdk.on_state = MagicMock()
        sdk.on_attributes = MagicMock()
        state = FakeDeviceStateMessage()
        sdk.get_cached_state = MagicMock(return_value=state)
        sdk.get_cached_attributes = MagicMock(return_value=None)

        coord = _make_coordinator(hass, sdk=sdk, api=mock_mower_api)
        await coord.async_setup()

        # Prevent HTTP fallback from overwriting the cached state
        coord._last_http_fetch = time.monotonic()

        with patch.object(coord, "async_ensure_valid_token", new_callable=AsyncMock):
            data = await coord._async_update_data()

        assert data["state"] is state
        assert data["meta"]["last_data_source"] == "mqtt_cache"

    async def test_http_fallback_when_mqtt_stale(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
    ) -> None:
        """When MQTT is stale and HTTP interval allows, fetches via HTTP."""
        sdk = MagicMock()
        sdk.on_state = MagicMock()
        sdk.on_attributes = MagicMock()
        sdk.get_cached_state = MagicMock(return_value=None)
        sdk.get_cached_attributes = MagicMock(return_value=None)

        coord = _make_coordinator(hass, sdk=sdk, api=mock_mower_api)
        await coord.async_setup()

        # MQTT is stale (never received), HTTP never fetched
        with patch.object(coord, "async_ensure_valid_token", new_callable=AsyncMock):
            data = await coord._async_update_data()

        assert data["meta"]["last_data_source"] == "http_fallback"
        mock_mower_api.async_get_device_status.assert_called_once()

    async def test_http_fallback_respects_interval(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
    ) -> None:
        """HTTP fallback is rate-limited by HTTP_FALLBACK_MIN_INTERVAL."""
        sdk = MagicMock()
        sdk.on_state = MagicMock()
        sdk.on_attributes = MagicMock()
        sdk.get_cached_state = MagicMock(return_value=None)
        sdk.get_cached_attributes = MagicMock(return_value=None)

        coord = _make_coordinator(hass, sdk=sdk, api=mock_mower_api)
        await coord.async_setup()

        # Simulate a recent HTTP fetch
        coord._last_http_fetch = time.monotonic()

        with patch.object(coord, "async_ensure_valid_token", new_callable=AsyncMock):
            data = await coord._async_update_data()

        # HTTP should NOT have been called because interval hasn't elapsed
        mock_mower_api.async_get_device_status.assert_not_called()


# ---------------------------------------------------------------------------
# Log-when-unavailable
# ---------------------------------------------------------------------------


class TestLogWhenUnavailable:
    """Tests for log-on-transition behavior."""

    async def test_logs_once_on_transition(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
    ) -> None:
        """Transition from available -> unavailable logs exactly once."""
        sdk = MagicMock()
        sdk.on_state = MagicMock()
        sdk.on_attributes = MagicMock()
        sdk.get_cached_state = MagicMock(return_value=None)
        sdk.get_cached_attributes = MagicMock(return_value=None)

        coord = _make_coordinator(hass, sdk=sdk, api=mock_mower_api)
        await coord.async_setup()
        coord._last_http_fetch = time.monotonic()  # prevent HTTP fetch

        with patch.object(
            coord, "async_ensure_valid_token", new_callable=AsyncMock
        ), patch(
            "custom_components.navimow.coordinator._LOGGER"
        ) as mock_logger:
            # First call: _was_available is None -> unavailable transition
            await coord._async_update_data()
            warning_count_1 = mock_logger.warning.call_count

            # Second call: still unavailable -> no additional log
            await coord._async_update_data()
            warning_count_2 = mock_logger.warning.call_count

            # Only one warning for the transition
            assert warning_count_1 == 1
            assert warning_count_2 == 1


# ---------------------------------------------------------------------------
# MQTT callback handling
# ---------------------------------------------------------------------------


class TestHandleState:
    """Tests for _handle_state via call_soon_threadsafe."""

    async def test_handle_state_updates_via_event_loop(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
    ) -> None:
        """_handle_state uses call_soon_threadsafe to dispatch to event loop."""
        sdk = MagicMock()
        sdk.on_state = MagicMock()
        sdk.on_attributes = MagicMock()
        sdk.get_cached_state = MagicMock(return_value=None)
        sdk.get_cached_attributes = MagicMock(return_value=None)

        coord = _make_coordinator(hass, sdk=sdk, api=mock_mower_api)
        await coord.async_setup()

        state = FakeDeviceStateMessage()

        with patch.object(hass.loop, "call_soon_threadsafe") as mock_call:
            coord._handle_state(state)
            mock_call.assert_called_once()
            args = mock_call.call_args[0]
            assert args[0] == coord._update_from_state
            assert args[1] is state

    async def test_handle_state_ignores_other_device(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
    ) -> None:
        """State messages for other devices are ignored."""
        sdk = MagicMock()
        sdk.on_state = MagicMock()
        sdk.on_attributes = MagicMock()
        sdk.get_cached_state = MagicMock(return_value=None)
        sdk.get_cached_attributes = MagicMock(return_value=None)

        coord = _make_coordinator(hass, sdk=sdk, api=mock_mower_api)
        await coord.async_setup()

        state = FakeDeviceStateMessage(device_id="other-device")

        with patch.object(hass.loop, "call_soon_threadsafe") as mock_call:
            coord._handle_state(state)
            mock_call.assert_not_called()

    async def test_handle_attributes_updates_via_event_loop(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
    ) -> None:
        """_handle_attributes uses call_soon_threadsafe."""
        sdk = MagicMock()
        sdk.on_state = MagicMock()
        sdk.on_attributes = MagicMock()
        sdk.get_cached_state = MagicMock(return_value=None)
        sdk.get_cached_attributes = MagicMock(return_value=None)

        coord = _make_coordinator(hass, sdk=sdk, api=mock_mower_api)
        await coord.async_setup()

        attrs = FakeDeviceAttributesMessage()

        with patch.object(hass.loop, "call_soon_threadsafe") as mock_call:
            coord._handle_attributes(attrs)
            mock_call.assert_called_once()
            args = mock_call.call_args[0]
            assert args[0] == coord._update_from_attributes
            assert args[1] is attrs


# ---------------------------------------------------------------------------
# Diagnostics data
# ---------------------------------------------------------------------------


class TestDiagnosticsData:
    """Tests for get_diagnostics_data."""

    async def test_get_diagnostics_data_keys(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """get_diagnostics_data returns expected keys."""
        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api
        )
        diag = coord.get_diagnostics_data()

        assert "last_data_source" in diag
        assert "mqtt_stale" in diag
        assert "http_fallback_active" in diag
        assert "device_available" in diag

    async def test_get_diagnostics_data_initial_state(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """Initial diagnostics state is correct."""
        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api
        )
        diag = coord.get_diagnostics_data()

        assert diag["last_data_source"] is None
        assert diag["mqtt_stale"] is True
        assert diag["http_fallback_active"] is False
        assert diag["device_available"] is False


# ---------------------------------------------------------------------------
# async_setup
# ---------------------------------------------------------------------------


class TestAsyncSetup:
    """Tests for coordinator async_setup."""

    async def test_registers_callbacks(
        self,
        hass: HomeAssistant,
        mock_mower_api: AsyncMock,
        mock_navimow_sdk: MagicMock,
    ) -> None:
        """async_setup registers on_state and on_attributes callbacks."""
        coord = _make_coordinator(
            hass, sdk=mock_navimow_sdk, api=mock_mower_api
        )
        await coord.async_setup()

        mock_navimow_sdk.on_state.assert_called_once_with(coord._handle_state)
        mock_navimow_sdk.on_attributes.assert_called_once_with(coord._handle_attributes)
