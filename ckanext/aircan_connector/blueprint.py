from flask import Blueprint
from flask.views import MethodView
import ckan.plugins.toolkit as toolkit
import ckan.logic as logic
import ckan.lib.helpers as core_helpers
from ckan.common import request


aircan = Blueprint(u'aircan', __name__)

class ResourceDataView(MethodView):

    def post(self, id, resource_id):
        payload = request.data
        try:
            toolkit.get_action(u'aircan_submit')(
                None, {
                    u'resource_id': resource_id,
                    u'resource_json': payload
                }
            )
        except logic.ValidationError:
            pass

        return core_helpers.redirect_to(
            u'datapusher.resource_data', id=id, resource_id=resource_id
        )

class DagStatusView(MethodView):
    def post(self, id, dag_id):
        try:
            payload = request.data
            log.info(payload)
            toolkit.get_action(u'aircan_status')(
                None, {
                    u'dag_id': dag_id,
                    u'airflow_process_status': payload
                }
            )
        except logic.ValidationError:
            pass

        return core_helpers.redirect_to(
            # WARNING Should here also be changed from dat_status to aircan_status ??
            u'datapusher.dag_status', id=id, dag_id=dag_id
        )


aircan.add_url_rule(
    u'/dataset/<id>/resource_data/<resource_id>',
    view_func=ResourceDataView.as_view(str(u'resource_data'))
)


aircan.add_url_rule(
    u'/aircan_status/<dag_id>',
    view_func=DagStatusView.as_view(str(u'aircan_status'))
)