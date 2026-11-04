# 📘 NovaSRE Argolis Enterprise Operator Runbook — 11-Scenario Chaos & Autonomous Self-Healing Catalog

**Platform Version:** 2.0 (Argolis Enterprise Hardened Edition)  
**Organization:** `jpaquay.altostrat.com` (`organizations/916967640475`)  
**Runtime Host Project (Spoke):** `antigravity-web-hub-argolis` (`723040006558`, Region: `europe-west1`)  
**Central Logging & Audit Hub (`cs-audit`):** `argodev-prod-audit-logs-0` (`618001173803`, Region: `europe-west1`)  
**Shared VPC Host Project:** `cs-host-78e19ed8055b4c6980cce9` (Subnet: `sb-prod-ew1-shared` `10.10.0.0/20`)  
**GKE Autopilot Target Cluster:** `online-boutique` (`europe-west1`)  

---

## 🏛️ 1. Overview & Governance Model

This operator runbook provides end-to-end operational procedures, telemetry queries, governance gates, and verification commands for all **11 scenarios** supported by the **NovaSRE** autonomous SRE platform:
- **Scenarios 1–8**: GKE Autopilot (`online-boutique` in `europe-west1`) workload, rollout, database, latency, network policy, CoreDNS, Cloud NAT, and Kubernetes Service selector failures.
- **Scenarios 9–11**: Argolis Fleet multi-project enterprise scenarios covering Direct Cloud Run IAP (`403 Forbidden` / `403 org_internal` / `302 Empty Token`), Vertex AI Reasoning Engine Quota & Model Routing Failover (`429 RESOURCE_EXHAUSTED` / `404 gemini-3.7-flash` / `400 thoughtSignature` + Model Armor), and Shared VPC Subnet IAM (`sb-prod-ew1-shared`) + Central Log Router Sink (`sre-gke-pam-telemetry-sink`) recovery.

### 3-Tier Operational Resolution & PAM JIT Governance

| Tier | Execution Mode | Service Account & PAM Scope | Applicable Playbooks |
| :--- | :--- | :--- | :--- |
| **Tier 1: Fast-Path Auto-Recovery** | Zero-touch autonomous A2A execution (`rca-telemetry-expert` $\rightarrow$ `remediation-executor`). | `sre-remediator-sa@antigravity-web-hub-argolis.iam.gserviceaccount.com` | **Playbook 1** (`gke-scale-recovery`)<br>**Playbook 2** (`gke-crashloop-rollback`)<br>**Playbook 6** (`gke-dns-recovery`)<br>**Playbook 10** (`argolis-vertex-quota-failover`) |
| **Tier 2: Gated HITL + PAM JIT** | Renders interactive **A2UI v0.8 Approval Card** (`[ ✅ Approve & Execute ]`). Elevates via Privileged Access Manager (`gke-editor`) with `[PAM_JUSTIFICATION]:` audit trail in `argodev-prod-audit-logs-0`. | `sre-remediator-sa@antigravity-web-hub-argolis.iam.gserviceaccount.com` + PAM Entitlement `gke-editor` | **Playbook 3** (`gke-pod-restart`)<br>**Playbook 4** (`gke-horizontal-upsize`)<br>**Playbook 5** (`gke-network-firewall-recovery`)<br>**Playbook 7** (`gcp-nat-port-recovery`)<br>**Playbook 8** (`gke-service-routing-recovery`)<br>**Playbook 9** (`argolis-cloudrun-iap-recovery`)<br>**Playbook 11** (`argolis-sharedvpc-logsink-recovery`) |
| **Tier 3: Zero-Shot Pro Escalation** | Escalates to `gemini-3.1-pro-preview` (`GEMINI_PRO_MODEL`) to synthesize novel recovery plans from raw telemetry; always gated by A2UI HITL approval. | `sre-investigator-sa` (Read-Only Triage) $\rightarrow$ `sre-remediator-sa` (HITL Approved) | Unscripted / zero-day infrastructure or application anomalies. |

---

## 📊 2. Master 11-Scenario Quick Reference Matrix

| # | Scenario / Simulation Skill | Playbook Skill | Target Resource (`europe-west1`) | Primary Telemetry Signal | Governance Tier |
| :- | :--- | :--- | :--- | :--- | :--- |
| **1** | `gke-scale-outage` | `gke-scale-recovery` | GKE `deployment/frontend` | `readyReplicas = 0`, HTTP `503` | **Tier 1 (Auto)** |
| **2** | `gke-bad-rollout` | `gke-crashloop-rollback` | GKE `deployment/cartservice` | `CrashLoopBackOff` + BQ `REL-042` (`broken-v2`) | **Tier 1 (Auto)** |
| **3** | `gke-pod-crash` | `gke-pod-restart` | GKE `deployment/redis-cart` | Connection pool exhaustion / pod deadlock | **Tier 2 (HITL + PAM)** |
| **4** | `gke-payment-latency` | `gke-horizontal-upsize` | GKE `deployment/paymentservice` | Trace p99 latency `> 2000ms`, CPU throttling | **Tier 2 (HITL + PAM)** |
| **5** | `gke-network-firewall-block` | `gke-network-firewall-recovery` | GKE `NetworkPolicy` (`checkoutservice`) | `dial tcp: i/o timeout`, Dataplane V2 packet drop | **Tier 2 (HITL + PAM)** |
| **6** | `gke-dns-outage` | `gke-dns-recovery` | GKE `deployment/coredns` (`kube-system`) | `.svc.cluster.local` lookup failure (`no such host`) | **Tier 1 / Tier 2** |
| **7** | `gcp-nat-port-drop` | `gcp-nat-port-recovery` | Cloud NAT Gateway (`europe-west1`) | `allocated_ports` cap reached, `dropped_sent_packets_count > 0` | **Tier 2 (HITL + PAM)** |
| **8** | `gke-service-routing-break` | `gke-service-routing-recovery` | K8s `service/checkoutservice` | Selector `app=broken-selector`, 0 active endpoints | **Tier 2 (HITL + PAM)** |
| **9** | `argolis-cloudrun-iap-drift` | `argolis-cloudrun-iap-recovery` | Cloud Run `antigravity-web-hub` (Direct IAP) | `403 Forbidden` (missing IAP SA `run.invoker`), `403 org_internal`, or `302 empty token` | **Tier 2 (HITL + PAM)** |
| **10** | `argolis-vertex-quota-spike` | `argolis-vertex-quota-failover` | Vertex AI Reasoning Engines (`europe-west1`) | `HTTP 429 RESOURCE_EXHAUSTED`, `404 gemini-3.7-flash`, `400 thoughtSignature` | **Tier 1 (Auto)** |
| **11** | `argolis-sharedvpc-logsink-lag` | `argolis-sharedvpc-logsink-recovery` | Shared VPC `sb-prod-ew1-shared` & Sink `sre-gke-pam-telemetry-sink` | `compute.subnetworks.use` denied or missing `bigquery.dataEditor` on `argodev-prod-audit-logs-0` | **Tier 2 (HITL + PAM)** |

---

## 🔍 3. Hub-and-Spoke Observability Queries (`argodev-prod-audit-logs-0`)

All deployment correlations, cross-project audit trails, and incident post-mortems are centralized in **`argodev-prod-audit-logs-0`** (`cs-audit`, Region `europe-west1`, `PHYSICAL` storage billing).

### A. Query Recent Releases Ledger (`sre_releases.recent_releases`)
```sql
SELECT
  release_id,
  service_name,
  namespace,
  revision,
  commit_sha,
  author_email,
  timestamp_utc,
  status
FROM `argodev-prod-audit-logs-0.sre_releases.recent_releases`
WHERE service_name IN ('cartservice', 'frontend', 'redis-cart', 'antigravity-web-hub', 'aether-web-gui', 'ge-hosted-agy-agent')
ORDER BY timestamp_utc DESC
LIMIT 10;
```

### B. Query Incident Post-Mortems & MTTD/MTTR Ledger (`sre_releases.incident_postmortems`)
```sql
SELECT
  incident_id,
  severity,
  target_resource,
  alert,
  root_cause,
  mttd_seconds,
  mttr_seconds,
  remediation_status,
  pam_grant_name,
  report_gcs_uri,
  incident_start_time
FROM `argodev-prod-audit-logs-0.sre_releases.incident_postmortems`
WHERE DATE(incident_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
ORDER BY incident_start_time DESC
LIMIT 20;
```

### C. Query PAM JIT Elevation & Cross-Project Audit Logs
```text
-- Cloud Logging Filter (projects/argodev-prod-audit-logs-0 or projects/antigravity-web-hub-argolis)
protoPayload.serviceName="privilegedaccessmanager.googleapis.com"
AND protoPayload.methodName:("CreateGrant" OR "ApproveGrant")
AND timestamp >= "2026-10-05T00:00:00Z"
```

---

## 🛠️ 4. Detailed Scenario Playbooks (Scenarios 1–11)

### Scenario 1: GKE Replica Scale Outage (`gke-scale-outage` $\rightarrow$ `gke-scale-recovery`)
* **Governance Tier**: **Tier 1 (Autonomous Auto-Recovery)**
* **Target Resource**: `deployment/frontend` in namespace `default` (`online-boutique`, `europe-west1`)
* **Symptoms**: Storefront returns `HTTP 503 Service Unavailable`; `kubectl get deployment frontend` reports `0/0` ready replicas.
* **Cloud Logging / PromQL Query**:
  ```promql
  sum(kubernetes_io:container_uptime{project_id="antigravity-web-hub-argolis", cluster_name="online-boutique", namespace_name="default", controller_name="frontend"}) == 0
  ```
* **Autonomous Remediation**:
  `rca-telemetry-expert` delegates via A2A to `remediation-executor` (`scale deployment frontend in namespace default to 1 replica in cluster online-boutique`).
* **Verification Command**:
  ```bash
  kubectl get deployment frontend -n default -o jsonpath='{.status.readyReplicas}{"\n"}'
  ```

---

### Scenario 2: GKE Bad Container Rollout (`gke-bad-rollout` $\rightarrow$ `gke-crashloop-rollback`)
* **Governance Tier**: **Tier 1 (Autonomous Auto-Rollback)**
* **Target Resource**: `deployment/cartservice` in namespace `default` (`online-boutique`, `europe-west1`)
* **Symptoms**: Adding items to cart fails with `500 Internal Server Error`; `cartservice` pods enter `CrashLoopBackOff` / `ErrImagePull`.
* **Cloud Logging & BigQuery Correlation**:
  - Cloud Logging:
    ```text
    resource.type="k8s_container" AND resource.labels.cluster_name="online-boutique" AND resource.labels. location="europe-west1" AND resource.labels.pod_name:"cartservice" AND severity>=ERROR
    ```
  - BigQuery Release Correlation (`argodev-prod-audit-logs-0`):
    ```sql
    SELECT * FROM `argodev-prod-audit-logs-0.sre_releases.recent_releases`
    WHERE service_name = 'cartservice' ORDER BY timestamp_utc DESC LIMIT 1;
    ```
* **Autonomous Remediation**:
  Reverts `deployment/cartservice` container image from `cartservice:broken-v2` (`REL-042`) to the verified stable image `gcr.io/google-samples/microservices-demo/cartservice:v1.0.4`.
* **Verification Command**:
  ```bash
  kubectl rollout status deployment/cartservice -n default --timeout=60s
  ```

---

### Scenario 3: Redis Cache Deadlock & Pod Crash (`gke-pod-crash` $\rightarrow$ `gke-pod-restart`)
* **Governance Tier**: **Tier 2 (Gated HITL Approval + PAM JIT)**
* **Target Resource**: `deployment/redis-cart` in namespace `default` (`online-boutique`, `europe-west1`)
* **Symptoms**: `cartservice` logs `redis: connection pool timeout` or `EOF`; `redis-cart` pod is deadlocked.
* **Cloud Logging Query**:
  ```text
  resource.type="k8s_container" AND resource.labels.cluster_name="online-boutique" AND resource.labels.pod_name:"redis-cart" AND severity>=WARNING
  ```
* **HITL Remediation**:
  Renders A2UI v0.8 approval card. Upon operator approval, elevates via PAM (`gke-editor`) and performs a clean rolling restart of `deployment/redis-cart`.
* **Verification Command**:
  ```bash
  kubectl get pods -n default -l app=redis-cart
  ```

---

### Scenario 4: Payment Service Latency Bottleneck (`gke-payment-latency` $\rightarrow$ `gke-horizontal-upsize`)
* **Governance Tier**: **Tier 2 (Gated HITL Approval + PAM JIT)**
* **Target Resource**: `deployment/paymentservice` in namespace `default` (`online-boutique`, `europe-west1`)
* **Symptoms**: Checkout requests experience p99 latency `> 2000ms`; Cloud Trace waterfalls identify `hipstershop.PaymentService/Charge` as the bottleneck span while `paymentservice` is throttled at `1` replica.
* **PromQL Query**:
  ```promql
  histogram_quantile(0.99, sum(rate(workload_googleapis_com:rpc_server_duration_bucket{project_id="antigravity-web-hub-argolis", service_name="paymentservice"}[5m])) by (le)) > 2000
  ```
* **HITL Remediation**:
  Upon operator approval, scales `deployment/paymentservice` from `1` to `3` replicas.
* **Verification Command**:
  ```bash
  kubectl get deployment paymentservice -n default
  ```

---

### Scenario 5: Restrictive NetworkPolicy Block (`gke-network-firewall-block` $\rightarrow$ `gke-network-firewall-recovery`)
* **Governance Tier**: **Tier 2 (Gated HITL Approval + PAM JIT)**
* **Target Resource**: `NetworkPolicy` isolating `checkoutservice` in namespace `default` (`online-boutique`, `europe-west1`)
* **Symptoms**: `checkoutservice` pods are `Running` (`1/1`) with `0` restarts, but all upstream/downstream gRPC calls fail with `dial tcp: i/o timeout`.
* **Cloud Logging Query**:
  ```text
  resource.type="k8s_container" AND resource.labels.cluster_name="online-boutique" AND resource.labels.pod_name:"checkoutservice" AND textPayload:"i/o timeout"
  ```
* **HITL Remediation**:
  Upon operator approval, deletes the isolating `NetworkPolicy` (`deny-all-checkout` / `checkout-isolation-policy`) in namespace `default`.
* **Verification Command**:
  ```bash
  kubectl get networkpolicy -n default
  ```

---

### Scenario 6: CoreDNS Cluster Resolution Outage (`gke-dns-outage` $\rightarrow$ `gke-dns-recovery`)
* **Governance Tier**: **Tier 1 / Tier 2 Cluster DNS Recovery**
* **Target Resource**: `deployment/coredns` (or `kube-dns`) in namespace `kube-system` (`online-boutique`, `europe-west1`)
* **Symptoms**: Cluster-wide service discovery fails with `lookup <service>.default.svc.cluster.local: no such host` or `i/o timeout` on port `53`.
* **Cloud Logging Query**:
  ```text
  resource.type="k8s_container" AND resource.labels.cluster_name="online-boutique" AND textPayload:"svc.cluster.local" AND severity>=ERROR
  ```
* **Remediation**:
  Restores `coredns` / `kube-dns` deployment in `kube-system` back to `2` healthy replicas.
* **Verification Command**:
  ```bash
  kubectl get deployment -n kube-system -l k8s-app=kube-dns
  ```

---

### Scenario 7: Cloud NAT Egress Port Exhaustion (`gcp-nat-port-drop` $\rightarrow$ `gcp-nat-port-recovery`)
* **Governance Tier**: **Tier 2 (Gated HITL Approval + PAM JIT)**
* **Target Resource**: Cloud NAT Gateway on router `sre-agent-router` (`europe-west1`) in `antigravity-web-hub-argolis`
* **Symptoms**: Outbound calls from private GKE Autopilot nodes fail intermittently; Cloud Monitoring metric `router.googleapis.com/nat/dropped_sent_packets_count` or `nat_allocation_failed` spikes.
* **PromQL Query**:
  ```promql
  sum(rate(router_googleapis_com:nat_dropped_sent_packets_count{project_id="antigravity-web-hub-argolis", region="europe-west1"}[5m])) > 0
  ```
* **HITL Remediation**:
  Upon operator approval, updates the Cloud NAT gateway in `europe-west1` to increase `minPortsPerVm` from `64` to `256` (and enables dynamic port allocation up to `maxPortsPerVm=4096`).
* **Verification Command**:
  ```bash
  gcloud compute routers nats describe sre-agent-nat --router=sre-agent-router --region=europe-west1 --project=antigravity-web-hub-argolis
  ```

---

### Scenario 8: Kubernetes Service Selector Corruption (`gke-service-routing-break` $\rightarrow$ `gke-service-routing-recovery`)
* **Governance Tier**: **Tier 2 (Gated HITL Approval + PAM JIT)**
* **Target Resource**: Kubernetes `Service/checkoutservice` in namespace `default` (`online-boutique`, `europe-west1`)
* **Symptoms**: `checkoutservice` deployment pods are `Running` (`1/1`), no `NetworkPolicy` exists, DNS resolves the ClusterIP, but connections fail with `Connection refused` or `no endpoints available` because `spec.selector.app` was mutated to `broken-selector`.
* **Diagnostic Check**:
  ```bash
  kubectl get svc checkoutservice -n default -o jsonpath='{.spec.selector}{"\n"}'
  kubectl get endpoints checkoutservice -n default
  ```
* **HITL Remediation**:
  Upon operator approval, patches `Service/checkoutservice` selector back to `app=checkoutservice`.
* **Verification Command**:
  ```bash
  kubectl get endpoints checkoutservice -n default
  ```

---

### Scenario 9: Argolis Direct Cloud Run IAP & OAuth Recovery (`argolis-cloudrun-iap-drift` $\rightarrow$ `argolis-cloudrun-iap-recovery`)
* **Governance Tier**: **Tier 2 (Gated HITL Approval + PAM JIT)**
* **Target Resource**: Direct IAP-protected Cloud Run services (`antigravity-web-hub`, `aether-web-gui`, `ge-hosted-agy-agent`) in `antigravity-web-hub-argolis` (`723040006558`, `europe-west1`)
* **Symptoms**:
  1. **`HTTP 403 Forbidden` after IAP sign-in**: The project's IAP Service Agent `service-723040006558@gcp-sa-iap.iam.gserviceaccount.com` lacks `roles/run.invoker` on the Cloud Run service.
  2. **`HTTP 403 org_internal` (`The OAuth client was not found` / `restricted to users within its organization`)**: Direct Cloud Run IAP is using the system-managed OAuth client instead of the custom Web Application OAuth 2.0 Client bound via `gcloud iap settings set`.
  3. **`HTTP 302 Redirect Loop` (`Invalid IAP credentials: empty token`)**: An Nginx frontend proxy inside Cloud Run forwards `X-Goog-IAP-JWT-Assertion` to an upstream service without clearing it (`proxy_set_header X-Goog-IAP-JWT-Assertion "";`).
* **Cloud Logging & BigQuery Audit Queries (`argodev-prod-audit-logs-0`)**:
  ```text
  resource.type="cloud_run_revision" AND resource.labels.service_name="antigravity-web-hub" AND resource.labels.location="europe-west1" AND (httpRequest.status=403 OR httpRequest.status=302)
  ```
  ```sql
  SELECT timestamp, protoPayload.methodName, protoPayload.authenticationInfo.principalEmail, protoPayload.resourceName
  FROM `argodev-prod-audit-logs-0.audit_export.cloudaudit_googleapis_com_activity`
  WHERE protoPayload.serviceName IN ('run.googleapis.com', 'iap.googleapis.com')
  ORDER BY timestamp DESC LIMIT 10;
  ```
* **Strict Argolis Security Rule (`go/argolis-iam-rules`)**:
  Zero `allUsers`, zero `allAuthenticatedUsers`, zero `@google.com`, and zero `domain:*` bindings. Only `serviceAccount:service-723040006558@gcp-sa-iap.iam.gserviceaccount.com` (`roles/run.invoker`) and explicit operator emails (`roles/iap.httpsResourceAccessor`) are permitted.
* **HITL Remediation & Verification Commands**:
  ```bash
  # 1. Ensure IAP Service Agent exists and holds roles/run.invoker
  gcloud beta services identity create --service=iap.googleapis.com --project=antigravity-web-hub-argolis
  gcloud run services add-iam-policy-binding antigravity-web-hub \
    --region=europe-west1 \
    --project=antigravity-web-hub-argolis \
    --member="serviceAccount:service-723040006558@gcp-sa-iap.iam.gserviceaccount.com" \
    --role="roles/run.invoker"

  # 2. Verify IAP settings and IAM bindings
  gcloud iap settings get --project=antigravity-web-hub-argolis --resource-type=cloud-run --service=antigravity-web-hub --region=europe-west1
  gcloud run services get-iam-policy antigravity-web-hub --region=europe-west1 --project=antigravity-web-hub-argolis
  ```

---

### Scenario 10: Argolis Vertex AI Quota Exhaustion, Model Routing & Model Armor Failover (`argolis-vertex-quota-spike` $\rightarrow$ `argolis-vertex-quota-failover`)
* **Governance Tier**: **Tier 1 (Autonomous Fast-Path Auto-Recovery)**
* **Target Resource**: Vertex AI Reasoning Engines (`rca-telemetry-expert`, `remediation-executor`, `outage-simulator`, `incident-report-writer`) in `antigravity-web-hub-argolis` (`europe-west1` / `global`)
* **Symptoms**:
  1. **`HTTP 429 RESOURCE_EXHAUSTED`**: Regional TPM or concurrent request quota saturation in `europe-west1` or `global`.
  2. **`HTTP 404 NOT_FOUND`**: Rollout referenced an unprovisioned model identifier (e.g. `gemini-3.7-flash`).
  3. **`HTTP 400 INVALID_ARGUMENT`**: Missing `thoughtSignature` on multi-turn tool calls with Gemini 3.x models (`gemini-3-flash-preview` / `gemini-3.1-pro-preview`), or Model Armor floor settings drift.
* **BigQuery Agent Analytics Query (`argodev-prod-audit-logs-0`)**:
  ```sql
  SELECT timestamp, model_name, location, status_code, error_message
  FROM `argodev-prod-audit-logs-0.agent_analytics.vertex_ai_user_telemetry`
  WHERE status_code IN (400, 404, 429)
  ORDER BY timestamp DESC LIMIT 20;
  ```
* **Autonomous Remediation**:
  Automatically routes standard agent calls to verified `gemini-2.5-flash` (with `gemini-3.1-pro-preview` for Tier 3 escalation), enables `global` $\leftrightarrow$ `europe-west1` endpoint failover in `GlobalGemini`, preserves `thoughtSignature` across tool turns, and verifies Model Armor inline screening (`INSPECT_AND_BLOCK`).
* **Verification Command**:
  ```bash
  python3 -c "from app.config import GEMINI_MODEL, GEMINI_PRO_MODEL, screen_prompt_with_model_armor; print(GEMINI_MODEL, GEMINI_PRO_MODEL, screen_prompt_with_model_armor('Check frontend pod status'))"
  ```

---

### Scenario 11: Argolis Shared VPC Subnet IAM & Central Log Sink Recovery (`argolis-sharedvpc-logsink-lag` $\rightarrow$ `argolis-sharedvpc-logsink-recovery`)
* **Governance Tier**: **Tier 2 (Gated HITL Approval + PAM JIT)**
* **Target Resource**:
  - Shared VPC Host Project `cs-host-78e19ed8055b4c6980cce9` (Subnet `sb-prod-ew1-shared` `10.10.0.0/20` in `europe-west1`)
  - Cloud Logging Sink `sre-gke-pam-telemetry-sink` in `antigravity-web-hub-argolis` exporting to `bigquery.googleapis.com/projects/argodev-prod-audit-logs-0/datasets/sre_releases`
* **Symptoms**:
  1. **Shared VPC Drift**: Cloud Run Direct VPC Egress or GKE Autopilot nodes fail with `Required 'compute.subnetworks.use' permission` on `sb-prod-ew1-shared`.
  2. **Log Sink Lag**: GKE container logs (`k8s_container`) and PAM grant logs stop appearing in `argodev-prod-audit-logs-0:sre_releases` because the sink's `writerIdentity` lost `roles/bigquery.dataEditor`.
* **Cloud Logging & Sink Diagnostic Commands**:
  ```bash
  gcloud logging sinks describe sre-gke-pam-telemetry-sink --project=antigravity-web-hub-argolis
  bq show --format=prettyjson argodev-prod-audit-logs-0:sre_releases
  ```
* **HITL Remediation & Verification Commands**:
  ```bash
  # Verify sink writer identity has roles/bigquery.dataEditor on argodev-prod-audit-logs-0:sre_releases
  export SINK_WRITER=$(gcloud logging sinks describe sre-gke-pam-telemetry-sink --project=antigravity-web-hub-argolis --format="value(writerIdentity)")
  echo "Verified Sink Writer Identity: $SINK_WRITER"
  ```
