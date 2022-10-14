# ckanext-aircan

A CKAN extension for integrating the [AirFlow-based AirCan Data Factory into CKAN][aircan]. Specifically, this extension provides:

[aircan]: https://tech.datopian.com/flows/#ckan-v3

* New APIs in CKAN for triggering and monitoring workflows (DAGs) in AirFlow
* Hooking key events in CKAN into the AirFlow instance. Specifically, resource creation and update trigger DAGs in AirFlow to load resource data into the DataStore. See https://tech.datopian.com/load/#ckan-v3

## Installation

### Basic Setup

There are two potential cases:

* Docker for Deployment: Install this extension in the usual way, see https://tech.datopian.com/ckan/install-extension.html
* Local Development Install manually via cloning the desired commit into the docker-ckan/src directory: `git@github.com:datopian/ckanext-aircan.git`

### Configuration

* Enable the extension in CKAN by adding the plugin `aircan_connector` to `CKAN__PLUGINS` list in your`.env`. Make sure to disable `datapusher` and `xloader` if you have them there as AirCan replaces them.
* Add details of the AirFlow instance -- details below for Local case and Cloud case

### Local Airflow instance
 
* In your`.env` file add  `CKAN__AIRFLOW__URL` according to [Apache AirFlow REST API Reference](https://airflow.apache.org/docs/stable/rest-api-ref#post--api-experimental-dags--DAG_ID--dag_runs). If you are running CKAN in a Docker container, make sure to specify the Airflow URL with `host.docker.internal` instead of `localhost`: `CKAN__AIRFLOW__URL=http://host.docker.internal:8080/api/experimental/dags/ckan_api_load_multiple_steps/dag_runs`. Also notice Airflow requires, by default, the endpoint `api/experimental/dags/DAG_ID` for API access.
* Add Airflow admin username and password for authorization:
  `CKAN__AIRFLOW__USERNAME=airflow_amin_username` and `CKAN__AIRFLOW__PASSWORD=airflow_admin_password`
* Also in your `.env` file, specify a temporary directory for files: `CKAN__AIRFLOW__STORAGE_PATH=/tmp/` and `CKAN__AIRFLOW__CLOUD=local`. 

### Airflow instance on Google Composer

Assuming you already have a Google Cloud Composer properly set up, it is possible to trigger a DAG on GoogleCloud Platform following these steps:

* Download your credentials file (a JSON file) from Google Cloud Platform. Convert it to a single-line JSON.
* Set up the following environment variables on your `.env` file:

  ```bash
  CKAN__AIRFLOW__CLOUD=GCP # this line activates the integration with GCP
  CKAN__AIRFLOW__CLOUD__PROJECT_ID=YOUR_PROJECT_ID_ON_COMPOSER
  CKAN__AIRFLOW__CLOUD__LOCATION=us-east1_OR_OTHER
  CKAN__AIRFLOW__CLOUD__COMPOSER_ENVIRONMENT=NAME_OF_COMPOSER_ENVIRONMENT
  CKAN__AIRFLOW__CLOUD__WEB_UI_ID=ID_FROM_AIRFLOW_UI_ON_COMPOSER
  CKAN__AIRFLOW__CLOUD__GOOGLE_APPLICATION_CREDENTIALS={ YOUR SINGLE LINE CREDENTIALS JSON FILE }
  ``` 

## Getting Started

### Triggering a Workflow (DAG)

Make a request to `http://YOUR-CKAN:5000/api/3/action/aircan_submit?dag_name=DAG_NAME`, specifying your `CKAN_API_KEY` on the header and send the following information on the body of the request, replacing the values accordingly:

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

NB: the DAG `ckan_api_load_gcp` is designed for Google Cloud Composer AirFlow instance and will load a resource into the DataStore.

The endpoint `http://YOUR-CKAN:5000/api/3/action/resource_create` produces the same effect of `http://YOUR-CKAN:5000/api/3/action/aircan_submit?dag_name=DAG_NAME`. Make sure you set up an extra variable on your `.env` file specifying the DAG you want to trigger:

```
# .env
# all other variables
CKAN__AIRFLOW__CLOUD__DAG_NAME=DAG_YOU_WANT_TO_TRIGGER
```
## For CKAN Datastore data loader dag

* Add `ckanext.aircan.load_with_postgres_copy=True` env to load with postgres copy loader. By default it loads with datastore API. 
* Add `ckanext.aircan.datastore_chunk_insert_rows_size=300` env variable to configure number of records to send a request to datastore. Default 250 rows.
* addd `append_or_update_datastore = true` if new data schema matches with old schema append or update data, otherwise create new table
* add `ckanext.aircan.enable_datastore_upload_configuration=true` to enable the upload configuration UI option.
* add `ckanext.aircan.notification_to = author, maintainer, editor, someone@gmail.com` failure email notification sent to. 
* add `ckanext.aircan.notification_from = sender@gmail.com` failure notification from email.
* add `ckanext.aircan.notification_subject` configure notification subject.


### Update aircan run status
 The `aircan_status_update` API can be use to store or update the run status for given resource. It accepts the POST request with authorized user.
```json
{ 
    "resource_id": "a4a520aa-c790-4b53-93aa-de61e1a2813c",
    "state": "progress",
    "message":"Pusing dataset records.",
    "dag_run_id":"394a1f0f-d8b3-47f2-9a51-08732349b785",
    "error": {
        "message" : "Failed to push data records."
    }
}
```

### Retrieving aircan run status 
 Use `aircan_status` API to get aircan run status for given resource providing resource id.
 eg.
  `http://YOUR-CKAN:5000/api/3/action/aircan_status`

```json
{
  "resource_id": "a4a520aa-c790-4b53-93aa-de61e1a2813c"
}
```

# Tests with Cypress

Test the aircan-connector with cypress.

## Installation

`npm install`

## Running

Opens up the cypress app and you can choose the specs to run.

`npm test`
