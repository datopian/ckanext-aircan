# Pure unit tests for the aircan_error_list parameter and payload helpers.
# CKAN is stubbed by importing test_precision_check, which installs the stubs.
import datetime

import pytest

from ckanext.aircan_connector.tests import test_precision_check  # noqa: F401  (installs stubs)
from ckanext.aircan_connector.logic import action  # noqa: E402
from ckanext.aircan_connector.logic.action import (  # noqa: E402
    _as_list,
    _error_message,
    _last_log_message,
    _load_json,
    _parse_limit,
    _parse_since,
)

# action.py reaches ValidationError through the stubbed ``ckan`` package, so it
# is a MagicMock there; swap in a real exception class the helpers can raise.
ValidationError = type('ValidationError', (Exception,), {})


@pytest.fixture(autouse=True)
def _real_validation_error(monkeypatch):
    monkeypatch.setattr(action, 'ValidationError', ValidationError)


@pytest.mark.parametrize('value, expected', [
    (None, []),
    ('', []),
    ('org-a', ['org-a']),
    ('org-a, org-b,', ['org-a', 'org-b']),
    (['org-a', ' org-b ', ''], ['org-a', 'org-b']),
])
def test_as_list(value, expected):
    assert _as_list(value) == expected


def test_parse_since_date_is_midnight():
    assert _parse_since('2026-11-01') == datetime.datetime(2026, 11, 1)


def test_parse_since_converts_aware_values_to_naive_utc():
    assert _parse_since('2026-11-01T09:00:00Z') == datetime.datetime(2026, 11, 1, 9)
    assert _parse_since('2026-11-01T10:00:00+01:00') == datetime.datetime(2026, 11, 1, 9)


def test_parse_since_empty_and_invalid():
    assert _parse_since(None) is None
    assert _parse_since('') is None
    with pytest.raises(ValidationError):
        _parse_since('yesterday')


def test_parse_limit():
    assert _parse_limit(None, 100, 1000, 'limit') == 100
    assert _parse_limit('25', 100, 1000, 'limit') == 25
    assert _parse_limit(5000, 100, 1000, 'limit') == 1000
    for bad in ('x', -1):
        with pytest.raises(ValidationError):
            _parse_limit(bad, 100, 1000, 'limit')


def test_load_json_falls_back_on_bad_or_null_input():
    assert _load_json('{"a": 1}', {}) == {'a': 1}
    assert _load_json('null', {}) == {}
    assert _load_json('not json', {}) == {}
    assert _load_json(None, {}) == {}


def test_error_and_log_messages():
    assert _error_message({'message': 'Failed to push'}) == 'Failed to push'
    assert _error_message({}) is None
    assert _error_message('plain text') == 'plain text'
    assert _last_log_message({'logs': [{'message': 'a'}, {'message': 'b'}]}) == 'b'
    assert _last_log_message({'logs': []}) is None
    assert _last_log_message('not a dict') is None
