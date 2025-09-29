import os

class Config:
    """Configuration class for the worker."""
    # GCP Project Info
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
    DATASTORE_EMULATOR_HOST = os.environ.get("DATASTORE_EMULATOR_HOST")

    # Dify API Info
    DIFY_API_ENDPOINT = os.environ.get("DIFY_API_ENDPOINT")
    DIFY_API_KEY_SECRET_ID = os.environ.get("DIFY_API_KEY_SECRET_ID")
    DIFY_API_TIMEOUT_MINUTES = int(os.environ.get("DIFY_API_TIMEOUT_MINUTES", 5))

    # Firestore Info
    FIRESTORE_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "dify_batch_process_status")