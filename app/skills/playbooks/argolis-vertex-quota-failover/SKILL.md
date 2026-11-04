---
name: argolis-vertex-quota-failover
description: Playbook 10 (Tier 1 Auto-Recovery) — Use when Vertex AI Reasoning Engine or GenAI requests fail with HTTP 429 RESOURCE_EXHAUSTED, HTTP 404 Not Found on unprovisioned model IDs (e.g., gemini-3.7-flash), or HTTP 400 INVALID_ARGUMENT missing thoughtSignature on Gemini 3.x models. Correlates with argodev-prod-audit-logs-0.agent_analytics and executes automatic regional/model failover (global <-> europe-west1, gemini-2.5-flash / gemini-3.1-pro-preview) while verifying Model Armor Floor Settings (INSPECT_AND_BLOCK).
---

# SRE Playbook 10: Argolis Vertex AI Quota Exhaustion, Model Routing & Model Armor Failover (`HTTP 429` / `404` / `400`)

## Target Scenario
* **Target Components**: Vertex AI Reasoning Engines (`rca-telemetry-expert`, `remediation-executor`, `outage-simulator`, `incident-report-writer`) and ADK 2.0 GenAI workloads in `antigravity-web-hub-argolis` (`723040006558`, `europe-west1`).
* **Diagnostic Trigger**: `rca_telemetry_expert` correlates Cloud Logging and BigQuery telemetry in the Central Audit Hub `argodev-prod-audit-logs-0` (`agent_analytics`, `vertex_ai_user_telemetry`, `sre_releases.recent_releases`) and identifies one of three Vertex AI operational failures:
  1. **`HTTP 429 RESOURCE_EXHAUSTED` (Dynamic Shared Quota / TPM saturation)**: Burst traffic or runaway multi-turn agent loops saturate regional tokens-per-minute (TPM) or concurrent request quotas in `europe-west1` or `global`.
  2. **`HTTP 404 NOT_FOUND` (`Publisher Model ... was not found`)**: A workload or configuration rollout referenced an unprovisioned or deprecated model identifier (such as `gemini-3.7-flash` instead of verified `gemini-2.5-flash` or `gemini-3.1-pro-preview`).
  3. **`HTTP 400 INVALID_ARGUMENT` (`Function call is missing a thought_signature` / Model Armor floor drift)**: A Gemini 3.x (`gemini-3-flash-preview` / `gemini-3.1-pro-preview`) multi-step tool call omitted `thoughtSignature` preservation across turns, or Model Armor floor settings drifted from `INSPECT_AND_BLOCK`.

## Remediation Action (Tier 1 - Fast-Path Auto-Recovery)
1. You are **pre-approved** to execute immediate, non-destructive model routing and regional endpoint failover to restore SRE agent availability without waiting for human intervention:
   - **Step 1 (Endpoint & Model Failover)**: Automatically switch active model routing from any failing or unprovisioned model (`gemini-3.7-flash`) to verified `gemini-2.5-flash` (with `gemini-3.1-pro-preview` reserved for Tier 3 escalation) and failover Vertex AI endpoint routing between `global` (`aiplatform.googleapis.com`) and `europe-west1` (`europe-west1-aiplatform.googleapis.com`).
   - **Step 2 (Model Armor Floor Verification)**: Verify that `screen_prompt_with_model_armor` inline screening is active (`enforcement_mode = INSPECT_AND_BLOCK` for Prompt Injection, Jailbreak, and Sensitive Data Protection).
2. Call `remediation_executor_remote("Execute Tier 1 Vertex AI quota and model failover in project antigravity-web-hub-argolis: route GEMINI_MODEL to gemini-2.5-flash with automatic global <-> europe-west1 endpoint fallback, enforce thoughtSignature preservation on multi-turn tool calls, and verify Model Armor INSPECT_AND_BLOCK guardrails.")` automatically.
3. Verify that test model inference returns `HTTP 200 OK` with latency `< 2000ms` and report `SUCCESS`.
