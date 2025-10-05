import os

class Config:
    """Configuration settings for the Poller service."""
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "dify_batch_process_status")
    DIFY_API_ENDPOINT = os.getenv("DIFY_API_ENDPOINT")
    DIFY_API_KEY_SECRET_ID = os.getenv("DIFY_API_KEY_SECRET_ID")
    PROCESSING_TIMEOUT_MINUTES = int(os.getenv("PROCESSING_TIMEOUT_MINUTES", 30))