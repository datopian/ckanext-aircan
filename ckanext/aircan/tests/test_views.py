"""Tests for views.py."""

import pytest

import ckanext.aircan.validators as validators


import ckan.plugins.toolkit as tk


@pytest.mark.ckan_config("ckan.plugins", "aircan")
@pytest.mark.usefixtures("with_plugins")
def test_aircan_blueprint(app, reset_db):
    resp = app.get(tk.h.url_for("aircan.page"))
    assert resp.status_code == 200
    assert resp.body == "Hello, aircan!"
