import json
import logging
import time

import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
from ckan.model.domain_object import DomainObjectOperation
from ckan.model.resource import Resource

import ckanext.aircan.helpers as helpers
import ckanext.aircan.views as views
from ckanext.aircan.logic import action, auth
from ckanext.aircan import interfaces

log = logging.getLogger(__name__)

# Ingestion modes that load into the *existing* datastore/BigQuery table rather
# than rebuilding it. For these, an existing column's type cannot change:
# BigQuery cannot re-type a column in place, that is only possible with a full
# "replace" (which rebuilds the table).
_TYPE_LOCKING_MODES = ("append", "upsert")


def _parse_schema(schema):
    """Return a Table Schema descriptor as a dict, or None when there is
    nothing to inspect. Accepts either a dict or a JSON string (both occur
    depending on the caller)."""
    if not schema:
        return None
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except (ValueError, TypeError):
            return None
    if not isinstance(schema, dict):
        return None
    return schema


def _fields_by_name(schema):
    """Map trimmed field name -> field dict for a parsed schema descriptor."""
    by_name = {}
    for field in schema.get("fields") or []:
        if not isinstance(field, dict):
            continue
        name = (field.get("name") or "").strip()
        if name:
            by_name[name] = field
    return by_name


def _retyped_columns(stored_schema, incoming_schema):
    """Names of columns present in both schemas whose declared ``type`` differs.
    New columns (absent from the stored schema) are ignored — they can be added
    with any type."""
    stored_fields = _fields_by_name(stored_schema)
    retyped = []
    for name, incoming in _fields_by_name(incoming_schema).items():
        original = stored_fields.get(name)
        if original is None:
            continue
        if (incoming.get("type") or "") != (original.get("type") or ""):
            retyped.append(name)
    return retyped


class AircanPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IResourceController, inherit=True)
    plugins.implements(plugins.IDomainObjectModification)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(interfaces.IAircan)

    # IConfigurer
    def update_config(self, config_):
        tk.add_template_directory(config_, "templates")
        tk.add_public_directory(config_, "public")
        tk.add_resource("assets", "aircan")

    # IConfigDeclaration
    def declare_config_options(self, declaration, key):
        declaration.annotate("Airflow connection")
        declaration.declare(key.ckanext.aircan.endpoint)
        declaration.declare(key.ckanext.aircan.dag_id)
        declaration.declare(key.ckanext.aircan.server).set_default("local")
        declaration.declare(key.ckanext.aircan.api_version).set_default("v2")
        declaration.declare(key.ckanext.aircan.timeout).set_default(90)
        declaration.declare(key.ckanext.aircan.token_endpoint).set_default("/auth/token")

        declaration.annotate("Airflow local authentication")
        declaration.declare(key.ckanext.aircan.airflow_username)
        declaration.declare(key.ckanext.aircan.airflow_password)

        declaration.annotate("Airflow GCP authentication")
        declaration.declare(key.ckanext.aircan.google_credentials_json)

        declaration.annotate("General processing options")
        declaration.declare(key.ckanext.aircan.formats)
        declaration.declare(key.ckanext.aircan.skip_leading_rows).set_default(1)
        declaration.declare(key.ckanext.aircan.temp_table_prefix).set_default("_temp_")
        declaration.declare(key.ckanext.aircan.infer_schema).set_default(True)
        declaration.declare(key.ckanext.aircan.validate_records).set_default(True)
        declaration.declare(key.ckanext.aircan.notification_to_email)
        declaration.declare(key.ckanext.aircan.notification_from_email)

        declaration.annotate("Google Cloud Storage configuration")
        declaration.declare(key.ckanext.aircan.gcs.project_id)
        declaration.declare(key.ckanext.aircan.gcs.bigquery_dataset_id)
        declaration.declare(key.ckanext.aircan.gcs.bucket)
        declaration.declare(key.ckanext.aircan.gcs.chunk_size).set_default(262144)
        declaration.declare(key.ckanext.aircan.gcs.signed_url_expiration_seconds).set_default(3600)

        declaration.annotate("S3 configuration")
        declaration.declare(key.ckanext.aircan.s3.bucket)
        declaration.declare(key.ckanext.aircan.s3.key_prefix)
        declaration.declare(key.ckanext.aircan.s3.endpoint_url)
        declaration.declare(key.ckanext.aircan.s3.region)

    # IResourceController
    def before_resource_update(self, context, current, resource):
        """Reject a type change to an existing datastore column when ingesting
        with append/upsert.

        BigQuery cannot re-type an existing column in place, so aircan can only
        honour a type change under "replace" (which rebuilds the table). The
        frontend already disables the type inputs in this case; this enforces
        the same rule before the change is committed, so API and harvester
        callers cannot smuggle a type change past the pipeline.
        """
        # Effective mode: the incoming value wins, otherwise the stored one (a
        # metadata-only patch may not resend it).
        mode = resource.get("ingestion_mode") or current.get("ingestion_mode")
        if mode not in _TYPE_LOCKING_MODES:
            return

        # Only guard resources that already have a datastore table to protect.
        # aircan sets this flag once a DAG has loaded data (see
        # update_resource_metadata); without it there is no existing table and
        # any type is fine.
        if not current.get("datastore_active"):
            return

        incoming_schema = _parse_schema(resource.get("schema"))
        stored_schema = _parse_schema(current.get("schema"))
        # No incoming schema (e.g. metadata-only update) or no stored schema to
        # compare against -> nothing to enforce.
        if incoming_schema is None or stored_schema is None:
            return

        retyped = _retyped_columns(stored_schema, incoming_schema)
        if retyped:
            raise tk.ValidationError(
                {
                    "schema": [
                        tk._(
                            "Column type cannot be changed for an existing "
                            "table when the processing mode is '{mode}': {cols}. "
                            "Use the 'replace' mode to change column types."
                        ).format(mode=mode, cols=", ".join(sorted(retyped)))
                    ]
                }
            )

    # IDomainObjectModification
    def notify(self, entity, operation):
        """
        Notify the plugin of a domain object modification.
        """
        if not isinstance(entity, Resource):
            return

        if operation not in (
            DomainObjectOperation.new,
            DomainObjectOperation.changed,
        ):
            return

        if operation == DomainObjectOperation.changed:
            url_changed = bool(getattr(entity, "url_changed", False))
            from sqlalchemy.orm import attributes as sa_attributes
            history = sa_attributes.get_history(entity, "last_modified")
            last_modified_changed = bool(history.added)
            if not (url_changed or last_modified_changed):
                return
        context = {
            "ignore_auth": True,
        }
        resource_dict = tk.get_action("resource_show")(
            context,
            {
                "id": entity.id,
            },
        )
        self._self_aircan_submit(resource_dict, self._current_user_email())

    @staticmethod
    def _current_user_email():
        """Capture the notification email before the commit hook loses context."""
        try:
            user_obj = getattr(tk.c, "userobj", None)
        except RuntimeError:
            # Domain modification callbacks can run outside a request context.
            return None

        return getattr(user_obj, "email", None)

    # CKAN can notify the same resource more than once per request: on file
    # uploads the new resource ends up in both the "new" and "changed" object
    # caches of DomainObjectModificationExtension (core only filters that for
    # packages), which used to trigger the DAG twice. All auto-submissions
    # therefore pass through a short in-process dedup window.
    _recent_submissions = {}
    _DEDUP_WINDOW_SECONDS = 10

    def _submitted_recently(self, resource_id):
        now = time.monotonic()
        self._recent_submissions = {
            rid: ts
            for rid, ts in self._recent_submissions.items()
            if now - ts < self._DEDUP_WINDOW_SECONDS
        }
        if resource_id in self._recent_submissions:
            return True
        self._recent_submissions[resource_id] = now
        return False

    def _self_aircan_submit(self, resource_dict, notification_email=None):
        """
        Submit the resource to Aircan for processing.

        Runs inside CKAN's commit hooks, so it must never raise: a failure
        to reach Airflow (or an unsupported format) must not break the
        resource create/update that triggered it.
        """
        resource_id = resource_dict.get("id")

        if resource_dict.get("url_type") == "datastore":
            return
        if not tk.h.allowed_aircan_format(resource_dict.get("format")):
            return
        if self._submitted_recently(resource_id):
            log.debug(
                "Skipping duplicate aircan submission for resource %s",
                resource_id,
            )
            return

        context = {"ignore_auth": True, "defer_commit": True}
        if notification_email:
            context["aircan_notification_email"] = notification_email
        try:
            tk.get_action("aircan_submit")(context, resource_dict)
        except Exception:
            log.exception("Failed to submit resource %s to Aircan", resource_id)

    # IAuthFunctions
    def get_auth_functions(self):
        return auth.get_auth_functions()

    # IActions
    def get_actions(self):
        return action.get_actions()

    # ITemplateHelpers
    def get_helpers(self):
        return helpers.get_helpers()

    # IBlueprint
    def get_blueprint(self):
        return [views.aircan]

    # IAircan
    def update_payload(self, context, payload):
        """Update the payload before submitting to Airflow.

        Args:
            context: The CKAN context dict
            payload: The payload dict to be updated (modified in place)
        """
        return payload
