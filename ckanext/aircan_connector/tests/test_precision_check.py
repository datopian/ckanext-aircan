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
    # google-cloud-logging / google-auth are installed in the container but not
    # necessarily here; action.py reaches them via dag_status_report/gcp_handler.
    'google.cloud.logging', 'google.oauth2', 'google.oauth2.id_token',
    'google.oauth2.service_account', 'google.auth', 'google.auth.transport',
    'google.auth.transport.requests',
]
for _mod in _CKAN_STUBS:
    sys.modules.setdefault(_mod, MagicMock())

# ValidationError must be a real exception class so pytest.raises works.
ValidationError = type('ValidationError', (Exception,), {})
sys.modules['ckan.logic'].ValidationError = ValidationError

from ckanext.aircan_connector.logic.action import (  # noqa: E402
    _sample_csv_for_precision_risk,
    precision_check_fingerprint,
)

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
# [] means "checked, nothing at risk" and callers clear a stored warning on it.
# None means "could not check" and must leave any stored warning alone.

def test_returns_none_when_href_is_none():
    """No file to sample is 'unknown', not 'all clear'."""
    result = _sample_csv_for_precision_risk(None, SCHEMA_NUMBER)
    assert result is None


def test_returns_none_when_schema_is_empty():
    result = _sample_csv_for_precision_risk("http://example.com/file.csv", {})
    assert result is None


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

def test_returns_none_on_download_failure():
    """A failed download must not be mistaken for an all-clear."""
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.side_effect = Exception("network error")
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_NUMBER
        )
    assert result is None


def test_returns_none_on_invalid_utf8_response():
    """A response with invalid UTF-8 bytes should be swallowed, not raised."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines.side_effect = UnicodeDecodeError('utf-8', b'', 0, 1, 'invalid')
    with patch("ckanext.aircan_connector.logic.action.requests.get") as mock_get:
        mock_get.return_value = mock_resp
        result = _sample_csv_for_precision_risk(
            "http://example.com/file.csv", SCHEMA_NUMBER
        )
    assert result is None


def test_returns_empty_list_not_none_when_schema_has_no_numeric_fields():
    """Retyping every risky column to string is a definitive all-clear, so a
    stored warning can be cleared without downloading the file again."""
    result = _sample_csv_for_precision_risk(
        "http://example.com/file.csv", SCHEMA_STRING
    )
    assert result == []
    assert result is not None


# ── cache fingerprint ─────────────────────────────────────────────────────────
# The bug behind "the warning never disappears": the check was cached against the
# file hash alone, so the schema fix it demanded never invalidated the cache.

def test_fingerprint_changes_when_numeric_column_is_retyped_to_string():
    same_file = "hash-unchanged"
    before = precision_check_fingerprint(same_file, SCHEMA_NUMBER)
    after = precision_check_fingerprint(same_file, SCHEMA_STRING)
    assert before != after, "retyping to string must invalidate the cached verdict"


def test_fingerprint_is_stable_for_identical_inputs():
    a = precision_check_fingerprint("h", SCHEMA_MIXED)
    b = precision_check_fingerprint("h", SCHEMA_MIXED)
    assert a == b


def test_fingerprint_changes_when_file_changes():
    assert (precision_check_fingerprint("hash-a", SCHEMA_NUMBER)
            != precision_check_fingerprint("hash-b", SCHEMA_NUMBER))


def test_fingerprint_ignores_non_numeric_column_edits():
    """Renaming or re-describing a text column must not force a re-download."""
    base = json.dumps({"fields": [
        {"name": "CODE", "type": "number"},
        {"name": "NAME", "type": "string", "description": "original"},
    ]})
    edited = json.dumps({"fields": [
        {"name": "CODE", "type": "number"},
        {"name": "NAME", "type": "string", "description": "reworded"},
    ]})
    assert (precision_check_fingerprint("h", base)
            == precision_check_fingerprint("h", edited))


def test_fingerprint_accepts_dict_and_string_schema():
    as_dict = {"fields": [{"name": "VALUE", "type": "number"}]}
    assert (precision_check_fingerprint("h", as_dict)
            == precision_check_fingerprint("h", json.dumps(as_dict)))


# ── aircan_submit integration ─────────────────────────────────────────────────

def _submit(schema, stored_extras=None, sample_return=None, resource_hash='abc'):
    """Drive aircan_submit with everything external stubbed.

    Returns (resource_object, enqueue_mock, sample_mock) so a test can assert on
    the extras the call left behind.
    """
    resource_json = {
        'url': 'http://example.com/file.csv',
        'url_type': 'upload',
        'schema': schema,
        'name': 'test-resource',
        'id': 'abc123',
        'package_id': 'pkg123',
        'hash': resource_hash,
    }
    data_dict = {
        'resource_json': resource_json,
        'package_name': 'test-dataset',
        'pacakge_name': 'test-dataset',
        'organization_name': 'test-org',
        'resource_hash': resource_hash,
    }

    res_obj = MagicMock()
    res_obj.extras = dict(stored_extras or {})
    model = MagicMock()
    model.Resource.get.return_value = res_obj

    with patch(
        'ckanext.aircan_connector.logic.action._sample_csv_for_precision_risk',
        return_value=sample_return,
    ) as mock_sample, patch(
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
        aircan_submit({'ignore_auth': True, 'model': model}, data_dict)

    return res_obj, mock_enqueue, mock_sample


def test_aircan_submit_warns_but_still_enqueues_when_suspects_found():
    """Suspect fields raise a sysadmin-visible warning without blocking ingestion.

    Deliberate: refusing the job would stall the monthly SCMD/PCA pipelines over a
    column-type issue that does not corrupt what BigQuery stores.
    """
    res_obj, mock_enqueue, mock_sample = _submit(
        SCHEMA_MIXED, sample_return=['CODE'],
    )
    mock_sample.assert_called_once()
    mock_enqueue.assert_called_once()
    assert res_obj.extras['precision_warning'] == 'CODE'


def test_aircan_submit_enqueues_job_when_no_suspects():
    """aircan_submit must enqueue the job normally when no suspects are found."""
    _, mock_enqueue, _ = _submit('{}', sample_return=[])
    mock_enqueue.assert_called_once()


def test_aircan_submit_clears_warning_once_the_column_is_retyped():
    """The reported bug: fixing the schema left the warning on screen forever.

    The stored fingerprint is the bare file hash written by the old code, and the
    file itself never changes again -- so this only clears if the schema is part
    of the cache key.
    """
    res_obj, _, mock_sample = _submit(
        SCHEMA_STRING,
        stored_extras={'precision_warning': 'VALUE', 'precision_check_hash': 'abc'},
        sample_return=[],
    )
    # If the schema were not part of the cache key this would never be called.
    mock_sample.assert_called_once()
    assert 'precision_warning' not in res_obj.extras
    assert res_obj.extras['precision_check_hash'] == precision_check_fingerprint(
        'abc', SCHEMA_STRING
    )


def test_aircan_submit_keeps_warning_when_the_check_could_not_run():
    """A download failure must not silently clear a real warning."""
    res_obj, _, _ = _submit(
        SCHEMA_NUMBER,
        stored_extras={'precision_warning': 'VALUE', 'precision_check_hash': 'stale'},
        sample_return=None,
    )
    assert res_obj.extras['precision_warning'] == 'VALUE'
    assert res_obj.extras['precision_check_hash'] == 'stale'


def test_aircan_submit_skips_the_download_when_fingerprint_is_unchanged():
    """Same file and same numeric columns: no re-download on every save."""
    fingerprint = precision_check_fingerprint('abc', SCHEMA_NUMBER)
    _, mock_enqueue, mock_sample = _submit(
        SCHEMA_NUMBER,
        stored_extras={'precision_check_hash': fingerprint},
        sample_return=[],
    )
    mock_sample.assert_not_called()
    mock_enqueue.assert_called_once()


# ── the one-off sweep for warnings already stuck on screen ───────────────────

def _sweep(resources, dry_run=True, resource_id=None):
    """Drive aircan_clear_stale_precision_warnings over fake resource rows."""
    rows = []
    for extras in resources:
        row = MagicMock()
        row.id = extras.pop('_id', 'res-1')
        row.name = extras.pop('_name', 'SCMD_FINAL_202603')
        row.package_id = 'pkg-1'
        row.extras = dict(extras)
        rows.append(row)

    query = MagicMock()
    query.filter.return_value = query
    query.__iter__ = lambda self: iter(rows)
    model = MagicMock()
    model.Session.query.return_value = query

    with patch('ckanext.aircan_connector.logic.action.check_access'), patch(
        'ckanext.aircan_connector.logic.action.asbool', lambda v: bool(v)
    ), patch(
        # the resource_show fallback used when extras carry no schema
        'ckanext.aircan_connector.logic.action.get_action',
        return_value=MagicMock(return_value={}),
    ):
        from ckanext.aircan_connector.logic.action import (
            aircan_clear_stale_precision_warnings,
        )
        data_dict = {'dry_run': dry_run}
        if resource_id:
            data_dict['resource_id'] = resource_id
        result = aircan_clear_stale_precision_warnings(
            {'ignore_auth': True, 'model': model}, data_dict
        )
    return result, rows, model


def test_sweep_reports_the_stuck_warning_without_writing_in_dry_run():
    """Mirrors prod resource 2359dce2: VMP_SNOMED_CODE already retyped to string."""
    result, rows, model = _sweep([{
        'precision_warning': 'VMP_SNOMED_CODE',
        'precision_check_hash': 'be6aa27d',
        'schema': json.dumps({'fields': [
            {'name': 'VMP_SNOMED_CODE', 'type': 'string'},
            {'name': 'UNIT_OF_MEASURE_IDENTIFIER', 'type': 'number'},
        ]}),
    }])
    assert result['stale_count'] == 1
    assert result['cleared_count'] == 0
    assert rows[0].extras['precision_warning'] == 'VMP_SNOMED_CODE'
    model.Session.commit.assert_not_called()


def test_sweep_clears_the_stuck_warning_when_not_a_dry_run():
    result, rows, model = _sweep([{
        'precision_warning': 'VMP_SNOMED_CODE',
        'precision_check_hash': 'be6aa27d',
        'schema': json.dumps({'fields': [{'name': 'VMP_SNOMED_CODE', 'type': 'string'}]}),
    }], dry_run=False)
    assert result['cleared_count'] == 1
    assert 'precision_warning' not in rows[0].extras
    # the stale fingerprint goes too, so the next real ingest recomputes
    assert 'precision_check_hash' not in rows[0].extras
    model.Session.commit.assert_called_once()


def test_sweep_leaves_warnings_whose_column_is_still_numeric():
    result, rows, model = _sweep([{
        'precision_warning': 'SNOMED_CODE',
        'schema': json.dumps({'fields': [{'name': 'SNOMED_CODE', 'type': 'integer'}]}),
    }], dry_run=False)
    assert result['stale_count'] == 0
    assert result['still_valid_count'] == 1
    assert rows[0].extras['precision_warning'] == 'SNOMED_CODE'
    model.Session.commit.assert_not_called()


def test_sweep_keeps_a_warning_when_only_some_columns_were_fixed():
    result, _, _ = _sweep([{
        'precision_warning': 'A_CODE, B_CODE',
        'schema': json.dumps({'fields': [
            {'name': 'A_CODE', 'type': 'string'},
            {'name': 'B_CODE', 'type': 'number'},
        ]}),
    }], dry_run=False)
    assert result['stale_count'] == 0
    assert result['still_valid'][0]['still_numeric'] == ['B_CODE']


def test_sweep_refuses_to_judge_a_warning_when_the_schema_is_unreadable():
    """Guard against the dangerous failure mode: with no readable schema every
    warning looks resolved, so a naive sweep would clear all of them."""
    result, rows, model = _sweep([{
        'precision_warning': 'SNOMED_CODE',
        # no 'schema' key at all, and the resource_show fallback returns {}
    }], dry_run=False)
    assert result['unreadable_count'] == 1
    assert result['stale_count'] == 0
    assert rows[0].extras['precision_warning'] == 'SNOMED_CODE'
    model.Session.commit.assert_not_called()


def test_sweep_survives_an_unparseable_schema():
    result, rows, _ = _sweep([{
        'precision_warning': 'SNOMED_CODE',
        'schema': 'not json at all {{{',
    }], dry_run=False)
    assert result['unreadable_count'] == 1
    assert rows[0].extras['precision_warning'] == 'SNOMED_CODE'


def test_sweep_ignores_resources_without_a_warning():
    result, _, _ = _sweep([
        {'schema': json.dumps({'fields': [{'name': 'X', 'type': 'number'}]})},
        {'precision_warning': '', 'schema': '{}'},
    ], dry_run=False)
    assert result['stale_count'] == 0
    assert result['still_valid_count'] == 0
