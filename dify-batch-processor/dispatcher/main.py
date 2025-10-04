from datetime import datetime
import logging
import json
import functions_framework
from google.cloud import datastore, tasks_v2

from config import Config
from shared.utils import update_datastore, get_entities_from_datastore

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

DB = datastore.Client(project=Config.PROJECT_ID)
tasks_client = tasks_v2.CloudTasksClient()

@functions_framework.http
def main(request: dict):
    """
    Periodically triggered to dispatch new tasks based on current system load.
    1. Counts jobs in 'PROCESSING' state.
    2. Calculates available capacity based on MAX_CONCURRENT_WORKFLOWS.
    3. Fetches 'PENDING' jobs to fill the capacity.
    4. Creates Cloud Tasks for them and updates their status to 'QUEUED'.
    """
    try:
        # 1. Count currently processing jobs
        processing_jobs_count = len(get_entities_from_datastore(
            "status", "PROCESSING", operator="=", key_only=True)
        )

        # 2. Calculate available slots
        available_slots = Config.MAX_CONCURRENT_WORKFLOWS - processing_jobs_count
        logging.info(f"Current processing: {processing_jobs_count}, Max concurrency: {Config.MAX_CONCURRENT_WORKFLOWS}, Available slots: {available_slots}")

        if available_slots <= 0:
            logging.info("No available slots. Exiting.")
            return "No available slots.", 200

        # 3. Fetch pending jobs to fill available slots
        jobs_to_dispatch = get_entities_from_datastore(
            "status", "PENDING", operator="=", limit=available_slots
        )

        if not jobs_to_dispatch:
            logging.info("No pending jobs to dispatch. Exiting.")
            return "No pending jobs.", 200

        logging.info(f"Found {len(jobs_to_dispatch)} pending job(s) to dispatch.")

        parent = tasks_client.queue_path(Config.PROJECT_ID, Config.LOCATION, Config.QUEUE_NAME)

        # 4. Create tasks and update status
        for job in jobs_to_dispatch:
            unique_id = job.key.name
            try:
                task_payload = {
                    "unique_id": unique_id,
                    "data": json.loads(job.get("data", "{}")),
                    "workflow_id": job.get("workflow_id")
                }

                task = {
                    "http_request": {
                        "http_method": tasks_v2.HttpMethod.POST,
                        "url": Config.WORKER_URL,
                        "headers": {"Content-type": "application/json"},
                        "body": json.dumps(task_payload).encode(),
                        "oidc_token": {
                            "service_account_email": Config.FUNCTION_SERVICE_ACCOUNT_EMAIL,
                        },
                    },
                    "name": f"{parent}/tasks/{unique_id}-{int(datetime.now().timestamp())}"
                }
                
                tasks_client.create_task(parent=parent, task=task)
                update_datastore(unique_id, 'QUEUED')
                logging.info(f"[{unique_id}] Task created and status updated to QUEUED.")

            except Exception as e:
                logging.error(f"[{unique_id}] Failed to create task or update status: {e}", exc_info=True)
                update_datastore(unique_id, 'FAILED', data={"message": f"Dispatcher failed: {e}"})

        return f"Dispatched {len(jobs_to_dispatch)} tasks.", 200

    except Exception as e:
        logging.critical(f"A critical error occurred in the dispatcher: {e}", exc_info=True)
        return "Internal Server Error", 500
