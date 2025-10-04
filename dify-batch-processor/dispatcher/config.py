import os

class Config:
    """Configuration settings for the Dispatcher service."""
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    LOCATION = os.getenv("GCP_LOCATION")
    FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "dify_batch_process_status")
    QUEUE_NAME = os.getenv("QUEUE_NAME")
    WORKER_URL = os.getenv("WORKER_URL")
    FUNCTION_SERVICE_ACCOUNT_EMAIL = os.getenv("FUNCTION_SERVICE_ACCOUNT_EMAIL")
    
    # The maximum number of workflows allowed to be in 'PROCESSING' state concurrently.
    MAX_CONCURRENT_WORKFLOWS = int(os.getenv("MAX_CONCURRENT_WORKFLOWS", 2))
