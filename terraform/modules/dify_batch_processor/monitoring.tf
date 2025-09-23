resource "google_monitoring_dashboard" "dify_batch_processor_dashboard" {
  project        = var.project_id
  dashboard_json = jsonencode({
    "displayName" : "${var.name_prefix} Monitoring Dashboard",
    "gridLayout" : {
      "columns" : "2",
      "widgets" : [
        {
          "title" : "Loader Service Invocations (Count)",
          "xyChart" : {
            "dataSets" : [
              {
                "timeSeriesQuery" : {
                  "timeSeriesFilter" : {
                    "filter" : "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" resource.label.service_name=\"${google_cloudfunctions2_function.loader.name}\"",
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
                "legendTemplate": "p50"
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
              }
            ],
            "timeshiftDuration" : "0s",
            "yAxis" : { "label" : "Utilization", "scale" : "LINEAR" }
          }
        },
        {
            "title": "Service Errors (Logs)",
            "logsPanel": {
                "filter": "resource.type=\"cloud_run_revision\"\nresource.labels.service_name=(\"${google_cloudfunctions2_function.loader.name}\" OR \"${google_cloudfunctions2_function.worker.name}\")\nseverity=\"ERROR\""
            }
        }
      ]
    }
  })
}
