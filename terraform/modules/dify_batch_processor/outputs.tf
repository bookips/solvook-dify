output "loader_service_uri" {
  description = "The URI of the Loader Cloud Run service."
  value       = google_cloudfunctions2_function.loader.service_config[0].uri
}

output "worker_service_uri" {
  description = "The URI of the Worker Cloud Run service."
  value       = google_cloudfunctions2_function.worker.service_config[0].uri
}

output "task_queue_name" {
  description = "The name of the Cloud Tasks queue."
  value       = google_cloud_tasks_queue.dify_batch_processor_queue.name
}
