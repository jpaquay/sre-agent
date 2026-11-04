output "sre_agent_sa_email" {
  description = "Backward-compatible alias pointing to the Investigator Service Account email."
  value       = google_service_account.sre_investigator_sa.email
}

output "sre_agent_sa_name" {
  description = "The fully qualified resource name of the Investigator Service Account."
  value       = google_service_account.sre_investigator_sa.name
}

output "investigator_sa_email" {
  description = "Email of the read-only rca-telemetry-expert Service Account."
  value       = google_service_account.sre_investigator_sa.email
}

output "remediator_sa_email" {
  description = "Email of the mutating remediation-executor Service Account."
  value       = google_service_account.sre_remediator_sa.email
}

output "reporter_sa_email" {
  description = "Email of the incident-report-writer Service Account."
  value       = google_service_account.sre_reporter_sa.email
}

output "simulator_sa_email" {
  description = "Email of the outage-simulator Service Account."
  value       = google_service_account.sre_simulator_sa.email
}
