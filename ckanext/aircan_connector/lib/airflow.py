# encoding: utf-8

import logging
import json
import uuid
import datetime

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

log = logging.getLogger(__name__)


class AirflowClient(object):
    """
    Airflow API client with two auth modes:
      - server_type="GCP": Google service-account AuthorizedSession
      - server_type="local": HTTP Basic Auth (api/v1) or JWT Bearer (api/v2)
    """

    AUTH_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'

    def __init__(self, config, payload=None):
        self.config = config
        self.payload = payload or {}
        self._authed_session = None
        self._access_token = None

        self.server_type = (config.get('ckan.airflow.cloud', 'local') or 'local').upper()
        self.api_version = config.get('ckan.airflow.api_version', self._default_api_version())
        self.timeout = int(config.get('ckan.airflow.timeout', 90) or 90)
        self.dag_id = config.get('ckan.airflow.cloud.dag_name')

        # local auth
        self.token_endpoint = config.get('ckan.airflow.token_endpoint', '/auth/token')
        self.username = config.get('ckan.airflow.username')
        self.password = config.get('ckan.airflow.password')

        if self.server_type == 'GCP':
            local_config_str = config.get('ckan.airflow.cloud.google_application_credentials')
            parsed_credentials = json.loads(local_config_str)
            creds = service_account.Credentials.from_service_account_info(
                parsed_credentials, scopes=[self.AUTH_SCOPE])
            self._authed_session = AuthorizedSession(creds)

    def _default_api_version(self):
        return 'v2' if self._composer_version() >= 3 else 'v1'

    def _composer_version(self):
        return int(self.config.get('ckan.airflow.cloud.composer_version', 2))

    def _join_url(self, endpoint):
        return '{}/{}'.format(self._get_base_url(), (endpoint or '').lstrip('/'))

    def _get_base_url(self):
        if self.server_type == 'GCP':
            if self._composer_version() >= 3:
                return self._get_composer3_webserver_url()
            webserver_id = self.config.get('ckan.airflow.cloud.web_ui_id')
            return 'https://{}.composer.googleusercontent.com'.format(webserver_id)
        return (self.config.get('ckan.airflow.url') or '').rstrip('/')

    def _get_composer_env_url(self):
        project_id = self.config.get('ckan.airflow.cloud.project_id')
        location = self.config.get('ckan.airflow.cloud.location')
        composer_environment = self.config.get('ckan.airflow.cloud.composer_environment')
        # Composer 3 uses stable v1 API; Composer 2 uses v1beta1
        api_ver = 'v1' if self._composer_version() >= 3 else 'v1beta1'
        return (
            'https://composer.googleapis.com/{}/projects/{}/locations/{}/environments/{}'
        ).format(api_ver, project_id, location, composer_environment)

    def _get_composer3_webserver_url(self):
        resp = self._authed_session.get(self._get_composer_env_url(), timeout=self.timeout)
        if resp.status_code != 200:
            raise Exception(
                'Failed to get Composer environment details: {!r} / {!r}'.format(
                    resp.status_code, resp.text))
        airflow_uri = resp.json().get('config', {}).get('airflowUri')
        if not airflow_uri:
            raise Exception('Could not find airflowUri in Composer environment config')
        return airflow_uri.rstrip('/')

    def _login_local(self):
        if not self.username or not self.password:
            raise ValueError('Missing config: ckan.airflow.username / ckan.airflow.password')
        url = self._join_url(self.token_endpoint)
        resp = requests.post(
            url,
            headers={'Content-Type': 'application/json'},
            json={'username': self.username, 'password': self.password},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        token = resp.json().get('access_token')
        if not token:
            raise requests.HTTPError('Token response did not include access_token')
        self._access_token = token
        return token

    def request(self, method, endpoint, **kwargs):
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout

        url = self._join_url(endpoint)

        if self.server_type == 'GCP':
            return self._authed_session.request(method, url, **kwargs)

        headers = kwargs.pop('headers', {}) or {}
        if self.api_version == 'v1':
            # Airflow 2 local: HTTP Basic Auth
            kwargs['auth'] = requests.auth.HTTPBasicAuth(self.username, self.password)
        else:
            # Airflow 3 local: JWT Bearer token
            if not self._access_token:
                self._login_local()
            headers['Authorization'] = 'Bearer ' + self._access_token
        kwargs['headers'] = headers
        return requests.request(method, url, **kwargs)

    def trigger_dag(self):
        log.info('Trigger DAG - {} on {}'.format(self.dag_id, self.server_type))
        payload = dict(self.payload)
        payload.setdefault('dag_run_id', str(uuid.uuid4()))
        if self.api_version == 'v2':
            payload.setdefault(
                'logical_date',
                datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            )
        endpoint = '/api/{}/dags/{}/dagRuns'.format(self.api_version, self.dag_id)
        log.info('DAG trigger URL: {}'.format(self._join_url(endpoint)))
        resp = self.request('POST', endpoint, json=payload)
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code == 403:
            raise Exception(
                'Service account does not have permission to access the Airflow web server.')
        raise Exception('Bad response from application: {!r} / {!r} / {!r}'.format(
            resp.status_code, resp.headers, resp.text))

    def get_dag_run(self, dag_run_id):
        endpoint = '/api/{}/dags/{}/dagRuns/{}'.format(self.api_version, self.dag_id, dag_run_id)
        resp = self.request('GET', endpoint)
        resp.raise_for_status()
        return resp.json()

    def get_aircan_report(self, dag_run_id):
        log.info('Building Airflow status report for DAG run {}'.format(dag_run_id))
        airflow_api_status = self.get_dag_run(dag_run_id)
        return {'success': True, 'airflow_api_aircan_status': airflow_api_status}

    def get_gcp_logs(self, dag_name):
        from google.cloud import logging as gcp_logging
        project_id = self.config.get('ckan.airflow.cloud.project_id', '')
        location = self.config.get('ckan.airflow.cloud.location', 'us-east1')
        composer_environment = self.config.get('ckan.airflow.cloud.composer_environment', 'aircan-airflow')
        client = gcp_logging.Client(project_id, credentials=self._authed_session.credentials)
        entries_filter = (
            'resource.type:cloud_composer_environment AND '
            'resource.labels.location:{} AND '
            'resource.labels.environment_name:{} AND {}'
        ).format(location, composer_environment, dag_name)
        return client.list_entries([project_id], filter_=entries_filter)
