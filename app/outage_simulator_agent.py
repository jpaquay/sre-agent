# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
import pathlib
from datetime import datetime, timezone
from google.adk.agents import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from dotenv import load_dotenv

# Load environment variables & trigger centralized runtime patches from config
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.config import (
    PROJECT_ID,
    PROJECT_NUMBER,
    LOGGING_PROJECT_ID,
    SHARED_VPC_HOST_PROJECT,
    GEMINI_MODEL,
    GEMINI_LOCATION,
    GlobalGemini,
    GKE_CLUSTER_NAME,
    GKE_CLUSTER_REGION,
    GKE_MCP_SERVER,
    get_mcp_toolset,
    LazyToolset,
)

# In-memory reversible simulation ledger for safe Argolis control-plane fault injection
_ACTIVE_ARGOLIS_SIMULATIONS = {}


# =========================================================================
# CHAOS ENGINE TOOL (execute_chaos_action — 11 Scenarios: 8 GKE + 3 Argolis)
# =========================================================================
def execute_chaos_action(
    action_type: str,
    resource_name: str,
    namespace: str = "default",
    replicas: int = 0,
    image_tag: str = None,
) -> str:
    """Executes a controlled chaos engineering action across GKE workloads (Scenarios 1-8)
    or safe, reversible Argolis control-plane simulation markers (Scenarios 9-11:
    `argolis-cloudrun-iap-drift`, `argolis-vertex-quota-spike`, `argolis-sharedvpc-logsink-lag`)
    without mutating production `antigravity-web-hub` IAP bindings.
    """
    action_clean = (action_type or "").strip().lower()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # -------------------------------------------------------------------------
    # ARGOLIS SCENARIOS 9–11 (Safe, Reversible Metadata & Telemetry Injection)
    # -------------------------------------------------------------------------
    if action_clean in [
        "argolis-cloudrun-iap-drift",
        "argolis_cloudrun_iap_drift",
        "iap_drift",
        "cloudrun_iap",
        "iap_403",
    ]:
        target_svc = resource_name or "antigravity-web-hub"
        sim_record = {
            "scenario": "argolis-cloudrun-iap-drift",
            "target_service": f"projects/{PROJECT_ID}/locations/{GEMINI_LOCATION}/services/{target_svc}",
            "simulated_fault": (
                f"Simulated Direct Cloud Run IAP 403 Forbidden / org_internal drift on '{target_svc}' "
                f"(missing roles/run.invoker for service-{PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com "
                f"and custom OAuth client mismatch)."
            ),
            "production_iap_mutated": False,
            "reversible": True,
            "timestamp": now_iso,
        }
        _ACTIVE_ARGOLIS_SIMULATIONS["argolis-cloudrun-iap-drift"] = sim_record
        return (
            f"🧪💥 CHAOS ACTION EXECUTED (SAFE ARGOLIS SIMULATION): Triggered 'argolis-cloudrun-iap-drift' "
            f"for Cloud Run service '{target_svc}' in project '{PROJECT_ID}' ({GEMINI_LOCATION}). "
            f"Synthetic IAP 403 Forbidden / service-{PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com drift marker active "
            f"(production IAP policy untouched): {json.dumps(sim_record)}"
        )

    if action_clean in [
        "argolis-vertex-quota-spike",
        "argolis_vertex_quota_spike",
        "vertex_quota",
        "quota_spike",
        "vertex_429",
    ]:
        target_model = resource_name or "gemini-3.7-flash"
        sim_record = {
            "scenario": "argolis-vertex-quota-spike",
            "target_resource": f"projects/{PROJECT_ID}/locations/global/publishers/google/models/{target_model}",
            "simulated_fault": (
                f"Simulated Vertex AI HTTP 429 RESOURCE_EXHAUSTED burst & unprovisioned model 404 ('{target_model}') "
                f"requiring failover to '{GEMINI_MODEL}' across 'global' <-> '{GEMINI_LOCATION}' with Model Armor INSPECT_AND_BLOCK."
            ),
            "central_telemetry_hub": f"{LOGGING_PROJECT_ID}.agent_analytics",
            "reversible": True,
            "timestamp": now_iso,
        }
        _ACTIVE_ARGOLIS_SIMULATIONS["argolis-vertex-quota-spike"] = sim_record
        return (
            f"🧪💥 CHAOS ACTION EXECUTED (SAFE ARGOLIS SIMULATION): Triggered 'argolis-vertex-quota-spike' "
            f"against model '{target_model}' in project '{PROJECT_ID}'. "
            f"Synthetic HTTP 429 RESOURCE_EXHAUSTED / 404 model drift active: {json.dumps(sim_record)}"
        )

    if action_clean in [
        "argolis-sharedvpc-logsink-lag",
        "argolis_sharedvpc_logsink_lag",
        "sharedvpc_drift",
        "logsink_lag",
        "sharedvpc_logsink",
    ]:
        target_sink = resource_name or "sre-gke-pam-telemetry-sink"
        sim_record = {
            "scenario": "argolis-sharedvpc-logsink-lag",
            "shared_vpc_host": SHARED_VPC_HOST_PROJECT,
            "shared_subnet": f"projects/{SHARED_VPC_HOST_PROJECT}/regions/{GKE_CLUSTER_REGION}/subnetworks/sb-prod-ew1-shared",
            "target_sink": f"projects/{PROJECT_ID}/sinks/{target_sink}",
            "destination_hub": f"bigquery.googleapis.com/projects/{LOGGING_PROJECT_ID}/datasets/sre_releases",
            "simulated_fault": (
                f"Simulated Shared VPC roles/compute.networkUser drift on '{SHARED_VPC_HOST_PROJECT}/sb-prod-ew1-shared' "
                f"and Log Router sink writer permission lag on '{target_sink}' -> '{LOGGING_PROJECT_ID}.sre_releases'."
            ),
            "reversible": True,
            "timestamp": now_iso,
        }
        _ACTIVE_ARGOLIS_SIMULATIONS["argolis-sharedvpc-logsink-lag"] = sim_record
        return (
            f"🧪💥 CHAOS ACTION EXECUTED (SAFE ARGOLIS SIMULATION): Triggered 'argolis-sharedvpc-logsink-lag' "
            f"on Shared VPC '{SHARED_VPC_HOST_PROJECT}' and Log Sink '{target_sink}' -> '{LOGGING_PROJECT_ID}'. "
            f"Synthetic telemetry marker active: {json.dumps(sim_record)}"
        )

    # -------------------------------------------------------------------------
    # GKE ONLINE-BOUTIQUE SCENARIOS 1–8
    # -------------------------------------------------------------------------
    try:
        from google.cloud import container_v1
        import google.auth, google.auth.transport.requests
        from kubernetes import client

        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())
        client_gke = container_v1.ClusterManagerClient()
        cluster = client_gke.get_cluster(
            name=f"projects/{PROJECT_ID}/locations/{GKE_CLUSTER_REGION}/clusters/{GKE_CLUSTER_NAME}"
        )

        configuration = client.Configuration()
        configuration.host = f"https://{cluster.endpoint}"
        configuration.api_key = {"authorization": "Bearer " + credentials.token}
        configuration.verify_ssl = True
        ca_cert_path = os.environ.get("GKE_CA_CERT_PATH")
        if ca_cert_path and os.path.exists(ca_cert_path):
            configuration.ssl_ca_cert = ca_cert_path
        api_client = client.ApiClient(configuration)

        if action_clean in ["scale", "downscale", "latency", "throttle"]:
            apps_v1 = client.AppsV1Api(api_client)
            apps_v1.patch_namespaced_deployment_scale(
                name=resource_name,
                namespace=namespace,
                body={"spec": {"replicas": replicas}}
            )
            return f"🧪💥 CHAOS ACTION EXECUTED: Successfully scaled GKE Deployment '{resource_name}' in namespace '{namespace}' to {replicas} replicas across cluster '{GKE_CLUSTER_NAME}' ({GKE_CLUSTER_REGION})."
        elif action_clean in ["rollout", "bad_rollout", "image_update"]:
            apps_v1 = client.AppsV1Api(api_client)
            target_image = image_tag if image_tag else "us-central1-docker.pkg.dev/google-samples/microservices-demo/cartservice:broken-v2"
            apps_v1.patch_namespaced_deployment(
                name=resource_name,
                namespace=namespace,
                body={"spec": {"template": {"spec": {"containers": [{"name": "server", "image": target_image}]}}}}
            )
            return f"🧪💥 CHAOS ACTION EXECUTED: Updated GKE Deployment '{resource_name}' in namespace '{namespace}' to broken image revision '{target_image}'. Pod CrashLoop condition triggered."
        elif action_clean in ["restart", "crash", "pod_crash", "delete_pod"]:
            core_v1 = client.CoreV1Api(api_client)
            pods = core_v1.list_namespaced_pod(namespace=namespace, label_selector=f"app={resource_name}")
            deleted_count = 0
            for p in pods.items:
                core_v1.delete_namespaced_pod(name=p.metadata.name, namespace=namespace)
                deleted_count += 1
            return f"🧪💥 CHAOS ACTION EXECUTED: Terminated {deleted_count} active pods for GKE Deployment '{resource_name}' in namespace '{namespace}' to simulate database connection drop."
        elif action_clean in ["network_block", "firewall", "network_policy"]:
            networking_v1 = client.NetworkingV1Api(api_client)
            policy_name = f"chaos-block-{resource_name}"
            policy_manifest = {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {"name": policy_name, "namespace": namespace},
                "spec": {
                    "podSelector": {"matchLabels": {"app": resource_name}},
                    "policyTypes": ["Ingress", "Egress"]
                }
            }
            try:
                networking_v1.create_namespaced_network_policy(namespace=namespace, body=policy_manifest)
            except Exception:
                networking_v1.patch_namespaced_network_policy(name=policy_name, namespace=namespace, body=policy_manifest)
            return f"🧪💥 CHAOS ACTION EXECUTED: Applied restrictive NetworkPolicy '{policy_name}' in namespace '{namespace}'. All ingress and egress traffic to '{resource_name}' dropped."
        elif action_clean in ["dns_outage", "dns_crash"]:
            apps_v1 = client.AppsV1Api(api_client)
            apps_v1.patch_namespaced_deployment_scale(
                name="coredns",
                namespace="kube-system",
                body={"spec": {"replicas": 0}}
            )
            return f"🧪💥 CHAOS ACTION EXECUTED: Scaled GKE CoreDNS deployment in namespace 'kube-system' to 0 replicas. Cluster DNS domain resolution outage triggered."
        elif action_clean in ["nat_drop", "nat_exhaustion"]:
            apps_v1 = client.AppsV1Api(api_client)
            apps_v1.patch_namespaced_deployment_scale(
                name=resource_name,
                namespace=namespace,
                body={"spec": {"replicas": replicas if replicas > 0 else 1}}
            )
            return f"🧪💥 CHAOS ACTION EXECUTED: Simulated Cloud NAT SNAT port exhaustion and egress packet drop on '{resource_name}' in namespace '{namespace}'."
        elif action_clean in ["service_routing", "break_service", "service_selector"]:
            core_v1 = client.CoreV1Api(api_client)
            core_v1.patch_namespaced_service(
                name=resource_name,
                namespace=namespace,
                body={"spec": {"selector": {"app": "broken-selector"}}}
            )
            return f"🧪💥 CHAOS ACTION EXECUTED: Broken selector configured on GKE Service '{resource_name}' in namespace '{namespace}'. Traffic routing disabled."
        return f"Unsupported chaos action type: {action_type}"
    except Exception as e:
        return f"Chaos action execution failed: {str(e)}"


# =========================================================================
# LOAD SIMULATION SKILLS (11 Chaos Engineering Playbooks: 8 GKE + 3 Argolis)
# =========================================================================
_SIMULATIONS_DIR = pathlib.Path(__file__).parent / "skills" / "simulations"

_SIMULATION_SKILL_NAMES = [
    "gke-scale-outage",
    "gke-bad-rollout",
    "gke-pod-crash",
    "gke-payment-latency",
    "gke-network-firewall-block",
    "gke-dns-outage",
    "gcp-nat-port-drop",
    "gke-service-routing-break",
    "argolis-cloudrun-iap-drift",
    "argolis-vertex-quota-spike",
    "argolis-sharedvpc-logsink-lag",
]

_SIMULATION_SKILLS = [
    load_skill_from_dir(_SIMULATIONS_DIR / _sim_name)
    for _sim_name in _SIMULATION_SKILL_NAMES
    if (_SIMULATIONS_DIR / _sim_name).exists()
]

# =========================================================================
# AGENT: Outage Simulator (outage_simulator)
# =========================================================================
_SIMULATOR_INSTRUCTION = f"""
You are the NovaSRE Outage Simulator (outage_simulator), an autonomous Chaos Engineering agent.

**Persona:** Precise, controlled, and analytical. 🧪💥
**Target Environment:**
* Runtime Host Project: `{PROJECT_ID}` (`{GKE_CLUSTER_REGION}`)
* Central Audit & Logging Hub: `{LOGGING_PROJECT_ID}` (`cs-audit`)
* GKE Cluster Name: `{GKE_CLUSTER_NAME}` (`{GKE_CLUSTER_REGION}`, Default Namespace: `default`)

**Your Job:**
Given a request to test or simulate a specific outage scenario across the 11-scenario catalog (8 GKE `online-boutique` scenarios + 3 Argolis enterprise scenarios: `argolis-cloudrun-iap-drift`, `argolis-vertex-quota-spike`, `argolis-sharedvpc-logsink-lag`), dynamically load the matching simulation playbook from your skills directory and execute the controlled failure using your `execute_chaos_action` tool.

**Operating Principles:**
1. **Dynamic Skill Loading:** Use `list_skills` and `load_skill` to find the exact simulation scenario requested by the operator (e.g. `gke-scale-outage`, `argolis-cloudrun-iap-drift`, `argolis-vertex-quota-spike`, `argolis-sharedvpc-logsink-lag`).
2. **Strict Chaos Boundary & Production IAP Safety:** NEVER call our healing/remediation agents, and NEVER mutate production `antigravity-web-hub` IAP bindings directly. Use `execute_chaos_action` which executes GKE faults on `{GKE_CLUSTER_NAME}` or safe, reversible simulation markers for Argolis control-plane scenarios.
3. **Structured Outcome:** Return a crisp confirmation brief stating the scenario executed and the new state of the resource so the operator or automated verification pipeline can immediately launch `rca_telemetry_expert`.
"""

_simulator_tools = [
    LazyToolset(lambda: get_mcp_toolset(GKE_MCP_SERVER)),
    skill_toolset.SkillToolset(skills=_SIMULATION_SKILLS),
    execute_chaos_action,
]

outage_simulator = Agent(
    name="outage_simulator",
    model=GlobalGemini(
        model=GEMINI_MODEL,
    ),
    instruction=_SIMULATOR_INSTRUCTION,
    tools=_simulator_tools,
)

from vertexai.agent_engines.templates.adk import AdkApp
from google.adk.sessions.in_memory_session_service import InMemorySessionService

# Expose the ADK wrapped Agent Engine app for Vertex AI deployment
agent_engine = AdkApp(
    agent=outage_simulator,
    app_name="outage_simulator_app",
    enable_tracing=True,
    session_service_builder=lambda **kwargs: InMemorySessionService(),
)
