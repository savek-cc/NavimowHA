"""Test constants for Navimow integration tests."""
from __future__ import annotations

MOCK_ACCESS_TOKEN = "mock-access-token-abc123"
MOCK_REFRESH_TOKEN = "mock-refresh-token-def456"

MOCK_TOKEN = {
    "access_token": MOCK_ACCESS_TOKEN,
    "refresh_token": MOCK_REFRESH_TOKEN,
    "token_type": "Bearer",
    "expires_in": 86400,
}

MOCK_TOKEN_NO_REFRESH = {
    "access_token": MOCK_ACCESS_TOKEN,
    "token_type": "Bearer",
    "expires_in": 86400,
}

MOCK_DEVICE_ID = "device-001"
MOCK_DEVICE_NAME = "My Navimow"
MOCK_DEVICE_MODEL = "H-Series"
MOCK_DEVICE_SERIAL = "SN-12345678"
MOCK_DEVICE_FW = "1.2.3"

MOCK_MQTT_INFO = {
    "mqttHost": "mqtt.test.navimow.com",
    "mqttUrl": "wss://mqtt.test.navimow.com:443/mqtt?token=abc",
    "userName": "mqtt-user",
    "pwdInfo": "mqtt-password-secret",
}

MOCK_CONFIG_ENTRY_DATA = {
    "auth_implementation": "navimow",
    "token": MOCK_TOKEN,
    "api_base_url": "https://navimow-fra.ninebot.com",
    "mqtt_broker": "mqtt.navimow.com",
    "mqtt_port": 1883,
    "mqtt_username": None,
    "mqtt_password": None,
}

MOCK_DEVICE_STATUS_DICT = {
    "device_id": MOCK_DEVICE_ID,
    "status": "mowing",
    "battery": 75,
    "signal_strength": -60,
    "position": {"lat": 50.0, "lon": 8.0},
    "error_code": "none",
    "error_message": None,
    "timestamp": 1700000000,
}

MOCK_STATE_MESSAGE_DICT = {
    "device_id": MOCK_DEVICE_ID,
    "timestamp": 1700000000,
    "state": "mowing",
    "battery": 75,
    "signal_strength": -60,
    "position": {"lat": 50.0, "lon": 8.0},
    "error": None,
    "metrics": None,
}
