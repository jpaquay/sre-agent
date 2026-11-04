---
name: argolis-sharedvpc-logsink-lag
description: Simulate a Shared VPC subnet IAM drift (missing roles/compute.networkUser on sb-prod-ew1-shared in cs-host-78e19ed8055b4c6980cce9) and Cloud Logging sink export lag to argodev-prod-audit-logs-0 (cs-audit).
---

# Outage Simulation 11: Argolis Shared VPC Subnet Drift & Central Log Sink Lag

You are executing a controlled **Chaos Engineering / Hub-and-Spoke Observability & Shared VPC Drift Simulation** across `antigravity-web-hub-argolis` and `argodev-prod-audit-logs-0` (`cs-audit`) in `europe-west1` to test Playbook 11 (`argolis-sharedvpc-logsink-recovery`).

## Target Resource
* **Resource Type**: Shared VPC Subnet (`sb-prod-ew1-shared` in `cs-host-78e19ed8055b4c6980cce9`) & Central Cloud Logging Sink (`sre-gke-pam-telemetry-sink`)
* **Resource Name**: `sre-gke-pam-telemetry-sink`
* **Runtime Project**: `antigravity-web-hub-argolis` (`723040006558`, `europe-west1`)
* **Central Audit Hub**: `argodev-prod-audit-logs-0` (`618001173803`, `europe-west1`)

## Simulation Instructions
1. When asked to execute the `argolis-sharedvpc-logsink-lag` simulation, inject a simulated Shared VPC `roles/compute.networkUser` permission drift alert on `sb-prod-ew1-shared` (`10.10.0.0/20`) and a central log sink writer permission lag alert on `sre-gke-pam-telemetry-sink` exporting to `argodev-prod-audit-logs-0:sre_releases`.
2. Call your `execute_chaos_action` tool with arguments: `action_type="argolis_sharedvpc_logsink_lag"`, `resource_name="sre-gke-pam-telemetry-sink"`, `namespace="default"`.
3. Output a clear confirmation brief: `"OUTAGE SIMULATION SUCCESSFUL: Injected Shared VPC sb-prod-ew1-shared networkUser drift and central log sink export lag alert targeting argodev-prod-audit-logs-0."`
