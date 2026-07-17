"""Tests for logic/action.py."""

import json

import pytest
from werkzeug.exceptions import HTTPException

import ckan.plugins.toolkit as tk
import ckan.tests.factories as factories
import ckan.tests.helpers as test_helpers


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestAircanSubmit:
    def test_submit_triggers_dag_and_queues_task(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        mock_airflow_client.reset_mock()

        result = test_helpers.call_action("aircan_submit", **resource)

        assert result["dag_run_id"] == "test-dag-run-id"
        assert result["dag_run"]["state"] == "queued"

        conf = mock_airflow_client.trigger_dag.call_args.kwargs["conf"]
        assert conf["resource"]["id"] == resource["id"]
        assert "ckan_config" in conf
        assert "gcs_config" in conf
        assert "s3_config" in conf

        task_status = test_helpers.call_action(
            "task_status_show",
            entity_id=resource["id"],
            task_type="aircan",
            key="pipeline",
        )
        assert task_status["state"] == "queued"
        value = json.loads(task_status["value"])
        assert value["dag_run_id"] == "test-dag-run-id"
        assert len(value["logs"]) == 1

    @pytest.mark.usefixtures("with_request_context")
    def test_submit_rejects_disallowed_format(self, mock_airflow_client):
        dataset = factories.Dataset()

        with pytest.raises(HTTPException):
            test_helpers.call_action(
                "aircan_submit",
                id="not-a-real-resource",
                package_id=dataset["id"],
                format="pdf",
            )
        mock_airflow_client.trigger_dag.assert_not_called()

    @pytest.mark.usefixtures("with_request_context")
    def test_submit_rejects_datastore_managed_resources(self, mock_airflow_client):
        dataset = factories.Dataset()

        with pytest.raises(HTTPException):
            test_helpers.call_action(
                "aircan_submit",
                id="not-a-real-resource",
                package_id=dataset["id"],
                format="CSV",
                url_type="datastore",
            )
        mock_airflow_client.trigger_dag.assert_not_called()


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestAircanStatus:
    def test_status_of_submitted_resource(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        test_helpers.call_action("aircan_submit", **resource)

        result = test_helpers.call_action("aircan_status", resource_id=resource["id"])

        # DB state is "queued"; live state comes from Airflow (mocked as running)
        assert result["state"] == "running"
        assert result["dag"]["dag_run_id"] == "test-dag-run-id"
        mock_airflow_client.get_dag_run.assert_called_with("test-dag-run-id")

    def test_status_accepts_id_alias(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        test_helpers.call_action("aircan_submit", **resource)

        result = test_helpers.call_action("aircan_status", id=resource["id"])
        assert result["entity_id"] == resource["id"]

    def test_status_missing_task_raises_not_found(self):
        with pytest.raises(tk.ObjectNotFound):
            test_helpers.call_action("aircan_status", resource_id="no-such-resource")


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestAircanHook:
    def test_missing_resource_id_raises(self):
        with pytest.raises(tk.ValidationError):
            test_helpers.call_action("aircan_hook", state="running")

    def test_creates_task_status_and_appends_logs(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")

        # clear_logs drops the "queued" entry written when the resource
        # creation auto-submitted the pipeline
        result = test_helpers.call_action(
            "aircan_hook",
            resource_id=resource["id"],
            dag_run_id="run-1",
            state="running",
            message="Ingestion started",
            clear_logs=True,
        )
        assert result["state"] == "running"
        assert result["entity_id"] == resource["id"]

        result = test_helpers.call_action(
            "aircan_hook",
            resource_id=resource["id"],
            state="running",
            message="Halfway there",
        )
        value = json.loads(result["value"])
        assert [entry["message"] for entry in value["logs"]] == [
            "Ingestion started",
            "Halfway there",
        ]
        # dag_run_id is carried over from the previously stored value
        assert value["dag_run_id"] == "run-1"

    def test_clear_logs_resets_previous_logs(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")

        test_helpers.call_action(
            "aircan_hook",
            resource_id=resource["id"],
            state="running",
            message="Old log entry",
        )
        result = test_helpers.call_action(
            "aircan_hook",
            resource_id=resource["id"],
            dag_run_id="run-2",
            state="queued",
            message="Requeued",
            clear_logs=True,
        )

        value = json.loads(result["value"])
        assert [entry["message"] for entry in value["logs"]] == ["Requeued"]
        assert result["error"] == ""

    def test_error_marks_task_failed(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")

        result = test_helpers.call_action(
            "aircan_hook",
            resource_id=resource["id"],
            type="error",
            message="Boom",
        )

        assert result["state"] == "failed"
        assert json.loads(result["error"]) == "Boom"
        # error messages are stored in `error`, not appended to the logs
        value = json.loads(result["value"])
        assert "Boom" not in [entry["message"] for entry in value["logs"]]

    def test_success_sets_datastore_active(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        shown = test_helpers.call_action("resource_show", id=resource["id"])
        assert not shown.get("datastore_active")

        result = test_helpers.call_action(
            "aircan_hook",
            resource_id=resource["id"],
            state="success",
            message="Ingestion finished",
        )
        assert result["state"] == "success"

        shown = test_helpers.call_action("resource_show", id=resource["id"])
        assert shown["datastore_active"]
