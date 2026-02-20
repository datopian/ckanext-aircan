import json
import requests
from ckan.plugins import toolkit as tk
import ckan.model as model


def get_aircan_badge(resource_id: str):
    """
    Helper function to get the status of a aircan for a given resource ID.
    Returns a dictionary with the status information.
    """
    context = {
        "model": model,
        "ignore_auth": True,
    }

    try:
        aircan_status = tk.get_action("aircan_status")(context, {"id": resource_id})
    except (tk.ObjectNotFound, tk.ValidationError, requests.ConnectionError):
        return ""

    if not aircan_status:
        return ""

    status = aircan_status.get("state", "")

    badge_class = {
        "success": "bg-success text-white",
        "running": "bg-info text-white",
        "failed": "bg-danger text-white",
        "queued": "bg-warning text-dark",
    }.get(status, "bg-secondary text-white")

    capitalized_status = status.capitalize() if status else "Unknown"

    # Create animated badge with initial dot and hover expansion
    return (
        f'<span class="badge-container d-inline-flex align-items-center">'
        f'<span class="badge-label rounded-pill overflow-hidden border" style="font-size: 12px;">'
        f'<span class="bg-dark text-white px-2 py-1">Pipeline</span>'
        f'<span class="{badge_class} px-2 py-1">{capitalized_status}</span>'
        "</span>"
        "</span>"
    )


def get_helpers():
    return {
        "get_aircan_badge": get_aircan_badge,
    }
