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

resource "google_bigquery_dataset" "sre_releases" {
  dataset_id                 = "sre_releases"
  friendly_name              = "NovaSRE Central Release & Post-Mortem Ledger"
  description                = "Cross-signal deployment correlation and MTTD/MTTR post-mortem ledger in cs-audit hub."
  location                   = var.gcp_region
  storage_billing_model      = "PHYSICAL"
  delete_contents_on_destroy = true
  project                    = var.logging_project_id

  depends_on = [var.depends_on_apis]
}

resource "google_bigquery_table" "recent_releases" {
  dataset_id          = google_bigquery_dataset.sre_releases.dataset_id
  table_id            = "recent_releases"
  project             = var.logging_project_id
  deletion_protection = false
  clustering          = ["service_name", "namespace"]
  schema              = <<EOF
[
  {
    "name": "release_id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Unique release identifier."
  },
  {
    "name": "service_name",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Target microservice or Cloud Run service name."
  },
  {
    "name": "namespace",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Kubernetes namespace or GCP environment."
  },
  {
    "name": "previous_revision",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Previous container image or stable release tag."
  },
  {
    "name": "new_revision",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "New container image or broken release tag."
  },
  {
    "name": "timestamp_utc",
    "type": "TIMESTAMP",
    "mode": "REQUIRED",
    "description": "Deployment execution timestamp."
  },
  {
    "name": "deployed_by",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "CI/CD system or user triggering the deployment."
  },
  {
    "name": "commit_hash",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Git commit hash."
  },
  {
    "name": "change_summary",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Summary of changes included in the rollout."
  }
]
EOF

  depends_on = [google_bigquery_dataset.sre_releases]
}

resource "google_bigquery_table" "incident_postmortems" {
  dataset_id          = google_bigquery_dataset.sre_releases.dataset_id
  table_id            = "incident_postmortems"
  project             = var.logging_project_id
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "incident_start_time"
  }

  clustering = ["severity", "target_resource"]

  schema = <<EOF
[
  {
    "name": "incident_id",
    "type": "STRING",
    "mode": "REQUIRED",
    "description": "Unique incident identifier."
  },
  {
    "name": "alert",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Triggering alert or symptom summary."
  },
  {
    "name": "root_cause",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Verified technical root cause."
  },
  {
    "name": "incident_start_time",
    "type": "TIMESTAMP",
    "mode": "NULLABLE",
    "description": "Timestamp when fault/outage began."
  },
  {
    "name": "detection_time",
    "type": "TIMESTAMP",
    "mode": "NULLABLE",
    "description": "Timestamp when anomaly was first detected."
  },
  {
    "name": "mitigation_executed_time",
    "type": "TIMESTAMP",
    "mode": "NULLABLE",
    "description": "Timestamp when remediation action was executed."
  },
  {
    "name": "recovery_verified_time",
    "type": "TIMESTAMP",
    "mode": "NULLABLE",
    "description": "Timestamp when service health was verified."
  },
  {
    "name": "mttd_seconds",
    "type": "INT64",
    "mode": "NULLABLE",
    "description": "Mean Time To Detect in seconds."
  },
  {
    "name": "mttr_seconds",
    "type": "INT64",
    "mode": "NULLABLE",
    "description": "Mean Time To Resolve in seconds."
  },
  {
    "name": "remediation_status",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Outcome of remediation execution."
  },
  {
    "name": "recommended_action",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Follow-up engineering action item."
  },
  {
    "name": "target_resource",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Impacted Kubernetes workload or GCP service."
  },
  {
    "name": "severity",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Incident severity classification (P1, P2, P3)."
  },
  {
    "name": "pam_grant_name",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "Privileged Access Manager JIT grant resource name."
  },
  {
    "name": "report_gcs_uri",
    "type": "STRING",
    "mode": "NULLABLE",
    "description": "GCS URI of the archived markdown post-mortem report."
  }
]
EOF

  depends_on = [google_bigquery_dataset.sre_releases]
}

resource "google_logging_project_sink" "sre_gke_pam_telemetry_sink" {
  name                   = "sre-gke-pam-telemetry-sink"
  project                = var.gcp_project_id
  destination            = "bigquery.googleapis.com/projects/${var.logging_project_id}/datasets/${google_bigquery_dataset.sre_releases.dataset_id}"
  filter                 = "(resource.type=\"k8s_container\" OR resource.type=\"k8s_pod\" OR resource.type=\"k8s_cluster\" OR protoPayload.serviceName=\"privilegedaccessmanager.googleapis.com\")"
  unique_writer_identity = true

  bigquery_options {
    use_partitioned_tables = true
  }

  depends_on = [google_bigquery_dataset.sre_releases]
}

resource "google_bigquery_dataset_iam_member" "sink_bq_writer" {
  project    = var.logging_project_id
  dataset_id = google_bigquery_dataset.sre_releases.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.sre_gke_pam_telemetry_sink.writer_identity
}

resource "terraform_data" "seed_bq_releases" {
  triggers_replace = [
    google_bigquery_table.recent_releases.id
  ]

  provisioner "local-exec" {
    command = <<-EOT
      export PATH=$PATH:/google/google-cloud-sdk/bin:/usr/lib/google-cloud-sdk/bin:/opt/google-cloud-sdk/bin:/usr/local/google-cloud-sdk/bin:/root/google-cloud-sdk/bin:/usr/local/bin:/usr/bin:/bin
      BQ_CMD=$(command -v bq || find / -name bq -type f 2>/dev/null | head -n 1)
      if [ -z "$BQ_CMD" ]; then echo "❌ bq CLI required to seed BigQuery table."; exit 1; fi

      echo "🌱 Seeding ${var.logging_project_id}.sre_releases.recent_releases with baseline deployment records..."
      $BQ_CMD --project_id=${var.logging_project_id} --location=${var.gcp_region} query --use_legacy_sql=false \
      'INSERT INTO `${var.logging_project_id}.sre_releases.recent_releases` (release_id, service_name, namespace, previous_revision, new_revision, timestamp_utc, deployed_by, commit_hash, change_summary) VALUES
      ("REL-20261005-042", "cartservice", "default", "gcr.io/google-samples/microservices-demo/cartservice:v1.0.4", "gcr.io/google-samples/microservices-demo/cartservice:broken-v2", CURRENT_TIMESTAMP(), "cloud-build-pipeline", "c83f91a2", "Updated shopping cart gRPC timeout and serialization format (Scenario 2 trigger)."),
      ("REL-20261005-038", "frontend", "default", "gcr.io/google-samples/microservices-demo/frontend:v0.9.8", "gcr.io/google-samples/microservices-demo/frontend:v1.0.0", TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR), "sre-automation", "a14f77c9", "Stable production UI update."),
      ("REL-20261005-035", "redis-cart", "default", "redis:6.2-alpine", "redis:7.0-alpine", TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY), "sre-automation", "e98a33b1", "Database engine minor release upgrade."),
      ("REL-20261005-051", "antigravity-web-hub", "europe-west1", "antigravity-web-hub-00018-stable", "antigravity-web-hub-00019-iap-drift", TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 45 MINUTE), "argolis-cd-pipeline", "f41d88e3", "Migrated Cloud Run ingress to Direct IAP with custom OAuth client (Scenario 9 trigger)."),
      ("REL-20261005-052", "aether-web-gui", "europe-west1", "aether-web-gui-00011-ew1", "aether-web-gui-00012-vertex-burst", TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 MINUTE), "argolis-cd-pipeline", "b92c4410", "Switched default LLM tier to unprovisioned preview endpoint without regional fallback (Scenario 10 trigger)."),
      ("REL-20261005-053", "ge-hosted-agy-agent", "europe-west1", "ge-hosted-agy-agent-00007", "ge-hosted-agy-agent-00008-vpc-sink", TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 15 MINUTE), "argolis-cd-pipeline", "d77a1904", "Updated Shared VPC subnet attachment and central cs-audit log sink filter (Scenario 11 trigger).")'

      echo "✅ BigQuery recent_releases table seeded successfully."
    EOT
  }

  depends_on = [google_bigquery_table.recent_releases]
}
