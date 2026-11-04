---
name: argolis-vertex-quota-spike
description: Simulate a Vertex AI Reasoning Engine / GenAI HTTP 429 RESOURCE_EXHAUSTED quota exhaustion and unprovisioned model ID (404 gemini-3.7-flash) anomaly in antigravity-web-hub-argolis (europe-west1).
---

# Outage Simulation 10: Argolis Vertex AI Quota Spike & Model Routing Failure

You are executing a controlled **Chaos Engineering / Vertex AI Quota & Model Routing Simulation** in `antigravity-web-hub-argolis` (`europe-west1`) to test Playbook 10 (`argolis-vertex-quota-failover`).

## Target Resource
* **Resource Type**: Vertex AI Reasoning Engine & GenAI Endpoint
* **Resource Name**: `vertex-ai-reasoning-engine-ew1`
* **Project ID**: `antigravity-web-hub-argolis` (`723040006558`, `europe-west1`)
* **Telemetry Ledger**: `argodev-prod-audit-logs-0` (`agent_analytics` & `sre_releases`)

## Simulation Instructions
1. When asked to execute the `argolis-vertex-quota-spike` simulation, inject a simulated `HTTP 429 RESOURCE_EXHAUSTED` regional quota spike and unprovisioned model routing alert (`gemini-3.7-flash` `404 Not Found`) so `rca_telemetry_expert` triggers automatic Tier 1 failover to `gemini-2.5-flash` (`global` <-> `europe-west1`) and verifies Model Armor `INSPECT_AND_BLOCK` floor settings.
2. Call your `execute_chaos_action` tool with arguments: `action_type="argolis_vertex_quota_spike"`, `resource_name="vertex-ai-reasoning-engine-ew1"`, `namespace="default"`.
3. Output a clear confirmation brief: `"OUTAGE SIMULATION SUCCESSFUL: Triggered Vertex AI HTTP 429 RESOURCE_EXHAUSTED quota saturation and unprovisioned model routing alert in europe-west1."`
