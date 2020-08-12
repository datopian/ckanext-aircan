# encoding: utf-8

import logging
import json
import requests
from gcp_handler import GCPHandler

from google.oauth2 import id_token, service_account

log = logging.getLogger(__name__)

IAM_SCOPE = 'https://www.googleapis.com/auth/iam'
OAUTH_TOKEN_URI = 'https://www.googleapis.com/oauth2/v4/token'

class DagStatusReport:
    def __init__(self, dag_name, execution_date, config):
        self.dag_name = dag_name
        self.config = config
        self.execution_date = (("/" + str(execution_date)) if execution_date != '' else '')

    def get_local_aircan_report(self):
        log.info("Building Airflow local status report")
        ckan_airflow_endpoint_url = self.config.get('ckan.airflow.url')
        log.info("Airflow Endpoint URL: {0}".format(ckan_airflow_endpoint_url))
        response = requests.get(ckan_airflow_endpoint_url,
                                 headers={'Content-Type': 'application/json',
                                          'Cache-Control': 'no-cache'})
        log.info(response.text)
        response.raise_for_status()
        log.info('Airflow status request completed')
        return {"success": True, "aircan_dag_status": response.json()}

    def get_gcp_report(self):
        log.info("Building GCP DAG status report")
        gcp = GCPHandler(self.config, {})
        client_id = gcp.client_setup()
        webserver_id = self.config.get('ckan.airflow.cloud.web_ui_id')
        webserver_url = (
            'https://'
            + webserver_id
            + '.appspot.com/api/experimental/dags/'
            + self.dag_name
            + '/dag_runs'
            + (self.execution_date)
        )
        
        return gcp.make_iap_request(webserver_url, client_id, method='GET')