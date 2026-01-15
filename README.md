[![Tests](https://github.com/Datopian/ckanext-aircan/workflows/Tests/badge.svg?branch=main)](https://github.com/Datopian/ckanext-aircan/actions)

# ckanext-aircan
A CKAN extension that integrates Airflow orchestrating with CKAN. This extension allows you to trigger, monitor, and display the status and logs of Aiflow data ingestion flows directly from the CKAN interface.


## Features
- **Trigger Prefect Flows**: Automatically or manually submit CKAN resources for processing via Prefect.
- **Status & Logs**: View the current status and logs of Prefect flow runs associated with CKAN resources.

## Requirements
- CKAN 2.11 or later (not tested on earlier versions)
- Python 3.8+
- A running [Airflow](https://airflow.apache.org/) server or Prefect Cloud

## Installation

**TODO:** Add any additional install steps to the list below.
For example installing any non-Python dependencies or adding any required
config settings.

To install ckanext-aircan:

1. Activate your CKAN virtual environment, for example:

   . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it on the virtualenv

   git clone https://github.com/Datopian/ckanext-aircan.git
   cd ckanext-aircan
   pip install -e .

3. Add `aircan` to the `ckan.plugins` setting in your CKAN
   config file (by default the config file is located at
   `/etc/ckan/default/ckan.ini`).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

   sudo service apache2 reload

## Config settings

```
ckanext.aircan.endpoint = http://localhost:8080
ckanext.aircan.server = gcp | local
ckanext.aircan.dag_id = example_dag
ckanext.aircan.api_version = v1 | v2

# If GCP server is used
ckanext.aircan.google_credentials_json =

# If local server is used
ckanext.aircan.airflow_password =
ckanext.aircan.airflow_username =

# Other settings
ckanext.aircan.ckan_api_key = 
ckanext.aircan.gcs.bucket = 
ckanext.aircan.gcs.project_id =
ckanext.aircan.gcs.bigquery_dataset_id =
ckanext.aircan.gcs.signed_url_expiration_seconds = 3600
ckanext.aircan.gcs.service_account_json =
ckanext.aircan.chunk_size = 104857600
ckanext.aircan.skip_leading_rows = 1
ckan.aircan.temp_table_prefix = _temp_
```

## Developer installation
To install ckanext-aircan for development, activate your CKAN virtualenv and
do:

    git clone https://github.com/Datopian/ckanext-aircan.git
    cd ckanext-aircan
    pip install -e .
    pip install -r dev-requirements.txt


## Endpoints

This extension adds three CKAN Action API endpoints:

* **`/api/3/action/aircan_submit`**
  Triggers an Airflow DAG run for a specified CKAN **resource**.

* **`/api/3/action/aircan_status`**
  Returns the status of the **most recent** Airflow DAG run for a specified CKAN **resource**.

* **`/api/3/action/aircan_status_logs`**
  Updates (or appends) progress logs on CKAN for a resource based on messages emitted during an Airflow DAG run.


Example request body used by `aircan_status_logs` (and/or as the shape of a status/log record):

```json
{
  "dag_run_id": "6591d0db-053e-4d9d-98d3-a0ce8f9a004d",
  "resource_id": "63b3d77e-032f-4ef0-8790-cc81d0509d5f",
  "state": "running",
  "message": "Queued for processing (dag_run_id=6591d0db-053e-4d9d-98d3-a0ce8f9a004d).",
  "type": "info",
  "error": null,
  "clear_logs": false
}
```

### Field descriptions
* **`resource_id`** *(string, required)*: CKAN resource UUID.
* **`dag_run_id`** *(string, required)*: Airflow DAG run identifier.
* **`state`** *(string, optional)*: Current run state (e.g. `queued`, `running`, `success`, `failed`).
* **`message`** *(string, optional)*: Human-readable progress or status message. It will time-stamped and stored in CKAN appended to previous messages unless `clear_logs` is set to `true`.
* **`type`** *(string, optional)*: Log level/category, e.g. `info`, `warning`, `error`. Default is `info`.
* **`error`** *(string|null, optional)*: Error details (use `null` when not applicable).
* **`clear_logs`** *(boolean, optional)*: If `true`, clears existing logs otherwise appends to them keep a history.

## Extending Aircan payload 
You can extend the payload sent to Airflow by implementing the `IAircan` interface in your own CKAN plugin.

```
class ExamplePlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(interfaces.IAircan)

    def update_payload(self, context, payload):
            payload['new_field'] = tk.config.get('ckanext.example.new_field')
            return payload
            
```

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
