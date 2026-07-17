"""Tests for plugin.py."""

import pytest

import ckan.plugins as plugins
import ckan.plugins.toolkit as tk


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins")
def test_plugin_is_loaded():
    assert plugins.plugin_loaded("aircan")


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins")
def test_actions_are_registered():
    for action_name in ("aircan_submit", "aircan_status", "aircan_hook"):
        assert tk.get_action(action_name)


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins")
def test_helpers_are_registered():
    for helper_name in (
        "get_aircan_badge",
        "allowed_aircan_format",
        "is_validate_records_enabled",
    ):
        assert helper_name in tk.h
