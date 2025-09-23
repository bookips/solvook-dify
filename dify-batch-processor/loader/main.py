import json
import logging
import os
import functions_framework
from google.cloud import firestore, tasks_v2
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config import Config

# --- Clients ---
db = firestore.Client()
tasks_client = tasks_v2.CloudTasksClient()

# Configure logging at the module level
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# --- Google Sheets API Setup ---
# This function assumes you have stored the service account JSON in Secret Manager.
# You need to grant the Cloud Function's service account access to this secret.
def get_sheets_service():
    """Builds and returns a Google Sheets API service object."""
    # TODO: Secret Manager에서 서비스 계정 키를 가져오는 로직을 구현해야 합니다.
    # 예시:
    # from google.cloud import secretmanager
    # client = secretmanager.SecretManagerServiceClient()
    # name = f"projects/{Config.PROJECT_ID}/secrets/YOUR_SECRET_ID/versions/latest"
    # response = client.access_secret_version(request={"name": name})
    # creds_json = response.payload.data.decode("UTF-8")
    # creds_info = json.loads(creds_json)
    # creds = service_account.Credentials.from_service_account_info(creds_info)
    
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
    else:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{Config.PROJECT_ID}/secrets/YOUR_SECRET_ID/versions/latest"
        response = client.access_secret_version(request={"name": name})
        creds_json = response.payload.data.decode("UTF-8")
        creds_info = json.loads(creds_json) 
        creds = service_account.Credentials.from_service_account_info(creds_info)

    service = build('sheets', 'v4', credentials=creds)
    return service

@functions_framework.http
def main(request: dict):
    """
    Main function for the Loader Cloud Function.
    Reads data from Google Sheets, filters it based on Firestore status,
    and creates tasks in Cloud Tasks for processing.
    """
    try:
        # 1. Get data from Google Sheets
        service = get_sheets_service()
        sheet = service.spreadsheets()
        data_range = f"{Config.SHEET_NAME}!A2:Z"
        result = sheet.values().get(spreadsheetId=Config.SPREADSHEET_ID, range=data_range).execute()
        rows = result.get('values', [])

        if not rows:
            logging.info("No data found in Google Sheets.")
            return "No data found in Google Sheets.", 200

        # 2. Get status from Firestore
        docs_ref = db.collection(Config.FIRESTORE_COLLECTION).stream()
        processed_ids = {doc.id: doc.to_dict().get('status') for doc in docs_ref}

        # 3. Filter data and create tasks
        tasks_created_count = 0
        for i, row in enumerate(rows):
            if not row: continue # Skip empty rows

            # Determine the unique ID
            if Config.UNIQUE_ID_COLUMN.upper() == 'ROW_NUMBER':
                unique_id = str(i + 2) # Row numbers start from 2 in this range
            else:
                try:
                    unique_id = row[int(Config.UNIQUE_ID_COLUMN)]
                except (IndexError, ValueError):
                    logging.warning(f"Could not determine unique ID for row {i+2}. Skipping.")
                    continue
            
            status = processed_ids.get(unique_id)

            # Process only if status is not 'SUCCESS'
            if status != 'SUCCESS':
                create_cloud_task(row, unique_id)
                tasks_created_count += 1
                # Update Firestore status to 'PENDING'
                db.collection(Config.FIRESTORE_COLLECTION).document(unique_id).set({
                    'status': 'PENDING',
                    'timestamp': firestore.SERVER_TIMESTAMP
                }, merge=True)

        logging.info(f"Successfully created {tasks_created_count} tasks.")
        return f"Created {tasks_created_count} tasks.", 200

    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        return "Internal Server Error", 500

def create_cloud_task(row_data: dict, unique_id: str):
    """Creates a task in Cloud Tasks."""
    parent = tasks_client.queue_path(Config.PROJECT_ID, Config.LOCATION, Config.QUEUE_NAME)

    # Construct the HTTP request for the worker.
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": Config.WORKER_URL,
            "headers": {"Content-type": "application/json"},
        }
    }

    # The payload to send to the worker function.
    payload = {
        "unique_id": unique_id,
        "data": row_data,
        "endpoint": "",
    }
    
    # Add the payload to the request.
    task["http_request"]["body"] = json.dumps(payload).encode()

    # Use the unique ID to prevent duplicate tasks if the loader is re-run.
    task["name"] = f"{parent}/tasks/{unique_id}-{int(firestore.SERVER_TIMESTAMP.now().timestamp())}"

    try:
        response = tasks_client.create_task(request={"parent": parent, "task": task})
        logging.info(f"Created task: {response.name}")
    except Exception as e:
        # Handle potential task duplication error if retrying
        if "ALREADY_EXISTS" in str(e):
            logging.warning(f"Task for ID {unique_id} likely already exists. Skipping.")
        else:
            logging.error(f"Error creating task for ID {unique_id}: {e}")
            raise