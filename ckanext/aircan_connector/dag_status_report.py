# encoding: utf-8

# import google.auth
# import requests
# import six.moves.urllib.parse
import logging
import json
import requests
# from google.auth.transport.requests import Request, AuthorizedSession

from google.oauth2 import id_token, service_account

log = logging.getLogger(__name__)

IAM_SCOPE = 'https://www.googleapis.com/auth/iam'
OAUTH_TOKEN_URI = 'https://www.googleapis.com/oauth2/v4/token'

class DagStatusReport:
    def __init__(self, dag_name, config):
        self.dag_name = dag_name
        self.config = config

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
        return {"success": True}