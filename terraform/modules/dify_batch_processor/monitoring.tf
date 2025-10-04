resource "google_monitoring_dashboard" "dify_batch_processor_dashboard" {
  project = var.project_id
  dashboard_json = jsonencode({
    "displayName" : "${var.name_prefix} Monitoring Dashboard",
    "gridLayout" : {
      "columns" : "2",
      "widgets" : [
        {
          "title" : "Worker Service Invocations (Count)",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.worker.name}\"",
                    "aggregation" : {
                      "perSeriesAligner" : "ALIGN_RATE"
                    }
                  }
                },
                "plotType" : "LINE"
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : {
              "label" : "Invocations",
              "scale" : "LINEAR"
            }
          }
        },
        {
          "title" : "Dispatcher Service Invocations (Count)",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.dispatcher.name}\"",
                    "aggregation" : {
                      "perSeriesAligner" : "ALIGN_RATE"
                    }
                  }
                },
                "plotType" : "LINE"
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : {
              "label" : "Invocations",
              "scale" : "LINEAR"
            }
          }
        },
        {
          "title" : "Poller Service Invocations (Count)",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.poller.name}\"",
                    "aggregation" : {
                      "perSeriesAligner" : "ALIGN_RATE"
                    }
                  }
                },
                "plotType" : "LINE"
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : {
              "label" : "Invocations",
              "scale" : "LINEAR"
            }
          }
        },
        {
          "title" : "Worker Service Execution Time (p50)",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/request_latencies\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.worker.name}\"",
                    "aggregation" : {
                      "perSeriesAligner" : "ALIGN_PERCENTILE_50"
                    }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "p50"
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : {
              "label" : "Latency (s)",
              "scale" : "LINEAR"
            }
          }
        },
        {
          "title" : "Cloud Tasks Queue Depth",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"cloudtasks.googleapis.com/queue/depth\" resource.type=\"cloud_tasks_queue\" resource.label.queue_id=\"${google_cloud_tasks_queue.dify_batch_processor_queue.name}\"",
                    "aggregation" : {
                      "perSeriesAligner" : "ALIGN_MEAN"
                    }
                  }
                },
                "plotType" : "LINE"
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : {
              "label" : "Task Count",
              "scale" : "LINEAR"
            }
          }
        },
        {
          "title" : "Container Instance Count",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/instance_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.loader.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MAX" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Loader"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/instance_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.worker.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MAX" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Worker"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/instance_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.dispatcher.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MAX" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Dispatcher"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/instance_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.poller.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MAX" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Poller"
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : { "label" : "Count", "scale" : "LINEAR" }
          }
        },
        {
          "title" : "Container CPU Utilization",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/cpu/utilization\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.loader.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MEAN" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Loader"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/cpu/utilization\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.worker.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MEAN" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Worker"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/cpu/utilization\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.dispatcher.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MEAN" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Dispatcher"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/cpu/utilization\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.poller.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MEAN" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Poller"
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : { "label" : "Utilization", "scale" : "LINEAR" }
          }
        },
        {
          "title" : "Container Memory Utilization",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/memory/utilization\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.loader.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MEAN" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Loader"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/memory/utilization\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.worker.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MEAN" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Worker"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/memory/utilization\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.dispatcher.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MEAN" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Dispatcher"
              },
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/container/memory/utilization\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.poller.name}\"",
                    "aggregation" : { "perSeriesAligner" : "ALIGN_MEAN" }
                  }
                },
                "plotType" : "LINE",
                "legendTemplate" : "Poller"
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : { "label" : "Utilization", "scale" : "LINEAR" }
          }
        },
        {
          "title" : "Service Errors (Logs)",
          "logsPanel" : {
            "filter" : "resource.type=\"cloud_run_revision\"\nresource.labels.service_name=(\"${google_cloudfunctions2_function.loader.name}\" OR \"${google_cloudfunctions2_function.worker.name}\" OR \"${google_cloudfunctions2_function.dispatcher.name}\" OR \"${google_cloudfunctions2_function.poller.name}\")\nseverity=\"ERROR\""
          }
        }
      ]
    }
  })
}

# --- Slack Alerting ---

resource "google_monitoring_notification_channel" "slack" {
  count        = var.slack_webhook_secret_name != null && var.slack_channel_name != null ? 1 : 0
  project      = var.project_id
  display_name = "Slack Notification Channel"
  type         = "slack"
  labels = {
    channel_name = var.slack_channel_name
  }
  sensitive_labels {
    auth_token = var.slack_webhook_token
  }
}

resource "google_monitoring_alert_policy" "worker_5xx_errors" {
  count        = var.slack_webhook_secret_name != null && var.slack_channel_name != null ? 1 : 0
  project      = var.project_id
  display_name = "${var.name_prefix}-worker 5xx Errors"
  combiner     = "OR"
  conditions {
    display_name = "Cloud Run service ${google_cloudfunctions2_function.worker.name} has 5xx errors"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.worker.name}\" metric.label.response_code_class=\"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      trigger {
        count = 1
      }
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
  notification_channels = [
    google_monitoring_notification_channel.slack[0].name
  ]
  user_labels = {
    "service" = "${var.name_prefix}-worker"
    "tier"    = "backend"
  }
}

resource "google_monitoring_alert_policy" "dispatcher_5xx_errors" {
  count        = var.slack_webhook_secret_name != null && var.slack_channel_name != null ? 1 : 0
  project      = var.project_id
  display_name = "${var.name_prefix}-dispatcher 5xx Errors"
  combiner     = "OR"
  conditions {
    display_name = "Cloud Run service ${google_cloudfunctions2_function.dispatcher.name} has 5xx errors"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.dispatcher.name}\" metric.label.response_code_class=\"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      trigger {
        count = 1
      }
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
  notification_channels = [
    google_monitoring_notification_channel.slack[0].name
  ]
  user_labels = {
    "service" = "${var.name_prefix}-dispatcher"
    "tier"    = "backend"
  }
}

resource "google_monitoring_alert_policy" "poller_5xx_errors" {
  count        = var.slack_webhook_secret_name != null && var.slack_channel_name != null ? 1 : 0
  project      = var.project_id
  display_name = "${var.name_prefix}-poller 5xx Errors"
  combiner     = "OR"
  conditions {
    display_name = "Cloud Run service ${google_cloudfunctions2_function.poller.name} has 5xx errors"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.poller.name}\" metric.label.response_code_class=\"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      trigger {
        count = 1
      }
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
  notification_channels = [
    google_monitoring_notification_channel.slack[0].name
  ]
  user_labels = {
    "service" = "${var.name_prefix}-poller"
    "tier"    = "backend"
  }
}