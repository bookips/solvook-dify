import os

class Config:
    """Configuration class for the worker."""
    # Dify API Info
    DIFY_API_ENDPOINT = os.environ.get("DIFY_API_ENDPOINT")
    DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
    DIFY_API_TIMEOUT_MINUTES = int(os.environ.get("DIFY_API_TIMEOUT_MINUTES", 5))

    # Firestore Info
    FIRESTORE_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "dify_batch_process_status")