from flask import Blueprint
import ckan.plugins.toolkit as toolkit
from flask.views import MethodView
import ckan.model as model
import ckan.logic as logic


aircan = Blueprint(u'aircan', __name__)

class ResourceDataController(MethodView):
    def _prepare(self, id, resource_id):
        context = {
            'model': model,
            'session': model.Session,
            'user': toolkit.g.user,
            'auth_user_obj': toolkit.g.userobj
        }
        return context


    def post(self, id, resource_id):
        context = self._prepare(id,resource_id)

        try:
            pacakge_dict = toolkit.get_action(u'package_show')(
                context, {
                    u'id': id,
                })
                
            resource_dict = toolkit.get_action(u'resource_show')(
                context, {
                    'id': resource_id,
                })
            toolkit.get_action(u'aircan_submit')(context, {
                    u'resource_id': resource_dict['id'],
                    u'resource_json': resource_dict,
                    u'pacakge_name': pacakge_dict.get('name'),
                    u'organization_name': pacakge_dict.get('organization', {}).get('name'),
                    u'resource_hash': resource_dict.get('hash')
                    })
        except logic.ValidationError:
            pass

        return toolkit.h.redirect_to(
            controller='aircan',
            action='resource_data',
            id=id,
            resource_id=resource_id
        )
        
    def get(self, id, resource_id):
        context = self._prepare(id, resource_id)
        try:
            toolkit.c.pkg_dict = toolkit.get_action('package_show')(
                context, {'id': id}
            )
            toolkit.c.resource = toolkit.get_action('resource_show')(
                context, {'id': resource_id}
            )
        except (logic.NotFound, logic.NotAuthorized):
            toolkit.abort(404, toolkit._('Resource not found'))

        try:
            aircan_status = toolkit.get_action('aircan_status')(
                context, {'resource_id': resource_id}
            )
        except logic.NotFound:
            aircan_status = {}
        except logic.NotAuthorized:
            toolkit.abort(403, toolkit._('Not authorized to see this page'))

        return toolkit.render('resource_data.html',
                        extra_vars={'status': aircan_status})

       

aircan.add_url_rule(
    u'/dataset/<id>/resource_data/<resource_id>',
    view_func=ResourceDataController.as_view(str(u'resource_data'))
)
