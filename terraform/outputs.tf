output "gke_cluster_name" {
  description = "The deployed GKE cluster name."
  value       = module.gke_demo.cluster_name
}

output "gke_cluster_endpoint" {
  description = "The deployed GKE cluster API endpoint."
  value       = module.gke_demo.cluster_endpoint
}

output "sre_agent_service_account" {
  description = "Backward-compatible alias pointing to the Investigator Service Account email."
  value       = module.iam.sre_agent_sa_email
}

output "investigator_sa_email" {
  description = "Email of the read-only rca-telemetry-expert Service Account."
  value       = module.iam.investigator_sa_email
}

output "remediator_sa_email" {
  description = "Email of the mutating remediation-executor Service Account."
  value       = module.iam.remediator_sa_email
}

output "reporter_sa_email" {
  description = "Email of the incident-report-writer Service Account."
  value       = module.iam.reporter_sa_email
}

output "simulator_sa_email" {
  description = "Email of the outage-simulator Service Account."
  value       = module.iam.simulator_sa_email
}

output "logging_project_id" {
  description = "The Central Audit & Logging Hub (cs-audit) Google Cloud Project ID."
  value       = var.logging_project_id
}

output "staging_bucket" {
  description = "The GCS telemetry bucket for reports and traces."
  value       = module.foundation.staging_bucket_name
}

output "playbooks_gcs_bucket" {
  description = "The central GCS bucket containing modular SRE markdown playbooks."
  value       = module.playbooks_gcs.playbooks_bucket_name
}
