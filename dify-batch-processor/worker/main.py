from dataclasses import dataclass
import json
import requests
import logging
import functions_framework
from dotenv import load_dotenv

load_dotenv()

from config import Config
from shared.utils import initialize_dify_api_keys, update_datastore

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

try:
    DIFY_API_KEYS_BY_WORKFLOW_ID = initialize_dify_api_keys(Config.PROJECT_ID, Config.DIFY_API_KEY_SECRET_ID)
except Exception:
    DIFY_API_KEYS_BY_WORKFLOW_ID = None

@dataclass
class TaskPayload:
    unique_id: str
    data: dict
    workflow_id: str

    @classmethod
    def from_dict(cls, payload: dict):
        return cls(
            unique_id=payload.get("unique_id"),
            data=payload.get("data", {}),
            workflow_id=payload.get("workflow_id")
        )

    def to_dify_payload(self) -> dict:
        return {
            "inputs": self.data,
            "response_mode": "streaming",
            "user": f"user-{self.unique_id}"
        }

@functions_framework.http
def main(request: dict):
    if not DIFY_API_KEYS_BY_WORKFLOW_ID:
        logging.error("DIFY_API_KEYS_BY_WORKFLOW_ID not initialized. Aborting.")
        return "Internal Server Error: Service is not configured.", 500

    if request.method != 'POST':
        return 'Only POST requests are accepted', 405

    task_payload = None
    try:
        data = request.get_json()
        task_payload = TaskPayload.from_dict(data)

        if not all([task_payload.unique_id, task_payload.data, task_payload.workflow_id]):
            logging.error("Missing 'unique_id', 'data', or 'workflow_id' in the payload.")
            return "Bad Request: Missing payload data.", 400
        
        logging.info(f"[{task_payload.unique_id}] Dispatching task for workflow {task_payload.workflow_id}.")
        
        api_key = DIFY_API_KEYS_BY_WORKFLOW_ID.get(task_payload.workflow_id)
        if not api_key:
            raise ValueError(f"No API key found for workflow_id: {task_payload.workflow_id}")

        dify_payload = task_payload.to_dify_payload()
        response = requests.post(
            Config.DIFY_API_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=dify_payload,
            timeout=60,
            stream=True
        )
        response.raise_for_status()

        workflow_run_id = None
        for line in response.iter_lines():
            if line:
                data_chunk = line.decode('utf-8')
                if data_chunk.startswith('data:'):
                    try:
                        event_data = json.loads(data_chunk.lstrip('data:'))
                        if event_data.get('event') == 'workflow_started':
                            workflow_run_id = event_data.get('workflow_run_id')
                            logging.info(f"[{task_payload.unique_id}] Dify workflow started with run ID: {workflow_run_id}")
                            break
                    except json.JSONDecodeError:
                        logging.warning(f"Could not decode JSON from line: {line}")
        
        if not workflow_run_id:
            raise Exception("Failed to retrieve workflow_run_id from Dify's streaming response.")

        update_data = {
            "workflow_run_id": workflow_run_id,
            "workflow_id": task_payload.workflow_id
        }
        update_datastore(task_payload.unique_id, 'PROCESSING', data=update_data)

        logging.info(f"[{task_payload.unique_id}] Successfully dispatched. Stored run ID {workflow_run_id}.")
        return "Task dispatched successfully.", 202

    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        if isinstance(e, requests.exceptions.RequestException):
            error_message = f"Failed to dispatch to Dify: {e}"
        
        logging.error(f"Error for ID {task_payload.unique_id if task_payload else 'unknown'}: {error_message}", exc_info=True)
        if task_payload:
            update_datastore(task_payload.unique_id, 'FAILED', data={"message": error_message})
        
        return "Internal Server Error", 500
