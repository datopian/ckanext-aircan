## ckanext-aircan

A CKAN extension for integrating AirCan into CKAN for notifying(triggering) the Airflow DAG about the data to be uploaded to DataStore.

TODO Clarify this readme file

### Prerequisites

You have a CKAN instance up and running - [instructions](https://github.com/okfn/docker-ckan#development-mode).

### Installation
1. This extension need to be installed manually via cloning the desired commit into the docker-ckan/src directory:
`git@github.com:datopian/ckanext-aircan.git`

2. Enable the extension in CKAN by adding in your`.env` file an `aircan_connector` to `CKAN__PLUGINS` list. Make sure to disable `datapusher` in case you have it.

### Local Airflow instance
 
* In your`.env` file add  `CKAN__AIRFLOW__URL` according to [Apache AirFlow REST API Reference](https://airflow.apache.org/docs/stable/rest-api-ref#post--api-experimental-dags--DAG_ID--dag_runs). If you are running CKAN in a Docker container, make sure to specify the Airflow URL with `host.docker.internal` instead of `localhost`: `CKAN__AIRFLOW__URL=http://host.docker.internal:8080/api/experimental/dags/ckan_api_load_multiple_steps/dag_runs`. Also notice Airflow requires, by default, the endpoint `api/experimental/dags/DAG_ID` for API access.

* Also in your `.env` file, specify a temporary directory for files: `CKAN__AIRFLOW__STORAGE_PATH=/tmp/` and `CKAN__AIRFLOW__CLOUD=local`. 

* Access your CKAN and upload of modify a resource. You must select a resource type. At this time, we support `CSV` only. 


### Airflow instance on Google Composer

Assuming you already have a Google Cloud Composer properly set up, it is possible to trigger a DAG on GoogleCloud Platform following these steps:

1. Download your credentials file (a JSON file) from Google Cloud Platform. Convert it to a single-line JSON.

2. Set up the following environment variables on your `.env` file:

```bash
CKAN__AIRFLOW__CLOUD=GCP # this line activates the integration with GCP
CKAN__AIRFLOW__CLOUD__PROJECT_ID=YOUR_PROJECT_ID_ON_COMPOSER
CKAN__AIRFLOW__CLOUD__LOCATION=us-east1_OR_OTHER
CKAN__AIRFLOW__CLOUD__COMPOSER_ENVIRONMENT=NAME_OF_COMPOSER_ENVIRONMENT
CKAN__AIRFLOW__CLOUD__WEB_UI_ID=ID_FROM_AIRFLOW_UI_ON_COMPOSER
CKAN__AIRFLOW__CLOUD__GOOGLE_APPLICATION_CREDENTIALS={ YOUR SINGLE LINE CREDENTIALS JSON FILE }
``` 

Here, we are using the DAG `ckan_api_load_gcp` for uploading a resource to CKAN using an Airflow instance on Google Cloud.

3. Make a request to `http://YOUR-CKAN:5000/api/3/action/aircan_submit?dag_name=DAG_NAME`, specifying your `CKAN_API_KEY` on the header and send the following information on the body of the request, replacing the values accordingly:

```json
{
  "package_id": "YOUR_PACKAGE_ID",
  "url":  "http://url.for.your.resource.com",
  "description": "This is the best resource ever!" ,
  "schema": {
    "fields":  [
          {
            "name": "FID",
            "type": "int",
            "format": "default"
          },
          {
            "name": "another-field",
            "type": "float",
            "format": "default"
          }
        ]
  }
}
```

Replace `dag_name` with the DAG you want to invoke, for example, `http://YOUR-CKAN:5000/api/3/action/aircan_submit?dag_name=ckan_api_load_gcp`. This will trigger the DAG `ckan_api_load_gcp`.

The endpoint `http://YOUR-CKAN:5000/api/3/action/resource_create` produces the same effect of `http://YOUR-CKAN:5000/api/3/action/aircan_submit?dag_name=DAG_NAME`. Make sure you set up an extra variable on your `.env` file specifying the DAG you want to trigger:

```
# .env
# all other variables
CKAN__AIRFLOW__CLOUD__DAG_NAME=DAG_YOU_WANT_TO_TRIGGER
```

## Retrieving a DAG status

After submitting a POST request to `http://YOUR-CKAN:5000/api/3/action/aircan_submit?dag_name=ckan_api_load_gcp`, you should get a response that contains the `execution date` of the triggered DAG. For example:

```json
{

    "help": "http://YOUR-CKAN:5000/api/3/action/help_show?name=aircan_submit",
    "success": true,
    "result": {
        "aircan_status": {
            "message": "Created <DagRun ckan_api_load_gcp @ 2020-08-12 00:56:59+00:00: manual__2020-08-12T00:56:59+00:00, externally triggered: True>"
        }
    }
}
```

You can then hit `http://YOUR-CKAN:5000/api/3/action/dag_status?dag_name=ckan_api_load_gcp` for a list of the most recent runs; or alternatively you can specify the execution date (the same you obtain on the response after triggering a DAG): `http://YOUR-CKAN:5000/api/3/action/dag_status?dag_name=ckan_api_load_gcp&execution_date=2020-07-09T14:29:54`. Note you must specify two parameters: `dag_name` and `execution_date`.

Then your response (assuming you specify an execution date) should be similar to:

```json
{
    "help": "http://ckan:5000/api/3/action/help_show?name=dag_status",
    "success": true,
    "result": {
        "state": "failed"
    }
}
```

Note: If you are using GCP, make sure to enable the following services for your Composer Project:
* Cloud Logging API
* Stackdriver Monitoring API

Also, make sure your service account key (which you can creating by accessing the IAM panel -> Service accounts) must have permissions to read logs and objects from buckets. Enable the following options for the service account (assuming you'll have a setup with StackDriver and Google Cloud Composer):
* Composer Administrator
* Environment and Storage Object Administrator
* Logging Admin
* Logs Bucket Writer
* Private Logs Viewer


# Tests with Cypress
Test the aircan-connector with cypress.

## Installation

`npm install`


## Running

Opens up the cypress app and you can choose the specs to run.

`npm test`


