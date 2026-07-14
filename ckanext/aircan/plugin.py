import logging
import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
import ckan.model as model
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

        # Deduplicate within a single request. A create-with-upload reaches this
        # hook twice for the same resource — once as `new`, then as `changed`
        # (url / last_modified set during the same request) — and each call would
        # fire the aircan DAG, double-loading the data into the datastore. The two
        # calls arrive on separate commits of the same request-scoped SQLAlchemy
        # session, so a marker on Session.info (discarded when the session is
        # torn down at end of request) collapses them to a single submit. This
        # deliberately stays in the model layer rather than using flask.g, so it
        # also covers non-Flask callers (CLI, tests).
        # `model.Session()` returns the current request-scoped Session instance;
        # `.info` is a real per-session dict (avoids relying on scoped_session
        # attribute proxying) and survives commits within the request.
        submitted = model.Session().info.setdefault(
            "_aircan_submitted_ids", set()
        )
        if entity.id in submitted:
            log.debug(
                "Skipping duplicate aircan submit for %s in this request",
                entity.id,
            )
            return
        submitted.add(entity.id)

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

    def _self_aircan_submit(self, resource_dict):
        """
        Re-submit the resource to Aircan for processing.
        """
        context = {"ignore_auth": True, "defer_commit": True}
        tk.get_action("aircan_submit")(context, resource_dict)

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
