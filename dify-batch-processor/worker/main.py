from dataclasses import dataclass
import requests
import logging
from datetime import datetime
import functions_framework
from google.cloud import datastore
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

from config import Config

# --- Clients ---
# Use Datastore client instead of Firestore
# When using the emulator, explicitly providing the project ID prevents the client
# from trying to use Application Default Credentials to determine the project.
if Config.DATASTORE_EMULATOR_HOST:
    db = datastore.Client(project=Config.PROJECT_ID)
else:
    db = datastore.Client()

# Configure logging at the module level
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def save_to_datastore(unique_id: str, status: str, result: dict | None = None, message: str | None = None):
    """Helper function to save status updates to Datastore."""
    key = db.key(Config.FIRESTORE_COLLECTION, unique_id)
    entity = datastore.Entity(key=key)

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
    endpoint: str

    @classmethod
    def from_dict(cls, payload: dict):
        """Create a TaskPayload instance from a dictionary."""
        return cls(
            unique_id=payload.get("unique_id"),
            data=payload.get("data", {}),
            endpoint=payload.get("endpoint")
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

        # Update Datastore status to 'PROCESSING'
        save_to_datastore(task_payload.unique_id, 'PROCESSING')
        # 2. Prepare and call the Dify API
        dify_payload = task_payload.to_dify_payload()
        response = requests.post(
            task_payload.endpoint,
            headers={
                "Authorization": f"Bearer {Config.DIFY_API_KEY}",
                "Content-Type": "application/json"
            },
            json=dify_payload,
            timeout=Config.DIFY_API_TIMEOUT_MINUTES * 60
        )
        response.raise_for_status()

        # 3. Update Datastore with the result
        dify_result = response.json()
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