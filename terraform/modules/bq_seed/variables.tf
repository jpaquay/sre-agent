variable "gcp_project_id" {
  description = "Google Cloud Runtime Project ID."
  type        = string
}

variable "logging_project_id" {
  description = "Central Audit & Logging Hub (cs-audit) Google Cloud Project ID."
  type        = string
  default     = "argodev-prod-audit-logs-0"
}

variable "gcp_region" {
  description = "Google Cloud region."
  type        = string
  default     = "europe-west1"
}

variable "depends_on_apis" {
  description = "Trigger to wait for BigQuery API enablement."
  type        = any
}
