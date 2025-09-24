import json
import logging
import os
import functions_framework
from google.cloud import firestore, tasks_v2
from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import Config

db = firestore.Client()
tasks_client = tasks_v2.CloudTasksClient()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def stream_structured_sheet_data(
    sheet_service,
    spreadsheet_id: str,
    sheet_name: str,
    header_row: int = 1,
    chunk_size: int = 1000,
    filter_column_name: str | None = None,
    filter_column_value: str | None = None
):
    """
    Reads data from Google Sheets in chunks and yields each row as a generator,
    avoiding loading the entire sheet into memory.
    """
    try:
        header_range = f"{sheet_name}!A{header_row}:Z{header_row}"
        header_result = sheet_service.values().get(spreadsheetId=spreadsheet_id, range=header_range).execute()
        header = header_result.get('values', [[]])[0]

        if not header:
            logging.warning("Sheet header is empty. Cannot process.")
            return

        current_row_index = header_row + 1
        while True:
            data_range = f"{sheet_name}!A{current_row_index}:Z{current_row_index + chunk_size - 1}"
            result = sheet_service.values().get(spreadsheetId=spreadsheet_id, range=data_range).execute()
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


def get_sheets_service():
    """Builds and returns a Google Sheets API service object."""
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        creds = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
    else:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{Config.PROJECT_ID}/secrets/{Config.GOOGLE_SHEETS_CREDENTIALS_SECRET_ID}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        creds_json = response.payload.data.decode("UTF-8")
        creds_info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(creds_info)

    service = build('sheets', 'v4', credentials=creds)
    return service


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
                "isNew": isNew
            }


def create_unique_id_by_category(data: list[dict], category: str) -> str:
    """Creates a unique task ID based on the category and a unique identifier from the data."""
    workflow_id = Config.DIFY_WORKFLOW_IDS_BY_CONTENT_CATEGORY.get(category)
    passage_group_id = find_data_by_name(data, "passageGroupId")
    match category:
        case "본문분석":
            return f"{workflow_id}/{passage_group_id}"
        case "워크북":
            passage_id = find_data_by_name(data, "passageId")
            return f"{workflow_id}/{passage_group_id}/{passage_id}"


def get_task_status(task_id: str, is_pattern_search: bool = False) -> str | None:
    """
    Retrieves the status of a task from Firestore.
    Can perform an exact match or a pattern-based search.

    Args:
        task_id: The document ID or ID pattern to search for.
        is_pattern_search: If True, performs a 'starts with' search. 
                           If any matching doc is 'SUCCESS', returns 'SUCCESS'.
                           If False, performs an exact match for the given task_id.

    Returns:
        The status string ('SUCCESS', 'PENDING', etc.) or None if not found.
    """
    collection_ref = db.collection(Config.FIRESTORE_COLLECTION)
    
    if is_pattern_search:
        end_pattern = task_id[:-1] + chr(ord(task_id[-1]) + 1)
        query = collection_ref.where(firestore.FieldPath.document_id(), ">=", task_id) \
                              .where(firestore.FieldPath.document_id(), "<", end_pattern)
        
        for doc in query.stream():
            if doc.to_dict().get('status') == 'SUCCESS':
                return 'SUCCESS'
        return None
    else:
        doc_ref = collection_ref.document(task_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('status')
        return None


@functions_framework.http
def main(request: dict):
    """
    Main function for the Loader Cloud Function.
    Reads data from Google Sheets, filters it based on Firestore status,
    and creates tasks in Cloud Tasks for processing.
    """
    try:
        service = get_sheets_service()
        data_stream = stream_structured_sheet_data(
            sheet_service=service,
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
                unique_id = create_unique_id_by_category(structured_row, each)

                # Use pattern search to see if any previous attempt for this pattern was successful.
                status = get_task_status(unique_id, is_pattern_search=(each=="워크북"))
                
                isNew = each == "워크북" and status == "SUCCESS" 
                input_data = to_dify_inputs_by_category(structured_row, each, isNew)

                if status != 'SUCCESS' or isNew:
                    # Always create a new, unique ID with a timestamp for the actual task.
                    unique_task_id = f"{unique_id}/{int(firestore.SERVER_TIMESTAMP.now().timestamp())}"
                    
                    create_cloud_task(input_data, unique_task_id)
                    tasks_created_count += 1

                    # Update state by unique_id to 'PENDING' if not already 'SUCCESS'
                    doc_ref = db.collection(Config.FIRESTORE_COLLECTION).document(unique_id)
                    doc_ref.set({
                        'status': 'PENDING',
                        'timestamp': firestore.SERVER_TIMESTAMP
                    }, merge=True)

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
        }
    }
    splitted = task_id.split('/')
    workflow_id, unique_id = splitted[0], '/'.join(splitted[:-1]) # unique_id without timestamp
    payload = {
        "unique_id": unique_id,
        "data": input_data,
        "endpoint": f"{Config.DIFY_API_ENDPOINT}/workflows/{workflow_id}/run",
    }

    task["http_request"]["body"] = json.dumps(payload).encode()
    task["name"] = f"{parent}/tasks/{task_id}"

    try:
        response = tasks_client.create_task(request={"parent": parent, "task": task})
        logging.info(f"Created task: {response.name} on dify workflow {workflow_id}")
    except Exception as e:
        if "ALREADY_EXISTS" in str(e):
            logging.warning(f"Task for ID {unique_id} likely already exists. Skipping.")
        else:
            logging.error(f"Error creating task for ID {unique_id}: {e}")
            raise
