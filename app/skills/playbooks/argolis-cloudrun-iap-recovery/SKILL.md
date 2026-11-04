---
name: argolis-cloudrun-iap-recovery
description: Playbook 9 (Tier 2 HITL Approval) — Use when Direct Cloud Run IAP authentication fails in Argolis (HTTP 403 Forbidden due to missing service-<PROJECT_NUM>@gcp-sa-iap.iam.gserviceaccount.com roles/run.invoker, HTTP 403 org_internal due to missing Custom OAuth 2.0 Client binding on gcloud iap settings, or HTTP 302 Invalid IAP credentials empty token on Nginx upstream proxy). Enforces strict go/argolis-iam-rules (explicit user emails only, zero allUsers, zero @google.com, zero domain:* bindings).
---

# SRE Playbook 9: Argolis Direct Cloud Run IAP & OAuth Recovery (`403 Forbidden` / `403 org_internal` / `302 Empty Token`)

## Target Scenario
* **Target Services**: Argolis Cloud Run services protected by Direct IAP in `antigravity-web-hub-argolis` (`723040006558`, `europe-west1`), such as `antigravity-web-hub`, `aether-web-gui`, `ge-hosted-agy-agent`, or `gcal-agent-webhook`.
* **Diagnostic Trigger**: `rca_telemetry_expert` queries Cloud Logging in `antigravity-web-hub-argolis` and the Central Audit Hub `argodev-prod-audit-logs-0` (`cs-audit`) and detects one of three canonical Argolis Direct Cloud Run IAP failure signatures:
  1. **`HTTP 403 Forbidden` (Cloud Run IAM rejection after IAP login)**: The IAP Service Agent `service-723040006558@gcp-sa-iap.iam.gserviceaccount.com` (`service-<PROJECT_NUM>@gcp-sa-iap.iam.gserviceaccount.com`) is missing `roles/run.invoker` on the target Cloud Run service, or the operator's explicit corporate/Argolis email is missing `roles/iap.httpsResourceAccessor`.
  2. **`HTTP 403 org_internal` (Google OAuth Error: This client is restricted to users within its organization)**: The Cloud Run service is using the default GCP-managed IAP OAuth client (which is restricted to `@jpaquay.altostrat.com` identities) instead of a custom Web Application OAuth 2.0 Client bound via `gcloud iap settings set`.
  3. **`HTTP 302 Redirect Loop` (`x-goog-iap-er: Invalid IAP credentials: empty token`)**: An Nginx or multi-container frontend reverse proxy inside Cloud Run is forwarding requests to an internal backend URL with `proxy_pass_request_headers on` without stripping `X-Goog-IAP-JWT-Assertion` (`proxy_set_header X-Goog-IAP-JWT-Assertion "";`) or is routing to an external `*.run.app` URL instead of `localhost` / internal service discovery.

## Strict Argolis Security Guardrails (`go/argolis-iam-rules`)
* **NEVER** bind `allUsers` or `allAuthenticatedUsers` to any Cloud Run service or IAP resource.
* **NEVER** bind `@google.com` or `domain:google.com` or `domain:jpaquay.altostrat.com` principals in Argolis IAM policies (`constraints/iam.allowedPolicyMemberDomains` is strictly enforced).
* **ALWAYS** bind only explicit, verified individual user emails (`user:<explicit-user-email>`) and the dedicated project IAP Service Agent (`serviceAccount:service-723040006558@gcp-sa-iap.iam.gserviceaccount.com`).

## Remediation Action (Tier 2 - HITL Approval Required + PAM JIT Audit)
1. **Present the Executive Resolution Plan** to the human operator via the A2UI v0.8 approval card:
   - Specify the exact failure signature (`missing_iap_service_agent_invoker`, `oauth_org_internal_mismatch`, or `nginx_iap_header_collision`).
   - Propose the exact declarative remediation steps:
     - **Signature 1 (Missing IAP Service Agent `roles/run.invoker`)**:
       `gcloud beta services identity create --service=iap.googleapis.com --project=antigravity-web-hub-argolis`
       `gcloud run services add-iam-policy-binding <SERVICE_NAME> --region=europe-west1 --project=antigravity-web-hub-argolis --member="serviceAccount:service-723040006558@gcp-sa-iap.iam.gserviceaccount.com" --role="roles/run.invoker"`
     - **Signature 2 (`403 org_internal` Custom OAuth Client Binding)**:
       Apply the custom OAuth 2.0 Web Client configuration (`oauthSettings.clientId` and `oauthSettings.clientSecretSha256`) via `gcloud iap settings set iap_settings.yaml --project=antigravity-web-hub-argolis --resource-type=cloud-run --service=<SERVICE_NAME> --region=europe-west1`.
     - **Signature 3 (`302 Empty Token` on Nginx Upstream)**:
       Roll back or patch the Cloud Run revision / Nginx config to strip `X-Goog-IAP-JWT-Assertion` before upstream forwarding and route over internal loopback.
2. **Upon Operator Approval (`APPROVED`)**:
   - Call `remediation_executor_remote("Restore Direct Cloud Run IAP configuration on service <SERVICE_NAME> in project antigravity-web-hub-argolis (region europe-west1): ensure service-723040006558@gcp-sa-iap.iam.gserviceaccount.com has roles/run.invoker, verify custom OAuth iap_settings binding, and enforce zero allUsers/@google.com bindings. [PAM_JUSTIFICATION]: Approved Tier 2 Direct Cloud Run IAP recovery for <SERVICE_NAME>")`.
3. **Post-Remediation Verification**:
   - Verify Cloud Run IAM policy contains `serviceAccount:service-723040006558@gcp-sa-iap.iam.gserviceaccount.com` with `roles/run.invoker` and zero prohibited principals.
   - Verify `httpRequest.status` returns `200 OK` on authenticated probe and report `SUCCESS`.
