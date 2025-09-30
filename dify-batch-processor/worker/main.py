from dataclasses import dataclass
import json
import requests
import logging
from datetime import datetime
import functions_framework
from google.cloud import datastore, secretmanager
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

from config import Config

def get_secret(project_id, secret_id, version_id="latest"):
    """Fetches a secret from Google Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# --- Clients ---
db = datastore.Client(project=Config.PROJECT_ID)

# Fetch Dify API Key from Secret Manager
DIFY_API_KEY_BY_WORKFLOW_ID = None
if Config.PROJECT_ID and Config.DIFY_API_KEY_SECRET_ID:
    try:
        secret_api_json = get_secret(Config.PROJECT_ID, Config.DIFY_API_KEY_SECRET_ID)
        DIFY_API_KEY_BY_WORKFLOW_ID = json.loads(secret_api_json)
    except Exception as e:
        logging.critical(f"Failed to fetch DIFY_API_KEY from Secret Manager: {e}", exc_info=True)
        # If the API key is critical for startup, you might want to exit or handle this differently.
else:
    logging.critical("GCP_PROJECT_ID and DIFY_API_KEY_SECRET_ID must be set.")


# Configure logging at the module level
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def save_to_datastore(unique_id: str, status: str, result: dict | None = None, message: str | None = None):
    """Helper function to save status updates to Datastore."""
    key = db.key(Config.FIRESTORE_COLLECTION, unique_id)
    # Exclude 'result' and 'message' from indexing to avoid 1500 byte limit.
    entity = datastore.Entity(key=key, exclude_from_indexes=('result', 'message'))

    entity.update({
        'status': status,
        'timestamp': datetime.now()
    })
    if result is not None:
        entity['result'] = str(result)  # Datastore has limits on nested objects, storing as string is safer
    if message is not None:
        entity['message'] = message

    db.put(entity)

@dataclass
class TaskPayload:
    """Class to represent the payload received from Cloud Tasks."""
    unique_id: str
    data: dict
    workflow_id: str

    @classmethod
    def from_dict(cls, payload: dict):
        """Create a TaskPayload instance from a dictionary."""
        return cls(
            unique_id=payload.get("unique_id"),
            data=payload.get("data", {}),
            workflow_id=payload.get("workflow_id")
        )

    def to_dify_payload(self) -> dict:
        """Convert the task payload to the format required by Dify API."""
        # The 'data' field from the loader is now the entire inputs payload
        return {
            "inputs": self.data,
            "response_mode": "blocking",
            "user": f"user-{self.unique_id}"
        }


@functions_framework.http
def main(request: dict):
    """
    Main function for the Worker Cloud Function.
    Receives a task from Cloud Tasks, executes the Dify workflow,
    and updates the status in Datastore.
    """
    if not DIFY_API_KEY_BY_WORKFLOW_ID:
        logging.error("DIFY_API_KEY is not configured. Aborting.")
        return "Internal Server Error: Service is not configured.", 500
        
    if request.method != 'POST':
        return 'Only POST requests are accepted', 405

    task_payload = None
    try:
        # 1. Parse the task payload
        data = request.get_json()
        task_payload = TaskPayload.from_dict(data)

        if not task_payload.unique_id or not task_payload.data:
            logging.error("Missing 'unique_id' or 'data' in the payload.")
            return "Bad Request: Missing payload data.", 400
        
        logging.info(f"Processing task for ID: {task_payload.unique_id}")
        # Update Datastore status to 'PROCESSING'
        save_to_datastore(task_payload.unique_id, 'PROCESSING')
        # 2. Prepare and call the Dify API
        dify_payload = task_payload.to_dify_payload()
        response = requests.post(
            Config.DIFY_API_ENDPOINT,
            headers={
                "Authorization": f"Bearer {DIFY_API_KEY_BY_WORKFLOW_ID.get(task_payload.workflow_id)}",
                "Content-Type": "application/json"
            },
            json=dify_payload,
            timeout=Config.DIFY_API_TIMEOUT_MINUTES * 60
        )

        # Handle specific HTTP errors like 403 Forbidden, which indicates an auth problem.
        if response.status_code == 403:
            error_message = "Dify API returned 403 Forbidden. Check if the DIFY_API_KEY is correct and has permissions."
            logging.error(f"{error_message} for ID {task_payload.unique_id}")
            save_to_datastore(task_payload.unique_id, 'FAILED', message=error_message)
            return "Dify API Forbidden", 500

        response.raise_for_status()

        # 3. Update Datastore with the result
        dify_result = response.json()
        if dify_result.get("data").get("status") == "failed":
            error_message = dify_result.get("data").get("error", "Unknown error")
            logging.error(f"Dify API processing failed for ID {task_payload.unique_id}: {error_message}")
            save_to_datastore(task_payload.unique_id, 'FAILED', message=error_message)
            return "Dify API processing failed", 500

        save_to_datastore(task_payload.unique_id, 'SUCCESS', result=dify_result)

        logging.info(f"Successfully processed ID: {task_payload.unique_id}")
        return "Success", 200

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Dify API for ID {task_payload.unique_id}: {e}", exc_info=True)
        if task_payload:
            save_to_datastore(task_payload.unique_id, 'FAILED', message=str(e))
        return "Dify API call failed", 500
        
    except Exception as e:
        logging.error(f"An unexpected error occurred for ID {task_payload.unique_id if task_payload else 'unknown'}: {e}", exc_info=True)
        if task_payload:
            save_to_datastore(task_payload.unique_id, 'FAILED', message=str(e))
        return "Internal Server Error", 500
