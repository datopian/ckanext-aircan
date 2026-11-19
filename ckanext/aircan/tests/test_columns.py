"""Tests for columns.py (no CKAN needed)."""

import io
from unittest import mock

import pytest

from ckanext.aircan import columns


class TestCompare:
    def test_equal_sets_in_any_order(self):
        assert columns.compare_columns(["a", "b"], ["b", "a"]) == ([], [])

    def test_new_and_missing(self):
        assert columns.compare_columns(["a", "b"], ["a", "c"]) == (["c"], ["b"])

    def test_names_are_trimmed(self):
        assert columns.compare_columns(["a ", "b"], [" a", "b"]) == ([], [])

    def test_system_columns_ignored_both_sides(self):
        assert columns.compare_columns(["_id", "a"], ["a", "_updated_at"]) == ([], [])

    def test_message_names_the_columns(self):
        message = columns.mismatch_message(["c"], ["b"])
        assert "not in the table: c" in message
        assert "missing from the file: b" in message
        assert "datastore_create" in message


class TestNormalizeFormat:
    @pytest.mark.parametrize("fmt,url,expected", [
        ("CSV", None, "csv"),
        (".tsv", None, "tsv"),
        ("text/csv", None, "csv"),
        ("application/vnd.apache.parquet", None, "parquet"),
        ("", "https://x.test/a/b/data.JSON", "json"),
        (None, "https://x.test/data", ""),
    ])
    def test_values(self, fmt, url, expected):
        assert columns.normalize_format(fmt, url) == expected


class TestColumnsFromBytes:
    def test_csv_header_with_bom_and_blank_first_line(self):
        data = "﻿\nDate,CP, MW \n1,2,3\n".encode("utf-8")
        assert columns.columns_from_bytes(data, "csv") == ["Date", "CP", "MW"]

    def test_tsv(self):
        assert columns.columns_from_bytes(b"a\tb\n1\t2\n", "tsv") == ["a", "b"]

    def test_quoted_csv_header(self):
        assert columns.columns_from_bytes(b'"a,1",b\n1,2\n', "csv") == ["a,1", "b"]

    def test_json_array_first_record(self):
        data = b'[ {"a": 1, "b": 2}, {"a": 3'  # head cut off mid second record
        assert columns.columns_from_bytes(data, "json") == ["a", "b"]

    def test_json_not_an_array_is_unreadable(self):
        assert columns.columns_from_bytes(b'{"a": 1}', "json") is None

    def test_ndjson_first_nonblank_line(self):
        data = b'\n{"a": 1, "b": 2}\n{"a": 3}\n'
        assert columns.columns_from_bytes(data, "ndjson") == ["a", "b"]

    def test_garbage_json_is_unreadable(self):
        assert columns.columns_from_bytes(b"[not json", "json") is None

    def test_unknown_format_is_unreadable(self):
        assert columns.columns_from_bytes(b"a,b", "xlsx") is None


class TestParquet:
    def test_reads_schema_from_footer(self):
        pa = pytest.importorskip("pyarrow")
        pq = pytest.importorskip("pyarrow.parquet")
        buf = io.BytesIO()
        pq.write_table(pa.table({"a": [1], "b": ["x"]}), buf)
        assert columns.columns_from_bytes(buf.getvalue(), "parquet") == ["a", "b"]


class TestReadSourceColumns:
    def test_upload_is_read_and_rewound(self):
        stream = io.BytesIO(b"a,b\n1,2\n")
        upload = mock.Mock(stream=stream)
        assert columns.read_source_columns(None, upload, "csv") == ["a", "b"]
        assert stream.tell() == 0

    def test_unsupported_format_returns_none(self):
        assert columns.read_source_columns("https://x.test/f.xlsx", None, "xlsx") is None

    def test_fetch_error_returns_none(self):
        with mock.patch.object(columns, "_is_public_url", return_value=True), \
                mock.patch.object(columns.requests, "get", side_effect=OSError("boom")):
            assert columns.read_source_columns("https://x.test/f.csv", None, "csv") is None

    def test_http_range_fetch(self):
        resp = mock.MagicMock(status_code=206)
        resp.__enter__.return_value = resp
        resp.iter_content.return_value = [b"a,b\n1,2\n"]
        with mock.patch.object(columns, "_is_public_url", return_value=True), \
                mock.patch.object(columns.requests, "get", return_value=resp) as get:
            assert columns.read_source_columns("https://x.test/f.csv", None, "csv") == ["a", "b"]
        assert get.call_args.kwargs["headers"]["Range"].startswith("bytes=0-")
        assert get.call_args.kwargs["allow_redirects"] is False

    def test_parquet_needs_range_support(self):
        resp = mock.MagicMock(status_code=200)
        resp.__enter__.return_value = resp
        with mock.patch.object(columns, "_is_public_url", return_value=True), \
                mock.patch.object(columns.requests, "get", return_value=resp):
            assert columns.read_source_columns("https://x.test/f.parquet", None, "parquet") is None


class TestPublicUrlGuard:
    @pytest.mark.parametrize("url,addr,expected", [
        ("https://data.test/f.csv", "93.184.216.34", True),
        ("http://metadata.internal/f.csv", "169.254.169.254", False),
        ("http://localhost/f.csv", "127.0.0.1", False),
        ("http://svc.cluster.local/f.csv", "10.0.0.7", False),
        ("ftp://data.test/f.csv", "93.184.216.34", False),
    ])
    def test_only_public_http_hosts(self, url, addr, expected):
        with mock.patch.object(columns.socket, "getaddrinfo",
                               return_value=[(2, 1, 6, "", (addr, 443))]):
            assert columns._is_public_url(url) is expected

    def test_unresolvable_host_is_refused(self):
        with mock.patch.object(columns.socket, "getaddrinfo", side_effect=OSError):
            assert columns._is_public_url("https://nope.test/f.csv") is False

    def test_internal_url_is_never_fetched(self):
        with mock.patch.object(columns.socket, "getaddrinfo",
                               return_value=[(2, 1, 6, "", ("10.0.0.7", 80))]), \
                mock.patch.object(columns.requests, "get") as get:
            assert columns.read_source_columns("http://svc/f.csv", None, "csv") is None
        get.assert_not_called()


class TestPresign:
    S3 = {"bucket": "b", "access_key": "k", "secret_key": "s",
          "host_name": "https://r2.test", "storage_path": "neso-dev",
          "region_name": "auto", "signature_version": "s3v4"}

    @pytest.mark.parametrize("url", [
        "https://site.test/dataset/ds/resource/rid1/download/my%20file.csv",
        "https://r2.test/b/neso-dev/resources/rid1/my%20file.csv",
    ])
    def test_key_from_both_url_shapes(self, url):
        assert columns._object_key(url, "neso-dev") == "neso-dev/resources/rid1/my file.csv"

    def test_foreign_url_is_not_presigned(self):
        assert columns._presigned_url("https://other.test/f.csv", self.S3) is None

    def test_without_storage_config_is_not_presigned(self):
        url = "https://site.test/dataset/ds/resource/rid1/download/f.csv"
        assert columns._presigned_url(url, {}) is None

    def test_presigned_fetch_skips_the_public_check(self):
        url = "https://site.test/dataset/ds/resource/rid1/download/f.csv"
        resp = mock.MagicMock(status_code=206)
        resp.__enter__.return_value = resp
        resp.iter_content.return_value = [b"a,b\n"]
        with mock.patch.object(columns, "_presigned_url", return_value="https://r2.test/signed"), \
                mock.patch.object(columns, "_is_public_url") as public, \
                mock.patch.object(columns.requests, "get", return_value=resp):
            assert columns.read_source_columns(url, None, "csv", self.S3) == ["a", "b"]
        public.assert_not_called()
