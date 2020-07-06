import datetime

# from nose.tools import eq_
# import mock

import ckan.plugins as p
from ckan.tests import helpers, factories


class TestNotify(object):

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
    def test_submit_on_resource_create(self, mock_datapusher_submit):
        dataset = factories.Dataset()

        assert not mock_datapusher_submit.called

        helpers.call_action('resource_create', {},
                            package_id=dataset['id'],
                            url='http://example.com/file.csv',
                            format='CSV')

        assert mock_datapusher_submit.called

    @helpers.mock_action('datapusher_submit')
    def test_submit_when_url_changes(self, mock_datapusher_submit):
        dataset = factories.Dataset()

        resource = helpers.call_action('resource_create', {},
                                       package_id=dataset['id'],
                                       url='http://example.com/file.pdf',
                                       )

        assert not mock_datapusher_submit.called  # because of the format being PDF

        helpers.call_action('resource_update', {},
                            id=resource['id'],
                            package_id=dataset['id'],
                            url='http://example.com/file.csv',
                            format='CSV'
                            )

        assert mock_datapusher_submit.called