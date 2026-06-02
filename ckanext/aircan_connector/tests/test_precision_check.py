# src/ckanext-aircan/ckanext/aircan_connector/tests/test_precision_check.py
#
# Pure unit tests — no CKAN installation required.
# CKAN and its dependencies are stubbed via sys.modules before any import of action.py.
import io
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# ── Stub out every CKAN / third-party module that action.py imports ──────────
# This lets the tests run outside the Docker container.
_CKAN_STUBS = [
    'ckan', 'ckan.common', 'ckan.plugins', 'ckan.plugins.toolkit',
    'ckan.logic', 'ckan.lib', 'ckan.lib.jobs', 'ckan.lib.helpers',
    'ckan.lib.uploader', 'ckan.config', 'ckan.config.middleware',
    'ckanext.aircan_connector.lib', 'ckanext.aircan_connector.lib.airflow',
    'sqlalchemy', 'boto3', 'botocore', 'botocore.client', 'user_agents',
]
for _mod in _CKAN_STUBS:
    sys.modules.setdefault(_mod, MagicMock())

# ValidationError must be a real exception class so pytest.raises works.
ValidationError = type('ValidationError', (Exception,), {})
sys.modules['ckan.logic'].ValidationError = ValidationError

from ckanext.aircan_connector.logic.action import _sample_csv_for_precision_risk  # noqa: E402

JS_MAX = 9_007_199_254_740_991

SCHEMA_NUMBER  = json.dumps({"fields": [{"name": "VALUE", "type": "number"}]})
SCHEMA_INTEGER = json.dumps({"fields": [{"name": "VALUE", "type": "integer"}]})
SCHEMA_FLOAT   = json.dumps({"fields": [{"name": "VALUE", "type": "float"}]})
SCHEMA_STRING  = json.dumps({"fields": [{"name": "VALUE", "type": "string"}]})
SCHEMA_MIXED   = json.dumps({
    "fields": [
        {"name": "CODE",   "type": "number"},
        {"name": "NAME",   "type": "string"},
        {"name": "AMOUNT", "type": "number"},
    ]
})


def _mock_response(csv_text):
    """Return a mock requests.Response that streams the given CSV text line by line."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    lines = [line.encode('utf-8') for line in csv_text.splitlines()]
    mock_resp.iter_lines.return_value = iter(lines)
    return mock_resp


# ── no-op / short-circuit cases ──────────────────────────────────────────────

def test_returns_empty_when_href_is_none():
    result = _sample_csv_for_precision_risk(None, SCHEMA_NUMBER)
    assert result == []


def test_returns_empty_when_schema_is_empty():
    result = _sample_csv_for_precision_risk("http://example.com/file.csv", {})
    assert result == []


def test_short_circuits_before_download_when_no_numeric_fields():
    """When schema has no numeric fields the helper must not make a network call."""
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_STRING
        )
    assert result == []
    mock_get.assert_not_called()


def test_returns_empty_when_values_are_small():
    csv_text = "VALUE\n123\n456\n789"
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_text)
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_NUMBER
        )
    assert result == []


# ── detection cases ───────────────────────────────────────────────────────────

def test_detects_large_integer_in_number_typed_field():
    large = JS_MAX + 1
    csv_text = f"VALUE\n{large}\n123"
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_text)
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_NUMBER
        )
    assert "VALUE" in result


def test_detects_large_integer_in_integer_typed_field():
    """Fields typed as 'integer' in the schema must also be checked."""
    large = JS_MAX + 1
    csv_text = f"VALUE\n{large}"
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_text)
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_INTEGER
        )
    assert "VALUE" in result


def test_detects_large_value_in_float_typed_field():
    """Fields typed as 'float' in the schema must also be checked."""
    large = float(JS_MAX + 1000)
    csv_text = f"VALUE\n{large}"
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_text)
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_FLOAT
        )
    assert "VALUE" in result


def test_detects_field_with_no_identifier_keyword_in_name():
    """Option B key behaviour: catches any column name, not just CODE/ID/SNOMED."""
    schema = json.dumps({"fields": [{"name": "MEASUREMENT", "type": "number"}]})
    large = JS_MAX + 1
    csv_text = f"MEASUREMENT\n{large}"
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_text)
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", schema
        )
    assert "MEASUREMENT" in result


def test_ignores_large_value_in_string_typed_field():
    """A string-typed field containing a large number must not be flagged."""
    large = JS_MAX + 1
    csv_text = f"VALUE\n{large}"
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_STRING
        )
    assert result == []
    mock_get.assert_not_called()


def test_detects_only_suspect_columns_in_mixed_schema():
    """Only columns whose sample values exceed the threshold should be returned."""
    large = JS_MAX + 1
    csv_text = f"CODE,NAME,AMOUNT\n{large},Alice,50\n123,Bob,75"
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_text)
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_MIXED
        )
    assert "CODE" in result
    assert "AMOUNT" not in result
    assert "NAME" not in result


def test_boundary_value_just_above_max_safe_integer():
    """JS_MAX + 1 must be detected; JS_MAX itself must not."""
    just_above = JS_MAX + 1
    just_at    = JS_MAX

    csv_above = f"VALUE\n{just_above}"
    csv_at    = f"VALUE\n{just_at}"

    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_above)
        assert "VALUE" in _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_NUMBER
        )

    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_at)
        assert _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_NUMBER
        ) == []


def test_accepts_schema_as_dict():
    """Schema can be passed as a plain dict, not just a JSON string."""
    schema_dict = {"fields": [{"name": "VALUE", "type": "number"}]}
    large = JS_MAX + 1
    csv_text = f"VALUE\n{large}"
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = _mock_response(csv_text)
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", schema_dict
        )
    assert "VALUE" in result


# ── resilience cases ──────────────────────────────────────────────────────────

def test_returns_empty_on_download_failure():
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.side_effect = Exception("network error")
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_NUMBER
        )
    assert result == []


def test_returns_empty_on_invalid_utf8_response():
    """A response with invalid UTF-8 bytes should be swallowed, not raised."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines.side_effect = UnicodeDecodeError('utf-8', b'', 0, 1, 'invalid')
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = mock_resp
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_NUMBER
        )
    assert result == []


# ── aircan_submit integration ─────────────────────────────────────────────────

def test_aircan_submit_raises_validation_error_when_suspects_found():
    """aircan_submit must raise ValidationError when suspect fields are found."""
    resource_json = {
        'url': 'http://example.com/file.csv',
        'url_type': 'upload',
        'schema': json.dumps({'fields': [{'name': 'SNOMED_CODE', 'type': 'number'}]}),
        'name': 'test-resource',
        'id': 'abc123',
        'package_id': 'pkg123',
    }
    data_dict = {
        'resource_json': resource_json,
        'package_name': 'test-dataset',
        'pacakge_name': 'test-dataset',
        'organization_name': 'test-org',
        'resource_hash': 'abc',
    }

    with patch(
        'ckanext.aircan_connector.logic.action._sample_csv_for_precision_risk',
        return_value=['SNOMED_CODE'],
    ) as mock_check, patch(
        'ckanext.aircan_connector.logic.action.ValidationError',
        ValidationError,
    ), patch(
        'ckanext.aircan_connector.logic.action.check_access'
    ), patch(
        'ckanext.aircan_connector.logic.action.get_action',
        return_value=MagicMock(return_value={'href': 'http://example.com/file.csv'}),
    ), patch(
        'ckanext.aircan_connector.logic.action.jobs.enqueue'
    ) as mock_enqueue, patch(
        'ckanext.aircan_connector.logic.action._get_editor_user_email',
        return_value='editor@example.com',
    ), patch(
        'ckanext.aircan_connector.logic.action.request'
    ):
        from ckanext.aircan_connector.logic.action import aircan_submit
        with pytest.raises(ValidationError) as exc_info:
            aircan_submit({'ignore_auth': True}, data_dict)

    mock_check.assert_called_once()
    mock_enqueue.assert_not_called()
    assert 'SNOMED_CODE' in str(exc_info.value)


def test_aircan_submit_enqueues_job_when_no_suspects():
    """aircan_submit must enqueue the job normally when no suspects are found."""
    resource_json = {
        'url': 'http://example.com/file.csv',
        'url_type': 'upload',
        'schema': '{}',
        'name': 'test-resource',
        'id': 'abc123',
        'package_id': 'pkg123',
    }
    data_dict = {
        'resource_json': resource_json,
        'package_name': 'test-dataset',
        'pacakge_name': 'test-dataset',
        'organization_name': 'test-org',
        'resource_hash': 'abc',
    }

    with patch(
        'ckanext.aircan_connector.logic.action._sample_csv_for_precision_risk',
        return_value=[],
    ), patch(
        'ckanext.aircan_connector.logic.action.check_access'
    ), patch(
        'ckanext.aircan_connector.logic.action.get_action',
        return_value=MagicMock(return_value={'href': 'http://example.com/file.csv'}),
    ), patch(
        'ckanext.aircan_connector.logic.action.jobs.enqueue'
    ) as mock_enqueue, patch(
        'ckanext.aircan_connector.logic.action._get_editor_user_email',
        return_value='editor@example.com',
    ), patch(
        'ckanext.aircan_connector.logic.action.request'
    ):
        from ckanext.aircan_connector.logic.action import aircan_submit
        aircan_submit({'ignore_auth': True}, data_dict)

    mock_enqueue.assert_called_once()
