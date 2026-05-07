import os

class Config:
    """Configuration settings for the Worker service."""
    PROJECT_ID = os.getenv("GCP_PROJECT_ID")
    DIFY_API_ENDPOINT = os.getenv("DIFY_API_ENDPOINT")
    DIFY_API_KEY_SECRET_ID = os.getenv("DIFY_API_KEY_SECRET_ID")
    DIFY_API_TIMEOUT_MINUTES = int(os.getenv("DIFY_API_TIMEOUT_MINUTES", 10))
