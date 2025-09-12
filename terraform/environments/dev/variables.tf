variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "dify_version" {
  type = string
}

variable "dify_sandbox_version" {
  type = string
}

variable "cloud_run_ingress" {
  type = string
}

variable "nginx_repository_id" {
  type = string
}

variable "web_repository_id" {
  type = string
}

variable "api_repository_id" {
  type = string
}

variable "plugin_daemon_repository_id" {
  type = string
}

variable "sandbox_repository_id" {
  type = string
}

variable "secret_key_secret_name" {
  type        = string
  description = "The name of the secret for SECRET_KEY."
  default     = "dify-secret-key"
}

variable "db_username" {
  type = string
}

variable "db_password_secret_name" {
  type        = string
  description = "The name of the secret for the database password."
  default     = "dify-db-password"
}

variable "db_port" {
  type = string
}

variable "db_database" {
  type = string
}

variable "db_database_plugin" {
  type = string
}

variable "db_deletion_protection" {
  type = bool
}

variable "storage_type" {
  type = string
}

variable "google_storage_bucket_name" {
  type = string
}

variable "vector_store" {
  type = string
}

variable "indexing_max_segmentation_tokens_length" {
  type = number
}

variable "plugin_daemon_key_secret_name" {
  type        = string
  description = "The name of the secret for PLUGIN_DAEMON_KEY."
  default     = "dify-plugin-daemon-key"
}

variable "plugin_dify_inner_api_key_secret_name" {
  type        = string
  description = "The name of the secret for PLUGIN_DIFY_INNER_API_KEY."
  default     = "dify-plugin-dify-inner-api-key"
}

variable "aws_access_key_id_secret_name" {
  type        = string
  description = "The name of the secret in Google Secret Manager holding the AWS Access Key ID."
  default     = "dify-aws-access-key-id"
}

variable "aws_secret_access_key_secret_name" {
  type        = string
  description = "The name of the secret in Google Secret Manager holding the AWS Secret Access Key."
  default     = "dify-aws-secret-access-key"
}

variable "dify_plugin_daemon_version" {
  type = string
}

variable "min_instance_count" {
  type = number
}

variable "max_instance_count" {
  type = number
}

variable "slack_webhook_secret_name" {
  type        = string
  description = "The name of the secret for the Slack webhook URL."
  default     = "dify-slack-webhook-url"
}

variable "slack_channel_name" {
  type = string
}
