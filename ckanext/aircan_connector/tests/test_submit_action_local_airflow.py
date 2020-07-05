
import os
import requests
import json
import ckan.plugins as p
from ckan.tests import helpers, factories
from nose.tools import assert_equal, assert_true, assert_in

CKAN_AIRFLOW_URL = 'http://localhost:8080/api/experimental/dags/{}/dag_runs'
DAG_ID = 'ckan_api_load_multiple_steps'

def get_sample_filepath(filename):
    return os.path.abspath(os.path.join(os.path.dirname(__file__), 'samples',
                                        filename))

class TestSubmit(object):

    @classmethod
    def setup_class(cls):
        if not p.plugin_loaded('datastore'):
            p.load('datastore')
        if not p.plugin_loaded('aircan_connector'):
            p.load('aircan_connector')

        helpers.reset_db()

    @classmethod
    def teardown_class(cls):

        p.unload('aircan_connector')
        p.unload('datastore')

        helpers.reset_db()

    @helpers.mock_action('datapusher_submit')
    def test_local_airflow_dag_triggered(self, mock_datapusher_submit):
        dataset = factories.Dataset()

        resource = helpers.call_action('resource_create', {},
                                        package_id=dataset['id'],
                                        url='http://example.com/file.csv',
                                        format='CSV'
                                        )
        assert mock_datapusher_submit.called

        ckan_airflow_endpoint_url = CKAN_AIRFLOW_URL.format(DAG_ID)
        json_output_file_path = get_sample_filepath('my2.json')
        payload = {
             "conf": {
                 "resource_id": resource['id'],
                 "schema_fields_array": ["FID", "Mkt-RF", "SMB", "HML", "RF"],
                 "csv_input": resource['url'],
                 "json_output": json_output_file_path
             }
        }
        response = requests.post(ckan_airflow_endpoint_url,
                                 data=json.dumps(payload),
                                 headers={'Content-Type': 'application/json',
                                          'Cache-Control': 'no-cache'}
                                 )
        print(response)
        assert_equal(200, response.status_code)







