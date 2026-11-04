output "bq_dataset_id" {
  description = "The seeded BigQuery dataset ID."
  value       = google_bigquery_dataset.sre_releases.dataset_id
}

output "bq_table_id" {
  description = "The seeded BigQuery recent_releases table ID."
  value       = google_bigquery_table.recent_releases.table_id
}

output "incident_postmortems_table_id" {
  description = "The partitioned BigQuery incident_postmortems table ID."
  value       = google_bigquery_table.incident_postmortems.table_id
}

output "telemetry_sink_writer_identity" {
  description = "The Cloud Logging sink writer identity routing GKE and PAM logs to BigQuery."
  value       = google_logging_project_sink.sre_gke_pam_telemetry_sink.writer_identity
}
