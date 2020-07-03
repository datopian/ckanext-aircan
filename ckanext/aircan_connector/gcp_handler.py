# encoding: utf-8

import google.auth
import requests
import six.moves.urllib.parse
import logging
import json
from google.auth.transport.requests import Request, AuthorizedSession

from google.oauth2 import id_token, service_account

log = logging.getLogger(__name__)

IAM_SCOPE = 'https://www.googleapis.com/auth/iam'
OAUTH_TOKEN_URI = 'https://www.googleapis.com/oauth2/v4/token'

class GCPHandler:
    def __init__(self, config, payload):
        self.config = config
        self.payload = payload

    def get_auth_session(self):
        local_config_str = self.config['ckan.airflow.cloud.google_application_credentials']
        parsed_credentials = json.loads(local_config_str)
        credentials = service_account.Credentials.from_service_account_info(parsed_credentials, scopes=['https://www.googleapis.com/auth/cloud-platform'])
        authed_session = AuthorizedSession(credentials)
        return authed_session

    def get_env_url(self):
        project_id = self.config['ckan.airflow.cloud.project_id']
        location = self.config['ckan.airflow.cloud.location']
        composer_environment = self.config['ckan.airflow.cloud.composer_environment']
        environment_url = (
            'https://composer.googleapis.com/v1beta1/projects/{}/locations/{}'
            '/environments/{}').format(project_id, location, composer_environment)
        return environment_url


    def client_setup(self):
        authed_session = self.get_auth_session()
        environment_url = self.get_env_url()
        composer_response = authed_session.request('GET', environment_url)
        environment_data = composer_response.json()
        airflow_uri = environment_data['config']['airflowUri']
        redirect_response = requests.get(airflow_uri, allow_redirects=False)
        redirect_location = redirect_response.headers['location']
        parsed = six.moves.urllib.parse.urlparse(redirect_location)
        query_string = six.moves.urllib.parse.parse_qs(parsed.query)
        client_id = query_string['client_id'][0]
        return client_id


    def trigger_dag(self):
        log.info("Trigger DAG on GCP")
        client_id = self.client_setup()
        # This should be part of your webserver's URL:
        # {tenant-project-id}.appspot.com
        webserver_id = self.config['ckan.airflow.cloud.web_ui_id']
        dag_name = self.config['ckan.airflow.cloud.dag_name']
        webserver_url = (
            'https://'
            + webserver_id
            + '.appspot.com/api/experimental/dags/'
            + dag_name
            + '/dag_runs'
        )
        # Make a POST request to IAP which then Triggers the DAG
        return self.make_iap_request(webserver_url, client_id, method='POST', json={"conf": self.payload})


    def get_google_token_id(self, client_id):
        local_config_str = self.config['ckan.airflow.cloud.google_application_credentials']
        parsed_credentials = json.loads(local_config_str)
        credentials = service_account.IDTokenCredentials.from_service_account_info(parsed_credentials, target_audience=client_id)
        request = Request()
        credentials.refresh(request)
        return credentials.token

    def make_iap_request(self, url, client_id, method='GET', **kwargs):
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 90
        
        google_open_id_connect_token = self.get_google_token_id(client_id)
        resp = requests.request(
            method, url,
            headers={'Authorization': 'Bearer {}'.format(
                google_open_id_connect_token)}, **kwargs)
        log.info('Request sent to GCP. Response code: {!r} '.format(resp.status_code))
        
        if resp.status_code == 403:
            raise Exception('Service account does not have permission to '
                            'access the IAP-protected application.')
        elif resp.status_code != 200:
            raise Exception(
                'Bad response from application: {!r} / {!r} / {!r}'.format(
                    resp.status_code, resp.headers, resp.text))
        else:
            return resp.text
