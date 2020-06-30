## ckanext-aircan

The custom extension for notifying(triggering) the Airflow DAG about the data to be uploaded to DataStore.

### Prerequisites

You have a CKAN instance up and running - [instructions](https://github.com/okfn/docker-ckan#development-mode).

### Installation
1. This extension need to be installed manually via cloning the desired commit into the docker-ckan/src directory:
`git@github.com:datopian/ckanext-aircan.git`

2. Enable the extension in CKAN by adding in your`.env` file an `aircan_connector` to `CKAN__PLUGINS` list. Make sure to disable `datapusher` in case you have it.
 
3. In your`.env` file add  `CKAN__AIRFLOW__URL` according to [Apache AirFlow REST API Reference](https://airflow.apache.org/docs/stable/rest-api-ref#post--api-experimental-dags--DAG_ID--dag_runs). If you are running CKAN in a Docker container, make sure to specify the Airflow URL with `host.docker.internal` instead of `localhost`: `CKAN__AIRFLOW__URL=http://host.docker.internal:8080/api/experimental/dags/ckan_api_load_multiple_steps/dag_runs`. Also notice Airflow requires, by default, the endpoint `api/experimental/dags/DAG_ID` for API access.

4. Also in your `.env` file, specify a temporary directory for files: `CKAN__AIRFLOW__STORAGE_PATH=/my/temp/path`. [TODO FIX TMP FILES]

5. Access your CKAN and upload of modify a resource. You must select a resource type. At this time, we support `CSV` only. 


