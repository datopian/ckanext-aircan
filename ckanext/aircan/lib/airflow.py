import logging
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

import ckan.plugins.toolkit as tk

log = logging.getLogger(__name__)


class AirflowClient:
    """
    Airflow API client (v2 endpoints only) with two auth modes:
      - server_type="gcp": Google service-account AuthorizedSession
      - server_type="local": fetch JWT from /auth/token and use Bearer token
    """

    AUTH_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

    def __init__(self):
        self.base_url = (tk.config.get("ckanext.aircan.endpoint") or "").rstrip("/")
        self.server_type = (
            tk.config.get("ckanext.aircan.server", "local") or "local"
        ).lower()
        self.api_version = tk.config.get("ckanext.aircan.api_version", "v2")
        self.timeout = int(tk.config.get("ckanext.aircan.timeout", 90) or 90)
        self.dag_id = tk.config.get("ckanext.aircan.dag_id")

        # local auth
        self.token_endpoint = tk.config.get(
            "ckanext.aircan.token_endpoint", "/auth/token"
        )
        self.username = tk.config.get("ckanext.aircan.airflow_username")
        self.password = tk.config.get("ckanext.aircan.airflow_password")

        # gcp auth
        self.service_account_file = tk.config.get(
            "ckanext.aircan.google_credentials_json"
        )

        self._authed_session: Optional[AuthorizedSession] = None
        self._access_token: Optional[str] = None

        if not self.base_url:
            raise ValueError("Missing config: ckanext.aircan.endpoint")

        if self.server_type == "gcp":
            if not self.service_account_file:
                raise ValueError(
                    "Missing config: ckanext.aircan.google_credentials_json"
                )

            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=[self.AUTH_SCOPE],
            )
            self._authed_session = AuthorizedSession(creds)

    def _join_url(self, endpoint: str) -> str:
        endpoint = (endpoint or "").lstrip("/")
        return f"{self.base_url}/{endpoint}"

    def _login_local(self) -> str:
        if not self.username or not self.password:
            raise ValueError(
                "Missing config: ckanext.aircan.airflow_username / ckanext.aircan.airflow_password"
            )

        url = self._join_url(self.token_endpoint)
        resp = requests.request(
            "POST",
            url,
            headers={"Content-Type": "application/json"},
            json={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        resp.raise_for_status()

        token = resp.json().get("access_token")
        if not token:
            raise requests.HTTPError("Token response did not include access_token")
        self._access_token = token
        return token

    def request(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        url = self._join_url(endpoint)

        if self.server_type == "gcp":
            if not self._authed_session:
                raise RuntimeError("GCP session not initialized")
            return self._authed_session.request(method, url, **kwargs)

        headers = kwargs.pop("headers", {}) or {}
        
        if self.api_version == "v2":
            if not self._access_token:
                self._login_local()
            headers["Authorization"] = f"Bearer {self._access_token}"
            kwargs["headers"] = headers
        else:
            kwargs["auth"] = requests.auth.HTTPBasicAuth(self.username, self.password)
        resp = requests.request(method, url, **kwargs)

        return resp

    def trigger_dag(
        self,
        conf: Dict[str, Any],
        dag_run_id: Optional[str] = None,
        logical_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:

        dag_run_id = dag_run_id or str(uuid.uuid4())
        logical_date = logical_date or datetime.now(timezone.utc)

        payload = {
            "dag_run_id": dag_run_id,
            "conf": conf or {},
            "logical_date": logical_date.isoformat().replace("+00:00", "Z"),
        }
        resp = self.request(
            "POST", f"/api/{self.api_version}/dags/{self.dag_id}/dagRuns", json=payload
        )

    
        if resp.status_code in (200, 201):
            data = resp.json()
            data.setdefault("dag_run_id", dag_run_id)
            return data

        if resp.status_code == 403:
            raise requests.HTTPError(
                "Forbidden: Check Airflow RBAC roles/permissions for this operation."
            )
        resp.raise_for_status()
        data = resp.json()
        data.setdefault("dag_run_id", dag_run_id)
        return data

    def get_dag_run(self, dag_run_id: str) -> Dict[str, Any]:
        resp = self.request(
            "GET", f"/api/{self.api_version}/dags/{self.dag_id}/dagRuns/{dag_run_id}"
        )
        resp.raise_for_status()
        return resp.json()