import logging
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
