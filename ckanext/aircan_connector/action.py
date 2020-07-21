# encoding: utf-8
import os
import requests
from datetime import date
from ckan.common import config
from ckan.plugins.toolkit import get_action
import logging
import json
import time
import urlparse

from gcp_handler import GCPHandler

log = logging.getLogger(__name__)


def datapusher_submit(context, data_dict):
    log.info("Submitting resource via Aircan")
    
    try:
        res_id = data_dict['resource_id']
        log.info(data_dict)
        user = get_action('user_show')(context, {'id': context['user']})
        ckan_api_key = user['apikey']
        
        ckan_resource = data_dict.get('resource_json', {})
        log.info(ckan_resource.get('url'))
        payload = { 
            "conf": {
                "path": ckan_resource.get('url'),
                "format": ckan_resource.get('format'),
                "ckan_resource_id": res_id,
                "schema": ckan_resource.get('schema'),
                "ckan_api_key": ckan_api_key,
                "ckan_site_url": config.get('ckan.site_url'),
                "output_bucket": str(date.today())
            }
        }

        if config.get('ckan.airflow.cloud','local') != "GCP":
            ckan_airflow_endpoint_url = config.get('ckan.airflow.url')
            log.info("Airflow Endpoint URL: {0}".format(ckan_airflow_endpoint_url))
            response = requests.post(ckan_airflow_endpoint_url,
                                     data=json.dumps(payload),
                                     headers={'Content-Type': 'application/json',
                                              'Cache-Control': 'no-cache'})
            response.raise_for_status()
            log.info('AirCan Load completed')
            return response.json()
        else:
            log.info("Invoking Airflow on Google Cloud Composer")
            invoke_gcp(config, payload)
    except Exception as e:
        return {"success": False, "errors": [e]}


def invoke_gcp(config, payload):
    log.info('Invoking GCP')
    gcp = GCPHandler(config, payload)
    log.info('Handler created')
    return gcp.trigger_dag()
