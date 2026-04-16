"""Diagnostics support for Navimow integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = config_entry.runtime_data
    if not runtime:
        return {"error": "Integration not loaded"}

    sdk = runtime.get("sdk")
    coordinators: dict = runtime.get("coordinators", {})
    devices = runtime.get("devices", [])

    return {
        "mqtt_connected": sdk.is_connected if sdk else False,
        "device_count": len(devices),
        "coordinators": {
            device_id: {
                "last_data_source": coord._last_data_source,
                "mqtt_stale": coord._last_mqtt_update is None,
                "http_fallback_active": coord._last_http_fetch is not None,
            }
            for device_id, coord in coordinators.items()
        },
        "config": {
            "api_base_url": config_entry.data.get("api_base_url"),
            "mqtt_broker": config_entry.data.get("mqtt_broker"),
            "mqtt_port": config_entry.data.get("mqtt_port"),
            # Never expose tokens or passwords
        },
    }
