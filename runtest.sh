#!/bin/bash -x

nosetests -vv -s --ckan --with-pylons=test.ini ckanext/aircan_connector/tests/test_plugin.py
