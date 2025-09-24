from dataclasses import dataclass
import requests
import logging
import functions_framework
from google.cloud import firestore

from config import Config

# --- Clients ---
db = firestore.Client()

# Configure logging at the module level
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


@dataclass
class TaskPayload:
    """Class to represent the payload received from Cloud Tasks."""
    unique_id: str
    data: list[dict]

    @classmethod
    def from_dict(cls, payload: dict):
        """Create a TaskPayload instance from a dictionary."""
        return cls(
            unique_id=payload.get("unique_id"),
            data=payload.get("data", []),
            endpoint=payload.get("endpoint", Config.DIFY_API_ENDPOINT)
        )

    def to_dify_payload(self) -> dict:
        """Convert the task payload to the format required by Dify API."""
        # {
        #   "inputs": {
        #     "{variable_name}":
        #     [
        #       {
        #       "transfer_method": "local_file",
        #       "upload_file_id": "{upload_file_id}",
        #       "type": "{document_type}"
        #       }
        #     ]
        #   }
        # }
        # 본문분석 워크플로우 input keys: "passage", "interpretation", "passageGroupId", "env"
        # 워크북 워크플로우 input keys: "passageId", "passage", "interpretation", "passageGroupId", "env", "isNew"
        # self.data: list of dicts, e.g., [{"id": "val1"}, {"query": "val2"}]
        return {
            "inputs": {
                key: value for item in self.data for key, value in item.items()
            },
            "response_mode": "blocking",
            "user": f"user-{self.unique_id}"
        }


@functions_framework.http
def main(request: dict):
    """
    Main function for the Worker Cloud Function.
    Receives a task from Cloud Tasks, executes the Dify workflow,
    and updates the status in Firestore.
    """
    if request.method != 'POST':
        return 'Only POST requests are accepted', 405

    try:
        # 1. Parse the task payload
        request_body = request.get_json()
        task_payload = TaskPayload.from_dict(request_body)

        if not task_payload.unique_id or not task_payload.data:
            logging.error("Missing 'unique_id' or 'data' in the payload.")
            return "Bad Request: Missing payload data.", 400

        # Update Firestore status to 'PROCESSING'
        doc_ref = db.collection(Config.FIRESTORE_COLLECTION).document(task_payload.unique_id)
        doc_ref.set({'status': 'PROCESSING', 'timestamp': firestore.SERVER_TIMESTAMP}, merge=True)

        # 2. Call the Dify API
        dify_payload = task_payload.to_dify_payload()
        response = requests.post(task_payload.endpoint, headers={
            "Authorization": f"Bearer {Config.DIFY_API_KEY}",
            "Content-Type": "application/json"
        }, json=dify_payload, timeout=Config.DIFY_API_TIMEOUT_MINUTES * 60)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        # 3. Update Firestore with the result
        dify_result = response.json() # Dify API 결과
        doc_ref.set({
            'status': 'SUCCESS',
            'result': dify_result, # Dify 결과 저장 (선택 사항)
            'timestamp': firestore.SERVER_TIMESTAMP
        }, merge=True)

        logging.info(f"Successfully processed ID: {task_payload.unique_id}")
        return "Success", 200

    except requests.exceptions.RequestException as e:
        # Network errors or HTTP errors (4xx, 5xx)
        logging.error(f"Error calling Dify API for ID {task_payload.unique_id}: {e}", exc_info=True)
        # Update Firestore status to 'FAILED'
        doc_ref.set({
            'status': 'FAILED',
            'message': str(e),
            'timestamp': firestore.SERVER_TIMESTAMP
        }, merge=True)
        return "Dify API call failed", 500
        
    except Exception as e:
        logging.error(f"An unexpected error occurred for ID {task_payload.unique_id}: {e}", exc_info=True)
        # Update Firestore status to 'FAILED'
        doc_ref.set({
            'status': 'FAILED',
            'message': str(e),
            'timestamp': firestore.SERVER_TIMESTAMP
        }, merge=True)
        return "Internal Server Error", 500
