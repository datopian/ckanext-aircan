import json

import ckan.plugins.toolkit as tk

DEFAULT_FORMATS = [
    "csv",
    "xls",
    "xlsx",
    "tsv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ods",
    "application/vnd.oasis.opendocument.spreadsheet",
]

def allowed_formats(format_):
    """Return True if `format_` is in allowed formats."""
    cfg = tk.config.get("ckanext.aircan.formats")
    if cfg and cfg.strip():
        formats = cfg.lower().split()
    else:
        formats = DEFAULT_FORMATS

    if not format_:
        return False

    return format_.lower() in formats
