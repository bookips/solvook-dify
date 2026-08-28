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

variable "sandbox_repository_id" {
  type = string
}

variable "vpc_network_name" {
  type = string
}

variable "vpc_subnet_name" {
  type = string
}

variable "plugin_daemon_repository_id" {
  type = string
}

variable "plugin_daemon_key_secret_name" {
  description = "Secret Manager secret holding the plugin daemon server key. Mounted at runtime, never rendered into the service config."
  type        = string
}

variable "plugin_dify_inner_api_key_secret_name" {
  description = "Secret Manager secret holding the Dify inner API key. Mounted at runtime, never rendered into the service config."
  type        = string
}

variable "dify_plugin_daemon_version" {
  type = string
}

variable "db_database" {
  type = string
}

variable "db_database_plugin" {
  type = string
}

variable "plugin_storage_bucket_name" {
  type = string
}

variable "nfs_server_ip" {
  type = string
}

variable "shared_env_vars" {
  type = map(string)
}

variable "shared_secret_env_vars" {
  description = "Environment variable name -> Secret Manager secret id. Injected as secret references so the values never appear in the Cloud Run config or in Terraform state."
  type        = map(string)
}

variable "min_instance_count" {
  type = number
}

variable "max_instance_count" {
  type = number
}

variable "slack_channel_name" {
  type        = string
  description = "The Slack channel name to send monitoring alerts to (e.g., #dify-alerts)."
}

variable "slack_webhook_token" {
  type        = string
  description = "The Slack webhook token."
  sensitive   = true
  default     = null
}
