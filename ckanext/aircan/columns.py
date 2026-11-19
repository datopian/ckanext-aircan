"""Column-set rule for append/upsert, checked before a resource is saved.

Append and upsert load into an existing table, so the file must carry exactly
the table's columns (order ignored). Only "replace" or `datastore_create` may
change the column set. The edit form already enforces this by reading the new
file's header; this module lets `resource_update` / `resource_patch` enforce the
same rule for API callers.

Kept free of CKAN imports so it can be tested on its own; the plugin passes the
few config values it needs.
"""

import csv
import io
import ipaddress
import json
import logging
import re
import socket
from urllib.parse import unquote, urlparse

import requests

log = logging.getLogger(__name__)

# Pipeline-managed columns; the stored schema normally omits them and a file
# may or may not carry them.
SYSTEM_COLUMNS = frozenset({"_id", "_updated_at"})

# Enough for any realistic header row or first JSON record. Larger than that
# is treated as unreadable and falls back to the schema comparison.
HEAD_BYTES = 256 * 1024
# A Parquet footer holds the schema; it sits at the end of the file.
PARQUET_TAIL_BYTES = 256 * 1024
FETCH_TIMEOUT = (5, 15)
PRESIGN_SECONDS = 300

_FORMAT_ALIASES = {
    "text/csv": "csv",
    "application/csv": "csv",
    "text/tsv": "tsv",
    "text/tab-separated-values": "tsv",
    "application/json": "json",
    "application/x-ndjson": "ndjson",
    "application/ndjson": "ndjson",
    "application/jsonl": "jsonl",
    "application/x-jsonlines": "jsonl",
    "application/parquet": "parquet",
    "application/x-parquet": "parquet",
    "application/vnd.apache.parquet": "parquet",
}

# Same two URL shapes the frontend recognises: an object URL straight from the
# storage bucket, and the download URL CKAN rebuilds for a stored upload.
_RAW_OBJECT = re.compile(r"/(?:[^/]+/)?[^/]+/resources/([^/]+)/([^/]+)$")
_CKAN_DOWNLOAD = re.compile(r"/dataset/[^/]+/resource/([^/]+)/download/([^/]+)$")


def normalize_format(fmt, url=None):
    """Lower-case format name, from the declared format or the URL extension."""
    value = (fmt or "").strip().lower().lstrip(".")
    value = _FORMAT_ALIASES.get(value, value)
    if value:
        return value
    path = urlparse(url or "").path
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _FORMAT_ALIASES.get(ext, ext)


def compare_columns(table_columns, file_columns):
    """Return (new, missing): file columns the table lacks, table columns the
    file lacks. Names are trimmed; system columns are ignored on both sides."""

    def clean(names):
        return {
            str(n).strip()
            for n in names
            if n is not None and str(n).strip() and str(n).strip() not in SYSTEM_COLUMNS
        }

    table = clean(table_columns)
    source = clean(file_columns)
    return sorted(source - table), sorted(table - source)


def mismatch_message(new, missing):
    parts = []
    if new:
        parts.append("column(s) not in the table: " + ", ".join(new))
    if missing:
        parts.append("column(s) missing from the file: " + ", ".join(missing))
    return (
        "The file's columns do not match the table ("
        + "; ".join(parts)
        + "). Append and upsert cannot add or drop columns. Use the 'replace' "
        "mode to refresh the whole schema, or create new columns with "
        "datastore_create first."
    )


# --- reading a header -------------------------------------------------------


def _decode(head):
    return head.decode("utf-8-sig", errors="replace")


def _delimited_columns(head, delimiter):
    text = _decode(head)
    for row in csv.reader(io.StringIO(text), delimiter=delimiter):
        if any(cell.strip() for cell in row):
            return [cell.strip() for cell in row if cell.strip()]
    return None


def _json_columns(head, fmt):
    text = _decode(head).lstrip()
    if fmt in ("ndjson", "jsonl"):
        line = next((ln for ln in text.splitlines() if ln.strip()), "")
        first = json.loads(line)
    else:
        if not text.startswith("["):
            return None
        # raw_decode reads one value, so a head cut off after the first record
        # still parses.
        decoder = json.JSONDecoder()
        idx = 1
        while idx < len(text) and text[idx].isspace():
            idx += 1
        first, _ = decoder.raw_decode(text, idx)
    if not isinstance(first, dict):
        return None
    return list(first.keys())


def _parquet_columns(tail):
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return None
    return list(pq.read_metadata(io.BytesIO(tail)).schema.to_arrow_schema().names)


def columns_from_bytes(data, fmt):
    """Column names from the start of a CSV/TSV/JSON/NDJSON file, or the end of
    a Parquet file. None when the format is unsupported or the bytes do not hold
    a readable header."""
    try:
        if fmt == "csv":
            return _delimited_columns(data, ",")
        if fmt == "tsv":
            return _delimited_columns(data, "\t")
        if fmt in ("json", "ndjson", "jsonl"):
            return _json_columns(data, fmt)
        if fmt == "parquet":
            return _parquet_columns(data)
    except Exception:
        log.warning("Could not read columns from %s data", fmt, exc_info=True)
    return None


# --- fetching the bytes -----------------------------------------------------


def _upload_stream(upload):
    """Readable, seekable stream of a multipart upload, or None."""
    stream = getattr(upload, "stream", None) or getattr(upload, "file", None) or upload
    if hasattr(stream, "read") and hasattr(stream, "seek"):
        return stream
    return None


def _read_upload(upload, fmt):
    stream = _upload_stream(upload)
    if stream is None:
        return None
    position = stream.tell() if hasattr(stream, "tell") else 0
    try:
        if fmt == "parquet":
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - PARQUET_TAIL_BYTES))
            return stream.read()
        stream.seek(0)
        return stream.read(HEAD_BYTES)
    finally:
        # CKAN stores the file after this hook, so leave it as we found it.
        stream.seek(position)


def _object_key(url, storage_path):
    path = unquote(urlparse(url).path)
    match = _CKAN_DOWNLOAD.search(path) or _RAW_OBJECT.search(path)
    if not match:
        return None
    resource_id, filename = match.group(1), match.group(2)
    prefix = f"{storage_path.strip('/')}/" if storage_path else ""
    return f"{prefix}resources/{resource_id}/{filename}"


def _presigned_url(url, s3):
    """Short-lived signed URL for an upload kept in the private bucket, or None
    when the URL is not one of ours or storage is not configured."""
    if not s3 or not s3.get("bucket") or not s3.get("access_key"):
        return None
    key = _object_key(url, s3.get("storage_path"))
    if key is None:
        return None
    import boto3
    from botocore.client import Config

    client = boto3.client(
        "s3",
        endpoint_url=s3.get("host_name") or None,
        aws_access_key_id=s3["access_key"],
        aws_secret_access_key=s3["secret_key"],
        region_name=s3.get("region_name") or "auto",
        config=Config(signature_version=s3.get("signature_version") or "s3v4"),
    )
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": s3["bucket"], "Key": key},
        ExpiresIn=PRESIGN_SECONDS,
    )


def _is_public_url(url):
    """True only for http(s) URLs whose host resolves to public addresses.

    The URL is chosen by whoever edits the resource and fetched from inside the
    cluster, and a mismatch error quotes the parsed header, so internal
    addresses (metadata server, cluster services) must never be fetched.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except OSError:
        return False
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            return False
    return True


def _http_bytes(url, fmt, trusted=False):
    if not trusted and not _is_public_url(url):
        raise ValueError("refusing to fetch a non-public address")
    if fmt == "parquet":
        headers = {"Range": f"bytes=-{PARQUET_TAIL_BYTES}"}
    else:
        headers = {"Range": f"bytes=0-{HEAD_BYTES - 1}"}
    with requests.get(
        url,
        headers=headers,
        stream=True,
        timeout=FETCH_TIMEOUT,
        allow_redirects=False,
    ) as resp:
        resp.raise_for_status()
        # A server that ignores Range sends the whole file; the start is still
        # a valid header, but a Parquet footer is at the end, so give up there.
        if fmt == "parquet" and resp.status_code != 206:
            return None
        data = b""
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            data += chunk
            if fmt != "parquet" and len(data) >= HEAD_BYTES:
                break
        return data


def read_source_columns(url, upload, fmt, s3=None):
    """Column names of the file a resource update points at, or None when they
    cannot be read (unsupported format, no access, timeout, unparseable).

    Never raises: the caller falls back to comparing schemas.
    """
    try:
        if fmt not in ("csv", "tsv", "json", "ndjson", "jsonl", "parquet"):
            return None
        if upload:
            data = _read_upload(upload, fmt)
        elif url:
            signed = _presigned_url(url, s3)
            data = _http_bytes(signed or url, fmt, trusted=bool(signed))
        else:
            return None
        if not data:
            return None
        return columns_from_bytes(data, fmt)
    except Exception:
        log.warning("Could not read the file's columns for %s", url, exc_info=True)
        return None
