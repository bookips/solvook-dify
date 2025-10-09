# --- Cloud Tasks Queue ---
resource "google_cloud_tasks_queue" "dify_batch_processor_queue" {
  project  = var.project_id
  location = var.location
  name     = "${var.name_prefix}-queue"

  retry_config {
    max_attempts  = 3
    min_backoff   = "30s"
    max_backoff   = "3600s"
    max_doublings = 2
  }

  rate_limits {
    max_dispatches_per_second = 1
    max_concurrent_dispatches = 2
  }
}

# --- GCS Buckets for Cloud Functions Source ---
resource "google_storage_bucket" "loader_bucket" {
  project       = var.project_id
  name          = "dify-batch-processor-loader"
  location      = var.location
  force_destroy = true
}

resource "google_storage_bucket" "worker_bucket" {
  project       = var.project_id
  name          = "dify-batch-processor-worker"
  location      = var.location
  force_destroy = true
}

resource "google_storage_bucket" "poller_bucket" {
  project       = var.project_id
  name          = "dify-batch-processor-poller"
  location      = var.location
  force_destroy = true
}

resource "google_storage_bucket" "dispatcher_bucket" {
  project       = var.project_id
  name          = "dify-batch-processor-dispatcher"
  location      = var.location
  force_destroy = true
}

# --- Source Code Archiving ---

# 1. Loader Source
data "archive_file" "loader_source" {
  type        = "zip"
  output_path = "/tmp/loader_source.zip"

  source {
    content  = file("${path.module}/../../../dify-batch-processor/loader/main.py")
    filename = "main.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/loader/config.py")
    filename = "config.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/loader/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/shared/__init__.py")
    filename = "shared/__init__.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/shared/utils.py")
    filename = "shared/utils.py"
  }
}

resource "google_storage_bucket_object" "loader_source_object" {
  name   = "source/loader-source-${data.archive_file.loader_source.output_md5}.zip"
  bucket = google_storage_bucket.loader_bucket.name
  source = data.archive_file.loader_source.output_path
}

# 2. Worker Source
data "archive_file" "worker_source" {
  type        = "zip"
  output_path = "/tmp/worker_source.zip"

  source {
    content  = file("${path.module}/../../../dify-batch-processor/worker/main.py")
    filename = "main.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/worker/config.py")
    filename = "config.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/worker/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/shared/__init__.py")
    filename = "shared/__init__.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/shared/utils.py")
    filename = "shared/utils.py"
  }
}

resource "google_storage_bucket_object" "worker_source_object" {
  name   = "source/worker-source-${data.archive_file.worker_source.output_md5}.zip"
  bucket = google_storage_bucket.worker_bucket.name
  source = data.archive_file.worker_source.output_path
}

# 3. Poller Source
data "archive_file" "poller_source" {
  type        = "zip"
  output_path = "/tmp/poller_source.zip"

  source {
    content  = file("${path.module}/../../../dify-batch-processor/poller/main.py")
    filename = "main.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/poller/config.py")
    filename = "config.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/poller/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/shared/__init__.py")
    filename = "shared/__init__.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/shared/utils.py")
    filename = "shared/utils.py"
  }
}

resource "google_storage_bucket_object" "poller_source_object" {
  name   = "source/poller-source-${data.archive_file.poller_source.output_md5}.zip"
  bucket = google_storage_bucket.poller_bucket.name
  source = data.archive_file.poller_source.output_path
}

# 4. Dispatcher Source
data "archive_file" "dispatcher_source" {
  type        = "zip"
  output_path = "/tmp/dispatcher_source.zip"

  source {
    content  = file("${path.module}/../../../dify-batch-processor/dispatcher/main.py")
    filename = "main.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/dispatcher/config.py")
    filename = "config.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/dispatcher/requirements.txt")
    filename = "requirements.txt"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/shared/__init__.py")
    filename = "shared/__init__.py"
  }
  source {
    content  = file("${path.module}/../../../dify-batch-processor/shared/utils.py")
    filename = "shared/utils.py"
  }
}

resource "google_storage_bucket_object" "dispatcher_source_object" {
  name   = "source/dispatcher-source-${data.archive_file.dispatcher_source.output_md5}.zip"
  bucket = google_storage_bucket.dispatcher_bucket.name
  source = data.archive_file.dispatcher_source.output_path
}


# --- Cloud Functions (2nd Gen) ---

# 1. Data Loader Service
resource "google_cloudfunctions2_function" "loader" {
  project     = var.project_id
  location    = var.location
  name        = "${var.name_prefix}-loader"
  description = "Data Loader Service"
  labels = {
    "source-generation" = google_storage_bucket_object.loader_source_object.generation
  }

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
    max_instance_count    = 5
    min_instance_count    = 0
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = var.function_service_account_email
    environment_variables = {
      GCP_PROJECT_ID                      = var.project_id
      GCP_LOCATION                        = var.location
      SPREADSHEET_ID                      = var.spreadsheet_id
      SHEET_NAME                          = var.sheet_name
      UNIQUE_ID_COLUMN                    = var.unique_id_column
      FIRESTORE_COLLECTION                = var.firestore_collection
      PASSAGE_ANALYSIS_WORKFLOW_ID        = var.passage_analysis_workflow_id
      PASSAGE_WORKBOOK_WORKFLOW_ID        = var.passage_workbook_workflow_id
      DIFY_API_ENDPOINT                   = var.dify_api_endpoint
      GOOGLE_SHEETS_CREDENTIALS_SECRET_ID = var.google_sheets_credentials_secret_id
    }
  }
}
# 2. Dify Worker Service
resource "google_cloudfunctions2_function" "worker" {
  project     = var.project_id
  location    = var.location
  name        = "${var.name_prefix}-worker"
  description = "Dify Worker Service"
  labels = {
    "source-generation" = google_storage_bucket_object.worker_source_object.generation
  }

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
    max_instance_count    = 10
    min_instance_count    = 0
    available_memory      = "256Mi"
    timeout_seconds       = 630
    service_account_email = var.function_service_account_email
    environment_variables = {
      GCP_PROJECT_ID           = var.project_id
      DIFY_API_ENDPOINT        = var.dify_api_endpoint
      FIRESTORE_COLLECTION     = var.firestore_collection
      DIFY_API_TIMEOUT_MINUTES = var.dify_api_timeout_minutes
      DIFY_API_KEY_SECRET_ID   = var.dify_api_key_secret_id
    }
  }
}

# 3. Dify Poller Service
resource "google_cloudfunctions2_function" "poller" {
  project     = var.project_id
  location    = var.location
  name        = "${var.name_prefix}-poller"
  description = "Polls Dify for workflow status."
  labels = {
    "source-generation" = google_storage_bucket_object.poller_source_object.generation
  }

  build_config {
    runtime     = "python313"
    entry_point = "main"
    source {
      storage_source {
        bucket = google_storage_bucket.poller_bucket.name
        object = google_storage_bucket_object.poller_source_object.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    min_instance_count    = 0
    available_memory      = "256Mi"
    timeout_seconds       = 300
    service_account_email = var.function_service_account_email
    environment_variables = {
      GCP_PROJECT_ID               = var.project_id
      FIRESTORE_COLLECTION         = var.firestore_collection
      DIFY_API_ENDPOINT            = var.dify_api_endpoint
      DIFY_API_KEY_SECRET_ID       = var.dify_api_key_secret_id
      PROCESSING_TIMEOUT_MINUTES   = var.processing_timeout_minutes
      AWS_S3_BUCKET                = var.aws_s3_bucket
      PASSAGE_ANALYSIS_WORKFLOW_ID = var.passage_analysis_workflow_id
      PASSAGE_WORKBOOK_WORKFLOW_ID = var.passage_workbook_workflow_id
      AWS_ACCESS_KEY_ID            = var.aws_access_key_id
      AWS_SECRET_ACCESS_KEY        = var.aws_secret_access_key
    }
  }
}

# 4. Dify Dispatcher Service
resource "google_cloudfunctions2_function" "dispatcher" {
  project     = var.project_id
  location    = var.location
  name        = "${var.name_prefix}-dispatcher"
  description = "Dispatches tasks based on current workflow concurrency."
  labels = {
    "source-generation" = google_storage_bucket_object.dispatcher_source_object.generation
  }

  build_config {
    runtime     = "python313"
    entry_point = "main"
    source {
      storage_source {
        bucket = google_storage_bucket.dispatcher_bucket.name
        object = google_storage_bucket_object.dispatcher_source_object.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    min_instance_count    = 0
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = var.function_service_account_email
    environment_variables = {
      GCP_PROJECT_ID                 = var.project_id
      GCP_LOCATION                   = var.location
      FIRESTORE_COLLECTION           = var.firestore_collection
      QUEUE_NAME                     = google_cloud_tasks_queue.dify_batch_processor_queue.name
      WORKER_URL                     = google_cloudfunctions2_function.worker.service_config[0].uri
      FUNCTION_SERVICE_ACCOUNT_EMAIL = var.function_service_account_email
      MAX_CONCURRENT_WORKFLOWS       = var.max_concurrent_workflows
    }
  }
}

# --- Schedulers ---

resource "google_cloud_scheduler_job" "poller_scheduler" {
  project   = var.project_id
  region    = var.location
  name      = "${var.name_prefix}-poller-scheduler"
  schedule  = "*/3 * * * *" # Every 3 minutes
  time_zone = "Etc/UTC"

  http_target {
    uri         = google_cloudfunctions2_function.poller.service_config[0].uri
    http_method = "POST"
    oidc_token {
      service_account_email = var.function_service_account_email
    }
  }
}

resource "google_cloud_scheduler_job" "dispatcher_scheduler" {
  project   = var.project_id
  region    = var.location
  name      = "${var.name_prefix}-dispatcher-scheduler"
  schedule  = "* * * * *" # Every minute
  time_zone = "Etc/UTC"

  http_target {
    uri         = google_cloudfunctions2_function.dispatcher.service_config[0].uri
    http_method = "POST"
    oidc_token {
      service_account_email = var.function_service_account_email
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

# Allow the function's service account (used by Cloud Scheduler) to invoke the Loader service
resource "google_cloud_run_v2_service_iam_member" "loader_invoker" {
  project  = var.project_id
  location = var.location
  name     = google_cloudfunctions2_function.loader.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.function_service_account_email}"
}

# Allow Cloud Tasks to invoke the Worker Cloud Run service
resource "google_cloud_run_v2_service_iam_member" "worker_invoker" {
  project  = var.project_id
  location = var.location
  name     = google_cloudfunctions2_function.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.function_service_account_email}"
}

# Allow Cloud Scheduler to invoke the Poller Cloud Run service
resource "google_cloud_run_v2_service_iam_member" "poller_invoker" {
  project  = var.project_id
  location = var.location
  name     = google_cloudfunctions2_function.poller.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.function_service_account_email}"
}

# Allow Cloud Scheduler to invoke the Dispatcher Cloud Run service
resource "google_cloud_run_v2_service_iam_member" "dispatcher_invoker" {
  project  = var.project_id
  location = var.location
  name     = google_cloudfunctions2_function.dispatcher.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.function_service_account_email}"
}
