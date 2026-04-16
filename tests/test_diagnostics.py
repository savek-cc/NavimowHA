"""Tests for Navimow diagnostics."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from homeassistant.core import HomeAssistant

from custom_components.navimow.diagnostics import (
    async_get_config_entry_diagnostics,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDiagnostics:
    """Tests for async_get_config_entry_diagnostics."""

    async def test_contains_expected_keys(self, hass: HomeAssistant) -> None:
        """Diagnostics output contains all expected top-level keys."""
        sdk = MagicMock()
        sdk.is_connected = True

        coordinator = MagicMock()
        coordinator.get_diagnostics_data.return_value = {
            "last_data_source": "mqtt_push",
            "mqtt_stale": False,
            "http_fallback_active": False,
            "device_available": True,
        }

        entry = MagicMock()
        entry.runtime_data = {
            "sdk": sdk,
            "api": MagicMock(),
            "devices": [MagicMock()],
            "coordinators": {"device-001": coordinator},
            "oauth_session": MagicMock(),
        }
        entry.data = {
            "api_base_url": "https://navimow-fra.ninebot.com",
            "mqtt_broker": "mqtt.navimow.com",
            "mqtt_port": 1883,
            "token": {"access_token": "secret-token"},
            "mqtt_password": "secret-password",
        }

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert "mqtt_connected" in result
        assert "device_count" in result
        assert "coordinators" in result
        assert "config" in result
        assert result["mqtt_connected"] is True
        assert result["device_count"] == 1

    async def test_redacts_tokens_and_passwords(
        self, hass: HomeAssistant
    ) -> None:
        """Diagnostics output must not contain tokens or passwords."""
        sdk = MagicMock()
        sdk.is_connected = False

        entry = MagicMock()
        entry.runtime_data = {
            "sdk": sdk,
            "api": MagicMock(),
            "devices": [],
            "coordinators": {},
            "oauth_session": MagicMock(),
        }
        entry.data = {
            "api_base_url": "https://navimow-fra.ninebot.com",
            "mqtt_broker": "mqtt.navimow.com",
            "mqtt_port": 1883,
            "token": {"access_token": "super-secret-token"},
            "mqtt_password": "super-secret-password",
            "mqtt_username": "mqtt-user",
        }

        result = await async_get_config_entry_diagnostics(hass, entry)

        # The config section should only contain safe keys
        config = result["config"]
        assert "api_base_url" in config
        assert "mqtt_broker" in config
        assert "mqtt_port" in config

        # Tokens and passwords must NOT appear in the diagnostics output
        result_str = str(result)
        assert "super-secret-token" not in result_str
        assert "super-secret-password" not in result_str

    async def test_not_loaded_returns_error(
        self, hass: HomeAssistant
    ) -> None:
        """When integration not loaded, returns error dict."""
        entry = MagicMock()
        entry.runtime_data = None

        result = await async_get_config_entry_diagnostics(hass, entry)
        assert result == {"error": "Integration not loaded"}

    async def test_coordinator_diagnostics_forwarded(
        self, hass: HomeAssistant
    ) -> None:
        """Per-device coordinator diagnostics are included."""
        sdk = MagicMock()
        sdk.is_connected = True

        coord1 = MagicMock()
        coord1.get_diagnostics_data.return_value = {
            "last_data_source": "mqtt_push",
            "mqtt_stale": False,
            "http_fallback_active": False,
            "device_available": True,
        }
        coord2 = MagicMock()
        coord2.get_diagnostics_data.return_value = {
            "last_data_source": "http_fallback",
            "mqtt_stale": True,
            "http_fallback_active": True,
            "device_available": True,
        }

        entry = MagicMock()
        entry.runtime_data = {
            "sdk": sdk,
            "api": MagicMock(),
            "devices": [MagicMock(), MagicMock()],
            "coordinators": {"dev-1": coord1, "dev-2": coord2},
            "oauth_session": MagicMock(),
        }
        entry.data = {}

        result = await async_get_config_entry_diagnostics(hass, entry)

        assert len(result["coordinators"]) == 2
        assert result["coordinators"]["dev-1"]["last_data_source"] == "mqtt_push"
        assert result["coordinators"]["dev-2"]["last_data_source"] == "http_fallback"
