---
name: argolis-sharedvpc-logsink-recovery
description: Playbook 11 (Tier 2 HITL Approval) — Use when Shared VPC subnet IAM bindings (roles/compute.networkUser on host project cs-host-78e19ed8055b4c6980cce9 subnet sb-prod-ew1-shared 10.10.0.0/20) drift for Cloud Run Serverless Robot or GKE service agents, or when centralized Cloud Logging sinks (sre-gke-pam-telemetry-sink, reasoning-engine-sink, cloud-run-adk-sink, audit-logs) fail to export telemetry from antigravity-web-hub-argolis to argodev-prod-audit-logs-0 (cs-audit).
---

# SRE Playbook 11: Argolis Shared VPC Subnet IAM & Central Log Sink Recovery (`cs-host` & `cs-audit`)

## Target Scenario
* **Target Components**:
  - **Shared VPC Host & Subnet**: `cs-host-78e19ed8055b4c6980cce9` (Subnet `sb-prod-ew1-shared`, CIDR `10.10.0.0/20`, Region `europe-west1`) and Spoke VPC (`sre-agent-vpc` / `sre-agent-subnet` in `antigravity-web-hub-argolis`).
  - **Central Logging & Audit Hub (`cs-audit`)**: `argodev-prod-audit-logs-0` (`618001173803`, Region `europe-west1`), receiving telemetry via Log Router sinks (`sre-gke-pam-telemetry-sink`, `reasoning-engine-sink`, `cloud-run-adk-sink`, and org-level `audit-logs`).
* **Diagnostic Trigger**: `rca_telemetry_expert` detects one of two cross-project Hub-and-Spoke infrastructure failures:
  1. **Shared VPC `roles/compute.networkUser` IAM Drift**: Cloud Run revisions with Direct VPC Egress or GKE Autopilot node pools in spoke projects fail to provision network interfaces (`PERMISSION_DENIED: Required 'compute.subnetworks.use' permission for 'projects/cs-host-78e19ed8055b4c6980cce9/regions/europe-west1/subnetworks/sb-prod-ew1-shared'`) because the Serverless Robot (`service-<PROJECT_NUM>@serverless-robot-prod.iam.gserviceaccount.com`) or GKE Service Agent (`service-<PROJECT_NUM>@container-engine-robot.iam.gserviceaccount.com`) lost subnet-level `roles/compute.networkUser`.
  2. **Central Log Router Sink Lag / Writer Permission Drop**: Telemetry tables in `argodev-prod-audit-logs-0:sre_releases` (`recent_releases`, `incident_postmortems`, `k8s_container`, `cloudaudit_googleapis_com_activity`) show an ingestion gap or `PERMISSION_DENIED` errors in `_Default` log sink metrics because `sre-gke-pam-telemetry-sink`'s unique `writer_identity` is missing `roles/bigquery.dataEditor` on `argodev-prod-audit-logs-0:sre_releases` or the sink filter was corrupted.

## Remediation Action (Tier 2 - HITL Approval Required + PAM JIT Audit)
1. **Present the Executive Resolution Plan** to the human operator via the A2UI v0.8 approval card:
   - Identify the exact broken cross-project binding (Shared VPC subnet `roles/compute.networkUser` on `sb-prod-ew1-shared` or Log Router sink `writer_identity` `roles/bigquery.dataEditor` on `argodev-prod-audit-logs-0:sre_releases`).
   - Specify the declarative restoration commands:
     - **Shared VPC Subnet Binding**: Grant `roles/compute.networkUser` on subnet `sb-prod-ew1-shared` (`europe-west1`) to `serviceAccount:service-723040006558@serverless-robot-prod.iam.gserviceaccount.com` and `serviceAccount:service-723040006558@container-engine-robot.iam.gserviceaccount.com`.
     - **Central Log Router Sink Restoration**: Reconcile sink `sre-gke-pam-telemetry-sink` in `antigravity-web-hub-argolis` targeting `bigquery.googleapis.com/projects/argodev-prod-audit-logs-0/datasets/sre_releases` with filter `resource.type="k8s_container" OR resource.type="k8s_pod" OR resource.type="k8s_cluster" OR protoPayload.serviceName="privilegedaccessmanager.googleapis.com"`, and bind its `writer_identity` to `roles/bigquery.dataEditor` on dataset `argodev-prod-audit-logs-0:sre_releases`.
2. **Upon Operator Approval (`APPROVED`)**:
   - Call `remediation_executor_remote("Restore Argolis cross-project Shared VPC networkUser bindings and reconcile Cloud Logging sink sre-gke-pam-telemetry-sink from antigravity-web-hub-argolis to argodev-prod-audit-logs-0:sre_releases with roles/bigquery.dataEditor on the sink writer_identity. [PAM_JUSTIFICATION]: Approved Tier 2 Shared VPC and Central Log Sink recovery")`.
3. **Post-Remediation Verification**:
   - Confirm `gcloud logging sinks describe sre-gke-pam-telemetry-sink --project=antigravity-web-hub-argolis` is active and its `writerIdentity` holds `roles/bigquery.dataEditor` on `argodev-prod-audit-logs-0:sre_releases`, then report `SUCCESS`.
