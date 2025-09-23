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
    data: list

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
        return {
            "inputs": {
                "query": self.data[0] if self.data else ""
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
        data = request.get_json()
        task_payload = TaskPayload.from_dict(data)

        if not task_payload.unique_id or not task_payload.data:
            logging.error("Missing 'unique_id' or 'data' in the payload.")
            return "Bad Request: Missing payload data.", 400

        # Update Firestore status to 'PROCESSING'
        doc_ref = db.collection(Config.FIRESTORE_COLLECTION).document(task_payload.unique_id)
        doc_ref.set({'status': 'PROCESSING', 'timestamp': firestore.SERVER_TIMESTAMP}, merge=True)

        # 2. Prepare and call the Dify API
        # headers = {
        #     "Authorization": f"Bearer {DIFY_API_KEY}",
        #     "Content-Type": "application/json"
        # }
        
        # --- Dify 페이로드 구성 ---
        # TODO: Google Sheets의 'row_data'를 Dify 워크플로우에 필요한 페이로드 형식으로 변환해야 합니다.
        # 이 예시에서는 row_data의 첫 번째 셀 값을 'query' 입력으로 사용한다고 가정합니다.
        # 실제 워크플로우의 입력에 맞게 이 부분을 수정하세요.
        # dify_payload = {
        #     "inputs": {
        #         "query": row_data[0] if row_data else "" 
        #     },
        #     "response_mode": "blocking", # 또는 "streaming"
        #     "user": f"user-{unique_id}" # Dify 로그 추적을 위한 사용자 식별자
        # }

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
        # Return a 500 error to allow Cloud Tasks to retry
        return "Dify API call failed", 500
        
    except Exception as e:
        logging.error(f"An unexpected error occurred for ID {task_payload.unique_id}: {e}", exc_info=True)
        # Update Firestore status to 'FAILED'
        doc_ref.set({
            'status': 'FAILED',
            'message': str(e),
            'timestamp': firestore.SERVER_TIMESTAMP
        }, merge=True)
        # Return a 500 error to allow Cloud Tasks to retry
        return "Internal Server Error", 500
