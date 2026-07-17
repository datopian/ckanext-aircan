"""Tests for views.py."""

import pytest

import ckan.plugins.toolkit as tk
import ckan.tests.factories as factories


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestAircanBlueprint:
    def test_routes_are_registered(self, app):
        assert (
            tk.h.url_for("aircan.resource_pipeline", id="ds", resource_id="res")
            == "/dataset/ds/resource_pipeline/res"
        )
        assert (
            tk.h.url_for("aircan.validation_report", id="ds", resource_id="res")
            == "/dataset/ds/resource_pipeline/res/validation_report"
        )

    def test_resource_pipeline_404_for_missing_dataset(self, app):
        url = tk.h.url_for(
            "aircan.resource_pipeline", id="missing", resource_id="missing"
        )
        resp = app.get(url)
        assert resp.status_code == 404

    def test_resource_pipeline_submit_denied_for_anonymous(
        self, app, mock_airflow_client
    ):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        mock_airflow_client.reset_mock()

        url = tk.h.url_for(
            "aircan.resource_pipeline",
            id=dataset["name"],
            resource_id=resource["id"],
        )
        resp = app.post(url)

        assert resp.status_code == 403
        mock_airflow_client.trigger_dag.assert_not_called()
