"""Shared fixtures for Navimow integration tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from .const import (
    MOCK_ACCESS_TOKEN,
    MOCK_CONFIG_ENTRY_DATA,
    MOCK_DEVICE_FW,
    MOCK_DEVICE_ID,
    MOCK_DEVICE_MODEL,
    MOCK_DEVICE_NAME,
    MOCK_DEVICE_SERIAL,
    MOCK_MQTT_INFO,
    MOCK_TOKEN,
)

# Try to import from the real SDK; fall back to stubs at the bottom of this file.
try:
    from mower_sdk.models import (
        Device as _RealDevice,
        DeviceAttributesMessage as _RealDAM,
        DeviceStateMessage as _RealDSM,
        DeviceStatus as _RealDS,
        MowerCommand as _RealMC,
    )

    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Auto-fixture: enable custom integrations for all tests in this suite
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def enable_custom_integrations(
    enable_custom_integrations: None,  # provided by pytest-homeassistant-custom-component
) -> None:
    """Enable custom integrations in all tests."""


# ---------------------------------------------------------------------------
# Fake SDK model classes
#
# When the real navimow-sdk is installed we use its dataclasses directly
# (they are simple @dataclass types). When running without the SDK
# (e.g. CI without the wheel) we provide lightweight stand-ins.
# ---------------------------------------------------------------------------


@dataclass
class FakeDevice:
    """Lightweight stand-in for mower_sdk.models.Device."""

    id: str = MOCK_DEVICE_ID
    name: str = MOCK_DEVICE_NAME
    model: str = MOCK_DEVICE_MODEL
    firmware_version: str = MOCK_DEVICE_FW
    serial_number: str = MOCK_DEVICE_SERIAL
    mac_address: str | None = None
    online: bool = True
    extra: dict | None = None
    product_key: str | None = None
    device_name: str | None = None
    iot_id: str | None = None


@dataclass
class FakeDeviceStateMessage:
    """Stand-in for mower_sdk.models.DeviceStateMessage."""

    device_id: str = MOCK_DEVICE_ID
    timestamp: int = 1700000000
    state: str = "mowing"
    battery: int = 75
    signal_strength: int = -60
    position: dict | None = field(default_factory=lambda: {"lat": 50.0, "lon": 8.0})
    error: dict | None = None
    metrics: dict | None = None


@dataclass
class FakeDeviceAttributesMessage:
    """Stand-in for mower_sdk.models.DeviceAttributesMessage."""

    device_id: str = MOCK_DEVICE_ID
    attributes: dict = field(default_factory=lambda: {"blade_life": 90})


@dataclass
class FakeDeviceStatus:
    """Stand-in for mower_sdk.models.DeviceStatus."""

    device_id: str = MOCK_DEVICE_ID
    timestamp: int = 1700000000
    status: MagicMock = field(default_factory=lambda: MagicMock(value="mowing"))
    battery: int = 75
    signal_strength: int = -60
    position: dict | None = field(default_factory=lambda: {"lat": 50.0, "lon": 8.0})
    error_code: MagicMock = field(default_factory=lambda: MagicMock(value="none"))
    error_message: str | None = None
    mowing_time: int | None = None
    total_mowing_time: int | None = None
    extra: dict | None = None


class FakeMowerCommand:
    """Stand-in for mower_sdk.models.MowerCommand."""

    START = "start"
    PAUSE = "pause"
    DOCK = "dock"
    RESUME = "resume"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_oauth_token() -> dict[str, Any]:
    """Return a valid OAuth2 token dict."""
    return dict(MOCK_TOKEN)


@pytest.fixture
def fake_device() -> FakeDevice:
    """Return a fake device."""
    return FakeDevice()


@pytest.fixture
def fake_state_message() -> FakeDeviceStateMessage:
    """Return a fake state message."""
    return FakeDeviceStateMessage()


@pytest.fixture
def fake_attributes_message() -> FakeDeviceAttributesMessage:
    """Return a fake attributes message."""
    return FakeDeviceAttributesMessage()


@pytest.fixture
def mock_mower_api(fake_device: FakeDevice) -> AsyncMock:
    """Return a mocked MowerAPI with sensible defaults."""
    api = AsyncMock()
    api.async_get_devices = AsyncMock(return_value=[fake_device])
    api.async_get_mqtt_user_info = AsyncMock(return_value=dict(MOCK_MQTT_INFO))
    api.async_get_device_status = AsyncMock(return_value=FakeDeviceStatus())
    api.async_send_command = AsyncMock(return_value=None)
    api.set_token = MagicMock()
    return api


@pytest.fixture
def mock_navimow_sdk() -> MagicMock:
    """Return a mocked NavimowSDK."""
    sdk = MagicMock()
    sdk.is_connected = True
    sdk.on_state = MagicMock()
    sdk.on_attributes = MagicMock()
    sdk.get_cached_state = MagicMock(return_value=None)
    sdk.get_cached_attributes = MagicMock(return_value=None)
    sdk.connect = MagicMock()
    sdk.disconnect = MagicMock()
    sdk.update_mqtt_credentials = MagicMock()
    return sdk


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MagicMock:
    """Return a MockConfigEntry for the navimow domain."""
    from homeassistant.config_entries import ConfigEntry

    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test-entry-id"
    entry.domain = "navimow"
    entry.data = dict(MOCK_CONFIG_ENTRY_DATA)
    entry.options = {}
    entry.runtime_data = None
    entry.unique_id = "navimow"
    entry.title = "Navimow"
    return entry


@pytest.fixture
def mock_setup_entry() -> None:
    """Prevent actual setup during config flow tests."""
    with patch(
        "custom_components.navimow.async_setup_entry",
        return_value=True,
    ):
        yield


# ---------------------------------------------------------------------------
# Stub module installation for mower_sdk (only needed when SDK is missing)
# ---------------------------------------------------------------------------


def install_mower_sdk_stubs() -> None:
    """Install minimal mower_sdk stubs into sys.modules.

    This allows importing custom_components.navimow.* without having
    the real navimow-sdk package installed. When the real SDK is
    available this function is a no-op.
    """
    import sys
    import types

    if "mower_sdk" in sys.modules:
        return

    # mower_sdk package
    mower_sdk = types.ModuleType("mower_sdk")
    sys.modules["mower_sdk"] = mower_sdk

    # mower_sdk.api
    api_mod = types.ModuleType("mower_sdk.api")

    class _MowerAPI:
        def __init__(self, session=None, token=None, base_url=None):
            self.session = session
            self._token = token
            self.base_url = base_url

        def set_token(self, token):
            self._token = token

        async def async_get_devices(self):
            return []

        async def async_get_mqtt_user_info(self):
            return {}

        async def async_get_device_status(self, device_id):
            return None

        async def async_send_command(self, device_id, command):
            return None

    api_mod.MowerAPI = _MowerAPI
    sys.modules["mower_sdk.api"] = api_mod

    # mower_sdk.errors
    errors_mod = types.ModuleType("mower_sdk.errors")

    class MowerAPIError(Exception):
        pass

    errors_mod.MowerAPIError = MowerAPIError
    sys.modules["mower_sdk.errors"] = errors_mod

    # mower_sdk.models
    models_mod = types.ModuleType("mower_sdk.models")
    models_mod.Device = FakeDevice
    models_mod.DeviceStateMessage = FakeDeviceStateMessage
    models_mod.DeviceAttributesMessage = FakeDeviceAttributesMessage
    models_mod.DeviceStatus = FakeDeviceStatus
    models_mod.MowerCommand = FakeMowerCommand
    sys.modules["mower_sdk.models"] = models_mod

    # mower_sdk.sdk
    sdk_mod = types.ModuleType("mower_sdk.sdk")

    class _NavimowSDK:
        def __init__(self, **kwargs):
            self.is_connected = False
            self._on_state = None
            self._on_attributes = None

        def on_state(self, cb):
            self._on_state = cb

        def on_attributes(self, cb):
            self._on_attributes = cb

        def get_cached_state(self, device_id):
            return None

        def get_cached_attributes(self, device_id):
            return None

        def connect(self):
            pass

        def disconnect(self):
            pass

        def update_mqtt_credentials(self, **kwargs):
            pass

    sdk_mod.NavimowSDK = _NavimowSDK
    sys.modules["mower_sdk.sdk"] = sdk_mod


# Install stubs only if the real SDK is not available
if not _SDK_AVAILABLE:
    install_mower_sdk_stubs()
