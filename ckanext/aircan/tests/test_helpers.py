"""Tests for helpers.py."""

import pytest

import ckanext.aircan.helpers as helpers


@pytest.mark.usefixtures("ckan_config")
class TestAllowedAircanFormat:
    def test_default_formats(self):
        assert helpers.allowed_aircan_format("csv")
        assert helpers.allowed_aircan_format("CSV")
        assert helpers.allowed_aircan_format("text/csv")
        assert helpers.allowed_aircan_format("parquet")

    def test_disallowed_formats(self):
        assert not helpers.allowed_aircan_format("pdf")
        assert not helpers.allowed_aircan_format("")
        assert not helpers.allowed_aircan_format(None)

    @pytest.mark.ckan_config("ckanext.aircan.formats", "xlsx csv")
    def test_formats_from_config(self):
        assert helpers.allowed_aircan_format("XLSX")
        assert helpers.allowed_aircan_format("csv")
        assert not helpers.allowed_aircan_format("json")


@pytest.mark.usefixtures("ckan_config")
class TestIsValidateRecordsEnabled:
    def test_enabled_by_default(self):
        assert helpers.is_validate_records_enabled() is True

    @pytest.mark.ckan_config("ckanext.aircan.validate_records", "false")
    def test_disabled_via_config(self):
        assert helpers.is_validate_records_enabled() is False
