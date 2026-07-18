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


class AircanPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IAuthFunctions)
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
        print("================== AircanPlugin.notify called for resource id:", entity.id)
        context = {
            "ignore_auth": True,
        }
        resource_dict = tk.get_action("resource_show")(
            context,
            {
                "id": entity.id,
            },
        )
        self._self_aircan_submit(resource_dict)

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

    def _self_aircan_submit(self, resource_dict):
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
