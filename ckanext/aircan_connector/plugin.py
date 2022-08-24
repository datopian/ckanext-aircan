# encoding: utf-8

import logging
import ckan.plugins as p
import ckan.plugins.toolkit as toolkit
import ckan.model as model
from ckanext.aircan_connector import  blueprint
from ckanext.aircan_connector.logic import action, auth, helpers
log = logging.getLogger(__name__)


DEFAULT_FORMATS = [
    u'csv',
    u'xls',
    u'xlsx',
    u'tsv',
    u'application/csv',
    u'application/vnd.ms-excel',
    u'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    u'ods',
    u'application/vnd.oasis.opendocument.spreadsheet',
]

class Aircan_ConnectorPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer, inherit=True)
    p.implements(p.IConfigurable, inherit=True)
    p.implements(p.IResourceUrlChange)
    p.implements(p.IAuthFunctions)
    p.implements(p.IBlueprint)
    p.implements(p.IActions)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IResourceController, inherit=True)

    # IConfigurer
    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('fanstatic', 'aircan_connector')

    def configure(self, config):
        self.config = config
        aircan_formats = config.get('ckan.aircan.formats', '').lower()
        self.aircan_formats = aircan_formats.split() or DEFAULT_FORMATS

    # IResourceUrlChange
    def notify(self, resource):
        context = {
            u'model': model,
            u'ignore_auth': True,
        }
        resource_dict = toolkit.get_action(u'resource_show')(
            context, {
                u'id': resource.id,
            }
        )
        self._submit_to_aircan(resource_dict)

    # IResourceController
    def after_create(self, context, resource_dict):
        self._submit_to_aircan(resource_dict)

    def _submit_to_aircan(self, resource_dict):
        context = {
            u'model': model,
            u'ignore_auth': True,
            u'defer_commit': True
        }
        resource_format = resource_dict.get('format')
        submit = (
                resource_format
                and resource_format.lower() in self.aircan_formats
        )
        if not submit:
            return

        resource_hash = resource_dict.get('hash')
        package_id = resource_dict.get('package_id')
        pacakge_dict = toolkit.get_action(u'package_show')(
            context, {
                u'id': package_id,
            }
        )
        pacakge_name = pacakge_dict.get('name')
        organization_name = pacakge_dict.get('organization', {}).get('name')
        log.debug("pacakge_name: {}".format(pacakge_name))
        log.debug("organization: {}".format(organization_name))

        try:
            log.debug(
                u'Submitting resource with aircan {0}'.format(resource_dict['id']) +
                u' to DataStore'
            )
            toolkit.get_action(u'aircan_submit')(
                context, {
                    u'resource_id': resource_dict['id'],
                    u'resource_json': resource_dict,
                    u'pacakge_name': pacakge_name,
                    u'organization_name': organization_name,
                    u'resource_hash': resource_hash
                }
            )
        except toolkit.ValidationError as e:
            # If datapusher is offline want to catch error instead
            # of raising otherwise resource save will fail with 500
            log.critical(e)
            pass

    # IActions
    def get_actions(self):
        return {
            'aircan_submit': action.aircan_submit,
            'aircan_status': action.aircan_status,
            'aircan_status_update': action.aircan_status_update,
            'datastore_info': action.datastore_info
        }


    # IBlueprint
    def get_blueprint(self):
       return blueprint.aircan

    # IAuthFunctions
    def get_auth_functions(self):
        return {
            'aircan_submit': auth.aircan_submit,
            'aircan_status': auth.aircan_status
        }

    
    #ITemplateHelpers
    def get_helpers(self):
        return {
            'aircan_status': helpers.aircan_status,
            'datastore_append_or_update': helpers.datastore_append_or_update
        }
