---
name: sre-correlation
description: Cross-signal correlation playbooks for Google Cloud observability across the Argolis Hub-and-Spoke topology (Runtime Host antigravity-web-hub-argolis and Central Logging & Audit Hub argodev-prod-audit-logs-0 in europe-west1). Use this skill whenever an investigation has produced one piece of evidence (a slow trace, a noisy log, a metric spike, an error group, a Cloud Run IAP 403, or a Vertex AI 429) and you need to find matching evidence across Cloud Trace, Cloud Logging, Cloud Monitoring, Error Reporting, and BigQuery ledgers (argodev-prod-audit-logs-0.sre_releases.recent_releases, incident_postmortems, audit_export, and agent_analytics).
---

# SRE Correlation Skill (Argolis Hub-and-Spoke Observability)

A single signal almost never tells the full story. This skill is the glue: it teaches the practical pivots that connect Cloud Trace, Cloud Logging, Cloud Monitoring, Cloud Error Reporting, and the **Central BigQuery & Audit Hub (`argodev-prod-audit-logs-0` / `cs-audit` in `europe-west1`)** via the IDs, resource labels, and timestamps they share. Use the per-API skills (`gcp-logging`, `gcp-monitoring`, `gcp-trace`, `gcp-error-reporting`) and deterministic hub helpers (`query_central_release_ledger`, `query_central_audit_logs`) to run the calls; this skill says **which call to run next and what to fill in**.

## The Seven Core Pivots (Spoke `antigravity-web-hub-argolis` ↔ Hub `argodev-prod-audit-logs-0`)

| From | To | Mechanism |
|---|---|---|
| Trace ID (or span ID) | All logs for that request | Cloud Logging `trace = "projects/antigravity-web-hub-argolis/traces/<TID>"` across `projects/antigravity-web-hub-argolis` and `projects/argodev-prod-audit-logs-0` |
| Metric series | The logs for the same resource | Reuse `resource.type` + `resource.labels.*` from the metric in a Logging filter (`location="europe-west1"`) |
| Any signal | Cross-service / app-level slicing | `apphub.googleapis.com/application` + `/service` + `/workload` labels |
| Latency p99 spike (distribution metric) | The exact slow request | Exemplars on distribution points → trace ID |
| Pod CrashLoop / 5xx / IAP 403 burst | Correlated code/image/config deployment | BigQuery SQL query on `argodev-prod-audit-logs-0.sre_releases.recent_releases` (clustered by `service_name, namespace` in `europe-west1`) |
| Vertex AI `429` / `404` / `400` error | GenAI model telemetry & OTel spans | BigQuery SQL query on `argodev-prod-audit-logs-0.agent_analytics` & `vertex_ai_user_telemetry` |
| Tier 2 HITL / PAM JIT remediation | Historical incident & PAM audit correlation | BigQuery SQL query on `argodev-prod-audit-logs-0.sre_releases.incident_postmortems` & `argodev-prod-audit-logs-0.audit_export` |

## When to use this skill

- "We see latency spiking — find me the slow request and its logs."
- "Error Reporting shows a new group — what's the actual stack and which request triggered it?"
- "There's a 5xx burst on service X — find traces and logs that explain it."
- "Cartservice pod entered CrashLoopBackOff — check what release was just deployed in `argodev-prod-audit-logs-0.sre_releases.recent_releases` and correlate the failure."
- "Direct Cloud Run IAP is returning `403 Forbidden` or `403 org_internal` on `antigravity-web-hub` — correlate Cloud Run IAM audit logs in `argodev-prod-audit-logs-0` with recent config rollouts."
- "Vertex AI Reasoning Engine is failing with `HTTP 429 RESOURCE_EXHAUSTED` or `404 gemini-3.7-flash` — correlate with `argodev-prod-audit-logs-0.agent_analytics`."
- "Telemetry stopped arriving in `argodev-prod-audit-logs-0` or Cloud Run/GKE failed with `compute.subnetworks.use` — correlate Shared VPC (`cs-host-78e19ed8055b4c6980cce9`) and Log Router sink (`sre-gke-pam-telemetry-sink`) status."

## Hard rules

1. **Carry the time window.** Whatever signal you started in, propagate the same `[start, end]` to the next signal (widen by 1–2 minutes on each side to allow for clock skew).
2. **Carry the resource labels.** If you found the issue on GKE workload `checkoutservice` in cluster `online-boutique` (`europe-west1`), the next call must scope to the same namespace and workload name. Don't drop labels — that's how you end up with unrelated noise.
3. **Respect Dual-Project Hub-and-Spoke Scoping.**
   - Runtime workloads (GKE `online-boutique`, Cloud Run, Reasoning Engines) execute in **`antigravity-web-hub-argolis`** (`723040006558`, `europe-west1`).
   - Centralized logs, deployment ledgers, post-mortems, and cross-org audit exports reside in **`argodev-prod-audit-logs-0`** (`618001173803`, `cs-audit`, `europe-west1`).
   - Always qualify BigQuery tables with the central hub project ID: `` `argodev-prod-audit-logs-0.sre_releases.recent_releases` `` and `` `argodev-prod-audit-logs-0.sre_releases.incident_postmortems` ``.
4. **One pivot at a time.** Don't combine two pivots in one mental hop — write down the intermediate IDs/labels.

## Standard correlation playbook (the canonical Argolis SRE walk)

When investigating an outage, walk the signals in this order:

1. **Start in `gcp-monitoring.list_alerts`** (scoped to `antigravity-web-hub-argolis`) — has anything fired? Open alerts have pre-built context (which condition, which resource).
2. **Check the Central BigQuery Release & Post-Mortem Ledgers in `argodev-prod-audit-logs-0` (`europe-west1`)**:
   - If a GKE deployment or Cloud Run service is in `CrashLoopBackOff` or experiencing sudden `5xx` / `403` / `404` errors after a rollout, call `query_central_release_ledger(service_name="<target_service>")` or execute SQL via BigQuery OneMCP (`execute_sql`):
     ```sql
     SELECT release_id, service_name, namespace, revision, commit_sha, author_email, timestamp_utc, status
     FROM `argodev-prod-audit-logs-0.sre_releases.recent_releases`
     WHERE service_name = '<target_service>'
     ORDER BY timestamp_utc DESC
     LIMIT 5;
     ```
   - If the timestamp correlates (`delta < 15m`) with a bad image rollout on GKE, report the correlated release ID (`REL-...`) and trigger **Playbook 2 (`gke-crashloop-rollback`, Tier 1 Auto-Rollback)**.
   - To check historical recurrence, MTTD/MTTR baselines, or prior PAM JIT grants for the same resource, query `incident_postmortems`:
     ```sql
     SELECT incident_id, alert, root_cause, mttd_seconds, mttr_seconds, remediation_status, pam_grant_name, report_gcs_uri
     FROM `argodev-prod-audit-logs-0.sre_releases.incident_postmortems`
     WHERE target_resource = '<target_resource>'
     ORDER BY incident_start_time DESC
     LIMIT 5;
     ```
3. **Correlate Cross-Org Audit & Agent Analytics in `argodev-prod-audit-logs-0` (`cs-audit`)**:
   - For IAM/IAP drift (`Playbook 9`), Shared VPC `networkUser` drift (`Playbook 11`), or PAM JIT elevation audits, query `argodev-prod-audit-logs-0.audit_export` or call `query_central_audit_logs`:
     ```sql
     SELECT timestamp, protoPayload.serviceName, protoPayload.methodName, protoPayload.authenticationInfo.principalEmail, protoPayload.status.message
     FROM `argodev-prod-audit-logs-0.audit_export.cloudaudit_googleapis_com_activity`
     WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
     ORDER BY timestamp DESC
     LIMIT 20;
     ```
   - For Vertex AI Reasoning Engine quota exhaustion (`HTTP 429`), unprovisioned models (`404 gemini-3.7-flash`), or Gemini 3.x `thoughtSignature` errors (`Playbook 10`), correlate against `argodev-prod-audit-logs-0.agent_analytics`.
4. **Confirm the spike numerically** in `gcp-monitoring.list_timeseries` (or PromQL).
5. **If the spiking metric is a distribution**, harvest **exemplar trace IDs**.
   - Otherwise, copy the metric's `resource.type` + `resource.labels` and call `gcp-logging.list_log_entries` (or `query_central_audit_logs`) across `projects/antigravity-web-hub-argolis` and `projects/argodev-prod-audit-logs-0` with `severity >= ERROR`.
6. **Pick a target trace ID** (from exemplar, or from a log entry's `trace` field). Run `gcp-trace.get_trace`.
7. **Identify the bottleneck span.** Its service/operation tells you where to keep digging.
8. **Pull all logs for that trace** with `gcp-logging.list_log_entries` filtered by `trace = "projects/antigravity-web-hub-argolis/traces/<TID>"`.
9. **If recurring**, check `gcp-error-reporting.list_group_stats` filtered to the same service in the same time window.
10. **Route to the matching Playbook (1–11)**: Map the correlated root cause to the 11-scenario catalog (Playbooks 1–8 for GKE `online-boutique` in `europe-west1`; Playbooks 9–11 for Argolis Direct Cloud Run IAP, Vertex AI Quota/Model Armor failover, and Shared VPC / Central Log Router Sink recovery).
