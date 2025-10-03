locals {
  shared_env_vars = {
    "SECRET_KEY"                                 = data.google_secret_manager_secret_version.secret_key.secret_data
    "LOG_LEVEL"                                  = "INFO"
    "CONSOLE_WEB_URL"                            = ""
    "CONSOLE_API_URL"                            = ""
    "SERVICE_API_URL"                            = ""
    "APP_WEB_URL"                                = ""
    "CHECK_UPDATE_URL"                           = "https://updates.dify.ai"
    "OPENAI_API_BASE"                            = "https://api.openai.com/v1"
    "FILES_URL"                                  = ""
    "MIGRATION_ENABLED"                          = "true"
    "CELERY_BROKER_URL"                          = "redis://${module.redis.redis_host}:${module.redis.redis_port}/1"
    "WEB_API_CORS_ALLOW_ORIGINS"                 = "*"
    "CONSOLE_CORS_ALLOW_ORIGINS"                 = "*"
    "DB_USERNAME"                                = var.db_username
    "DB_PASSWORD"                                = data.google_secret_manager_secret_version.db_password.secret_data
    "DB_HOST"                                    = module.cloudsql.cloudsql_internal_ip
    "DB_PORT"                                    = var.db_port
    "SQLALCHEMY_POOL_SIZE"                       = "50"
    "SQLALCHEMY_POOL_RECYCLE"                    = "3600"
    "STORAGE_TYPE"                               = var.storage_type
    "GOOGLE_STORAGE_BUCKET_NAME"                 = module.storage.storage_bucket_name
    "GOOGLE_STORAGE_SERVICE_ACCOUNT_JSON_BASE64" = module.storage.storage_admin_key_base64
    "REDIS_HOST"                                 = module.redis.redis_host
    "REDIS_PORT"                                 = module.redis.redis_port
    "VECTOR_STORE"                               = var.vector_store
    "PGVECTOR_HOST"                              = module.cloudsql.cloudsql_internal_ip
    "PGVECTOR_PORT"                              = "5432"
    "PGVECTOR_USER"                              = var.db_username
    "PGVECTOR_PASSWORD"                          = data.google_secret_manager_secret_version.db_password.secret_data
    "PGVECTOR_DATABASE"                          = var.db_database
    "CODE_EXECUTION_ENDPOINT"                    = module.cloudrun.dify_sandbox_url
    "CODE_EXECUTION_API_KEY"                     = "dify-sandbox"
    "INDEXING_MAX_SEGMENTATION_TOKENS_LENGTH"    = var.indexing_max_segmentation_tokens_length
    "PLUGIN_DAEMON_KEY"                          = data.google_secret_manager_secret_version.plugin_daemon_key.secret_data
    "PLUGIN_DIFY_INNER_API_KEY"                  = data.google_secret_manager_secret_version.plugin_dify_inner_api_key.secret_data
    "CODE_MAX_DEPTH"                             = "10"
    "CODE_MAX_STRING_ARRAY_LENGTH"               = "500"
    "CODE_MAX_OBJECT_ARRAY_LENGTH"               = "500"
    "CODE_EXECUTION_TIMEOUT"                     = "10"
    "WORKFLOW_MAX_EXECUTION_STEPS"               = "1000"
    "WORKFLOW_MAX_EXECUTION_TIME"                = "3000"
    "APP_MAX_EXECUTION_TIME"                     = "3000"
    "AWS_REGION"                                 = "ap-northeast-2"
    "AWS_ACCESS_KEY_ID"                          = data.google_secret_manager_secret_version.aws_access_key_id.secret_data
    "AWS_SECRET_ACCESS_KEY"                      = data.google_secret_manager_secret_version.aws_secret_access_key.secret_data
  }
}

data "google_secret_manager_secret_version" "aws_access_key_id" {
  project = var.project_id
  secret  = var.aws_access_key_id_secret_name
}

data "google_secret_manager_secret_version" "aws_secret_access_key" {
  project = var.project_id
  secret  = var.aws_secret_access_key_secret_name
}

data "google_secret_manager_secret_version" "secret_key" {
  project = var.project_id
  secret  = var.secret_key_secret_name
}

data "google_secret_manager_secret_version" "db_password" {
  project = var.project_id
  secret  = var.db_password_secret_name
}

data "google_secret_manager_secret_version" "plugin_daemon_key" {
  project = var.project_id
  secret  = var.plugin_daemon_key_secret_name
}

data "google_secret_manager_secret_version" "plugin_dify_inner_api_key" {
  project = var.project_id
  secret  = var.plugin_dify_inner_api_key_secret_name
}

data "google_secret_manager_secret_version" "slack_webhook" {
  count   = var.slack_webhook_secret_name != null ? 1 : 0
  project = var.project_id
  secret  = var.slack_webhook_secret_name
}

data "google_compute_network" "default" {
  name = "default"
}

data "google_compute_subnetwork" "default" {
  name   = "default"
  region = var.region
}

module "cloudrun" {
  source = "../../modules/cloudrun"

  project_id                  = var.project_id
  region                      = var.region
  dify_version                = var.dify_version
  dify_sandbox_version        = var.dify_sandbox_version
  cloud_run_ingress           = var.cloud_run_ingress
  nginx_repository_id         = var.nginx_repository_id
  web_repository_id           = var.web_repository_id
  api_repository_id           = var.api_repository_id
  sandbox_repository_id       = var.sandbox_repository_id
  vpc_network_name            = data.google_compute_network.default.name
  vpc_subnet_name             = data.google_compute_subnetwork.default.name
  plugin_daemon_repository_id = var.plugin_daemon_repository_id
  plugin_daemon_key           = data.google_secret_manager_secret_version.plugin_daemon_key.secret_data
  plugin_dify_inner_api_key   = data.google_secret_manager_secret_version.plugin_dify_inner_api_key.secret_data
  dify_plugin_daemon_version  = var.dify_plugin_daemon_version
  db_database                 = var.db_database
  db_database_plugin          = var.db_database_plugin
  filestore_ip_address        = module.filestore.filestore_ip_address
  filestore_fileshare_name    = module.filestore.filestore_fileshare_name
  shared_env_vars             = local.shared_env_vars
  min_instance_count          = var.min_instance_count
  max_instance_count          = var.max_instance_count
  slack_channel_name          = var.slack_channel_name
  slack_webhook_token         = var.slack_webhook_secret_name != null ? data.google_secret_manager_secret_version.slack_webhook[0].secret_data : null

  depends_on = [google_project_service.enabled_services]
}

module "cloudsql" {
  source = "../../modules/cloudsql"

  project_id          = var.project_id
  region              = var.region
  db_username         = var.db_username
  db_password         = data.google_secret_manager_secret_version.db_password.secret_data
  deletion_protection = var.db_deletion_protection

  vpc_network_name = data.google_compute_network.default.name

  depends_on = [google_project_service.enabled_services]
}

module "redis" {
  source = "../../modules/redis"

  project_id = var.project_id
  region     = var.region

  vpc_network_name = data.google_compute_network.default.name

  depends_on = [google_project_service.enabled_services]
}

module "storage" {
  source = "../../modules/storage"

  project_id                 = var.project_id
  region                     = var.region
  google_storage_bucket_name = var.google_storage_bucket_name

  depends_on = [google_project_service.enabled_services]
}

module "filestore" {
  source = "../../modules/filestore"

  region = var.region

  vpc_network_name = data.google_compute_network.default.name

  depends_on = [google_project_service.enabled_services]
}

module "registry" {
  source = "../../modules/registry"

  project_id                  = var.project_id
  region                      = var.region
  nginx_repository_id         = var.nginx_repository_id
  web_repository_id           = var.web_repository_id
  api_repository_id           = var.api_repository_id
  sandbox_repository_id       = var.sandbox_repository_id
  plugin_daemon_repository_id = var.plugin_daemon_repository_id

  depends_on = [google_project_service.enabled_services]
}

locals {
  services = [
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "redis.googleapis.com",
    "vpcaccess.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_project_service" "enabled_services" {
  for_each = toset(local.services)
  project  = var.project_id
  service  = each.value
}

# --- Dify Data Processor ---
# This service account will be used to run the Cloud Functions.
# It needs permissions for Firestore, Cloud Tasks, Secret Manager, and Google Sheets.
resource "google_service_account" "dify_batch_processor_sa" {
  project      = var.project_id
  account_id   = "dify-batch-processor-sa"
  display_name = "Dify Batch Processor Service Account"
}

# Grant necessary roles to the service account.
resource "google_project_iam_member" "dify_batch_processor_sa_roles" {
  for_each = toset([
    "roles/datastore.user",
    "roles/cloudtasks.enqueuer",
    "roles/secretmanager.secretAccessor"
    # "roles/run.invoker" is now granted on a per-service basis for security.
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.dify_batch_processor_sa.email}"
}

# Allow the service account to "act as" itself, which is required for creating
# Cloud Tasks with OIDC tokens that use the same service account.
resource "google_service_account_iam_member" "dify_batch_processor_sa_actas_self" {
  service_account_id = google_service_account.dify_batch_processor_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.dify_batch_processor_sa.email}"
}


module "dify_batch_processor" {
  source = "../../modules/dify_batch_processor"

  project_id                          = var.project_id
  location                            = var.region
  spreadsheet_id                      = var.spreadsheet_id
  sheet_name                          = var.sheet_name
  unique_id_column                    = var.unique_id_column
  dify_api_endpoint                   = var.dify_api_endpoint
  dify_api_key_secret_id              = var.dify_api_key_secret_id
  dify_api_timeout_minutes            = var.dify_api_timeout_minutes
  google_sheets_credentials_secret_id = var.google_sheets_credentials_secret_id
  function_service_account_email      = google_service_account.dify_batch_processor_sa.email
  passage_analysis_workflow_id        = var.passage_analysis_workflow_id
  passage_workbook_workflow_id        = var.passage_workbook_workflow_id
  slack_channel_name                  = var.slack_channel_name
  slack_webhook_token                 = var.slack_webhook_secret_name != null ? data.google_secret_manager_secret_version.slack_webhook[0].secret_data : null

  depends_on = [
    google_project_service.enabled_services,
    google_project_iam_member.dify_batch_processor_sa_roles
  ]
}

# --- Cloud Scheduler to trigger the loader function daily ---
resource "google_cloud_scheduler_job" "dify_batch_processor_trigger" {
  project      = var.project_id
  region       = var.region
  name         = "dify-batch-processor-daily-trigger"
  description  = "Triggers the Dify Batch Processor loader function every day at midnight."
  schedule     = "0 */3 * * *" # Runs every 3 hours
  time_zone    = "Asia/Seoul"
  attempt_deadline = "320s"

  http_target {
    uri = module.dify_batch_processor.loader_service_uri
    http_method = "POST"

    oidc_token {
      service_account_email = google_service_account.dify_batch_processor_sa.email
    }
  }
}
