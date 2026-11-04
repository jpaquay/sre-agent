variable "gcp_project_id" {
  description = "Google Cloud Project ID."
  type        = string
}

variable "logging_project_id" {
  description = "Central Audit & Logging Hub Google Cloud Project ID."
  type        = string
  default     = "argodev-prod-audit-logs-0"
}

variable "gcp_region" {
  description = "Google Cloud region."
  type        = string
}

variable "staging_bucket_name" {
  description = "Staging bucket name for Agent Engine artifacts."
  type        = string
}

variable "service_account_email" {
  description = "Dedicated execution Service Account email."
  type        = string
}

variable "investigator_sa_email" {
  description = "Email of the read-only rca-telemetry-expert Service Account."
  type        = string
  default     = ""
}

variable "remediator_sa_email" {
  description = "Email of the mutating remediation-executor Service Account."
  type        = string
  default     = ""
}

variable "reporter_sa_email" {
  description = "Email of the incident-report-writer Service Account."
  type        = string
  default     = ""
}

variable "simulator_sa_email" {
  description = "Email of the outage-simulator Service Account."
  type        = string
  default     = ""
}

variable "gemini_model" {
  description = "Gemini model name."
  type        = string
}

variable "deploy_agents" {
  description = "Master toggle to execute the Python deploy script."
  type        = bool
}

variable "depends_on_apis" {
  description = "API trigger."
  type        = string
}

variable "depends_on_iam" {
  description = "IAM trigger."
  type        = string
}
