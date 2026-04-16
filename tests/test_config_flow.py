"""Tests for Navimow config flow (OAuth2 + reauth + test-before-configure)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow

from custom_components.navimow.auth import NavimowOAuth2Implementation
from custom_components.navimow.const import CLIENT_ID, CLIENT_SECRET, DOMAIN

from .const import (
    MOCK_ACCESS_TOKEN,
    MOCK_CONFIG_ENTRY_DATA,
    MOCK_TOKEN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_oauth2_impl(hass: HomeAssistant) -> NavimowOAuth2Implementation:
    """Register the NavimowOAuth2Implementation so the flow can find it."""
    impl = NavimowOAuth2Implementation(
        hass=hass,
        domain=DOMAIN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    config_entry_oauth2_flow.async_register_implementation(hass, DOMAIN, impl)
    return impl


# ---------------------------------------------------------------------------
# Full user flow
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("mock_setup_entry")
class TestFullFlow:
    """Test the full user-initiated OAuth2 flow."""

    async def test_full_flow_init_shows_external_step_or_form(
        self,
        hass: HomeAssistant,
        aioclient_mock,
    ) -> None:
        """User starts flow -> sees external step or pick-implementation form."""
        _register_oauth2_impl(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # With AbstractOAuth2FlowHandler, the first step is EXTERNAL_STEP
        # (redirect to auth URL) or FORM (pick implementation).
        assert result["type"] in (
            FlowResultType.EXTERNAL_STEP,
            FlowResultType.FORM,
        )

    async def test_flow_already_configured_aborts(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Second attempt with same unique_id -> abort already_configured."""
        from homeassistant.config_entries import ConfigEntry

        _register_oauth2_impl(hass)

        # Create an existing entry with the same unique_id via the proper HA API
        existing_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Navimow",
            data=dict(MOCK_CONFIG_ENTRY_DATA),
            source=config_entries.SOURCE_USER,
            unique_id=DOMAIN,
            discovery_keys={},
            options={},
            subentries_data=None,
        )
        await hass.config_entries.async_add(existing_entry)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# async_oauth_create_entry (test-before-configure)
#
# This is the core of the config flow: after OAuth2 token exchange, the flow
# calls async_oauth_create_entry which probes the API before creating the entry.
# We test this method directly since the full OAuth2 redirect cycle requires
# browser interaction.
# ---------------------------------------------------------------------------


class TestOAuthCreateEntry:
    """Test async_oauth_create_entry probe logic."""

    def _make_handler(self, hass: HomeAssistant) -> "NavimowOAuth2FlowHandler":
        """Create a NavimowOAuth2FlowHandler with hass attached."""
        from custom_components.navimow.config_flow import NavimowOAuth2FlowHandler

        handler = NavimowOAuth2FlowHandler()
        handler.hass = hass
        return handler

    async def test_probe_success_creates_entry(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Successful probe creates a config entry."""
        handler = self._make_handler(hass)
        handler.context = {"source": config_entries.SOURCE_USER}

        with patch(
            "custom_components.navimow.config_flow.MowerAPI",
        ) as mock_api_cls, patch(
            "custom_components.navimow.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ):
            mock_api_instance = AsyncMock()
            mock_api_instance.async_get_devices = AsyncMock(return_value=[MagicMock()])
            mock_api_cls.return_value = mock_api_instance

            result = await handler.async_oauth_create_entry(
                {"token": {"access_token": MOCK_ACCESS_TOKEN}}
            )
            assert result["type"] is FlowResultType.CREATE_ENTRY
            assert result["title"] == "Navimow"
            assert result["data"]["auth_implementation"] == DOMAIN

    async def test_probe_cannot_connect(
        self,
        hass: HomeAssistant,
    ) -> None:
        """MowerAPIError during probe -> abort cannot_connect."""
        from mower_sdk.errors import MowerAPIError

        handler = self._make_handler(hass)

        with patch(
            "custom_components.navimow.config_flow.MowerAPI",
        ) as mock_api_cls, patch(
            "custom_components.navimow.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ):
            mock_api_instance = AsyncMock()
            mock_api_instance.async_get_devices = AsyncMock(
                side_effect=MowerAPIError("connection failed")
            )
            mock_api_cls.return_value = mock_api_instance

            result = await handler.async_oauth_create_entry(
                {"token": {"access_token": MOCK_ACCESS_TOKEN}}
            )
            assert result["type"] is FlowResultType.ABORT
            assert result["reason"] == "cannot_connect"

    async def test_probe_unknown_error(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Generic exception during probe -> abort unknown."""
        handler = self._make_handler(hass)

        with patch(
            "custom_components.navimow.config_flow.MowerAPI",
        ) as mock_api_cls, patch(
            "custom_components.navimow.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ):
            mock_api_instance = AsyncMock()
            mock_api_instance.async_get_devices = AsyncMock(
                side_effect=ValueError("unexpected")
            )
            mock_api_cls.return_value = mock_api_instance

            result = await handler.async_oauth_create_entry(
                {"token": {"access_token": MOCK_ACCESS_TOKEN}}
            )
            assert result["type"] is FlowResultType.ABORT
            assert result["reason"] == "unknown"

    async def test_probe_no_access_token_aborts_oauth_error(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Missing access_token -> abort oauth_error."""
        handler = self._make_handler(hass)

        result = await handler.async_oauth_create_entry({"token": {}})
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "oauth_error"

    async def test_probe_empty_data_aborts_oauth_error(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Empty data dict -> abort oauth_error."""
        handler = self._make_handler(hass)

        result = await handler.async_oauth_create_entry({})
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "oauth_error"

    async def test_reauth_source_updates_existing_entry(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Reauth source updates existing entry and aborts reauth_successful."""
        from homeassistant.config_entries import ConfigEntry

        # Create a real ConfigEntry registered in hass
        existing_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Navimow",
            data=dict(MOCK_CONFIG_ENTRY_DATA),
            source=config_entries.SOURCE_USER,
            unique_id=DOMAIN,
            discovery_keys={},
            options={},
            subentries_data=None,
        )
        await hass.config_entries.async_add(existing_entry)

        handler = self._make_handler(hass)
        handler.context = {"source": config_entries.SOURCE_REAUTH}
        handler.entry = existing_entry

        with patch(
            "custom_components.navimow.config_flow.MowerAPI",
        ) as mock_api_cls, patch(
            "custom_components.navimow.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ):
            mock_api_instance = AsyncMock()
            mock_api_instance.async_get_devices = AsyncMock(return_value=[MagicMock()])
            mock_api_cls.return_value = mock_api_instance

            result = await handler.async_oauth_create_entry(
                {"token": {"access_token": "new-token"}}
            )
            assert result["type"] is FlowResultType.ABORT
            assert result["reason"] == "reauth_successful"

    async def test_entry_data_contains_mqtt_config(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Created entry contains MQTT broker config."""
        handler = self._make_handler(hass)
        handler.context = {"source": config_entries.SOURCE_USER}

        with patch(
            "custom_components.navimow.config_flow.MowerAPI",
        ) as mock_api_cls, patch(
            "custom_components.navimow.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ):
            mock_api_instance = AsyncMock()
            mock_api_instance.async_get_devices = AsyncMock(return_value=[MagicMock()])
            mock_api_cls.return_value = mock_api_instance

            result = await handler.async_oauth_create_entry(
                {"token": {"access_token": MOCK_ACCESS_TOKEN}}
            )
            assert result["type"] is FlowResultType.CREATE_ENTRY
            data = result["data"]
            assert "mqtt_broker" in data
            assert "mqtt_port" in data
            assert "api_base_url" in data


# ---------------------------------------------------------------------------
# Reauth flow
# ---------------------------------------------------------------------------


class TestReauthFlow:
    """Test the reauth flow."""

    def _make_handler(self, hass: HomeAssistant) -> "NavimowOAuth2FlowHandler":
        from custom_components.navimow.config_flow import NavimowOAuth2FlowHandler

        handler = NavimowOAuth2FlowHandler()
        handler.hass = hass
        return handler

    async def test_reauth_flow_shows_confirm_form(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Reauth step shows a form with empty schema (not None)."""
        handler = self._make_handler(hass)

        result = await handler.async_step_reauth_confirm(user_input=None)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"
        assert result.get("data_schema") is not None

    async def test_reauth_delegates_to_reauth_confirm(
        self,
        hass: HomeAssistant,
    ) -> None:
        """async_step_reauth delegates to async_step_reauth_confirm."""
        handler = self._make_handler(hass)

        result = await handler.async_step_reauth(user_input=None)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

    async def test_reauth_confirm_submits_to_oauth_flow(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Submitting the reauth confirm form triggers the OAuth2 flow."""
        _register_oauth2_impl(hass)
        handler = self._make_handler(hass)

        # When user_input is provided, it calls super().async_step_user()
        # which starts the OAuth2 authorization
        with patch.object(
            handler.__class__.__bases__[0],
            "async_step_user",
            new_callable=AsyncMock,
            return_value={"type": FlowResultType.EXTERNAL_STEP},
        ):
            result = await handler.async_step_reauth_confirm(user_input={})
            assert result["type"] is FlowResultType.EXTERNAL_STEP

    async def test_reauth_full_success(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Full reauth: confirm form -> new token -> entry updated."""
        from homeassistant.config_entries import ConfigEntry

        existing_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Navimow",
            data=dict(MOCK_CONFIG_ENTRY_DATA),
            source=config_entries.SOURCE_USER,
            unique_id=DOMAIN,
            discovery_keys={},
            options={},
            subentries_data=None,
        )
        await hass.config_entries.async_add(existing_entry)

        handler = self._make_handler(hass)
        handler.context = {"source": config_entries.SOURCE_REAUTH}
        handler.entry = existing_entry

        with patch(
            "custom_components.navimow.config_flow.MowerAPI",
        ) as mock_api_cls, patch(
            "custom_components.navimow.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ):
            mock_api_instance = AsyncMock()
            mock_api_instance.async_get_devices = AsyncMock(return_value=[MagicMock()])
            mock_api_cls.return_value = mock_api_instance

            result = await handler.async_oauth_create_entry(
                {"token": {"access_token": "new-token"}}
            )
            assert result["type"] is FlowResultType.ABORT
            assert result["reason"] == "reauth_successful"


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class TestOptionsFlow:
    """Test the options flow handler."""

    async def test_options_flow_shows_form(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Options flow shows a form on init."""
        from custom_components.navimow.config_flow import NavimowOptionsFlowHandler

        entry = MagicMock()
        entry.data = dict(MOCK_CONFIG_ENTRY_DATA)
        entry.options = {}

        handler = NavimowOptionsFlowHandler(entry)
        handler.hass = hass

        result = await handler.async_step_init(user_input=None)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

    async def test_options_flow_creates_entry_on_submit(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Submitting options creates an entry."""
        from custom_components.navimow.config_flow import NavimowOptionsFlowHandler

        entry = MagicMock()
        entry.data = dict(MOCK_CONFIG_ENTRY_DATA)
        entry.options = {}

        handler = NavimowOptionsFlowHandler(entry)
        handler.hass = hass

        result = await handler.async_step_init(user_input={"some_option": True})
        assert result["type"] is FlowResultType.CREATE_ENTRY


# ---------------------------------------------------------------------------
# OAuth2 implementation registration
# ---------------------------------------------------------------------------


class TestOAuth2ImplementationProperty:
    """Test the oauth2_implementation property on the handler."""

    async def test_registers_implementation(
        self,
        hass: HomeAssistant,
    ) -> None:
        """oauth2_implementation property registers the implementation."""
        from custom_components.navimow.config_flow import NavimowOAuth2FlowHandler

        handler = NavimowOAuth2FlowHandler()
        handler.hass = hass

        impl = handler.oauth2_implementation
        assert isinstance(impl, NavimowOAuth2Implementation)
