"""Tests for logic/auth.py."""

import pytest

import ckan.model as model
import ckan.plugins.toolkit as tk
import ckan.tests.factories as factories
import ckan.tests.helpers as test_helpers


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestAircanAuth:
    def _editor_with_resource(self):
        user = factories.User()
        org = factories.Organization(
            users=[{"name": user["name"], "capacity": "editor"}]
        )
        dataset = factories.Dataset(owner_org=org["id"])
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        return user, resource

    def test_aircan_submit_allowed_for_editor(self, mock_airflow_client):
        user, resource = self._editor_with_resource()
        context = {"user": user["name"], "model": model}
        assert test_helpers.call_auth(
            "aircan_submit", context=context, resource_id=resource["id"]
        )

    def test_aircan_submit_denied_for_anonymous(self, mock_airflow_client):
        _, resource = self._editor_with_resource()
        context = {"user": "", "model": model}
        with pytest.raises(tk.NotAuthorized):
            test_helpers.call_auth(
                "aircan_submit", context=context, resource_id=resource["id"]
            )

    def test_aircan_status_allowed_for_anonymous_on_public_resource(
        self, mock_airflow_client
    ):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        context = {"user": "", "model": model}
        assert test_helpers.call_auth(
            "aircan_status", context=context, resource_id=resource["id"]
        )

    def test_aircan_hook_allowed_for_editor(self, mock_airflow_client):
        user, resource = self._editor_with_resource()
        context = {"user": user["name"], "model": model}
        assert test_helpers.call_auth(
            "aircan_hook", context=context, resource_id=resource["id"]
        )

    def test_aircan_hook_denied_for_anonymous(self, mock_airflow_client):
        _, resource = self._editor_with_resource()
        context = {"user": "", "model": model}
        with pytest.raises(tk.NotAuthorized):
            test_helpers.call_auth(
                "aircan_hook", context=context, resource_id=resource["id"]
            )
