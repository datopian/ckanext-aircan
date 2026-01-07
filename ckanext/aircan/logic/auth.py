import ckan.authz as authz
from ckan.types import Context, DataDict, AuthResult


def aircan_submit(context: Context, data_dict: DataDict) -> AuthResult:
    return authz.is_authorized(
        "resource_create", context, {"id": data_dict.get("resource_id")}
    )


def aircan_status(context: Context, data_dict: DataDict) -> AuthResult:
    return authz.is_authorized(
        "resource_show", context, {"id": data_dict.get("resource_id")}
    )


def aircan_status_update(context: Context, data_dict: DataDict) -> AuthResult:
    return authz.is_authorized(
        "resource_update", context, {"id": data_dict.get("resource_id")}
    )


def get_auth_functions():
    return {
        "aircan_submit": aircan_submit,
        "aircan_status": aircan_status,
        "aircan_status_update": aircan_status_update,
    }
