# encoding: utf-8

import logging
import json

from google.auth.transport.requests import Request, AuthorizedSession

from google.oauth2 import service_account

log = logging.getLogger(__name__)

IAM_SCOPE = 'https://www.googleapis.com/auth/iam'
OAUTH_TOKEN_URI = 'https://www.googleapis.com/oauth2/v4/token'

class GCPHandler:
    def __init__(self, config, payload):
        self.config = config
        self.payload = payload

    def get_auth_session(self):
        local_config_str = self.config.get('ckan.airflow.cloud.google_application_credentials')
        parsed_credentials = json.loads(local_config_str)
        credentials = service_account.Credentials.from_service_account_info(parsed_credentials, scopes=['https://www.googleapis.com/auth/cloud-platform'])
        authed_session = AuthorizedSession(credentials)
        return authed_session

    def get_env_url(self):
        project_id = self.config.get('ckan.airflow.cloud.project_id')
        location = self.config.get('ckan.airflow.cloud.location')
        composer_environment = self.config.get('ckan.airflow.cloud.composer_environment')
        environment_url = (
            'https://composer.googleapis.com/v1beta1/projects/{}/locations/{}'
            '/environments/{}').format(project_id, location, composer_environment)
        return environment_url


    def trigger_dag(self):
        dag_name = self.config.get('ckan.airflow.cloud.dag_name')
        log.info("Trigger DAG - {} on GCP".format(dag_name))
        webserver_id = self.config.get('ckan.airflow.cloud.web_ui_id')
        webserver_url = (
            'https://'
            + webserver_id
            + '.composer.googleusercontent.com/api/v1/dags/'
            + dag_name
            + '/dagRuns'
        )
        log.info("The Webserver Url: {}".format(webserver_url))
        # Make a POST request to IAP which then Triggers the DAG
        return self.make_iap_request(webserver_url, method='POST', json=self.payload)


    def get_google_token_id(self, client_id):
        local_config_str = self.config.get('ckan.airflow.cloud.google_application_credentials')
        parsed_credentials = json.loads(local_config_str)
        credentials = service_account.IDTokenCredentials.from_service_account_info(parsed_credentials, target_audience=client_id)
        request = Request()
        credentials.refresh(request)
        return credentials.token


    def make_iap_request(self, url, method='GET', **kwargs):
        """
        Make a request to Cloud Composer 2 environment's web server.
        Args:
        url: The URL to fetch.
        method: The request method to use ('GET', 'OPTIONS', 'HEAD', 'POST', 'PUT',
            'PATCH', 'DELETE')
        **kwargs: Any of the parameters defined for the request function:
                    https://github.com/requests/requests/blob/master/requests/api.py
                    If no timeout is provided, it is set to 90 by default.
        """

        authed_session = self.get_auth_session()

        # Set the default timeout, if missing
        if "timeout" not in kwargs:
            kwargs["timeout"] = 90

        resp = authed_session.request(method, url, **kwargs)
        log.info("Response from IAP: {}".format(resp.text))
        log.info('Request sent to GCP. Response code: {!r} '.format(resp.status_code))
        
        if resp.status_code == 403:
            raise Exception('Service account does not have permission to '
                            'access the IAP-protected application.')
        elif resp.status_code != 200:
            raise Exception(
                'Bad response from application: {!r} / {!r} / {!r}'.format(
                    resp.status_code, resp.headers, resp.text))
        else:
            return resp.json()
