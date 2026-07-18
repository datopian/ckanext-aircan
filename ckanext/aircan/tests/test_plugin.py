"""Tests for plugin.py."""

import pytest

import ckan.model as model
import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
import ckan.tests.factories as factories
from ckan.model.domain_object import DomainObjectOperation


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


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestAutoSubmit:
    def test_resource_create_submits_exactly_once(self, mock_airflow_client):
        dataset = factories.Dataset()
        factories.Resource(package_id=dataset["id"], format="CSV")

        assert mock_airflow_client.trigger_dag.call_count == 1

    def test_duplicate_notifications_are_deduped(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")

        # simulate CKAN notifying the same resource again within one request,
        # as happens on file uploads (resource lands in both the "new" and
        # "changed" object caches of DomainObjectModificationExtension)
        plugin_obj = plugins.get_plugin("aircan")
        res_obj = model.Resource.get(resource["id"])
        plugin_obj.notify(res_obj, DomainObjectOperation.new)

        assert mock_airflow_client.trigger_dag.call_count == 1

    def test_disallowed_format_is_skipped_without_breaking_creation(
        self, mock_airflow_client
    ):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="PDF")

        assert resource["id"]
        mock_airflow_client.trigger_dag.assert_not_called()

    def test_airflow_failure_does_not_break_resource_creation(
        self, mock_airflow_client
    ):
        import requests

        mock_airflow_client.trigger_dag.side_effect = requests.ConnectionError(
            "airflow down"
        )
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")

        assert resource["id"]
