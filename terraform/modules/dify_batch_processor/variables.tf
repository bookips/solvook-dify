variable "project_id" {
  description = "The ID of the Google Cloud project."
  type        = string
}

variable "location" {
  description = "The Google Cloud region for the resources."
  type        = string
}

variable "name_prefix" {
  description = "A prefix to be added to resource names."
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
  default     = "0"
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
  default     = 5
}

variable "google_sheets_credentials_secret_id" {
  description = "The ID of the Secret Manager secret containing the Google Sheets service account credentials."
  type        = string
}

variable "function_service_account_email" {
  description = "The email of the service account to run the Cloud Functions."
  type        = string
}
