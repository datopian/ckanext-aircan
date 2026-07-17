"""Shared fixtures for ckanext-aircan tests."""

from unittest import mock

import pytest


@pytest.fixture
def mock_airflow_client():
    """Replace AirflowClient so tests never talk to a real Airflow.

    The aircan plugin submits resources to Airflow whenever a resource is
    created or its url changes (IDomainObjectModification), so any test that
    creates resources needs this fixture active.
    """
    with mock.patch("ckanext.aircan.logic.action.AirflowClient") as client_cls:
        client = client_cls.return_value
        client.dag_id = "aircan_dag"
        client.trigger_dag.return_value = {
            "dag_run_id": "test-dag-run-id",
            "state": "queued",
        }
        client.get_dag_run.return_value = {
            "dag_run_id": "test-dag-run-id",
            "state": "running",
        }
        yield client
