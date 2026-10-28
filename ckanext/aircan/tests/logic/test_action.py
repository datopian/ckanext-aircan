"""Tests for logic/action.py."""

import json

import pytest
from werkzeug.exceptions import HTTPException

import ckan.plugins.toolkit as tk
import ckan.tests.factories as factories
import ckan.tests.helpers as test_helpers
from ckanext.aircan.logic import action


@pytest.mark.parametrize(
    ("global_value", "package_value", "expected"),
    [
        (True, "true", True),
        (True, "false", False),
        (True, None, True),
        (False, "true", False),
    ],
)
def test_validate_records_enabled(
    monkeypatch, global_value, package_value, expected
):
    monkeypatch.setattr(
        action.tk.config,
        "get",
        lambda key, default=None: global_value
        if key == "ckanext.aircan.validate_records"
        else default,
    )

    def package_show(_context, _data_dict):
        return {"aircan_validate_records": package_value}

    monkeypatch.setattr(
        action.tk,
        "get_action",
        lambda name: package_show if name == "package_show" else None,
    )

    assert (
        action._validate_records_enabled({}, {"package_id": "package-id"})
        is expected
    )


@pytest.mark.parametrize(
    ("frontend_url", "expected"),
    [
        ("https://portal.example.com/", "https://portal.example.com/datasets/my-ds/resources/res-1/validation-report"),
        ("", ""),
        (None, ""),
    ],
)
def test_validation_report_url(monkeypatch, frontend_url, expected):
    monkeypatch.setattr(
        action.tk.config,
        "get",
        lambda key, default=None: frontend_url
        if key == "ckanext.aircan.frontend_url"
        else default,
    )
    monkeypatch.setattr(
        action.tk,
        "get_action",
        lambda name: (lambda _c, _d: {"name": "my-ds"}),
    )

    assert (
        action._validation_report_url({}, {"id": "res-1", "package_id": "pkg-id"})
        == expected
    )


def test_validation_report_url_needs_package_id(monkeypatch):
    monkeypatch.setattr(
        action.tk.config, "get", lambda key, default=None: "https://portal.example.com"
    )

    assert action._validation_report_url({}, {"id": "res-1"}) == ""


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


@pytest.mark.ckan_config("ckan.plugins", "aircan datatables_view")
@pytest.mark.ckan_config("ckan.views.default_views", "datatables_view")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestAircanHookDatastoreViews:
    def _view_types(self, resource_id):
        views = test_helpers.call_action("resource_view_list", id=resource_id)
        return [view["view_type"] for view in views]

    def test_success_creates_datastore_views(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        # datastore views are not created on resource creation
        assert "datatables_view" not in self._view_types(resource["id"])

        test_helpers.call_action(
            "aircan_hook", resource_id=resource["id"], state="success"
        )

        assert self._view_types(resource["id"]).count("datatables_view") == 1

    def test_success_creates_views_when_read_misses_flag(
        self, mock_airflow_client, monkeypatch
    ):
        # A read right after the flag is written can still return the old
        # resource (e.g. a stale search-index copy); the views must not depend
        # on it.
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        get_action = action.tk.get_action

        def stale_resource_show(context, data_dict):
            resource_dict = get_action("resource_show")(context, data_dict)
            resource_dict.pop("datastore_active", None)
            return resource_dict

        monkeypatch.setattr(
            action.tk,
            "get_action",
            lambda name: stale_resource_show
            if name == "resource_show"
            else get_action(name),
        )

        test_helpers.call_action(
            "aircan_hook", resource_id=resource["id"], state="success"
        )

        assert self._view_types(resource["id"]).count("datatables_view") == 1

    def test_repeated_success_does_not_duplicate_views(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")

        for _ in range(2):
            test_helpers.call_action(
                "aircan_hook", resource_id=resource["id"], state="success"
            )

        assert self._view_types(resource["id"]).count("datatables_view") == 1

    def test_non_success_does_not_create_views(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")

        test_helpers.call_action(
            "aircan_hook", resource_id=resource["id"], state="running"
        )
        test_helpers.call_action(
            "aircan_hook", resource_id=resource["id"], state="success", type="error"
        )

        assert "datatables_view" not in self._view_types(resource["id"])


@pytest.fixture
def clean_activity_db(clean_db, migrate_db_for):
    """clean_db plus the activity plugin's migrations, as CKAN's own activity
    tests do."""
    migrate_db_for("activity")


@pytest.mark.ckan_config("ckan.plugins", "aircan activity")
@pytest.mark.usefixtures("with_plugins", "clean_activity_db")
class TestAircanHookActivities:
    @pytest.fixture(autouse=True)
    def _pipeline_user(self, with_plugins, clean_activity_db):
        # The DAG calls the hook with a service account's API token. Calls
        # made as the site user would be hidden from activity lists.
        self.pipeline_user = factories.Sysadmin()

    def _hook(self, **kwargs):
        return test_helpers.call_action(
            "aircan_hook", context={"user": self.pipeline_user["name"]}, **kwargs
        )

    def _start_run(self, resource_id, dag_run_id="run-1"):
        self._hook(
            resource_id=resource_id,
            dag_run_id=dag_run_id,
            state="queued",
            message="Queued",
            clear_logs=True,
        )

    def _ingestion_activities(self, dataset_id, user=None, **kwargs):
        # lists as the (sysadmin) pipeline user unless told otherwise; the
        # default call_action caller is treated as anonymous by the labels
        if user is None:
            user = self.pipeline_user["name"]
        kwargs["context"] = {"user": user, "ignore_auth": False}
        return test_helpers.call_action(
            "package_activity_list",
            id=dataset_id,
            activity_types=[
                action.INGESTION_SUCCEEDED_ACTIVITY,
                action.INGESTION_FAILED_ACTIVITY,
            ],
            **kwargs,
        )

    def test_success_records_activity_with_logs(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        self._start_run(resource["id"])

        self._hook(
            resource_id=resource["id"],
            state="success",
            message="Pipeline completed successfully",
        )

        [activity] = self._ingestion_activities(dataset["id"], include_data=True)
        assert activity["activity_type"] == action.INGESTION_SUCCEEDED_ACTIVITY
        assert activity["user_id"] == self.pipeline_user["id"]
        data = activity["data"]
        assert data["resource"]["id"] == resource["id"]
        assert data["dag_run_id"] == "run-1"
        assert data["channel"] == "system"
        assert [entry["message"] for entry in data["logs"]] == [
            "Queued",
            "Pipeline completed successfully",
        ]
        assert "error" not in data
        # the snapshot is taken after the datastore flag is set
        assert data["package"]["resources"][0]["datastore_active"]

    def test_failure_records_activity_with_error(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        self._start_run(resource["id"])

        self._hook(
            resource_id=resource["id"],
            state="failed",
            type="error",
            message=json.dumps({"message": "Bad row 3"}),
        )

        [activity] = self._ingestion_activities(dataset["id"], include_data=True)
        assert activity["activity_type"] == action.INGESTION_FAILED_ACTIVITY
        assert activity["data"]["error"] == {"message": "Bad row 3"}
        assert [entry["message"] for entry in activity["data"]["logs"]] == [
            "Queued"
        ]

    def test_failure_is_hidden_from_public_users(self, mock_airflow_client):
        member = factories.User()
        outsider = factories.User()
        organization = factories.Organization(
            users=[{"name": member["name"], "capacity": "member"}]
        )
        dataset = factories.Dataset(owner_org=organization["id"])
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        self._start_run(resource["id"])

        self._hook(resource_id=resource["id"], type="error", message="Boom")

        assert len(self._ingestion_activities(dataset["id"], user=member["name"])) == 1
        assert self._ingestion_activities(dataset["id"], user=outsider["name"]) == []
        assert self._ingestion_activities(dataset["id"], user="") == []

    def test_success_is_public_on_public_datasets(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        self._start_run(resource["id"])

        self._hook(resource_id=resource["id"], state="success")

        assert len(self._ingestion_activities(dataset["id"], user="")) == 1

    def test_repeated_final_call_records_once(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        self._start_run(resource["id"])

        for _ in range(2):
            self._hook(resource_id=resource["id"], state="success")

        assert len(self._ingestion_activities(dataset["id"])) == 1

    def test_each_run_records_its_outcome(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")

        self._start_run(resource["id"], dag_run_id="run-1")
        self._hook(resource_id=resource["id"], type="error", message="Boom")
        self._start_run(resource["id"], dag_run_id="run-2")
        self._hook(resource_id=resource["id"], state="success")

        activities = self._ingestion_activities(dataset["id"], include_data=True)
        assert [
            (activity["activity_type"], activity["data"]["dag_run_id"])
            for activity in activities
        ] == [
            (action.INGESTION_SUCCEEDED_ACTIVITY, "run-2"),
            (action.INGESTION_FAILED_ACTIVITY, "run-1"),
        ]

    def test_progress_updates_record_nothing(self, mock_airflow_client):
        dataset = factories.Dataset()
        resource = factories.Resource(package_id=dataset["id"], format="CSV")
        self._start_run(resource["id"])

        self._hook(
            resource_id=resource["id"],
            state="running",
            message="Upserting to BigQuery",
        )

        assert self._ingestion_activities(dataset["id"]) == []
