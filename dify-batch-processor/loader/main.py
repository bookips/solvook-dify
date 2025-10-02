import json
import logging
from datetime import datetime
import functions_framework
from google.cloud import datastore, tasks_v2, secretmanager
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

from config import Config

def get_secret(project_id, secret_id, version_id="latest"):
    """Fetches a secret from Google Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def get_gcp_credentials():
    """
    Builds and returns a GCP credentials object for Google Sheets API.
    - For local development, it uses the service account file specified by GOOGLE_APPLICATION_CREDENTIALS.
    - In a GCP environment, it fetches the credentials from Secret Manager.
    """
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets.readonly'
    ]
    # For local development with a service account file
    if Config.GOOGLE_APPLICATION_CREDENTIALS:
        logging.info(f"Using credentials from file: {Config.GOOGLE_APPLICATION_CREDENTIALS}")
        return service_account.Credentials.from_service_account_file(
            Config.GOOGLE_APPLICATION_CREDENTIALS,
            scopes=scopes
        )
    
    # In GCP, fetch credentials from Secret Manager
    if Config.GOOGLE_SHEETS_CREDENTIALS_SECRET_ID:
        try:
            logging.info(f"Fetching Sheets credentials from Secret Manager, secret_id: {Config.GOOGLE_SHEETS_CREDENTIALS_SECRET_ID}")
            creds_json_str = get_secret(Config.PROJECT_ID, Config.GOOGLE_SHEETS_CREDENTIALS_SECRET_ID)
            creds_info = json.loads(creds_json_str)
            return service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
        except Exception as e:
            logging.error(f"Failed to load credentials from Secret Manager: {e}", exc_info=True)
            return None

    # Fallback to Application Default Credentials (ADC) if no specific credentials are provided
    logging.warning("No explicit credentials provided. Falling back to Application Default Credentials for Sheets API.")
    return None

# --- Clients ---
# For Firestore and Cloud Tasks, we can rely on Application Default Credentials (ADC) in GCP.
# For local development, GOOGLE_APPLICATION_CREDENTIALS should be set, which ADC will pick up.
db = datastore.Client(project=Config.PROJECT_ID)
tasks_client = tasks_v2.CloudTasksClient()

# Configure logging at the module level
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def stream_structured_sheet_data(
    sheet_service,
    spreadsheet_id: str,
    sheet_name: str,
    header_row: int = 1,
    chunk_size: int = 300,
    filter_column_name: str | None = None,
    filter_column_value: str | None = None
):
    """
    Reads data from Google Sheets in chunks and yields each row as a generator.
    """
    try:
        sheets_api = sheet_service.spreadsheets()
        header_range = f"{sheet_name}!A{header_row}:Z{header_row}"
        header_result = sheets_api.values().get(spreadsheetId=spreadsheet_id, range=header_range).execute()
        header = header_result.get('values', [[]])[0]

        if not header:
            logging.warning("Sheet header is empty. Cannot process.")
            return

        current_row_index = header_row + 1
        while True:
            data_range = f"{sheet_name}!A{current_row_index}:Z{current_row_index + chunk_size - 1}"
            result = sheets_api.values().get(spreadsheetId=spreadsheet_id, range=data_range).execute()
            rows = result.get('values', [])

            if not rows:
                break

            for i, row in enumerate(rows):
                row_number = current_row_index + i
                structured_row = []
                padded_row = row + [''] * (len(header) - len(row))
                for j, cell_value in enumerate(padded_row):
                    if j < len(header):
                        column_name = header[j]
                        if column_name:
                            structured_row.append({column_name: cell_value})

                if filter_column_name and filter_column_value:
                    cell_value = find_data_by_name(structured_row, filter_column_name)
                    if cell_value != filter_column_value:
                        continue

                yield row_number, structured_row

            if len(rows) < chunk_size:
                break

            current_row_index += chunk_size

    except Exception as e:
        logging.error(f"Error streaming sheet data: {e}", exc_info=True)


def find_data_by_name(structured_row: list[dict], name: str) -> str | None:
    """Finds and returns the value associated with a given name in a structured row."""
    for item in structured_row:
        if name in item:
            return item.get(name)
    return None


def get_sheets_service(creds):
    """Builds and returns a Google Sheets API service object."""
    return build('sheets', 'v4', credentials=creds)


def to_dify_inputs_by_category(data: list[dict], category: str, isNew: bool = True) -> dict:
    """Constructs the payload to send to the Dify API."""
    match category:
        case "본문분석":
            return {
                "passage": find_data_by_name(data, "passage"),
                "interpretation": find_data_by_name(data, "interpretation"),
                "passageGroupId": find_data_by_name(data, "passageGroupId"),
                "env": find_data_by_name(data, "env")
            }
        case "워크북":
            return {
                "passageId": find_data_by_name(data, "passageId"),
                "passage": find_data_by_name(data, "passage"),
                "interpretation": find_data_by_name(data, "interpretation"),
                "passageGroupId": find_data_by_name(data, "passageGroupId"),
                "env": find_data_by_name(data, "env"),
                "isNew": "true" if isNew else "false"
            }


def create_unique_id_by_category(data: list[dict], category: str, row_number: int) -> str:
    """Creates a unique task ID based on the category and a unique identifier from the data."""
    workflow_id = Config.DIFY_WORKFLOW_IDS_BY_CONTENT_CATEGORY.get(category)
    passage_group_id = find_data_by_name(data, "passageGroupId")
    match category:
        case "본문분석":
            return f"{workflow_id}_{passage_group_id}"
        case "워크북":
            passage_id = find_data_by_name(data, "passageId")
            return f"{workflow_id}_{passage_group_id}_{passage_id}"


def get_task_status(task_id: str) -> str | None:
    """Retrieves the status of a task from Datastore by its key."""
    key = db.key(Config.FIRESTORE_COLLECTION, task_id)
    entity = db.get(key)
    if entity:
        return entity.get('status')
    return None


@functions_framework.http
def main(request: dict):
    """
    Main function for the Loader Cloud Function.
    Reads data from Google Sheets, filters it based on Datastore status,
    and creates tasks in Cloud Tasks for processing.
    """
    try:
        # Get credentials for Sheets API.
        creds = get_gcp_credentials()
        if not creds:
            # If running in GCP, the runtime service account might have direct access.
            # Let's try with ADC by passing None.
            logging.warning("Could not build credentials explicitly. Proceeding with Application Default Credentials.")

        # Build the sheets service with the credentials
        sheets_service = get_sheets_service(creds)
        data_stream = stream_structured_sheet_data(
            sheet_service=sheets_service,
            spreadsheet_id=Config.SPREADSHEET_ID,
            sheet_name=Config.SHEET_NAME,
            filter_column_name="target",
            filter_column_value="TRUE"
        )

        tasks_created_count = 0
        processed_rows = 0
        for row_number, structured_row in data_stream:
            processed_rows += 1
            if not structured_row: continue

            category = find_data_by_name(structured_row, "content_category")
            if not category:
                logging.warning(f"Row {row_number} missing 'content_category'. Skipping.")
                continue

            for each in category.split(","):
                each = each.strip()
                unique_id = create_unique_id_by_category(structured_row, each, row_number)

                task_creation_needed = False
                with db.transaction():
                    key = db.key(Config.FIRESTORE_COLLECTION, unique_id)
                    entity = db.get(key)
                    status = entity.get("status") if entity else None

                    # Only create a task if it's new (no status) or has failed.
                    # Do not re-queue tasks that are PENDING, PROCESSING, or SUCCESS.
                    if status is None or status == 'FAILED':
                        if not entity:
                            entity = datastore.Entity(key=key)
                        entity.update({
                            'status': 'PENDING',
                            'timestamp': datetime.now()
                        })
                        db.put(entity)
                        task_creation_needed = True
                    else:
                        logging.info(f"Skipping task creation for ID {unique_id} because its status is '{status}'.")

                if task_creation_needed:
                    # The original `isNew` logic would re-trigger successful workbooks,
                    # which contradicts the goal of preventing duplicates.
                    isNew = each == "워크북" and status == "SUCCESS"
                    input_data = to_dify_inputs_by_category(structured_row, each, isNew)

                    # Create a unique task name with a timestamp to avoid Cloud Tasks' deduplication,
                    # as our transaction now handles the idempotency.
                    task_id = f"{unique_id}_{int(datetime.now().timestamp())}"
                    create_cloud_task(input_data, task_id)
                    tasks_created_count += 1

        if processed_rows == 0:
            logging.info("No data found in Google Sheets that matches the filter.")
            return "No data found in Google Sheets.", 200

        logging.info(f"Successfully created {tasks_created_count} tasks.")
        return f"Created {tasks_created_count} tasks.", 200

    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        return "Internal Server Error", 500


def create_cloud_task(input_data: dict, task_id: str):
    """Creates a task in Cloud Tasks."""
    parent = tasks_client.queue_path(Config.PROJECT_ID, Config.LOCATION, Config.QUEUE_NAME)
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": Config.WORKER_URL,
            "headers": {"Content-type": "application/json"},
            "oidc_token": {
                "service_account_email": Config.FUNCTION_SERVICE_ACCOUNT_EMAIL,
            },
        }
    }
    splitted = task_id.split('_')
    workflow_id, unique_id = splitted[0], '_'.join(splitted[:-1])
    payload = {
        "unique_id": unique_id,
        "data": input_data,
        "workflow_id": workflow_id,
    }

    task["http_request"]["body"] = json.dumps(payload).encode()
    task["name"] = f"{parent}/tasks/{task_id}"

    try:
        response = tasks_client.create_task(request={"parent": parent, "task": task})
        logging.info(f"Created task: {response.name} on dify workflow {workflow_id}")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e):
            logging.warning(f"Task for ID {task_id} likely already exists. Skipping.")
        else:
            logging.error(f"Error creating task for ID {task_id}: {e}")
            raise
