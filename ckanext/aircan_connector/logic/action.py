# encoding: utf-8
import requests
from datetime import date
from ckan.common import config
from ckan.plugins.toolkit import get_action, check_access
import logging
import json
import uuid
import datetime

from ckan.common import request
from gcp_handler import GCPHandler
from dag_status_report import DagStatusReport
import ckan.logic as logic
import ckan.plugins as p
import ckan.lib.helpers as h

REACHED_RESOPONSE  = False
AIRCAN_RESPONSE_AFTER_SUBMIT = None

log = logging.getLogger(__name__)

ValidationError = logic.ValidationError
NotFound = logic.NotFound
_get_or_bust = logic.get_or_bust


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

        table_schema = ckan_resource.get('schema', {})
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
        dag_run_id = str(uuid.uuid4())
        payload = { 
            "dag_run_id": dag_run_id,
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

        # Update the aircan run status
        p.toolkit.get_action('aircan_status_update')(context,{ 
            'dag_run_id': dag_run_id,
            'resource_id': res_id,
            'state': 'pending',
            'message': 'Added to the queue to be processed.',
            'clear_logs': True
            })

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


def aircan_dag_status(dag_name, dag_run_id):
    dag_status_report = DagStatusReport(dag_name, dag_run_id, config)
    if config.get('ckan.airflow.cloud','local') != "GCP":
        return dag_status_report.get_local_aircan_report()
    return dag_status_report.get_gcp_report()

def aircan_status(context, data_dict):
    ''' Get the status of a aircan job for a certain resource.
    :param resource_id: The resource id of the resource that you want the
        aircan status for.
    :type resource_id: string
    '''
    if 'id' in data_dict:
        data_dict['resource_id'] = data_dict['id']
    res_id = _get_or_bust(data_dict, 'resource_id')

    task = p.toolkit.get_action('task_status_show')(context, {
        'entity_id': res_id,
        'task_type': 'aircan',
        'key': 'aircan'
    })
    return_dict = {
        'status': task['state'],
        'last_updated': task['last_updated'],
        'error': json.loads(task['error']),
        'value': json.loads(task['value'])
    }
    return_dict.update(json.loads(task['value']))
    return_dict.pop('value')
    dag_run_id = return_dict.get('dag_run_id', False)
    if dag_run_id:
        try:
            dag_status = aircan_dag_status(
                    config.get('ckan.airflow.cloud.dag_name',
                    'ckan_api_load_multiple_steps'), 
                    dag_run_id)['airflow_api_aircan_status'] 

            airflow_to_ckan_state = {
                'queued': 'pending',
                'running':'progress',
                'success': 'complete',
                'failed': 'error',
                'up_for_retry': 'progress',
                'upstream_failed': 'error'
            }
            return_dict['status'] = airflow_to_ckan_state.get(
                    dag_status['state'], 
                    return_dict['status']
                    )
            return_dict.update(dag_status)
        except Exception as e:
            log.error(e)
    return return_dict

def aircan_status_update(context, data_dict):
    ''' Update the aircan dag status for a certain resource.
    :param id: the id of the task status to update
    :type id: string
    :param resource_id:
    :type resource_id: string
    :param message: message string
    :type message: string
    :param state: (optional)
    :type state:
    :param last_updated: (optional)
    :type last_updated:
    :param error: (optional)
    :type error:
    :returns: the updated task status
    :rtype: dictionary
    '''

    task_value = data_dict.get('value', {})
    now_date = str(datetime.datetime.utcnow())

    # Update dag_run_id in value
    if data_dict.get('dag_run_id', False):
        task_value.update({'dag_run_id': data_dict.get('dag_run_id')}) 

    log_item = { 'datetime': now_date, 'message': data_dict.get('message', '')}
    try:
        old_task_status = p.toolkit.get_action('aircan_status')(
            {}, {'resource_id': data_dict.get('resource_id', '')})

        # Preserve old dag run id if new is not provided 
        if not data_dict.get('dag_run_id') and \
                old_task_status.get('dag_run_id', ''):
            task_value.update({'dag_run_id': old_task_status.get('dag_run_id')}) 
        
        # Clear log and add new log if clear_logs is true
        if data_dict.get('clear_logs', False):
            old_task_status['logs'] = [log_item] 
        # Append new log wihout distorying old one
        elif old_task_status.get('logs', False):
            old_task_status['logs'].append(log_item)

        task_value.update({'logs': old_task_status['logs']})
    except p.toolkit.ObjectNotFound:
        task_value['logs'] = [log_item] 
    task_dict =  {
        'entity_id': data_dict.get('resource_id', ''),
        'entity_type': 'resource',
        'task_type': 'aircan',
        'state': data_dict.get('state', ''),
        'last_updated': data_dict.get('last_updated', now_date),
        'key': 'aircan',
        'value': json.dumps(task_value),
        'error': json.dumps(data_dict.get('error', {})),
    }
    task_update = p.toolkit.get_action('task_status_update')(context, task_dict)
    return task_update