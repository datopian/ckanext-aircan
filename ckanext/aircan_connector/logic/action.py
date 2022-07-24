# encoding: utf-8
import os
import requests
from datetime import date
from ckan.common import config
from ckan.plugins.toolkit import get_action, check_access
import logging
import json
import time
import urlparse
from ckan.common import request
from gcp_handler import GCPHandler
from dag_status_report import DagStatusReport
import ckan.logic as logic
import ckan.lib.helpers as h

REACHED_RESOPONSE  = False
AIRCAN_RESPONSE_AFTER_SUBMIT = None

log = logging.getLogger(__name__)

ValidationError = logic.ValidationError
NotFound = logic.NotFound

NO_SCHEMA_ERROR_MESSAGE = 'Resource <a href="{0}">{1}</a> has no schema so cannot be imported into the DataStore.'\
                        ' Please add a Table Schema in the resource schema attribute.'\
                        ' See <a href="https://github.com/datopian/ckanext-aircan#airflow-instance-on-google-composer"> Airflow instance on Google Composer </a>' \
                        ' section in AirCan docs for more.'


def aircan_submit(context, data_dict):
    log.info("Submitting resource via Aircan")
    check_access('aircan_submit', context, data_dict)
    try:
        res_id = data_dict['resource_id']        
        user = get_action('user_show')(context, {'id': context['user']})
        ckan_api_key = user['apikey']
        
        ckan_resource = data_dict.get('resource_json', {})
        ckan_resource_url = config.get('ckan.site_url') + '/dataset/' + ckan_resource.get('package_id') + '/resource/' + res_id
        ckan_resource_name = ckan_resource.get('name')


        '''Sample schema structure we are expecting to receive frfom ckan_resource.get('schema')
            schema = {
                "fields": [
                    {
                        "name": "FID",
                        "title": "FID",
                        "type": "number",
                        "description": "FID`"
                    },
                    {
                        "name": "MktRF",
                        "title": "MktRF",
                        "type": "number",
                        "description": "MktRF`"
                    },
                    {
                        "name": "SMB",
                        "title": "SMB",
                        "type": "number",
                        "description": "SMB`"
                    },
                    {
                        "name": "HML",
                        "title": "HML",
                        "type": "number",
                        "description": "HML`"
                    },
                    {
                        "name": "RF",
                        "title": "RF",
                        "type": "number",
                        "description": "RF`"
                    }
                ]
        }
        '''

        table_schema = ckan_resource.get('schema')
        if not table_schema:    
            raise ValueError()
        schema = json.dumps(table_schema)

        # create giftless resource file uri to be passed to aircan
        pacakge_name = data_dict['pacakge_name']
        organization_name = data_dict['organization_name']
        resource_hash = data_dict['resource_hash']
        giftless_bucket = config.get('ckan.giftless.bucket', '')
        gcs_uri = 'gs://%s/%s/%s/%s' % (giftless_bucket, organization_name, pacakge_name, resource_hash)
        log.debug("gcs_uri: {}".format(gcs_uri))

        bq_table_name = ckan_resource.get('bq_table_name')
        log.debug("bq_table_name: {}".format(bq_table_name))
        payload = { 
            "conf": {
                "resource": {
                    "path": ckan_resource.get('url'),
                    "format": ckan_resource.get('format'),
                    "ckan_resource_id": res_id,
                    "schema": schema
                },
                "ckan_config": {
                    "api_key": ckan_api_key,
                    "site_url": config.get('ckan.site_url'),    
                },
                "big_query": {
                    "gcs_uri": gcs_uri,
                    "bq_project_id": config.get('ckanext.bigquery.project', 'NA'),
                    "bq_dataset_id": config.get('ckanext.bigquery.dataset', 'NA'),
                    "bq_table_name": bq_table_name
                },
                "output_bucket": str(date.today())
            }
        }
        log.debug("payload: {}".format(payload))
        global REACHED_RESOPONSE
        REACHED_RESOPONSE = True
        global AIRCAN_RESPONSE_AFTER_SUBMIT 

        if config.get('ckan.airflow.cloud','local') != "GCP":
            ckan_airflow_endpoint_url = config.get('ckan.airflow.url')
            log.info("Airflow Endpoint URL: {0}".format(ckan_airflow_endpoint_url))
            response = requests.post(ckan_airflow_endpoint_url,
                                     auth=requests.auth.HTTPBasicAuth( 
                                        config['ckan.airflow.username'], 
                                        config['ckan.airflow.password']),
                                     data=json.dumps(payload),
                                     headers={'Content-Type': 'application/json',
                                              'Cache-Control': 'no-cache'})
            log.info(response.text)
            response.raise_for_status()
            log.info('AirCan Load completed')
            
            AIRCAN_RESPONSE_AFTER_SUBMIT = {"aircan_status": response.json()}
        else:
            log.info("Invoking Airflow on Google Cloud Composer")
            dag_name = request.params.get('dag_name')
            if dag_name:
                config['ckan.airflow.cloud.dag_name'] = dag_name
            gcp_response = invoke_gcp(config, payload)
            AIRCAN_RESPONSE_AFTER_SUBMIT = {"aircan_status": gcp_response}
    except ValueError:
        log.error(NO_SCHEMA_ERROR_MESSAGE)
        h.flash_error(NO_SCHEMA_ERROR_MESSAGE.format(ckan_resource_url , ckan_resource_name),  allow_html=True)
    except Exception as e:
        return {"success": False, "errors": [e]}

    if REACHED_RESOPONSE == True:
        return AIRCAN_RESPONSE_AFTER_SUBMIT

def invoke_gcp(config, payload):
    log.info('Invoking GCP')
    gcp = GCPHandler(config, payload)
    log.info('Handler created')
    return gcp.trigger_dag()


def dag_status(context, data_dict):
    log.info(context)
    check_access('aircan_status', context, data_dict)
    dag_name = request.params.get('dag_name')
    execution_date = request.params.get('execution_date', '')
    dag_status_report = DagStatusReport(dag_name, execution_date, config)
    if config.get('ckan.airflow.cloud','local') != "GCP":
        return dag_status_report.get_local_aircan_report()
    return dag_status_report.get_gcp_report()
