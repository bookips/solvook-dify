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
                logging.warning(f"[{unique_id}] Job has been in 'PROCESSING' state for over {Config.PROCESSING_TIMEOUT_MINUTES} minute(s)")
                match workflow_id:
                    case Config.PASSAGE_ANALYSIS_WORKFLOW_ID:
                        passage_group_id = job_data.get("passageGroupId")
                        object_name = f"passage_analysis/{passage_group_id}/result.json"
                    case Config.WORKBOOK_WORKFLOW_ID:
                        passage_group_id = job_data.get("passageGroupId")
                        passage_id = job_data.get("passageId")
                        object_name = f"passage-workbook/{passage_group_id}/{passage_id}/result.json"
                if check_object_exists(Config.AWS_S3_BUCKET, object_name):
                    update_datastore(unique_id, 'SUCCESS', data={"message": f"Found s3://{Config.AWS_S3_BUCKET}/{object_name}"})
                else:
                    update_datastore(unique_id, 'FAILED', data={"message": f"Job timed out in poller after {Config.PROCESSING_TIMEOUT_MINUTES} minute(s)."})
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
                logging.error(f"[{unique_id}] Workflow run {workflow_run_id} failed.")
                error_message = data.get("error", "Dify workflow failed.")
                update_datastore(unique_id, 'FAILED', data={"message": error_message, "result": str(data)})
            else:
                logging.info(f"[{unique_id}] Workflow run {workflow_run_id} is still in progress (status: {workflow_status}).")

        except Exception as e:
            logging.error(f"[{unique_id}] An unexpected error occurred for workflow {workflow_run_id}: {e}", exc_info=True)
            update_datastore(unique_id, 'FAILED', data={"message": f"Polling failed: {e}"})

    return f"Polled {len(processing_jobs)} jobs.", 200
