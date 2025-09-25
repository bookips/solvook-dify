import os

class Config:
    """Configuration class for the application."""
    # GCP Project Info
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
    LOCATION = os.environ.get("GCP_LOCATION") # e.g., 'asia-northeast3'

    # Google Sheets Info
    SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
    SHEET_NAME = os.environ.get("SHEET_NAME")
    # The column index (0-based) to be used as a unique ID for each row.
    # 행 번호를 ID로 사용하려면 'ROW_NUMBER'로 설정하세요.
    UNIQUE_ID_COLUMN = os.environ.get("id", "0") 

    # Cloud Tasks Info
    QUEUE_NAME = os.environ.get("QUEUE_NAME") # The name of the Cloud Tasks queue
    WORKER_URL = os.environ.get("WORKER_URL") # The URL of the Worker Cloud Function

    # Firestore Info
    FIRESTORE_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "dify_batch_process_status")
    DIFY_WORKFLOW_IDS_BY_CONTENT_CATEGORY = {
        "본문분석": os.environ.get("PASSAGE_ANALYSIS_WORKFLOW_ID"),
        "워크북": os.environ.get("PASSAGE_WORKBOOK_WORKFLOW_ID"),
    }
    DIFY_API_ENDPOINT = os.environ.get("DIFY_API_ENDPOINT")