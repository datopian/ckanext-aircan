# encoding: utf-8
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
