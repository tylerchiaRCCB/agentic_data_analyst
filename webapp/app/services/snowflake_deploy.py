"""Deploy a semantic model YAML to Snowflake as a semantic view.

Uses the same AKV credential pattern as the pipeline's snowflake_client.
The webapp worker already has SNOWFLAKE_* env vars forwarded, so credentials
are available when needed.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class DeployError(RuntimeError):
    pass


def _parse_ref(ref: str) -> tuple[str, str, str]:
    """Parse DB.SCHEMA.VIEW into (database, schema, view_name)."""
    parts = [p.strip() for p in ref.split(".")]
    if len(parts) != 3 or not all(parts):
        raise DeployError(
            f"Snowflake reference must be DB.SCHEMA.VIEW, got: {ref!r}"
        )
    return parts[0], parts[1], parts[2]


def deploy_semantic_view(snowflake_ref: str, yaml_content: str) -> str:
    """Deploy YAML as a Cortex semantic view to Snowflake.

    Returns a success message string.
    Raises DeployError on any failure.
    """
    database, schema, view_name = _parse_ref(snowflake_ref)

    try:
        import snowflake.connector
    except ImportError as e:
        raise DeployError(
            "snowflake-connector-python is not installed in the webapp venv."
        ) from e

    # Load credentials — try team AKV pattern first, fall back to env vars
    conn_args = _build_conn_args(database, schema)

    # Use dollar-quoting to safely embed the YAML
    sql = (
        f"CREATE OR REPLACE SEMANTIC VIEW {database}.{schema}.{view_name}\n"
        f"  AS CORTEX_SEMANTIC_MODEL($$\n{yaml_content}\n$$)"
    )

    logger.info("Deploying semantic view %s.%s.%s", database, schema, view_name)
    try:
        conn = snowflake.connector.connect(**conn_args)
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchone()
            cursor.close()
        finally:
            conn.close()
    except Exception as e:
        raise DeployError(f"Snowflake deploy failed: {e}") from e

    msg = f"Deployed {database}.{schema}.{view_name}"
    if result:
        msg += f" — {result[0]}"
    logger.info(msg)
    return msg


def _build_conn_args(database: str, schema: str) -> dict:
    """Build Snowflake connection arguments from AKV or env vars."""
    # Try team AKV pattern
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        vault_url = "https://glccbdsdevkv.vault.azure.net/"
        credential = DefaultAzureCredential()
        secret_client = SecretClient(vault_url=vault_url, credential=credential)

        username = secret_client.get_secret("snowflake-etl-username").value
        private_key_pem = secret_client.get_secret("snowflake-etl-private-key-raw").value
        passphrase = secret_client.get_secret("snowflake-etl-private-key-passphrase").value

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=passphrase.encode(),
            backend=default_backend(),
        )
        pk_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        logger.info("Using AKV credentials for Snowflake deploy")
        return {
            "account": "reyesholdings.east-us-2.azure",
            "user": username,
            "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "CCB_DATASCIENCE_S_WH"),
            "role": os.environ.get("SNOWFLAKE_ROLE", "CCB_DATASCIENCE_SNOWFLAKE"),
            "database": database,
            "schema": schema,
            "private_key": pk_bytes,
        }
    except Exception:
        pass

    # Fall back to SNOWFLAKE_* env vars
    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    password = os.environ.get("SNOWFLAKE_PASSWORD")

    if not (account and user and password):
        raise DeployError(
            "No Snowflake credentials available. Set SNOWFLAKE_ACCOUNT, "
            "SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD, or configure AKV access."
        )

    return {
        "account": account,
        "user": user,
        "password": password,
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "CCB_DATASCIENCE_S_WH"),
        "role": os.environ.get("SNOWFLAKE_ROLE", "CCB_DATASCIENCE_SNOWFLAKE"),
        "database": database,
        "schema": schema,
    }
