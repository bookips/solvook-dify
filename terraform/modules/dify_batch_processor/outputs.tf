output "loader_service_uri" {
  description = "The URI of the loader Cloud Run service."
  value       = google_cloudfunctions2_function.loader.service_config[0].uri
}