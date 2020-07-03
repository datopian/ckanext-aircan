# encoding: utf-8
import os
import requests
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

        try:
            resource, dataset = get_resource_and_dataset(res_id)
        except Exception as e:
            # try again in 5 seconds just in case CKAN is slow at adding resource
            time.sleep(5)
            resource, dataset = get_resource_and_dataset(res_id)

        resource_download_url = '/dataset/{}/resource/{}/download/{}' \
            .format(dataset['name'], resource['id'], resource['name'])

        ckan_site_url = config['ckan.site_url']
        resource_ckan_url = urlparse.urljoin(ckan_site_url, resource_download_url)
        log.info("resource_ckan_url: {}".format(resource_ckan_url))

        json_output_file_name = os.path.splitext(resource['name'])[0]+'.json'
        ckan_airflow_storage_path = config['ckan.airflow.storage_path']
        json_output_file_path = ckan_airflow_storage_path + json_output_file_name
        log.info("json_output_file_path : {0}".format(json_output_file_path))

        payload = {
            "conf": {
                "resource_id": res_id,
                "schema_fields_array": [ "FID", "Mkt-RF", "SMB", "HML", "RF" ],
                "csv_input": resource_ckan_url,
                "json_output": json_output_file_path
            }
        }
        if config['ckan.airflow.cloud'] != "GCP": 
            ckan_airflow_endpoint_url = config['ckan.airflow.url']
            log.info("Airflow Endpoint URL: {0}".format(ckan_airflow_endpoint_url))
            response = requests.post(ckan_airflow_endpoint_url,
                                     data=json.dumps(payload),
                                     headers={'Content-Type': 'application/json',
                                              'Cache-Control': 'no-cache'}
                                     )
            log.info(response)
            response.raise_for_status()
            log.info('AirCan Load completed')
            return response.json()
        else:
            log.info("Invoking Airflow on Google Cloud Composer")
            invoke_gcp(config, payload)


def get_resource_and_dataset(resource_id):
    """
    Gets available information about the resource and its dataset from CKAN
    """
    res_dict = get_action('resource_show')(None, {'id': resource_id})
    pkg_dict = get_action('package_show')(None, {'id': res_dict['package_id']})
    return res_dict, pkg_dict


def invoke_gcp(config, payload):
    log.info('Invoking GCP')
    gcp = GCPHandler(config, payload)
    log.info('Handler created')
    return gcp.trigger_dag()
