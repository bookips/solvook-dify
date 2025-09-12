resource "google_logging_project_bucket_config" "default_bucket_retention" {
  project       = var.project_id
  location      = "global"
  bucket_id     = "_Default"
  retention_days = 30
}
