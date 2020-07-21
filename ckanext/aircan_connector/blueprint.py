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
            toolkit.get_action(u'datapusher_submit')(
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


aircan.add_url_rule(
    u'/dataset/<id>/resource_data/<resource_id>',
    view_func=ResourceDataView.as_view(str(u'resource_data'))
)
