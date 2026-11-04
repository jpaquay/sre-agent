variable "gcp_project_id" {
  description = "Google Cloud Project ID."
  type        = string
}

variable "logging_project_id" {
  description = "Central Audit & Logging Hub Google Cloud Project ID."
  type        = string
  default     = "argodev-prod-audit-logs-0"
}

variable "telemetry_bucket_name" {
  description = "Name of the GCS telemetry bucket for scoped reporter write access."
  type        = string
  default     = ""
}

variable "depends_on_apis" {
  description = "API enablement dependency trigger."
  type        = string
}
