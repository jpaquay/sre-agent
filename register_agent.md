# 🛡️ NovaSRE — Agent Registration & Verification Guide (Argolis `europe-west1` Edition)

This guide provides step-by-step instructions for registering and verifying the **`outage-simulator`** and **`rca-telemetry-expert`** Vertex AI Reasoning Engines in your **Gemini Enterprise** web application across the `jpaquay.altostrat.com` Argolis organization.

---

## 📋 Dynamic Component & Argolis Environment Discovery

Extract your deployment's active live identifiers from `antigravity-web-hub-argolis` (`723040006558`, region `europe-west1`):

```bash
# Set target Argolis Runtime Host Project, Central Audit Hub, and Region
export GCP_PROJECT_ID="antigravity-web-hub-argolis"
export LOGGING_PROJECT_ID="argodev-prod-audit-logs-0"
export GCP_REGION="europe-west1"
export GCP_PROJECT_NUM="723040006558"

# Extract active Reasoning Engine URNs from Vertex AI in europe-west1 (or read deployed_urns.json)
export SIM_URN=$(curl -4 -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://${GCP_REGION}-aiplatform.googleapis.com/v1beta1/projects/${GCP_PROJECT_NUM}/locations/${GCP_REGION}/reasoningEngines" \
  | grep -B 1 '"displayName": "outage-simulator"' | grep 'projects/' | grep -o 'projects/[^"]*' | head -n 1)

export RCA_URN=$(curl -4 -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://${GCP_REGION}-aiplatform.googleapis.com/v1beta1/projects/${GCP_PROJECT_NUM}/locations/${GCP_REGION}/reasoningEngines" \
  | grep -B 1 '"displayName": "rca-telemetry-expert"' | grep 'projects/' | grep -o 'projects/[^"]*' | head -n 1)

export RCA_A2A_URL="https://${GCP_REGION}-aiplatform.googleapis.com/v1beta1/${RCA_URN}/a2a"

echo "========================================================"
echo "Runtime Host Project ID:            $GCP_PROJECT_ID ($GCP_PROJECT_NUM)"
echo "Central Logging & Audit Hub:        $LOGGING_PROJECT_ID (618001173803)"
echo "GCP Region:                         $GCP_REGION"
echo "Outage Simulator URN:               $SIM_URN"
echo "RCA Telemetry Expert URN:           $RCA_URN"
echo "RCA Telemetry Expert A2A URL:       $RCA_A2A_URL"
echo "OAuth Redirect URI:                 https://vertexaisearch.cloud.google.com/oauth-redirect"
echo "========================================================"
```

### Component Reference Matrix

| Component | Description | Format / Argolis Value |
| :--- | :--- | :--- |
| **Runtime Host Project ID** | Spoke project hosting Reasoning Engines & GKE | `antigravity-web-hub-argolis` (`723040006558`) |
| **Central Audit & Logging Hub** | Hub project hosting `sre_releases` BQ & Audit Sinks | `argodev-prod-audit-logs-0` (`618001173803` / `cs-audit`) |
| **GCP Region** | Region hosting Vertex AI Reasoning Engines & GKE | `europe-west1` |
| **Per-Agent Service Accounts** | 4 Least-Privilege SAs in `antigravity-web-hub-argolis` | `sre-investigator-sa`, `sre-remediator-sa`, `sre-reporter-sa`, `sre-simulator-sa` |
| **Gemini Models** | Verified Vertex AI Model Tiering | `gemini-2.5-flash` (default) / `gemini-3.1-pro-preview` (Tier 3) |
| **OAuth 2.0 Redirect URI** | Authorized redirect endpoint for 3LO | `https://vertexaisearch.cloud.google.com/oauth-redirect` |
| **Outage Simulator Engine URN** | Serverless runtime URN for Chaos Engine | `projects/723040006558/locations/europe-west1/reasoningEngines/<SIM_ENGINE_ID>` |
| **RCA Telemetry Expert URN** | Serverless runtime URN for Diagnostician | `projects/723040006558/locations/europe-west1/reasoningEngines/<RCA_ENGINE_ID>` |
| **RCA Telemetry Expert A2A URL** | Direct HTTP+JSON A2A protocol endpoint | `https://europe-west1-aiplatform.googleapis.com/v1beta1/<RCA_URN>/a2a` |

---

## 🔑 Step 1: Create OAuth 2.0 Web Client Credentials

The `rca-telemetry-expert` agent executes operations on behalf of the signed-in operator using Three-Legged OAuth (3LO).

1. Open the [Google Cloud Console Credentials Page](https://console.cloud.google.com/apis/credentials?project=antigravity-web-hub-argolis).
2. If prompted to configure the **OAuth consent screen**:
   - Choose **Internal** (scoped to `jpaquay.altostrat.com`) and click **Create**.
   - Set **App name**: `NovaSRE Assistant`.
   - Provide your support and developer contact email address.
3. In the **Credentials** page:
   - Click **+ Create Credentials** → **OAuth client ID**.
   - Set **Application type**: **Web application**.
   - Set **Name**: `Gemini Enterprise SRE Client`.
   - Under **Authorized redirect URIs**, add:
     ```text
     https://vertexaisearch.cloud.google.com/oauth-redirect
     ```
   - Click **Create** and securely store the **Client ID** and **Client Secret** in Secret Manager (`gsec-env`).

---

## 🤖 Step 2: Register the Outage Simulator in Gemini Enterprise

1. Open your Gemini Enterprise administrative console or Agent Gallery.
2. Click **Add Custom Agent** → **Agent Runtime** (Vertex AI Reasoning Engine).
3. Enter the registration parameters:
   - **Agent Name**: `outage-simulator`
   - **Display Name**: `NovaSRE Chaos Engine (11 Scenarios)`
   - **Reasoning Engine Resource Name / URN**: Use your resolved `$SIM_URN`:
     ```text
     projects/723040006558/locations/europe-west1/reasoningEngines/<SIM_ENGINE_ID>
     ```
   - **Description**:
     ```text
     NovaSRE Chaos Engine (europe-west1). Injects 11 controlled failure modes across GKE Autopilot (online-boutique) and the Argolis fleet (Direct Cloud Run IAP drift, Vertex AI 429 quota spikes, and Shared VPC / Log Sink lag).
     ```
4. Click **Save / Register**.

---

## 🩺 Step 3: Register the RCA Telemetry Expert in Gemini Enterprise

1. In the Gemini Enterprise Console, click **Add Custom Agent** → **Agent-to-Agent (A2A)**.
2. In the **OAuth 2.0 Authentication** section, provide:
   - **Client ID**: `<YOUR_CLIENT_ID_FROM_STEP_1>`
   - **Client Secret**: `<YOUR_CLIENT_SECRET_FROM_STEP_1>`
   - **Authorization URL**: `https://accounts.google.com/o/oauth2/auth?access_type=offline&prompt=consent`
   - **Token URL**: `https://oauth2.googleapis.com/token`
   - **Scope**: `https://www.googleapis.com/auth/cloud-platform`
3. In the **Agent Card** JSON field, paste the following specification (substituting `<RCA_ENGINE_ID>`):

```json
{
  "name": "rca-telemetry-expert",
  "description": "NovaSRE RCA Telemetry Expert (europe-west1). Performs dual-project root-cause analysis across antigravity-web-hub-argolis and argodev-prod-audit-logs-0 (cs-audit), screens with Model Armor, and delegates remediation across 11 playbooks under Tier 1 Auto-Recovery and Tier 2 A2UI HITL + PAM JIT gating.",
  "version": "2.0",
  "protocolVersion": "0.3.0",
  "url": "https://europe-west1-aiplatform.googleapis.com/v1beta1/projects/723040006558/locations/europe-west1/reasoningEngines/<RCA_ENGINE_ID>/a2a",
  "capabilities": {
    "streaming": true,
    "extensions": [
      {
        "uri": "https://a2ui.org/a2a-extension/a2ui/v0.8",
        "description": "Provides agent driven UI using the A2UI JSON format."
      }
    ]
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [],
  "preferredTransport": "HTTP+JSON"
}
```
4. Click **Save / Register**.

---

## 🧪 Step 4: Testing & Verification in Gemini Enterprise (11 Scenarios)

### Test A: Trigger GKE Scale Outage (`Scenario 1` — Tier 1 Auto-Recovery)
```text
@outage-simulator Run the gke-scale-outage simulation — scale the frontend deployment in namespace default in cluster online-boutique (europe-west1) to 0 replicas.
```
```text
@rca-telemetry-expert The online-boutique store in europe-west1 is returning HTTP 503 errors. Investigate root cause and remediate.
```

### Test B: Trigger Argolis Direct Cloud Run IAP Drift (`Scenario 9` — Tier 2 HITL + PAM JIT)
```text
@outage-simulator Run the argolis-cloudrun-iap-drift simulation on antigravity-web-hub in europe-west1.
```
```text
@rca-telemetry-expert Direct Cloud Run IAP on antigravity-web-hub is returning 403 Forbidden / 403 org_internal. Correlate audit logs in argodev-prod-audit-logs-0 and propose Playbook 9 recovery.
```

### Test C: Trigger Argolis Vertex AI Quota Failover (`Scenario 10` — Tier 1 Auto-Recovery)
```text
@outage-simulator Run the argolis-vertex-quota-spike simulation in europe-west1.
```
```text
@rca-telemetry-expert Vertex AI Reasoning Engine requests are failing with HTTP 429 RESOURCE_EXHAUSTED and 404 gemini-3.7-flash. Correlate with argodev-prod-audit-logs-0.agent_analytics and execute Playbook 10 failover.
```
