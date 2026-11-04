---
name: gcp-logging
description: Query Google Cloud Logging effectively via the logging MCP tools (list_log_entries, list_log_names, list_buckets, list_views) and Central Audit Hub helpers across the Argolis Hub-and-Spoke architecture (Spoke Runtime Host antigravity-web-hub-argolis and Central Logging & Audit Hub argodev-prod-audit-logs-0 in europe-west1). Use this skill whenever the user asks about logs, log entries, error messages in logs, PAM/IAM audit logs, Cloud Run IAP logs, Vertex AI Reasoning Engine logs, or GKE container logs. DO NOT use this skill for aggregated error stats — use gcp-error-reporting for that.
---

# GCP Logging Skill (Argolis Dual-Project Hub-and-Spoke Edition)

You are querying **Cloud Logging** through the logging MCP toolset (`LOGGING_MCP_SERVER`) and the dual-project helper `query_central_audit_logs`. This skill teaches you how to write **selective, fast, low-payload** filters across both our Spoke Runtime Host (`antigravity-web-hub-argolis`) and our Central Logging & Audit Hub (`argodev-prod-audit-logs-0` / `cs-audit` in `europe-west1`).

## Hub-and-Spoke Logging Topology (`europe-west1`)

| Project Role | Project ID & Number | What Logs Live Here | Sink / Routing Mechanism |
|---|---|---|---|
| **Spoke / Runtime Host** | `antigravity-web-hub-argolis` (`723040006558`) | Live GKE Autopilot (`online-boutique`), Cloud Run (`antigravity-web-hub`, `aether-web-gui`, `ge-hosted-agy-agent`), Vertex AI Reasoning Engines, Cloud NAT (`europe-west1`) | Local `_Default` bucket + exports via Log Router sinks to `argodev-prod-audit-logs-0` |
| **Central Logging & Audit Hub (`cs-audit`)** | `argodev-prod-audit-logs-0` (`618001173803`) | Centralized GKE & PAM audit logs (`sre_releases` BQ sink), org-wide Cloud Audit Logs (`audit-logs`), Vertex AI Reasoning Engine telemetry (`reasoning-engine-sink`), Cloud Run ADK logs (`cloud-run-adk-sink`) | Log Router sinks: `sre-gke-pam-telemetry-sink`, `reasoning-engine-sink`, `cloud-run-adk-sink`, `audit-logs` |

## Tools you have

| Tool | When to use |
|---|---|
| `list_log_entries` | **Primary OneMCP tool.** Search/retrieve log entries with a filter. Always supply `resourceNames` (`["projects/antigravity-web-hub-argolis"]` or `["projects/argodev-prod-audit-logs-0"]`) and `filter`. |
| `query_central_audit_logs` | **Dual-Project Hub Helper.** Simultaneously queries `argodev-prod-audit-logs-0` (`cs-audit`) and `antigravity-web-hub-argolis` with automatic fallback. |
| `list_log_names` | Discover what logs (e.g. `cloudaudit.googleapis.com/activity`, `run.googleapis.com/requests`) exist in a project. Cheap. |
| `list_buckets` / `get_bucket` | Inspect log storage configuration in `argodev-prod-audit-logs-0` or `antigravity-web-hub-argolis` when troubleshooting retention/routing (`Playbook 11`). |
| `list_views` / `get_view` | Inspect log views for access-control questions. |

## Hard rules

1. **`resourceNames` is required.** Always pass `["projects/antigravity-web-hub-argolis"]` for spoke runtime queries or `["projects/argodev-prod-audit-logs-0"]` for centralized audit/sink queries (never invent a project ID). Note: `list_log_entries` accepts one project per OneMCP call, or use `query_central_audit_logs` to query both projects seamlessly.
2. **Always include a `timestamp` restriction** in the filter. Without one you scan everything and the response is huge. Default to the last 1 hour for active investigations, last 15 minutes when correlating with a known incident time.
3. **Always include a `resource.type` restriction** unless querying cross-service audit logs. This is the single biggest payload-size lever:
   - GKE workloads (`online-boutique` in `europe-west1`): `resource.type="k8s_container" OR resource.type="k8s_pod" OR resource.type="k8s_cluster"`
   - Cloud Run services (Direct IAP): `resource.type="cloud_run_revision"`
   - Vertex AI Reasoning Engines: `resource.type="aiplatform.googleapis.com/ReasoningEngine"`
   - Cloud NAT gateways: `resource.type="nat_gateway"`
   - PAM JIT grants: `protoPayload.serviceName="privilegedaccessmanager.googleapis.com"`
4. **Use indexed fields first** (`resource.type`, `resource.labels.*`, `severity`, `logName`, `timestamp`, `trace`, `httpRequest.status`, `labels.*`). Free-text search via `:` is slow and last-resort.
5. **Page small.** Set `pageSize` to 20–50 for first probe, then increase only if needed.
6. **Order:** Use `orderBy="timestamp desc"` to get the most recent issues first when investigating an active outage.

## Canonical Argolis Log Filters (Scenarios 1–11)

- **GKE Container Crash / Error (`Scenarios 1–6, 8`)**:
  ```text
  resource.type="k8s_container" AND resource.labels.cluster_name="online-boutique" AND resource.labels.location="europe-west1" AND severity>=ERROR
  ```
- **Direct Cloud Run IAP `403 Forbidden` / `403 org_internal` / `302 Empty Token` (`Scenario 9`)**:
  ```text
  resource.type="cloud_run_revision" AND resource.labels.location="europe-west1" AND (httpRequest.status=403 OR httpRequest.status=302 OR severity>=WARNING)
  ```
- **Vertex AI Quota `429 RESOURCE_EXHAUSTED` / Unprovisioned Model `404` / `400 thoughtSignature` (`Scenario 10`)**:
  ```text
  (resource.type="aiplatform.googleapis.com/ReasoningEngine" OR protoPayload.serviceName="aiplatform.googleapis.com") AND (severity>=ERROR OR textPayload:"RESOURCE_EXHAUSTED" OR textPayload:"429" OR textPayload:"thought_signature")
  ```
- **Shared VPC `networkUser` Drift & PAM JIT Audit Trail (`Scenario 11` & Tier 2 Governance)**:
  ```text
  protoPayload.serviceName=("compute.googleapis.com" OR "privilegedaccessmanager.googleapis.com" OR "logging.googleapis.com") AND (severity>=NOTICE OR protoPayload.status.code!=0)
  ```

## Standard investigation flow

1. **Establish scope.** Confirm the resource type and target project (`antigravity-web-hub-argolis` vs `argodev-prod-audit-logs-0`).
2. **Bound time tightly.** `timestamp >= "<ISO_START>" AND timestamp < "<ISO_END>"`.
3. **Filter by severity** for triage: `severity >= ERROR`.
4. **Pivot.** If you find a `trace` field on a hit, hand off to `sre-correlation` to pull every log on that request or correlate with `argodev-prod-audit-logs-0.sre_releases.recent_releases`.
5. **Dig into payloads.** For structured logs use `jsonPayload.field = "value"` or `protoPayload.status.message`. For unstructured, `textPayload:"substring"`.

## When NOT to use this skill

- For **counts/trends/group statistics** of recurring crashes → use `gcp-error-reporting`.
- For **metric values** (CPU, memory, latency p99) → use `gcp-monitoring`.
- For **per-request span timings** → use `gcp-trace`.
