import ckan.authz as authz
import ckan.plugins.toolkit as tk
from ckan.types import Context, DataDict, AuthResult


def aircan_submit(context: Context, data_dict: DataDict) -> AuthResult:
    # aircan_submit is called both with a full resource dict ("id") and
    # with an explicit "resource_id" key
    resource_id = data_dict.get("resource_id") or data_dict.get("id")
    return authz.is_authorized("resource_create", context, {"id": resource_id})


@tk.auth_allow_anonymous_access
def aircan_status(context: Context, data_dict: DataDict) -> AuthResult:
    # read-only: defer entirely to resource_show, which handles
    # anonymous access to public/private resources itself
    return authz.is_authorized(
        "resource_show", context, {"id": data_dict.get("resource_id")}
    )


def aircan_hook(context: Context, data_dict: DataDict) -> AuthResult:
    return authz.is_authorized(
        "resource_update", context, {"id": data_dict.get("resource_id")}
    )


def get_auth_functions():
    return {
        "aircan_submit": aircan_submit,
        "aircan_status": aircan_status,
        "aircan_hook": aircan_hook,
    }
