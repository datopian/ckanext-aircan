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
from ckan.common import request
from gcp_handler import GCPHandler
from dag_status_report import DagStatusReport
import ckan.logic as logic

REACHED_RESOPONSE  = False
AIRCAN_RESPONSE_AFTER_SUBMIT = None

log = logging.getLogger(__name__)

ValidationError = logic.ValidationError
NotFound = logic.NotFound

NO_SCHEMA_ERROR_MESSAGE = "This resource has no schema so cannot be imported into the DataStore."\
                        " Please add a Table Schema in the resource schema attribute."\
                        " See `Airflow instance on Google Composer` section in AirCan docs [https://github.com/datopian/ckanext-aircan#airflow-instance-on-google-composer] for more."

def datapusher_submit(context, data_dict):
    log.info("Submitting resource via Aircan")
    
    try:
        res_id = data_dict['resource_id']
        user = get_action('user_show')(context, {'id': context['user']})
        ckan_api_key = user['apikey']
        
        ckan_resource = data_dict.get('resource_json', {})

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
            raise NotFound({'Schema Not Found': NO_SCHEMA_ERROR_MESSAGE})
        schema = json.dumps(table_schema)

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
                    "bq_project_id": config.get('ckanext.bigquery.project', 'NA'),
                    "bq_dataset_id": config.get('ckanext.bigquery.dataset', 'NA')
                },
                "output_bucket": str(date.today())
            }
        }
        log.info(payload)
        global REACHED_RESOPONSE
        REACHED_RESOPONSE = True
        global AIRCAN_RESPONSE_AFTER_SUBMIT 

        if config.get('ckan.airflow.cloud','local') != "GCP":
            ckan_airflow_endpoint_url = config.get('ckan.airflow.url')
            log.info("Airflow Endpoint URL: {0}".format(ckan_airflow_endpoint_url))
            response = requests.post(ckan_airflow_endpoint_url,
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
    except NotFound:
        log.error(NO_SCHEMA_ERROR_MESSAGE)
        raise
    except Exception as e:
        return {"success": False, "errors": [e]}


def invoke_gcp(config, payload):
    log.info('Invoking GCP')
    gcp = GCPHandler(config, payload)
    log.info('Handler created')
    return gcp.trigger_dag()


def aircan_submit(context, data_dict):
    log.info("Aircan submit action")
    resource = get_action('resource_create')(context, data_dict)
    if REACHED_RESOPONSE == True:
        return AIRCAN_RESPONSE_AFTER_SUBMIT

def dag_status(context, data_dict):
    dag_name = request.params.get('dag_name')
    execution_date = request.params.get('execution_date', '')
    dag_status_report = DagStatusReport(dag_name, execution_date, config)
    if config.get('ckan.airflow.cloud','local') != "GCP":
        return dag_status_report.get_local_aircan_report()
    return dag_status_report.get_gcp_report()
