---
name: argolis-cloudrun-iap-drift
description: Simulate a Direct Cloud Run IAP configuration drift in Argolis (HTTP 403 Forbidden from missing service-<PROJECT_NUM>@gcp-sa-iap.iam.gserviceaccount.com roles/run.invoker or HTTP 403 org_internal OAuth client mismatch) without breaking live production IAP endpoints.
---

# Outage Simulation 9: Argolis Direct Cloud Run IAP & OAuth Drift

You are executing a controlled, non-destructive **Chaos Engineering / Security Configuration Drift Simulation** in the Argolis environment (`antigravity-web-hub-argolis`, region `europe-west1`) to test Playbook 9 (`argolis-cloudrun-iap-recovery`).

## Target Resource
* **Resource Type**: Cloud Run Service (Direct IAP Protected)
* **Resource Name**: `antigravity-web-hub` (simulated via safe metadata/telemetry marker so live operator sessions are never disrupted)
* **Project ID**: `antigravity-web-hub-argolis` (`723040006558`)
* **Central Audit Hub**: `argodev-prod-audit-logs-0` (`cs-audit`)

## Simulation Instructions
1. When asked to execute the `argolis-cloudrun-iap-drift` simulation, inject a synthetic Direct Cloud Run IAP `403 Forbidden` / `403 org_internal` drift state and emit structured audit telemetry so `rca_telemetry_expert` can triage the anomaly safely without locking out live human operators.
2. Call your `execute_chaos_action` tool with arguments: `action_type="argolis_cloudrun_iap_drift"`, `resource_name="antigravity-web-hub"`, `namespace="default"`.
3. Output a clear confirmation brief: `"OUTAGE SIMULATION SUCCESSFUL: Injected Direct Cloud Run IAP configuration drift (missing service-723040006558@gcp-sa-iap.iam.gserviceaccount.com roles/run.invoker & 403 org_internal OAuth telemetry signature) on 'antigravity-web-hub' in europe-west1."`
