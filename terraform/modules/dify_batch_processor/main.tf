# --- Cloud Tasks Queue ---
resource "google_cloud_tasks_queue" "dify_batch_processor_queue" {
  project  = var.project_id
  location = var.location
  name     = "${var.name_prefix}-queue"

  retry_config {
    max_attempts       = 3
    min_backoff        = "30s"
    max_backoff        = "3600s"
    max_doublings      = 2
  }
}

# --- GCS Buckets for Cloud Functions Source ---
resource "google_storage_bucket" "loader_bucket" {
  project       = var.project_id
  name          = "dify-batch-processor-loader"
  location      = var.location
  force_destroy = true # Set to true for easier cleanup in dev environments
}

resource "google_storage_bucket" "worker_bucket" {
  project       = var.project_id
  name          = "dify-batch-processor-worker"
  location      = var.location
  force_destroy = true # Set to true for easier cleanup in dev environments
}

# --- Cloud Functions (2nd Gen) - Deployed as Cloud Run Services ---
# Cloud Functions (2nd gen) is built on top of Cloud Run and Eventarc.
# The following resources define two functions that are automatically deployed as Cloud Run services.

# 1. Data Loader Service (triggered by HTTP)
data "archive_file" "loader_source" {
  type        = "zip"
  source_dir  = "${path.module}/../../../dify-batch-processor/loader"
  output_path = "/tmp/loader_source.zip"
}

resource "google_storage_bucket_object" "loader_source_object" {
  name   = "source/dify-loader-source.zip"
  bucket = google_storage_bucket.loader_bucket.name
  source = data.archive_file.loader_source.output_path
}

# This resource defines a 2nd gen Cloud Function, which is deployed as a Cloud Run service.
resource "google_cloudfunctions2_function" "loader" {
  project  = var.project_id
  location = var.location
  name     = "${var.name_prefix}-loader"

  build_config {
    runtime     = "python313"
    entry_point = "main"
    source {
      storage_source {
        bucket = google_storage_bucket.loader_bucket.name
        object = google_storage_bucket_object.loader_source_object.name
      }
    }
  }

  service_config {
    max_instance_count = 5
    min_instance_count = 0
    available_memory   = "256Mi"
    timeout_seconds    = 60
    service_account_email = var.function_service_account_email
    environment_variables = {
      GCP_PROJECT_ID       = var.project_id
      GCP_LOCATION         = var.location
      SPREADSHEET_ID       = var.spreadsheet_id
      SHEET_NAME           = var.sheet_name
      UNIQUE_ID_COLUMN     = var.unique_id_column
      QUEUE_NAME           = google_cloud_tasks_queue.dify_batch_processor_queue.name
      WORKER_URL           = google_cloudfunctions2_function.worker.service_config[0].uri
      FIRESTORE_COLLECTION = var.firestore_collection
      PASSAGE_ANALYSIS_WORKFLOW_ID = var.passage_analysis_workflow_id
      PASSAGE_WORKBOOK_WORKFLOW_ID = var.passage_workbook_workflow_id
    }
    secret_environment_variables {
      key        = "GOOGLE_SHEETS_CREDENTIALS"
      project_id = var.project_id
      secret     = var.google_sheets_credentials_secret_id
      version    = "latest"
    }
  }
}

# 2. Dify Worker Service (triggered by Cloud Tasks)
data "archive_file" "worker_source" {
  type        = "zip"
  source_dir  = "${path.module}/../../../dify-batch-processor/worker"
  output_path = "/tmp/worker_source.zip"
}

resource "google_storage_bucket_object" "worker_source_object" {
  name   = "source/dify-worker-source.zip"
  bucket = google_storage_bucket.worker_bucket.name
  source = data.archive_file.worker_source.output_path
}

# This resource defines a 2nd gen Cloud Function, which is deployed as a Cloud Run service.
resource "google_cloudfunctions2_function" "worker" {
  project  = var.project_id
  location = var.location
  name     = "${var.name_prefix}-worker"

  build_config {
    runtime     = "python313"
    entry_point = "main"
    source {
      storage_source {
        bucket = google_storage_bucket.worker_bucket.name
        object = google_storage_bucket_object.worker_source_object.name
      }
    }
  }

  service_config {
    max_instance_count = 10 # Set a reasonable upper limit
    min_instance_count = 0
    available_memory   = "256Mi"
    timeout_seconds    = 300 # 5 minutes for Dify API call
    service_account_email = var.function_service_account_email
    environment_variables = {
      DIFY_API_ENDPOINT          = var.dify_api_endpoint
      FIRESTORE_COLLECTION       = var.firestore_collection
      DIFY_API_TIMEOUT_MINUTES   = var.dify_api_timeout_minutes
    }
    secret_environment_variables {
      key        = "DIFY_API_KEY"
      project_id = var.project_id
      secret     = var.dify_api_key_secret_id
      version    = "latest"
    }
  }
}

# --- IAM Bindings ---

# Allow Loader to create tasks in the queue
resource "google_cloud_tasks_queue_iam_member" "loader_enqueuer" {
  project  = var.project_id
  location = var.location
  name     = google_cloud_tasks_queue.dify_batch_processor_queue.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${var.function_service_account_email}"
}

# Allow public access to the Loader Cloud Run service (e.g., for Cloud Scheduler)
resource "google_cloud_run_v2_service_iam_member" "loader_invoker" {
  project  = var.project_id
  location = var.location
  name     = google_cloudfunctions2_function.loader.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Allow Cloud Tasks to invoke the Worker Cloud Run service
resource "google_cloud_run_v2_service_iam_member" "worker_invoker" {
  project  = var.project_id
  location = var.location
  name     = google_cloudfunctions2_function.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.function_service_account_email}" # Assuming Cloud Tasks uses the same SA
}
