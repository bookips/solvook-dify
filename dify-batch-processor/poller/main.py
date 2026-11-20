import json
import logging
import boto3
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import functions_framework

load_dotenv()

from config import Config
from shared.utils import get_entities_from_datastore, initialize_dify_api_keys, update_datastore

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

try:
    DIFY_API_KEYS_BY_WORKFLOW_ID = initialize_dify_api_keys(Config.PROJECT_ID, Config.DIFY_API_KEY_SECRET_ID)
except Exception:
    DIFY_API_KEYS_BY_WORKFLOW_ID = None

def check_object_exists(bucket: str, object_name: str) -> bool:
    """
    Checks if an object exists in a AWS bucket.
    """
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
        region_name="ap-northeast-2"
    )
    try:
        s3_client.head_object(Bucket=bucket, Key=object_name)
        return True
    except s3_client.exceptions.ClientError:
        return False


# Substrings of a Dify run `error` that mean the plugin daemon was not ready yet
# (cold start: plugins are still being launched). Allowlist: anything else is FAILED.
TRANSIENT_ERROR_MARKERS = (
    "no available node",
    "plugin runtime not found",
)


def is_retryable(error_message: str | None) -> bool:
    """True when a failed run's error is a transient plugin-daemon error worth re-running."""
    if not error_message:
        return False
    return any(marker in error_message for marker in TRANSIENT_ERROR_MARKERS)


def handle_timeout(unique_id: str, workflow_id: str, job_data: dict, elapsed_minutes: int = None):
    """Handles jobs that have timed out."""
    minutes = elapsed_minutes or Config.PROCESSING_TIMEOUT_MINUTES
    logging.warning(f"[{unique_id}] Job has been in 'PROCESSING' state for over {minutes} minute(s)")
    
    object_name = None
    match workflow_id:
        case Config.HIGH_PASSAGE_ANALYSIS_WORKFLOW_ID | Config.MIDDLE_PASSAGE_ANALYSIS_WORKFLOW_ID:
            passage_group_id = job_data.get("passageGroupId")
            object_name = f"passage-analysis/{passage_group_id}/result.json"
        case Config.HIGH_PASSAGE_WORKBOOK_WORKFLOW_ID | Config.MIDDLE_PASSAGE_WORKBOOK_WORKFLOW_ID:
            passage_group_id = job_data.get("passageGroupId")
            passage_id = job_data.get("passageId")
            object_name = f"passage-workbook/{passage_group_id}/{passage_id}/result.json"

    if object_name is None:
        update_datastore(unique_id, 'FAILED', data={"message": f"Job timed out, but workflow_id '{workflow_id}' is unknown or data is missing."})
        return

    logging.info(f"[{unique_id}] Checking for result object in S3: s3://{Config.AWS_S3_BUCKET}/{object_name}")                        
    if check_object_exists(Config.AWS_S3_BUCKET, object_name):
        update_datastore(unique_id, 'SUCCESS', data={"message": f"Found s3://{Config.AWS_S3_BUCKET}/{object_name}"})
    else:
        update_datastore(unique_id, 'FAILED', data={"message": f"Job timed out in poller after {minutes} minute(s)."})


@functions_framework.http
def main(request: dict):
    if not DIFY_API_KEYS_BY_WORKFLOW_ID:
        logging.error("DIFY_API_KEYS_BY_WORKFLOW_ID not initialized. Aborting.")
        return "Internal Server Error: Service is not configured.", 500

    processing_jobs = get_entities_from_datastore("status", "PROCESSING", operator="=", key_only=False)
    if not processing_jobs:
        logging.info("No jobs in 'PROCESSING' state found. Poller exiting.")
        return "No jobs to process.", 200

    logging.info(f"Found {len(processing_jobs)} job(s) to poll.")

    for job in processing_jobs:
        unique_id = job.key.name
        workflow_run_id = job.get("workflow_run_id")
        workflow_id = job.get("workflow_id")

        # Timeout logic
        last_updated = job.get("timestamp")

        if last_updated:
            # Ensure last_updated is timezone-aware (Datastore stores UTC)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            time_difference = now - last_updated
            
            if time_difference > timedelta(minutes=Config.PROCESSING_TIMEOUT_MINUTES):
                job_data = json.loads(job.get("data", "{}"))
                handle_timeout(unique_id, workflow_id, job_data)
                continue

        if not workflow_run_id and workflow_id:
            if last_updated:
                now = datetime.now(timezone.utc)
                no_runid_elapsed = now - last_updated
                if no_runid_elapsed > timedelta(minutes=Config.PROCESSING_NO_RUNID_TIMEOUT_MINUTES):
                    elapsed_min = int(no_runid_elapsed.total_seconds() / 60)
                    logging.warning(f"[{unique_id}] Job missing 'workflow_run_id' for {elapsed_min} minute(s). Checking S3 for results.")
                    job_data = json.loads(job.get("data", "{}"))
                    handle_timeout(unique_id, workflow_id, job_data, elapsed_minutes=elapsed_min)
                else:
                    logging.info(f"[{unique_id}] Job missing 'workflow_run_id', waiting for no-runid timeout ({Config.PROCESSING_NO_RUNID_TIMEOUT_MINUTES}m).")
            continue

        if not workflow_run_id or not workflow_id:
            logging.warning(f"[{unique_id}] Job is 'PROCESSING' but missing 'workflow_run_id' or 'workflow_id'. Skipping.")
            continue

        try:
            api_key = DIFY_API_KEYS_BY_WORKFLOW_ID.get(workflow_id)
            if not api_key:
                raise ValueError(f"No API key found for workflow_id: {workflow_id}")

            url = f"{Config.DIFY_API_ENDPOINT}/{workflow_run_id}"
            headers = {"Authorization": f"Bearer {api_key}"}

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            workflow_status = data.get("status")

            if workflow_status == "succeeded" or workflow_status == "partial-succeeded":
                logging.info(f"[{unique_id}] Workflow run {workflow_run_id} succeeded.")
                update_datastore(unique_id, 'SUCCESS', data={"result": str(data)})
            elif workflow_status == "failed":
                error_message = data.get("error") or "Dify workflow failed."
                retry_count = job.get("retry_count") or 0
                if is_retryable(error_message) and retry_count < Config.MAX_TRANSIENT_RETRIES:
                    attempt = retry_count + 1
                    logging.warning(
                        f"[{unique_id}] Workflow run {workflow_run_id} failed with a transient plugin error. "
                        f"Re-queuing as PENDING (retry {attempt}/{Config.MAX_TRANSIENT_RETRIES})."
                    )
                    update_datastore(unique_id, 'PENDING', data={
                        "workflow_run_id": None,
                        "retry_count": attempt,
                        "message": f"Transient retry {attempt}/{Config.MAX_TRANSIENT_RETRIES}: {error_message}",
                        "result": str(data),
                    })
                else:
                    logging.error(f"[{unique_id}] Workflow run {workflow_run_id} failed.")
                    update_datastore(unique_id, 'FAILED', data={"message": error_message, "result": str(data)})
            else:
                logging.info(f"[{unique_id}] Workflow run {workflow_run_id} is still in progress (status: {workflow_status}).")

        except Exception as e:
            logging.error(f"[{unique_id}] An unexpected error occurred for workflow {workflow_run_id}: {e}", exc_info=True)
            update_datastore(unique_id, 'FAILED', data={"message": f"Polling failed: {e}"})

    return f"Polled {len(processing_jobs)} jobs.", 200
