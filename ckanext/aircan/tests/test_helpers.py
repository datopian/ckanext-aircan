"""Tests for helpers.py."""

import ckanext.aircan.helpers as helpers


def test_aircan_hello():
    assert helpers.aircan_hello() == "Hello, aircan!"
