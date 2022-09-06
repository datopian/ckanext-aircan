import logging
import ckan.plugins.toolkit as toolkit


log = logging.getLogger(__name__)

def aircan_status(resource_id):
    try:
        return toolkit.get_action('aircan_status')(
            {}, {'resource_id': resource_id})
    except toolkit.ObjectNotFound:
        return {
            'status': 'unknown'
        }
