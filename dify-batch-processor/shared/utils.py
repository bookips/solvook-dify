import os
import json
import logging
from datetime import datetime
from google.cloud import datastore, secretmanager

# --- GCP Clients ---
DB = datastore.Client(project=os.getenv("GCP_PROJECT_ID"))
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "dify_batch_process_status")

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


# --- Datastore Operations ---
def update_datastore(unique_id: str, status: str, data: dict | None = None):
    """
    Updates or creates an entity in Datastore.

    Args:
        unique_id: The unique identifier for the entity (key name).
        status: The new status to set.
        data: A dictionary of other fields to set or update on the entity.
    """
    try:
        key = DB.key(FIRESTORE_COLLECTION, unique_id)
        entity = DB.get(key)
        if not entity:
            entity = datastore.Entity(key=key)

        update_payload = {
            'status': status,
            'timestamp': datetime.now()
        }
        if data:
            update_payload.update(data)

        entity.update(update_payload)
        
        excluded_from_indexes = ('result', 'message')
        # Create a tuple of keys that are in the entity and should be excluded.
        entity.exclude_from_indexes = tuple(k for k in entity if k in excluded_from_indexes)

        DB.put(entity)
        logging.info(f"[{unique_id}] Datastore entity updated with status '{status}'.")
    except Exception as e:
        logging.error(f"[{unique_id}] Failed to update datastore: {e}", exc_info=True)

def get_items_from_datastore(field: str, value: str, condition: str = "="):
    query = DB.query(kind=FIRESTORE_COLLECTION)
    query.add_filter(field, condition, value)
    return list(query.fetch())

# --- Secret Management ---
def get_secret(project_id, secret_id, version_id="latest"):
    """Fetches a secret from Google Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
