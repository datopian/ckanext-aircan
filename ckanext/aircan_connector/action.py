# encoding: utf-8

import requests
from ckan.common import config
from ckan.plugins.toolkit import get_action
#import urlparse
import logging
import json
import tempfile

log = logging.getLogger(__name__)

def datapusher_submit(context, data_dict):
    log.info("Submitting resource via API")
    try:
        res_id = data_dict['resource_id']
        resource = get_resource_and_dataset(res_id)
        resource_url = resource.get('url')
        # fetch the resource data
        log.info('Fetching from: {0}'.format(resource_url))
        tmp_file = get_tmp_file(resource_url)
        log.info('tmp_file.name: {0}'.format(tmp_file.name))
        #records = read_from_file(tmp_file.name)
        #log.info("records")
        #log.info(records)
        json_output_file_path = config['ckan.storage_path']+'/my.json'
        log.info("json_output_file_path : {0}".format(json_output_file_path))
        payload = {
            "conf": {
                "resource_i": res_id,
                "schema_fields_array": ["id", "full_text", "FID"],
                "csv_input": tmp_file.name,
                "json_output": json_output_file_path
            }
        }
        url = config['ckan.airflow.url']
        log.info("Airflow URL: {0}".format(url))
        response = requests.post(url,
                                 data=payload,
                                 headers={'Content-Type': 'application/json',
                                          'Cache-Control': 'no-cache'}
                                 )
        #log.info(response)
        response.raise_for_status()
        log.info(response.json())
        return response.json()
    except Exception as e:
        return {"success": False, "errors": [e]}

    #url = 'http://ckan:8081/api/experimental/dags/ckan_api_load_multiple_steps/dag_runs'
    #log.info("Aircan URL: " + url)
    #response = requests.get(url)
    ##response = requests.post(self.url, data=payload, headers=self.headers)
    #response.raise_for_status()
    #return response.json()


def get_resource_and_dataset(resource_id):
    """
    Gets available information about the resource and its dataset from CKAN
    """
    res_dict = get_action('resource_show')(None, {'id': resource_id})
    return res_dict

def get_tmp_file(url):
    filename = url.split('/')[-1].split('#')[0].split('?')[0]
    log.info('get_tmp_file filename: {0}'.format(filename))
    tmp_file = tempfile.NamedTemporaryFile(suffix=filename)
    return tmp_file

def read_from_file(filename):
    content = None
    with open(filename, 'r') as fd:
        content = fd.read()
    return content