import logging
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Dict

import requests

import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
import ckan.lib.search as search
from ckan import model
from ckan.lib.plugins import get_permission_labels

from ckanext.aircan import interfaces
from ckanext.aircan.lib.airflow import AirflowClient

log = logging.getLogger(__name__)

# Activity types recorded on the dataset when a pipeline run ends. They end in
# "package" on purpose: the activity extension only applies permission labels
# to activity types ending in "package", and the labels are what keep failed
# ingestions away from users outside the dataset's organization.
INGESTION_SUCCEEDED_ACTIVITY = "ingestion succeeded package"
INGESTION_FAILED_ACTIVITY = "ingestion failed package"


def register_activity_types():
    """Let the activity extension accept the ingestion activity types.

    The activity extension has no hook for new types, so they are added to
    the dicts its activity_type and object_id validators look up. Adding them
    to VALIDATORS_PACKAGE_ACTIVITY_TYPES also lists them in its type filter.
    """
    try:
        from ckanext.activity.logic import validators
    except ImportError:
        return

    for activity_type in (INGESTION_SUCCEEDED_ACTIVITY, INGESTION_FAILED_ACTIVITY):
        validators.VALIDATORS_PACKAGE_ACTIVITY_TYPES[activity_type] = (
            "package_id_exists"
        )
        validators.object_id_validators[activity_type] = "package_id_exists"


def _notification_email(context):
    """Return the current user's email for pipeline failure notifications."""
    email = context.get("aircan_notification_email")
    if email:
        return email

    user_obj = context.get("auth_user_obj")
    email = getattr(user_obj, "email", None)

    if isinstance(user_obj, dict):
        email = user_obj.get("email")

    return email


def _validate_records_enabled(context, data_dict: Dict[str, Any]) -> bool:
    globally_enabled = tk.asbool(
        tk.config.get("ckanext.aircan.validate_records", True)
    )
    package_id = data_dict.get("package_id")
    if not globally_enabled or not package_id:
        return globally_enabled

    package = tk.get_action("package_show")(context, {"id": package_id})
    package_setting = package.get("aircan_validate_records")
    if package_setting in (None, ""):
        return True
    return tk.asbool(package_setting)


def _validation_report_url(context, data_dict: Dict[str, Any]) -> str:
    """Frontend link to the resource's validation report, or "" when no
    frontend is configured. Failure emails put this link in front of users, who
    work in the frontend rather than the CKAN UI."""
    frontend_url = (tk.config.get("ckanext.aircan.frontend_url") or "").rstrip("/")
    package_id = data_dict.get("package_id")
    if not frontend_url or not package_id or not data_dict.get("id"):
        return ""

    # The frontend routes datasets by name, not id.
    package = tk.get_action("package_show")(context, {"id": package_id})
    return "{}/datasets/{}/resources/{}/validation-report".format(
        frontend_url, package["name"], data_dict["id"]
    )


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
            "validate_records": _validate_records_enabled(context, data_dict),
            "validation_report_url": _validation_report_url(context, data_dict),
            "organization_name": tk.config.get("ckanext.aircan.organization_name")
            or "",
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
    notification_email = _notification_email(context)
    recipients = payload["others_config"]["notification_to_email"]
    notify_editor = "editor" in recipients
    recipients[:] = [recipient for recipient in recipients if recipient != "editor"]
    if notify_editor and notification_email and notification_email not in recipients:
        recipients.append(notification_email)

    for plugin in plugins.PluginImplementations(interfaces.IAircan):
        plugin.update_payload(context, payload)

    log.debug("Triggering Airflow DAG with payload: %s", json.dumps(payload, indent=2))

    client = AirflowClient()
    try:
        dag_run = client.trigger_dag(conf=payload)
        dag_run_id = dag_run.get("dag_run_id")
        context.update({"session": context["model"].meta.create_local_session()})
        tk.get_action("aircan_hook")(
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


def update_resource_metadata(resource_id, update_dict):
    """
    Set appropriate datastore_active flag on CKAN resource.

    Called after the Aircan DAG has ingested data into the DataStore.
    """
    # We're modifying the resource extra directly here to avoid a
    # race condition, see ckan/ckan#3245 for details and plan for a
    # better fix
    q = (
        model.Session.query(model.Resource)
        .with_for_update(of=model.Resource)
        .filter(model.Resource.id == resource_id)
    )
    resource = q.one()

    # update extras in database for record
    extras = dict(resource.extras or {})
    extras.update(update_dict)
    q.update({"extras": extras}, synchronize_session=False)

    model.Session.commit()

    # get package with updated resource from solr
    # find changed resource, patch it and reindex package
    psi = search.PackageSearchIndex()
    solr_query = search.PackageSearchQuery()
    q = {
        "q": 'id:"{0}"'.format(resource.package_id),
        "fl": "data_dict",
        "wt": "json",
        "fq": 'site_id:"%s"' % tk.config.get("ckan.site_id"),
        "rows": 1,
    }
    for record in solr_query.run(q)["results"]:
        solr_data_dict = json.loads(record["data_dict"])
        for res in solr_data_dict["resources"]:
            if res["id"] == resource_id:
                res.update(update_dict)
                psi.index_package(solr_data_dict)
                break


def _create_datastore_views(context, resource_id):
    """
    Create the default views flagged with `requires_datastore` for a resource.

    Only view types listed in `ckan.views.default_views` are considered, and
    view types already present on the resource are skipped, so it is safe to
    call this on every successful ingestion.

    Called right after update_resource_metadata, which writes the flag with a
    raw SQL update and patches the search index by hand. The dicts are read
    with use_cache=False so package_show goes to the database instead of the
    search index's cached copy, and datastore_active is set on the resource
    dict explicitly: view plugins such as recline_view only offer a view when
    it is true, and a read that misses the fresh flag made them silently skip
    the view.
    """
    context = dict(context, use_cache=False)
    resource_dict = tk.get_action("resource_show")(context, {"id": resource_id})
    resource_dict["datastore_active"] = True
    dataset_dict = tk.get_action("package_show")(
        context, {"id": resource_dict["package_id"]}
    )
    views = tk.get_action("resource_create_default_resource_views")(
        context,
        {
            "resource": resource_dict,
            "package": dataset_dict,
            "create_datastore_views": True,
        },
    )
    log.info(
        "Created datastore views for resource_id=%s: %s",
        resource_id,
        [view["view_type"] for view in views] or "none",
    )
    return views


def _failure_permission_labels(package):
    """Permission labels that limit an activity to the dataset's own people.

    The dataset's labels minus "public", plus its organization's members (or
    its creator when it has no organization). Sysadmins see every activity.
    """
    labels = {
        label
        for label in get_permission_labels().get_dataset_labels(package)
        if label != "public"
    }
    if package.owner_org:
        labels.add(f"member-{package.owner_org}")
    elif package.creator_user_id:
        labels.add(f"creator-{package.creator_user_id}")
    return sorted(labels)


def _parse_error(message):
    """The DAG sends the error payload as a JSON string; keep it structured."""
    try:
        return json.loads(message)
    except (TypeError, ValueError):
        return message


def _record_ingestion_activity(
    context, resource_id, succeeded, dag_run_id, logs, error
):
    """
    Record the outcome of a pipeline run in the dataset's activity stream.

    The activity's data carries the run's logs (the ones the data pipeline
    panel shows) and, for failures, the error. Failures only get labels for
    the dataset's organization, so public users never see them. Like CKAN's
    own package activities, the data also holds a full package snapshot:
    activity diffs compare an activity with the one before it on the same
    dataset, whatever its type.

    Returns True when an activity was created.
    """
    resource = model.Resource.get(resource_id)
    package = model.Package.get(resource.package_id) if resource else None
    if package is None:
        return False

    user = model.User.get(context.get("user") or "")
    if user is None:
        site_user = tk.get_action("get_site_user")({"ignore_auth": True}, {})
        user = model.User.get(site_user["name"])

    package_dict = tk.get_action("package_show")(
        {"ignore_auth": True, "for_view": False, "use_cache": False},
        {"id": package.id, "include_tracking": False},
    )

    data = {
        "package": package_dict,
        "actor": user.name,
        # ckanext-neso stamps the channel from the request's API token, which
        # would label the pipeline's own calls as "api"
        "channel": "system",
        "resource": {
            "id": resource.id,
            "name": resource.name,
            "format": resource.format,
        },
        "dag_run_id": dag_run_id,
        "logs": logs,
    }
    if succeeded:
        activity_type = INGESTION_SUCCEEDED_ACTIVITY
        permission_labels = get_permission_labels().get_dataset_labels(package)
    else:
        activity_type = INGESTION_FAILED_ACTIVITY
        permission_labels = _failure_permission_labels(package)
        data["error"] = error

    activity = tk.get_action("activity_create")(
        {"ignore_auth": True},
        {
            "user_id": user.id,
            "object_id": package.id,
            "activity_type": activity_type,
            "data": data,
            "permission_labels": permission_labels,
        },
    )
    return activity is not None


def aircan_hook(context, data_dict):
    """
    Update Aircan task. This action is typically called by Airflow DAG
    to update task status for an 'aircan' task and append a log entry.

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

    tk.check_access("aircan_hook", context, {"resource_id": resource_id})

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    message = data_dict.get("message") or ""
    dag_run_id = data_dict.get("dag_run_id") or ""
    state = data_dict.get("state") or ""
    key = data_dict.get("key") or "pipeline"
    _type = (data_dict.get("type") or "info").lower()
    clear_logs = tk.asbool(data_dict.get("clear_logs", False))

    logs = []
    # outcome of the run already recorded in the activity stream, so a retried
    # or duplicated final call doesn't record it twice
    recorded_outcome = None
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
                recorded_outcome = parsed.get("recorded_outcome")
                if not isinstance(logs, list):
                    logs = []
        except Exception:
            log.exception(
                "Failed to load previous aircan logs for resource_id=%s", resource_id
            )

    if _type != "error":
        logs.append({"datetime": now, "message": message})

    is_error = _type == "error"

    error_payload = message if is_error else None

    if state == "success" and not is_error:
        # the DAG ingested the data successfully, so mark the resource's
        # data as available in the datastore
        try:
            update_resource_metadata(resource_id, {"datastore_active": True})
        except Exception:
            log.exception(
                "Failed to set datastore_active flag for resource_id=%s", resource_id
            )

        # create the default views that need the data in the datastore
        # (e.g. datatables_view), mirroring what ckanext-datapusher does
        try:
            _create_datastore_views(dict(context), resource_id)
        except Exception:
            log.exception(
                "Failed to create datastore views for resource_id=%s", resource_id
            )

    if is_error:
        outcome = "failed"
    elif state == "success":
        outcome = "success"
    else:
        outcome = None
    if outcome and outcome != recorded_outcome:
        try:
            if _record_ingestion_activity(
                context,
                resource_id,
                succeeded=outcome == "success",
                dag_run_id=dag_run_id,
                logs=logs,
                error=_parse_error(message) if is_error else None,
            ):
                recorded_outcome = outcome
        except Exception:
            model.Session.rollback()
            log.exception(
                "Failed to record ingestion activity for resource_id=%s", resource_id
            )

    value = {"dag_run_id": dag_run_id, "logs": logs}
    if recorded_outcome:
        value["recorded_outcome"] = recorded_outcome

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
        "aircan_hook": aircan_hook,
    }
