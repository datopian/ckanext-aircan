## ckanext-aircan

The custom extension for notifying(triggering) the Airflow DAG about the data to be uploaded to DataStore.

### Prerequisites

You have a CKAN instance up and running - [instructions](https://github.com/okfn/docker-ckan#development-mode).

### Installation
1. This extension need to be installed manually via cloning the desired commit into the docker-ckan/src directory:
`git@github.com:datopian/ckanext-aircan.git`

2. Enable the extension in CKAN by adding in your`.env` file an `aircan_connector` to `CKAN__PLUGINS` list.
 
3. In your`.env` file add  `CKAN__AIRFLOW__URL` according to [Apache AirFlow REST API Reference](https://airflow.apache.org/docs/stable/rest-api-ref#post--api-experimental-dags--DAG_ID--dag_runs).


