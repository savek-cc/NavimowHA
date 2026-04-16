"""Tests for Navimow integration setup (__init__.py)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.navimow import async_setup, async_setup_entry, async_unload_entry

from .conftest import FakeDevice
from .const import (
    MOCK_CONFIG_ENTRY_DATA,
    MOCK_MQTT_INFO,
    MOCK_TOKEN,
)

DOMAIN = "navimow"


# ---------------------------------------------------------------------------
# async_setup
# ---------------------------------------------------------------------------


class TestAsyncSetup:
    """Tests for async_setup (component-level setup)."""

    async def test_registers_oauth2_implementation(
        self,
        hass: HomeAssistant,
    ) -> None:
        """async_setup registers the OAuth2 implementation."""
        result = await async_setup(hass, {})
        assert result is True
        assert DOMAIN in hass.data


# ---------------------------------------------------------------------------
# async_unload_entry
# ---------------------------------------------------------------------------


class TestAsyncUnloadEntry:
    """Tests for async_unload_entry."""

    async def test_happy_path(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Unload disconnects SDK and returns True."""
        sdk = MagicMock()
        sdk.disconnect = MagicMock()
        unload_flag = [False]

        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.runtime_data = {
            "sdk": sdk,
            "api": MagicMock(),
            "devices": [],
            "coordinators": {},
            "oauth_session": MagicMock(),
            "unload_flag": unload_flag,
        }

        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await async_unload_entry(hass, entry)
            assert result is True
            sdk.disconnect.assert_called_once()

    async def test_marks_unload_flag(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Unload sets the unload flag to prevent MQTT credential refresh."""
        sdk = MagicMock()
        sdk.disconnect = MagicMock()
        unload_flag = [False]

        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.runtime_data = {
            "sdk": sdk,
            "api": MagicMock(),
            "devices": [],
            "coordinators": {},
            "oauth_session": MagicMock(),
            "unload_flag": unload_flag,
        }

        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await async_unload_entry(hass, entry)
            assert unload_flag[0] is True

    async def test_unload_when_no_runtime_data(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Unload with no runtime_data still succeeds."""
        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.runtime_data = None

        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await async_unload_entry(hass, entry)
            assert result is True

    async def test_unload_disconnect_error_handled(
        self,
        hass: HomeAssistant,
    ) -> None:
        """SDK disconnect error is caught and logged."""
        sdk = MagicMock()
        sdk.disconnect = MagicMock(side_effect=RuntimeError("MQTT error"))

        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.runtime_data = {
            "sdk": sdk,
            "api": MagicMock(),
            "devices": [],
            "coordinators": {},
            "oauth_session": MagicMock(),
            "unload_flag": [False],
        }

        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        ):
            # Should not raise despite disconnect error
            result = await async_unload_entry(hass, entry)
            assert result is True

    async def test_unload_returns_false_when_platforms_fail(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Unload returns False when platform unload fails."""
        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.runtime_data = {
            "sdk": MagicMock(),
            "api": MagicMock(),
            "devices": [],
            "coordinators": {},
            "oauth_session": MagicMock(),
            "unload_flag": [False],
        }

        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await async_unload_entry(hass, entry)
            assert result is False


# ---------------------------------------------------------------------------
# async_setup_entry
#
# Full integration setup has many dependencies (OAuth2, MowerAPI, NavimowSDK,
# coordinator, MQTT). Testing the happy path end-to-end requires extensive
# patching of closures and executors. We test the key error paths instead,
# which exercise the critical branching logic.
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    """Tests for async_setup_entry error paths."""

    async def test_auth_failure_invalid_implementation(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Non-NavimowOAuth2Implementation -> ConfigEntryAuthFailed."""
        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.data = dict(MOCK_CONFIG_ENTRY_DATA)
        entry.runtime_data = None

        with patch(
            "custom_components.navimow.config_entry_oauth2_flow.async_get_config_entry_implementation",
            new_callable=AsyncMock,
            return_value=MagicMock(),  # Not a NavimowOAuth2Implementation
        ):
            with pytest.raises(ConfigEntryAuthFailed, match="Invalid OAuth2"):
                await async_setup_entry(hass, entry)

    async def test_auth_failure_no_token(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Token fetch returns None and no fallback -> ConfigEntryAuthFailed."""
        from custom_components.navimow.auth import NavimowOAuth2Implementation

        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.data = {**MOCK_CONFIG_ENTRY_DATA, "token": None}
        entry.runtime_data = None

        mock_impl = MagicMock(spec=NavimowOAuth2Implementation)

        with patch(
            "custom_components.navimow.config_entry_oauth2_flow.async_get_config_entry_implementation",
            new_callable=AsyncMock,
            return_value=mock_impl,
        ), patch(
            "custom_components.navimow.config_entry_oauth2_flow.OAuth2Session",
        ) as mock_session_cls, patch(
            "custom_components.navimow.async_get_oauth_token",
            new_callable=AsyncMock,
            return_value=None,
        ):
            mock_session = MagicMock()
            mock_session.token = None
            mock_session_cls.return_value = mock_session

            with pytest.raises(ConfigEntryAuthFailed, match="No valid token"):
                await async_setup_entry(hass, entry)

    async def test_auth_failure_no_access_token(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Token dict without access_token -> ConfigEntryAuthFailed."""
        from custom_components.navimow.auth import NavimowOAuth2Implementation

        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.data = dict(MOCK_CONFIG_ENTRY_DATA)
        entry.runtime_data = None

        mock_impl = MagicMock(spec=NavimowOAuth2Implementation)

        with patch(
            "custom_components.navimow.config_entry_oauth2_flow.async_get_config_entry_implementation",
            new_callable=AsyncMock,
            return_value=mock_impl,
        ), patch(
            "custom_components.navimow.config_entry_oauth2_flow.OAuth2Session",
        ) as mock_session_cls, patch(
            "custom_components.navimow.async_get_oauth_token",
            new_callable=AsyncMock,
            return_value={"token_type": "Bearer"},  # no access_token key
        ):
            mock_session = MagicMock()
            mock_session.token = {"token_type": "Bearer"}
            mock_session_cls.return_value = mock_session

            with pytest.raises(ConfigEntryAuthFailed, match="No access token"):
                await async_setup_entry(hass, entry)

    async def test_device_discovery_fails(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Device discovery MowerAPIError -> ConfigEntryNotReady."""
        from mower_sdk.errors import MowerAPIError

        from custom_components.navimow.auth import NavimowOAuth2Implementation

        entry = MagicMock()
        entry.entry_id = "test-entry"
        entry.data = dict(MOCK_CONFIG_ENTRY_DATA)
        entry.runtime_data = None

        mock_impl = MagicMock(spec=NavimowOAuth2Implementation)
        mock_api = AsyncMock()
        mock_api.async_get_devices = AsyncMock(
            side_effect=MowerAPIError("timeout")
        )

        with patch(
            "custom_components.navimow.config_entry_oauth2_flow.async_get_config_entry_implementation",
            new_callable=AsyncMock,
            return_value=mock_impl,
        ), patch(
            "custom_components.navimow.config_entry_oauth2_flow.OAuth2Session",
        ) as mock_session_cls, patch(
            "custom_components.navimow.async_get_oauth_token",
            new_callable=AsyncMock,
            return_value=dict(MOCK_TOKEN),
        ), patch(
            "custom_components.navimow.async_get_clientsession",
            return_value=MagicMock(),
        ), patch(
            "mower_sdk.api.MowerAPI",
            return_value=mock_api,
        ):
            mock_session = MagicMock()
            mock_session.token = dict(MOCK_TOKEN)
            mock_session_cls.return_value = mock_session

            with pytest.raises(ConfigEntryNotReady, match="Failed to discover"):
                await async_setup_entry(hass, entry)
