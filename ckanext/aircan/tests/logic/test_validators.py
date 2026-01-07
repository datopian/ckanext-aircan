"""Tests for validators.py."""

import pytest

import ckan.plugins.toolkit as tk

from ckanext.aircan.logic import validators


def test_aircan_reauired_with_valid_value():
    assert validators.aircan_required("value") == "value"


def test_aircan_reauired_with_invalid_value():
    with pytest.raises(tk.Invalid):
        validators.aircan_required(None)
