# encoding: utf-8
import ckan.authz as authz
import ckan.plugins as p


def aircan_auth(context, data_dict, privilege='resource_update'):
    if 'id' not in data_dict:
        data_dict['id'] = data_dict.get('resource_id')

    user = context.get('user')

    authorized = p.toolkit.check_access(privilege, context, data_dict)

    if not authorized:
        return {
            'success': False,
            'msg': p.toolkit._(
                'User {0} not authorized for aircan'
                    .format(str(user))
            )
        }
    else:
        return {'success': True}

def aircan_submit(context, data_dict):
    return aircan_auth(context, data_dict)


def aircan_status(context, data_dict):
    return aircan_auth(context, data_dict)


def aircan_clear_stale_precision_warnings(context, data_dict):
    # Sweeps across every resource, so it is sysadmin-only. CKAN grants
    # sysadmins access regardless of what an auth function returns, so denying
    # everyone here is exactly "sysadmin only".
    return {
        'success': False,
        'msg': p.toolkit._('Only sysadmins can clear precision warnings in bulk'),
    }


@p.toolkit.auth_disallow_anonymous_access
def aircan_error_list(context, data_dict):
    # Any logged-in user may call it; the action itself limits non-sysadmins to
    # the organizations where they can edit datasets. The decorator alone does
    # not stop anonymous API calls on CKAN 2.10+: they carry an AnonymousUser
    # object in auth_user_obj, which the decorator treats as logged in.
    if authz.auth_is_anon_user(context):
        return {
            'success': False,
            'msg': p.toolkit._('You must be logged in to list aircan errors'),
        }
    return {'success': True}
