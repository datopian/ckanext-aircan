# encoding: utf-8
import os
import requests
from ckan.common import config
import logging
import tempfile
import math
import hashlib
import messytables

log = logging.getLogger(__name__)

SSL_VERIFY = True
if not SSL_VERIFY:
    requests.packages.urllib3.disable_warnings()

CHUNK_SIZE = 16 * 1024  # 16kb
DOWNLOAD_TIMEOUT = 30

def get_file_headers(resource, api_key):

    url = resource.get('url')

    # fetch the resource data
    log.info('Fetching from: {0}'.format(url))
    tmp_file = get_tmp_file(url)
    length = 0

    try:
        headers = {}
        if resource.get('url_type') == 'upload':
            # If this is an uploaded file to CKAN, authenticate the request,
            # otherwise we won't get file from private resources
            headers['Authorization'] = api_key
        log.info("headers: {}".format(headers))
        log.info("SSL_VERIFY: {}".format(SSL_VERIFY))
        response = requests.get(
            url,
            headers=headers,
            timeout=DOWNLOAD_TIMEOUT,
            verify=SSL_VERIFY,
            stream=True,  # just gets the headers for now
        )
        response.raise_for_status()

        # download the file to a tempfile on disk
        for chunk in response.iter_content(CHUNK_SIZE):
            length += len(chunk)
            tmp_file.write(chunk)

        log.info('Downloaded ok - %s', printable_file_size(length))

        tmp_file.seek(0)

        headers_row = get_headers_row(tmp_file.name)
        return headers_row
    except Exception as error:
        tmp_file.close()
        # status code error
        log.error('Fetching resource error: {}'.format(error))
    finally:
        tmp_file.close()

def get_headers_row(csv_filepath, mimetype='text/csv'):
    # use messytables to determine the header row
    extension = os.path.splitext(csv_filepath)[1]
    with open(csv_filepath, 'rb') as f:
        try:
            table_set = messytables.any_tableset(f, mimetype=mimetype,
                                                 extension=extension)
        except Exception as error:
            log.error('messytables error: {}'.format(error))

        if not table_set.tables:
            log.error('Could not detect tabular data in this file')
        row_set = table_set.tables.pop()
        header_offset, headers = messytables.headers_guess(row_set.sample)
        return headers

def get_tmp_file(url):
    filename = url.split('/')[-1].split('#')[0].split('?')[0]
    tmp_file = tempfile.NamedTemporaryFile(suffix=filename)
    return tmp_file

def printable_file_size(size_bytes):
    if size_bytes == 0:
        return '0 bytes'
    size_name = ('bytes', 'KB', 'MB', 'GB', 'TB')
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 1)
    return "%s %s" % (s, size_name[i])


