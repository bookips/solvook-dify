#!/usr/bin/env python3
"""One-time migration: Datastore -> PostgreSQL for batch_process_status"""

import os
import sys
import logging
from datetime import datetime
from google.cloud import datastore
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS batch_process_status (
    unique_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'PENDING',
    workflow_id TEXT,
    workflow_run_id TEXT,
    data TEXT,
    result TEXT,
    message TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bps_status ON batch_process_status(status);
"""

def main():
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_DATABASE"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
    )

    # Create table
    with conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
    logging.info("Table batch_process_status created/verified.")

    # Read from Datastore
    ds_client = datastore.Client(project=os.getenv("GCP_PROJECT_ID"))
    query = ds_client.query(kind="dify_batch_process_status")
    entities = list(query.fetch())
    logging.info(f"Fetched {len(entities)} entities from Datastore.")

    # Batch insert to PostgreSQL
    batch_size = 500
    total_inserted = 0

    for i in range(0, len(entities), batch_size):
        batch = entities[i:i+batch_size]
        rows = []
        for e in batch:
            rows.append((
                e.key.name,
                e.get("status") or "UNKNOWN",
                e.get("workflow_id"),
                e.get("workflow_run_id"),
                e.get("data"),
                e.get("result"),
                e.get("message"),
                e.get("timestamp"),
            ))

        with conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """INSERT INTO batch_process_status
                       (unique_id, status, workflow_id, workflow_run_id, data, result, message, timestamp)
                       VALUES %s
                       ON CONFLICT (unique_id) DO NOTHING""",
                    rows
                )
                total_inserted += cur.rowcount

        logging.info(f"Batch {i//batch_size + 1}: inserted {cur.rowcount} rows (total: {total_inserted})")

    conn.close()
    logging.info(f"Migration complete. {total_inserted} rows inserted into PostgreSQL.")

if __name__ == "__main__":
    main()
