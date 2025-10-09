variable "project_id" {
  description = "The GCP project ID."
  type        = string
}

variable "location" {
  description = "The GCP location (region) for the resources."
  type        = string
}

variable "name_prefix" {
  description = "A prefix to apply to resource names."
  type        = string
  default     = "dify-batch-processor"
}

variable "firestore_collection" {
  description = "The name of the Firestore collection for status tracking."
  type        = string
  default     = "dify_batch_process_status"
}

variable "spreadsheet_id" {
  description = "The ID of the Google Sheet to process."
  type        = string
}

variable "sheet_name" {
  description = "The name of the sheet within the spreadsheet."
  type        = string
}

variable "unique_id_column" {
  description = "The column index (0-based) or 'ROW_NUMBER' to use as a unique ID."
  type        = string
  default     = "id"
}

variable "dify_api_endpoint" {
  description = "The endpoint URL for the self-hosted Dify workflow API."
  type        = string
}

variable "dify_api_key_secret_id" {
  description = "The ID of the Secret Manager secret containing the Dify API key."
  type        = string
}

variable "dify_api_timeout_minutes" {
  description = "The timeout in minutes for the Dify API call in the worker function."
  type        = number
  default     = 10
}

variable "google_sheets_credentials_secret_id" {
  description = "The ID of the Secret Manager secret containing the Google Sheets service account credentials."
  type        = string
}

variable "function_service_account_email" {
  description = "The email of the service account for the Cloud Functions."
  type        = string
}

variable "passage_analysis_workflow_id" {
  description = "The workflow ID for passage analysis."
  type        = string
}

variable "passage_workbook_workflow_id" {
  description = "The workflow ID for passage workbook creation."
  type        = string
}

variable "slack_webhook_secret_name" {
  type        = string
  description = "The name of the secret for the Slack webhook URL."
  default     = null
}

variable "slack_channel_name" {
  type        = string
  description = "The name of the Slack channel to send notifications to."
  default     = null
}

variable "processing_timeout_minutes" {
  description = "The maximum time in minutes a job can be in the 'PROCESSING' state before being marked as FAILED."
  type        = number
  default     = 30
}

variable "slack_webhook_token" {
  description = "The Slack webhook token for notifications."
  type        = string
  sensitive   = true
}


variable "max_concurrent_workflows" {
  description = "The maximum number of workflows to run concurrently."
  type        = number
  default     = 2
}

variable "aws_s3_bucket" {
  description = "the result object buccket name"
  type        = string
  default     = "solvook-creator"
}

variable "aws_access_key_id" {
  description = "The AWS access key ID for S3."
  type        = string
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "The AWS secret access key for S3."
  type        = string
  sensitive   = true
}
