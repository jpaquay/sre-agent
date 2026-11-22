# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# =========================================================================
# WAF SECURITY PILLAR: Decomposed Per-Agent Least-Privilege Service Accounts
# Zero Org-Policy Overrides (Strictly compliant with go/argolis-iam-rules)
# =========================================================================

data "google_project" "project" {
  project_id = var.gcp_project_id
}

# 1. Investigator SA (Strictly Read-Only across Runtime & Audit Hub)
resource "google_service_account" "sre_investigator_sa" {
  account_id   = "sre-investigator-sa"
  display_name = "NovaSRE Read-Only Investigator Service Account (rca-telemetry-expert)"
  project      = var.gcp_project_id
}

# 2. Remediator SA (Isolated Mutating Worker + PAM JIT Eligible User)
resource "google_service_account" "sre_remediator_sa" {
  account_id   = "sre-remediator-sa"
  display_name = "NovaSRE Mutating Remediation Service Account (remediation-executor)"
  project      = var.gcp_project_id
}

# 3. Reporter SA (Scoped Post-Mortem Archiver to GCS & Audit Hub BigQuery)
resource "google_service_account" "sre_reporter_sa" {
  account_id   = "sre-reporter-sa"
  display_name = "NovaSRE Async Post-Mortem Reporter Service Account (incident-report-writer)"
  project      = var.gcp_project_id
}

# 4. Simulator SA (Scoped Chaos Engineering Identity for Online Boutique)
resource "google_service_account" "sre_simulator_sa" {
  account_id   = "sre-simulator-sa"
  display_name = "NovaSRE Outage Simulator Service Account (outage-simulator)"
  project      = var.gcp_project_id
}

locals {
  investigator_runtime_roles = toset([
    "roles/logging.viewer",
    "roles/monitoring.viewer",
    "roles/cloudtrace.viewer",
    "roles/cloudtrace.agent",
    "roles/errorreporting.viewer",
    "roles/container.viewer",
    "roles/compute.viewer",
    "roles/mcp.toolUser",
    "roles/aiplatform.user",
    "roles/bigquery.jobUser",
    "roles/storage.objectViewer",
  ])

  investigator_logging_hub_roles = toset([
    "roles/logging.viewer",
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
  ])

  remediator_runtime_roles = toset([
    # Standing cluster/network write roles removed (Doc 1 W1); granted JIT via PAM gke-editor below.
    "roles/container.viewer",
    "roles/compute.viewer",
    "roles/mcp.toolUser",
    "roles/aiplatform.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
  ])

  reporter_runtime_roles = toset([
    "roles/aiplatform.user",
    "roles/mcp.toolUser",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
  ])

  reporter_logging_hub_roles = toset([
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
  ])

  simulator_runtime_roles = toset([
    # Standing roles/container.developer removed (Doc 1 W1); elevate via PAM when running chaos drills.
    "roles/container.viewer",
    "roles/aiplatform.user",
    "roles/mcp.toolUser",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
  ])

  telemetry_bucket = var.telemetry_bucket_name != "" ? var.telemetry_bucket_name : "${var.gcp_project_id}-telemetry"
}

# --- 1a. Investigator SA Runtime Project Bindings (Read-Only) ---
resource "google_project_iam_member" "investigator_runtime_roles" {
  for_each = local.investigator_runtime_roles
  project  = var.gcp_project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.sre_investigator_sa.email}"
}

# --- 1b. Investigator SA Central Audit Hub Bindings (Cross-Project Read-Only) ---
resource "google_project_iam_member" "investigator_logging_hub_roles" {
  for_each = local.investigator_logging_hub_roles
  project  = var.logging_project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.sre_investigator_sa.email}"
}

# --- 2. Remediator SA Runtime Project Bindings (Mutating Worker) ---
resource "google_project_iam_member" "remediator_runtime_roles" {
  for_each = local.remediator_runtime_roles
  project  = var.gcp_project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.sre_remediator_sa.email}"
}

# --- 3a. Reporter SA Runtime Project Bindings ---
resource "google_project_iam_member" "reporter_runtime_roles" {
  for_each = local.reporter_runtime_roles
  project  = var.gcp_project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.sre_reporter_sa.email}"
}

# --- 3b. Reporter SA Scoped Object Admin on Telemetry Bucket ---
resource "google_storage_bucket_iam_member" "reporter_telemetry_bucket_admin" {
  bucket = local.telemetry_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sre_reporter_sa.email}"
}

# --- 3c. Reporter SA Central Audit Hub Bindings (BigQuery Post-Mortem Writer) ---
resource "google_project_iam_member" "reporter_logging_hub_roles" {
  for_each = local.reporter_logging_hub_roles
  project  = var.logging_project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.sre_reporter_sa.email}"
}

# --- 4. Simulator SA Runtime Project Bindings (Chaos Engine) ---
resource "google_project_iam_member" "simulator_runtime_roles" {
  for_each = local.simulator_runtime_roles
  project  = var.gcp_project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.sre_simulator_sa.email}"
}

# =========================================================================
# PRIVILEGED ACCESS MANAGER (PAM) — JIT elevation for remediation
# =========================================================================
resource "google_privileged_access_manager_entitlement" "gke_editor" {
  entitlement_id = "gke-editor"
  location       = "global"
  parent         = "projects/${var.gcp_project_id}"

  max_request_duration = "3600s"

  requester_justification_config {
    unstructured {}
  }

  approval_workflow {
    manual_approvals {
      require_approver_justification = true
      steps {
        approvals_needed = 1
        approvers {
          principals = [
            "group:gcp-security-admins@jpaquay.altostrat.com",
          ]
        }
      }
    }
  }

  eligible_users {
    principals = [
      "serviceAccount:${google_service_account.sre_remediator_sa.email}",
    ]
  }

  privileged_access {
    gcp_iam_access {
      resource      = "//cloudresourcemanager.googleapis.com/projects/${var.gcp_project_id}"
      resource_type = "cloudresourcemanager.googleapis.com/Project"

      role_bindings {
        role = "roles/container.developer"
      }
    }
  }
}
