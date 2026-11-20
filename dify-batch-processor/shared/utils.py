import os
import json
import logging
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from google.cloud import secretmanager

# --- Database Configuration ---
TABLE_NAME = "batch_process_status"

# Columns that exist in the table (besides unique_id, status, timestamp which are
# always handled). Any key in the `data` dict that matches a column name is written
# directly; unknown keys are silently ignored.
_KNOWN_COLUMNS = frozenset(
    {"unique_id", "status", "workflow_id", "workflow_run_id", "data", "result", "message", "timestamp", "retry_count"}
)
# Columns a caller may set through `data`; unique_id/status/timestamp are set explicitly.
# Derived, not listed again, so a new column cannot be added to one writer only.
_DATA_COLUMNS = _KNOWN_COLUMNS - {"unique_id", "status", "timestamp"}


def get_db_connection():
    """Create a new database connection from environment variables."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_DATABASE"),
    )


def check_and_upsert_status(
    conn,
    unique_id: str,
    new_status: str,
    data: dict | None = None,
    force: bool = False,
) -> tuple[bool, str | None]:
    """
    Atomically check current status and upsert if eligible.

    A row is eligible for upsert when:
    - No existing row (status is None)
    - Current status is FAILED
    - Current status is SUCCESS **and** force is True

    Uses the caller-provided connection (caller manages lifecycle).
    Must be called inside a ``with conn:`` block so that the transaction
    is committed/rolled-back by the caller's context manager.

    Returns:
        (upserted, current_status) -- *upserted* is True when the INSERT was
        executed, False when skipped. *current_status* is the status that was
        found before the decision (None when no row existed).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM batch_process_status WHERE unique_id = %s FOR UPDATE",
            (unique_id,),
        )
        row = cur.fetchone()
        current_status = row[0] if row else None

        eligible = (
            current_status is None
            or current_status == "FAILED"
            or (current_status == "SUCCESS" and force)
        )

        if not eligible:
            return False, current_status

        # Build column/value lists
        columns = ["unique_id", "status", "timestamp"]
        values: list = [unique_id, new_status, datetime.now(timezone.utc)]

        if data:
            for k, v in data.items():
                if k in _DATA_COLUMNS:
                    columns.append(k)
                    values.append(v)

        placeholders = ", ".join(["%s"] * len(values))
        col_names = ", ".join(columns)
        update_parts = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in columns if c != "unique_id"
        )

        cur.execute(
            f"INSERT INTO batch_process_status ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT (unique_id) DO UPDATE SET {update_parts}",
            values,
        )
        return True, current_status


# ---------------------------------------------------------------------------
# EntityProxy – mimics Datastore entity for backward compatibility
# ---------------------------------------------------------------------------
class EntityProxy:
    """Mimics Datastore entity for backward compatibility."""

    def __init__(self, row_dict):
        self._data = row_dict
        self.key = type("Key", (), {"name": row_dict["unique_id"]})()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def __repr__(self):
        return f"EntityProxy({self._data!r})"


# ---------------------------------------------------------------------------
# Dify API key initialization (unchanged)
# ---------------------------------------------------------------------------
def initialize_dify_api_keys(project_id: str = None, secret_id: str = None):
    """
    Fetches the Dify API key secret (JSON) and loads it into a global dictionary.
    """
    project_id = project_id or os.getenv("GCP_PROJECT_ID")
    secret_id = secret_id or os.getenv("DIFY_API_KEY_SECRET_ID")
    if project_id and secret_id:
        try:
            secret_json = get_secret(project_id, secret_id)
            api_keys_by_workflow_id = json.loads(secret_json)
            logging.info("Successfully initialized Dify API keys.")
            return api_keys_by_workflow_id
        except Exception as e:
            logging.critical(f"Failed to fetch or parse DIFY_API_KEY_SECRET_ID: {e}", exc_info=True)
            return None
    else:
        logging.critical("GCP_PROJECT_ID and DIFY_API_KEY_SECRET_ID must be set.")
        return None


# ---------------------------------------------------------------------------
# Database Operations (PostgreSQL)
# ---------------------------------------------------------------------------
def update_datastore(
    unique_id: str,
    status: str,
    data: dict | None = None,
    excluded_from_indexes: tuple = ("result", "message", "data"),
    expect: dict | None = None,
) -> bool:
    """
    Upserts a row in the batch_process_status table.

    Args:
        unique_id: The unique identifier for the row (primary key).
        status: The new status to set.
        data: A dictionary of other fields to set or update on the row.
        excluded_from_indexes: Kept for backward compatibility; ignored in PostgreSQL.
        expect: Optional {column: value} the existing row must still match for the
            update to apply (compared with IS NOT DISTINCT FROM, so None matches NULL).
            Used by the poller, which writes from a snapshot read earlier: since a
            row can go PROCESSING -> PENDING -> PROCESSING, a stale snapshot must not
            overwrite a newer run. Pass the status and timestamp that were read.

    Returns:
        True when the row was written. False when an ``expect`` condition no longer
        matched (the update was skipped) or the database call failed (logged).
    """
    expect = expect or {}
    unknown = set(expect) - _KNOWN_COLUMNS
    if unknown:
        raise ValueError(f"Unknown columns in expect: {sorted(unknown)}")

    try:
        # Build the payload: always include status and timestamp
        payload = {
            "unique_id": unique_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc),
        }
        if data:
            for k, v in data.items():
                if k in _KNOWN_COLUMNS:
                    payload[k] = v

        columns = list(payload.keys())
        placeholders = [f"%({c})s" for c in columns]
        # On conflict, update every column except unique_id
        update_cols = [c for c in columns if c != "unique_id"]
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

        sql = (
            f"INSERT INTO {TABLE_NAME} ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) "
            f"ON CONFLICT (unique_id) DO UPDATE SET {update_clause}"
        )
        params = dict(payload)
        if expect:
            conditions = []
            for c, v in expect.items():
                conditions.append(f"{TABLE_NAME}.{c} IS NOT DISTINCT FROM %(expect_{c})s")
                params[f"expect_{c}"] = v
            sql += " WHERE " + " AND ".join(conditions)

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                applied = cur.rowcount == 1
            conn.commit()
        finally:
            conn.close()

        if applied:
            logging.info(f"[{unique_id}] Database row upserted with status '{status}'.")
        else:
            logging.warning(
                f"[{unique_id}] Skipped writing status '{status}': row no longer matches {expect}."
            )
        return applied
    except Exception as e:
        logging.error(f"[{unique_id}] Failed to update database: {e}", exc_info=True)
        return False


# Whitelist of fields that may be queried to prevent SQL injection via column names.
_QUERYABLE_FIELDS = frozenset({"status", "workflow_id", "workflow_run_id"})


def get_entities_from_datastore(
    field: str,
    value: str,
    operator: str = "=",
    limit: int = None,
    key_only: bool = False,
):
    """
    Queries the batch_process_status table and returns a list of EntityProxy objects
    that behave like Datastore entities (support .key.name and .get()).

    Args:
        field: Column to filter on (must be in the whitelist).
        value: Value to compare against.
        operator: SQL comparison operator (default "=").
        limit: Maximum number of rows to return.
        key_only: If True, only fetch unique_id (mirrors Datastore keys_only).
    """
    if field not in _QUERYABLE_FIELDS:
        raise ValueError(f"Field '{field}' is not in the queryable whitelist: {_QUERYABLE_FIELDS}")

    # Whitelist the operator to prevent injection
    allowed_operators = {"=", "!=", "<", "<=", ">", ">="}
    if operator not in allowed_operators:
        raise ValueError(f"Operator '{operator}' is not allowed. Use one of {allowed_operators}")

    select_clause = "unique_id" if key_only else "*"
    sql = f"SELECT {select_clause} FROM {TABLE_NAME} WHERE {field} {operator} %s"
    params: list = [value]

    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [EntityProxy(dict(row)) for row in rows]


# ---------------------------------------------------------------------------
# Secret Management (unchanged)
# ---------------------------------------------------------------------------
def get_secret(project_id, secret_id, version_id="latest"):
    """Fetches a secret from Google Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
