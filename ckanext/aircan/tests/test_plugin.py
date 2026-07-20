"""Tests for plugin.py."""

import pytest

import ckan.model as model
import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
import ckan.tests.factories as factories
from ckan.model.domain_object import DomainObjectOperation

from ckanext.aircan.plugin import AircanPlugin, _parse_schema, _retyped_columns


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


class TestParseSchema:
    def test_accepts_dict(self):
        schema = {"fields": [{"name": "a", "type": "integer"}]}
        assert _parse_schema(schema) == schema

    def test_accepts_json_string(self):
        assert _parse_schema('{"fields": []}') == {"fields": []}

    @pytest.mark.parametrize(
        "value", [None, "", {}, [], "not json", "[1, 2]", 5]
    )
    def test_returns_none_for_unusable_input(self, value):
        assert _parse_schema(value) is None


class TestRetypedColumns:
    STORED = {"fields": [{"name": "a", "type": "integer"},
                         {"name": "b", "type": "string"}]}

    def test_no_change(self):
        assert _retyped_columns(self.STORED, self.STORED) == []

    def test_detects_changed_type(self):
        incoming = {"fields": [{"name": "a", "type": "string"},
                              {"name": "b", "type": "string"}]}
        assert _retyped_columns(self.STORED, incoming) == ["a"]

    def test_new_column_is_allowed(self):
        incoming = {"fields": [{"name": "a", "type": "integer"},
                              {"name": "b", "type": "string"},
                              {"name": "c", "type": "number"}]}
        assert _retyped_columns(self.STORED, incoming) == []

    def test_matches_names_after_trimming(self):
        incoming = {"fields": [{"name": " a ", "type": "string"}]}
        assert _retyped_columns(self.STORED, incoming) == ["a"]

    def test_dropped_column_is_not_reported(self):
        incoming = {"fields": [{"name": "b", "type": "string"}]}
        assert _retyped_columns(self.STORED, incoming) == []


class TestTypeLockOnUpdate:
    """before_resource_update rejects a type change to an existing datastore
    column under append/upsert, but allows it under replace / for new
    columns / when there is no existing table."""

    STORED = {"fields": [{"name": "a", "type": "integer"},
                         {"name": "b", "type": "string"}]}
    RETYPE = {"fields": [{"name": "a", "type": "string"},
                        {"name": "b", "type": "string"}]}

    def _run(self, current, resource):
        AircanPlugin().before_resource_update({}, current, resource)

    @pytest.mark.parametrize("mode", ["append", "upsert"])
    def test_retype_rejected_for_append_and_upsert(self, mode):
        current = {"datastore_active": True, "ingestion_mode": mode,
                   "schema": self.STORED}
        with pytest.raises(tk.ValidationError) as exc:
            self._run(current, {"ingestion_mode": mode, "schema": self.RETYPE})
        assert "schema" in exc.value.error_dict

    def test_retype_allowed_for_replace(self):
        current = {"datastore_active": True, "ingestion_mode": "replace",
                   "schema": self.STORED}
        self._run(current, {"ingestion_mode": "replace", "schema": self.RETYPE})

    def test_retype_allowed_without_existing_table(self):
        current = {"ingestion_mode": "append", "schema": self.STORED}
        self._run(current, {"ingestion_mode": "append", "schema": self.RETYPE})

    def test_new_column_allowed_on_append(self):
        incoming = {"fields": self.STORED["fields"] +
                    [{"name": "c", "type": "number"}]}
        current = {"datastore_active": True, "ingestion_mode": "append",
                   "schema": self.STORED}
        self._run(current, {"ingestion_mode": "append", "schema": incoming})

    def test_metadata_only_update_allowed(self):
        current = {"datastore_active": True, "ingestion_mode": "append",
                   "schema": self.STORED}
        self._run(current, {"description": "changed"})

    def test_mode_falls_back_to_stored_value(self):
        # Incoming patch omits the mode; the stored append mode still locks it.
        current = {"datastore_active": True, "ingestion_mode": "append",
                   "schema": self.STORED}
        with pytest.raises(tk.ValidationError):
            self._run(current, {"schema": self.RETYPE})
