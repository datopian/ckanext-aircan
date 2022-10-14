import logging
import ckan.plugins.toolkit as toolkit

boolean_validator = toolkit.get_validator('boolean_validator')

log = logging.getLogger(__name__)

def aircan_status(resource_id):
    try:
        return toolkit.get_action('aircan_status')(
            {}, {'resource_id': resource_id})
    except toolkit.ObjectNotFound:
        return {
            'status': 'unknown'
        }

def datastore_append_or_update():
    active = toolkit.config.get('ckanext.aircan.enable_datastore_upload_configuration', False)
    return boolean_validator(active, {})