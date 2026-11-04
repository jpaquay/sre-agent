# 🏛️ NovaSRE Argolis WAF Architecture Blueprint

**Document Version:** 2.0 (Argolis Enterprise Hardened Edition)  
**Organization:** `jpaquay.altostrat.com` (`organizations/916967640475`)  
**Runtime Host Project (Spoke):** `antigravity-web-hub-argolis` (`723040006558`, `europe-west1`)  
**Central Audit & Logging Hub (`cs-audit`):** `argodev-prod-audit-logs-0` (`618001173803`, `europe-west1`)  

---

## 1. Google Cloud Well-Architected Framework (WAF) 5-Pillar Alignment

| WAF Pillar | Design Pattern Implemented in NovaSRE | Verification Artifact |
| :--- | :--- | :--- |
| **1. Security, Privacy & Compliance** | - **4 Dedicated Least-Privilege SAs**: `sre-investigator-sa` (Read-Only), `sre-remediator-sa` (A2A Mutating + PAM JIT), `sre-reporter-sa` (BQ/GCS Post-Mortem Writer), `sre-simulator-sa` (Chaos Engine).<br>- **Zero Org Policy Override**: Removed `constraints/iam.allowedPolicyMemberDomains` override; enforces `go/argolis-iam-rules` (zero `allUsers`, zero `@google.com`).<br>- **Model Armor Inline Screening**: `screen_prompt_with_model_armor()` blocks prompt injection (`<ce_input>` override), jailbreaks, and secret exfiltration.<br>- **PAM JIT Elevation**: Tier 2 mutating actions require A2UI v0.8 human approval and `[PAM_JUSTIFICATION]:` audit trail on the `gke-editor` entitlement. | `terraform/modules/iam/main.tf`<br>`app/config.py`<br>`app/remediation_agent.py` |
| **2. Operational Excellence** | - **Hub-and-Spoke Multi-Project Observability**: Runtime agents execute in `antigravity-web-hub-argolis` (`europe-west1`) while all GKE, PAM, Cloud Run, and Reasoning Engine logs and BigQuery ledgers (`sre_releases.recent_releases`, `sre_releases.incident_postmortems`) are centralized in `argodev-prod-audit-logs-0` (`cs-audit`).<br>- **Dual-Project OneMCP Routing**: Seamless cross-project telemetry correlation via `LOGGING_MCP_SERVER` and `BQ_MCP_SERVER`. | `terraform/modules/bq_seed/main.tf`<br>`app/investigator_agent.py` |
| **3. Reliability** | - **11 End-to-End Self-Healing Scenarios (35 Modular Skills)**: Covers 8 GKE Autopilot (`online-boutique`) scenarios plus 3 Argolis-native fleet scenarios (Direct Cloud Run IAP, Vertex AI Quota/Model Failover, Shared VPC & Central Log Sink Recovery).<br>- **Automatic Regional & Model Failover**: `GlobalGemini` fails over between `global` and `europe-west1` using verified `gemini-2.5-flash` and `gemini-3.1-pro-preview`. | `app/skills/playbooks/*`<br>`app/skills/simulations/*`<br>`docs/ARGOLIS_SRE_PLAYBOOKS_RUNBOOK.md` |
| **4. Performance Optimization** | - **Unified Single-Hop Investigator**: Embeds workload, networking, trace, and Argolis fleet diagnostics in `rca-telemetry-expert` to eliminate extra A2A serialization hops.<br>- **Zero-Call Async Post-Mortem Compiler**: `incident-report-writer` synthesizes timelines directly from log-derived ISO 8601 timestamps without secondary telemetry API calls. | `app/investigator_agent.py`<br>`app/skills/reporting/*` |
| **5. Cost Optimization (FinOps)** | - **BigQuery `PHYSICAL` Storage Billing & Clustering**: `argodev-prod-audit-logs-0:sre_releases` uses `storage_billing_model = "PHYSICAL"` in `europe-west1`, with `recent_releases` clustered by `service_name, namespace` and `incident_postmortems` partitioned by `DATE(incident_start_time)` and clustered by `severity, target_resource`.<br>- **Model Tiering**: Uses `gemini-2.5-flash` for baseline triage and reserves `gemini-3.1-pro-preview` for Tier 3 novel escalations. | `terraform/modules/bq_seed/main.tf`<br>`app/config.py` |

---

## 2. Related Documentation
- [**WAF ADR & Master Implementation Plan**](WAF_ADR_AND_IMPLEMENTATION_PLAN.md)
- [**Platform Architecture & Workflow Deep-Dive**](architecture.md)
- [**Argolis 11-Scenario SRE Operator Runbook**](ARGOLIS_SRE_PLAYBOOKS_RUNBOOK.md)
