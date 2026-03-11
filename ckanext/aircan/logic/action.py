import logging
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Dict

import requests

import ckan.plugins as plugins
import ckan.plugins.toolkit as tk

from ckanext.aircan import interfaces
from ckanext.aircan.lib.airflow import AirflowClient

log = logging.getLogger(__name__)


def aircan_submit(context, data_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit a resource to Airflow for processing via Aircan DAG.
    param data_dict: Resource dict
    """
    tk.check_access("aircan_submit", context, data_dict)
    resource_format = data_dict.get("format")
    if not tk.h.allowed_aircan_format(resource_format):
        log.debug(
            "Skipping aircan resource %s because format '%s' is not allowed.",
            data_dict.get("id"),
            resource_format,
        )
        context.update({"session": context["model"].meta.create_local_session()})
        return tk.abort(
            400,
            tk._("Resource format '%s' is not allowed for Aircan.") % resource_format,
        )

    if data_dict.get("url_type") == "datastore":
        log.debug(
            "Skipping aircan resource %s as resource is managed by DataStore API.",
            data_dict.get("id"),
        )
        return tk.abort(
            400, tk._("Resources managed by DataStore API are not supported by Aircan.")
        )

    payload = {
        "resource": data_dict,
        "ckan_config": {
            "site_url": tk.config.get("ckan.site_url"),
            "site_id": tk.config.get("ckan.site_id"),
        },
        "gcs_config": {
            "project_id": tk.config.get("ckanext.aircan.gcs.project_id"),
            "dataset_id": tk.config.get("ckanext.aircan.gcs.bigquery_dataset_id"),
            "bucket": tk.config.get("ckanext.aircan.gcs.bucket"),
            "chunk_size": tk.asint(
                tk.config.get("ckanext.aircan.gcs.chunk_size", 262144)
            ),
            "signed_url_expiration_seconds": tk.asint(
                tk.config.get("ckanext.aircan.gcs.signed_url_expiration_seconds", 3600)
            ),
        },
        "others_config": {
            "skip_leading_rows": tk.config.get("ckanext.aircan.skip_leading_rows", 1),
            "temp_table_prefix": tk.config.get(
                "ckanext.aircan.temp_table_prefix", "_temp_"
            ),
            "infer_schema": tk.asbool(
                tk.config.get("ckanext.aircan.infer_schema", True)
            ),
            "notification_to_email": (
                tk.config.get("ckanext.aircan.notification_to_email") or ""
            ).split()
            or [],
            "validate_records": tk.asbool(
                tk.config.get("ckanext.aircan.validate_records", True)
            ),
            "notification_from_email": tk.config.get(
                "ckanext.aircan.notification_from_email"
            ),
        },
        "s3_config": {
            "bucket": tk.config.get("ckanext.aircan.s3.bucket"),
            "key_prefix": (tk.config.get("ckanext.aircan.s3.key_prefix") or "").replace(
                "%resource_id%",
                str(data_dict.get("id")),
            ),
            "endpoint_url": tk.config.get("ckanext.aircan.s3.endpoint_url"),
            "region": tk.config.get("ckanext.aircan.s3.region"),
        },
    }

    for plugin in plugins.PluginImplementations(interfaces.IAircan):
        plugin.update_payload(context, payload)

    log.debug("Triggering Airflow DAG with payload: %s", json.dumps(payload, indent=2))

    client = AirflowClient()
    try:
        dag_run = client.trigger_dag(conf=payload)
        dag_run_id = dag_run.get("dag_run_id")
        context.update({"session": context["model"].meta.create_local_session()})
        tk.get_action("aircan_status_update")(
            context,
            {
                "resource_id": data_dict.get("id"),
                "dag_run_id": dag_run.get("dag_run_id"),
                "state": "queued",
                "message": f"Added to the queue to be processed with {dag_run_id}.",
                "clear_logs": True,
            },
        )
        return {
            "dag_run": dag_run,
            "dag_run_id": dag_run_id,
        }
    except requests.HTTPError as e:
        log.error(tk._("Failed to trigger Airflow DAG '%s': %s"), client.dag_id, str(e))
        raise tk.ValidationError(
            {
                "airflow": [
                    tk._("Failed to trigger Airflow DAG '%s': %s")
                    % (client.dag_id, str(e))
                ]
            }
        )


def aircan_status(context, data_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch task status for an 'aircan' task.
    Expected data_dict keys:
      - resource_id (required) or id
    """

    if "id" in data_dict:
        data_dict["resource_id"] = data_dict["id"]

    resource_id = tk.get_or_bust(data_dict, "resource_id")
    tk.check_access("aircan_status", context, data_dict)

    task_status = tk.get_action("task_status_show")(
        context, {"entity_id": resource_id, "task_type": "aircan", "key": "pipeline"}
    )
    if task_status:
        dag_run_id = json.loads(task_status.get("value", "{}")).get("dag_run_id", "")
        if dag_run_id:
            client = AirflowClient()
            try:
                dag_run = client.get_dag_run(dag_run_id)
                task_status.update(
                    {
                        "dag": dag_run,
                        "state": dag_run.get("state"),
                    }
                )
            except requests.ConnectionError as e:
                log.error(
                    tk._(
                        "Unable to connect to Airflow while fetching DAG run '%s': %s"
                    ),
                    dag_run_id,
                    str(e),
                )
                raise
            except requests.HTTPError as e:
                log.error(
                    tk._("Failed to fetch Airflow DAG run '%s': %s"),
                    dag_run_id,
                    str(e),
                )
        else:
            log.debug(
                "Skipping Airflow DAG run fetch for resource %s because dag_run_id is empty.",
                resource_id,
            )

    return task_status


def aircan_status_update(context, data_dict):
    """
    Update task status for an 'aircan' task and append a log entry.

    Expected data_dict keys:
      - resource_id (required)
      - message (optional)
      - dag_run_id (optional)
      - state (optional)
      - clear_logs (optional, bool-ish)
      - key (optional, default: "pipeline")
      - type (optional, default: "info"; if "error" -> marks task failed)
      - last_updated (optional)
    """
    resource_id = data_dict.get("resource_id")

    if not resource_id:
        raise tk.ValidationError({"resource_id": ["Missing resource_id"]})

    tk.check_access("aircan_status_update", context, {"resource_id": resource_id})

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    message = data_dict.get("message") or ""
    dag_run_id = data_dict.get("dag_run_id") or ""
    state = data_dict.get("state") or ""
    key = data_dict.get("key") or "pipeline"
    _type = (data_dict.get("type") or "info").lower()
    clear_logs = tk.asbool(data_dict.get("clear_logs", False))

    logs = []
    if not clear_logs:
        try:
            show_res = tk.get_action("task_status_show")(
                context,
                {"entity_id": resource_id, "task_type": "aircan", "key": key},
            )
            value = show_res.get("value")
            if value:
                parsed = json.loads(value)
                logs = parsed.get("logs") or []
                dag_run_id = parsed.get("dag_run_id", dag_run_id)
                if not isinstance(logs, list):
                    logs = []
        except Exception:
            log.exception(
                "Failed to load previous aircan logs for resource_id=%s", resource_id
            )

    if _type != "error":
        logs.append({"datetime": now, "message": message})

    value = {"dag_run_id": dag_run_id, "logs": logs}

    is_error = _type == "error"

    error_payload = message if is_error else None

    task_dict = {
        "entity_id": resource_id,
        "entity_type": "resource",
        "task_type": "aircan",
        "state": "failed" if is_error else state,
        "last_updated": data_dict.get("last_updated") or now,
        "key": key,
        "value": json.dumps(value),
        "error": (
            "" if clear_logs else (json.dumps(error_payload) if error_payload else None)
        ),
    }
    return tk.get_action("task_status_update")(context, task_dict)


def get_actions():
    return {
        "aircan_submit": aircan_submit,
        "aircan_status": aircan_status,
        "aircan_status_update": aircan_status_update,
    }
