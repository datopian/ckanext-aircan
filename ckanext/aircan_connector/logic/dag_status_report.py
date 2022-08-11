# encoding: utf-8

import logging as l
import json
import requests
from gcp_handler import GCPHandler

from google.oauth2 import id_token, service_account
# from google.cloud import logging_v2
from google.cloud import logging


log = l.getLogger(__name__)

IAM_SCOPE = 'https://www.googleapis.com/auth/iam'
OAUTH_TOKEN_URI = 'https://www.googleapis.com/oauth2/v4/token'

class DagStatusReport:
    def __init__(self, dag_name, dag_run_id, config):
        self.dag_name = dag_name
        self.config = config
        self.dag_run_id = dag_run_id

    def get_local_aircan_report(self):
        log.info("Building Airflow local status report")
        ckan_airflow_endpoint_url = self.config.get('ckan.airflow.url')
        log.info("Airflow Endpoint URL: {0}/{1}".format(ckan_airflow_endpoint_url, self.dag_run_id))
        response = requests.get('{0}/{1}'.format(ckan_airflow_endpoint_url, self.dag_run_id),
                                auth=requests.auth.HTTPBasicAuth(
                                        self.config['ckan.airflow.username'], 
                                        self.config['ckan.airflow.password']),
                                 headers={'Content-Type': 'application/json',
                                          'Cache-Control': 'no-cache'})
        response.raise_for_status()
        log.info('Airflow status request completed')
        return {"success": True, "airflow_api_aircan_status": response.json()}


    def get_gcp_report(self):
        gcp = GCPHandler(self.config, {})
        log.info("Trigger DAG - {} on GCP".format(self.dag_name))
        webserver_id = self.config.get('ckan.airflow.cloud.web_ui_id')
        webserver_url = (
            'https://'
            + webserver_id
            + '.composer.googleusercontent.com/api/v1/dags/'
            + self.dag_name
            + '/dagRuns/'
            + self.dag_run_id
        )
        log.info("The Webserver Url: {}".format(webserver_url))
        # Make a POST request to IAP which then Triggers the DAG
        airflow_api_status = gcp.make_iap_request(webserver_url, method='GET')
        return {"success": True, "airflow_api_aircan_status": airflow_api_status, "gcp_logs": {} }

    def get_gcp_logs_for_dag(self):
        project_id = self.config.get('ckan.airflow.cloud.project_id', "")
        local_config_str = self.config.get('ckan.airflow.cloud.google_application_credentials')
        parsed_credentials = json.loads(local_config_str)
        credentials = service_account.Credentials.from_service_account_info(parsed_credentials, scopes=['https://www.googleapis.com/auth/cloud-platform'])
        client = logging.client.Client(project_id, credentials=credentials)
        entries_filter = "resource.type:cloud_composer_environment AND resource.labels.location:us-east1 AND resource.labels.environment_name:aircan-airflow AND" + self.dag_name
        entries = client.list_entries([project_id], filter_=entries_filter)
        return entries
