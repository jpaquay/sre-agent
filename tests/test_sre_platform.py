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

"""End-to-End & Unit Validation Runner for the 4-Agent NovaSRE Platform on Argolis."""

import argparse
import json
import os
import pathlib
import sys
from dotenv import load_dotenv

SRE_AGENT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(SRE_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(SRE_AGENT_ROOT))

load_dotenv(SRE_AGENT_ROOT / ".env")

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "antigravity-web-hub-argolis")
PROJECT_NUMBER = os.environ.get("NOVASRE_PROJECT_NUMBER", "723040006558")
LOGGING_PROJECT_ID = os.environ.get("LOGGING_PROJECT_ID", "argodev-prod-audit-logs-0")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")
GKE_CLUSTER_NAME = os.environ.get("GKE_CLUSTER_NAME", "online-boutique")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
DEPLOYED_URNS_PATH = SRE_AGENT_ROOT / "deployed_urns.json"

NOVASRE_11_SCENARIOS = {
    "scale_to_zero": {
        "id": 1,
        "tier": "Tier 1 Auto-Recovery",
        "playbook": "gke-scale-recovery",
        "simulation": "gke-scale-to-zero",
        "alert_template": "CRITICAL ALERT: GKE Deployment 'frontend' in namespace '{namespace}' in cluster '{cluster}' ({region}) has 0/1 readyReplicas.",
    },
    "bad_image_rollout": {
        "id": 2,
        "tier": "Tier 1 Auto-Recovery",
        "playbook": "gke-crashloop-rollback",
        "simulation": "gke-bad-image-rollout",
        "alert_template": "CRITICAL ALERT: GKE Deployment 'cartservice' in namespace '{namespace}' in cluster '{cluster}' ({region}) is failing in CrashLoopBackOff / ErrImagePull after canary rollout.",
    },
    "pod_delete": {
        "id": 3,
        "tier": "Tier 2 HITL + PAM JIT",
        "playbook": "gke-pod-restart",
        "simulation": "gke-pod-delete",
        "alert_template": "CRITICAL ALERT: GKE Pod '{pod}' (redis-cart) in namespace '{namespace}' is experiencing stateful Redis lock / pod termination.",
    },
    "cpu_throttle": {
        "id": 4,
        "tier": "Tier 2 HITL + PAM JIT",
        "playbook": "gke-horizontal-upsize",
        "simulation": "gke-cpu-throttle",
        "alert_template": "CRITICAL ALERT: GKE Deployment 'paymentservice' (pod {pod}) in namespace '{namespace}' is experiencing severe CPU throttling and p99 latency > 2000ms.",
    },
    "corrupt_service_selector": {
        "id": 5,
        "tier": "Tier 2 HITL + PAM JIT",
        "playbook": "gke-service-routing-recovery",
        "simulation": "gke-corrupt-service-selector",
        "alert_template": "CRITICAL ALERT: GKE Service 'checkoutservice' in namespace '{namespace}' has 0 active endpoints due to selector mismatch (app=broken-selector).",
    },
    "dns_outage": {
        "id": 6,
        "tier": "Tier 2 HITL + PAM JIT",
        "playbook": "gke-dns-recovery",
        "simulation": "gke-dns-outage",
        "alert_template": "CRITICAL ALERT: CoreDNS / kube-dns resolution failure in cluster '{cluster}' ({region}); microservices cannot resolve internal service hostnames.",
    },
    "network_policy_block": {
        "id": 7,
        "tier": "Tier 2 HITL + PAM JIT",
        "playbook": "gke-network-firewall-recovery",
        "simulation": "gke-network-policy-block",
        "alert_template": "CRITICAL ALERT: Restrictive NetworkPolicy 'chaos-block-checkoutservice' in namespace '{namespace}' is dropping all ingress and egress traffic.",
    },
    "nat_port_exhaustion": {
        "id": 8,
        "tier": "Tier 2 HITL + PAM JIT",
        "playbook": "gcp-nat-port-recovery",
        "simulation": "gcp-nat-port-exhaustion",
        "alert_template": "CRITICAL ALERT: Cloud NAT gateway 'sre-agent-nat' on router 'sre-agent-router' in '{region}' is dropping outbound packets due to SNAT port exhaustion.",
    },
    "argolis_cloudrun_iap_drift": {
        "id": 9,
        "tier": "Tier 2 HITL + PAM JIT",
        "playbook": "argolis-cloudrun-iap-recovery",
        "simulation": "argolis-cloudrun-iap-drift",
        "alert_template": "CRITICAL ALERT: Direct Cloud Run IAP service 'antigravity-web-hub' in project 'antigravity-web-hub-argolis' ({region}) is returning HTTP 403 Forbidden / org_internal.",
    },
    "argolis_vertex_quota_spike": {
        "id": 10,
        "tier": "Tier 1 Auto-Recovery",
        "playbook": "argolis-vertex-quota-failover",
        "simulation": "argolis-vertex-quota-spike",
        "alert_template": "CRITICAL ALERT: Vertex AI Reasoning Engine 'ge-hosted-agy-agent' in 'antigravity-web-hub-argolis' ({region}) is encountering HTTP 429 RESOURCE_EXHAUSTED and unprovisioned model 404 (gemini-3.7-flash).",
    },
    "argolis_sharedvpc_logsink_lag": {
        "id": 11,
        "tier": "Tier 2 HITL + PAM JIT",
        "playbook": "argolis-sharedvpc-logsink-recovery",
        "simulation": "argolis-sharedvpc-logsink-lag",
        "alert_template": "CRITICAL ALERT: Central Audit Hub log sink 'sre-gke-pam-telemetry-sink' to 'argodev-prod-audit-logs-0.sre_releases' and Shared VPC subnet 'sb-prod-ew1-shared' report PERMISSION_DENIED drift.",
    },
}

# Legacy CLI aliases mapped to the 11-scenario catalog
LEGACY_ALERT_ALIASES = {
    "oom": "bad_image_rollout",
    "latency": "cpu_throttle",
    "fake": "pod_delete",
}


def resolve_deployed_urns() -> dict:
    """Resolve the 4 NovaSRE Reasoning Engine URNs from deployed_urns.json or environment variables."""
    file_data = {}
    if DEPLOYED_URNS_PATH.is_file():
        try:
            file_data = json.loads(DEPLOYED_URNS_PATH.read_text(encoding="utf-8"))
        except Exception:
            file_data = {}

    default_prefix = f"projects/{PROJECT_NUMBER}/locations/{LOCATION}/reasoningEngines"
    return {
        "rca-telemetry-expert": (
            os.environ.get("NOVASRE_RCA_URN")
            or os.environ.get("INVESTIGATOR_AGENT_URN")
            or file_data.get("NOVASRE_RCA_URN")
            or file_data.get("rca-telemetry-expert")
            or f"{default_prefix}/rca-telemetry-expert"
        ),
        "remediation-executor": (
            os.environ.get("NOVASRE_REMEDIATOR_URN")
            or os.environ.get("REMEDIATION_AGENT_URN")
            or file_data.get("NOVASRE_REMEDIATOR_URN")
            or file_data.get("remediation-executor")
            or f"{default_prefix}/remediation-executor"
        ),
        "outage-simulator": (
            os.environ.get("NOVASRE_SIMULATOR_URN")
            or os.environ.get("OUTAGE_SIMULATOR_URN")
            or file_data.get("NOVASRE_SIMULATOR_URN")
            or file_data.get("outage-simulator")
            or f"{default_prefix}/outage-simulator"
        ),
        "incident-report-writer": (
            os.environ.get("NOVASRE_REPORTER_URN")
            or os.environ.get("INCIDENT_REPORT_WRITER_URN")
            or file_data.get("NOVASRE_REPORTER_URN")
            or file_data.get("incident-report-writer")
            or f"{default_prefix}/incident-report-writer"
        ),
    }


def build_alert_message(alert_type: str, pod: str = "frontend-0", namespace: str = "default") -> str:
    """Build a realistic alert message for any of the 11 NovaSRE scenarios or legacy CLI aliases."""
    scenario_key = LEGACY_ALERT_ALIASES.get(alert_type, alert_type)
    spec = NOVASRE_11_SCENARIOS.get(scenario_key, NOVASRE_11_SCENARIOS["scale_to_zero"])
    return spec["alert_template"].format(
        pod=pod,
        namespace=namespace,
        cluster=GKE_CLUSTER_NAME,
        region=LOCATION,
    )


# =========================================================================
# PYTEST UNIT TESTS
# =========================================================================
def test_sre_platform_configuration_and_urn_resolution():
    """Verify NovaSRE platform test runner defaults to antigravity-web-hub-argolis and europe-west1."""
    assert PROJECT_ID == "antigravity-web-hub-argolis"
    assert LOGGING_PROJECT_ID == "argodev-prod-audit-logs-0"
    assert LOCATION == "europe-west1"
    assert GKE_CLUSTER_NAME == "online-boutique"
    assert GEMINI_MODEL == "gemini-2.5-flash"

    urns = resolve_deployed_urns()
    assert set(urns.keys()) == {
        "rca-telemetry-expert",
        "remediation-executor",
        "outage-simulator",
        "incident-report-writer",
    }
    for agent_name, urn in urns.items():
        assert "europe-west1" in urn and "reasoningEngines/" in urn, (
            f"Unexpected URN format for {agent_name}: {urn}"
        )


def test_sre_platform_11_scenarios_alert_formulation():
    """Verify all 11 NovaSRE scenarios (8 GKE + 3 Argolis) produce non-empty structured alerts."""
    assert len(NOVASRE_11_SCENARIOS) == 11
    for key, spec in NOVASRE_11_SCENARIOS.items():
        msg = build_alert_message(key, pod="cartservice-abc", namespace="default")
        assert "CRITICAL ALERT:" in msg
        assert spec["playbook"]
        assert spec["simulation"]


def main():
    import vertexai
    from vertexai.preview import reasoning_engines

    all_choices = list(NOVASRE_11_SCENARIOS.keys()) + list(LEGACY_ALERT_ALIASES.keys())
    parser = argparse.ArgumentParser(
        description="End-to-End Test Runner for 4-Agent NovaSRE Platform on Argolis"
    )
    parser.add_argument(
        "--pod",
        type=str,
        default="frontend-0",
        help="The GKE pod or service name to target (default: frontend-0)",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="default",
        help="The GKE namespace of the pod (default: 'default')",
    )
    parser.add_argument(
        "--alert-type",
        type=str,
        choices=all_choices,
        default="scale_to_zero",
        help="The scenario simulation type to run (supports all 11 NovaSRE scenarios)",
    )
    args = parser.parse_args()

    urns = resolve_deployed_urns()
    investigator_urn = urns["rca-telemetry-expert"]

    print("=" * 80)
    print("STARTING END-TO-END NOVASRE PLATFORM VALIDATION (ARGOLIS)")
    print("=" * 80)
    print(f"Runtime Project:  {PROJECT_ID} ({PROJECT_NUMBER})")
    print(f"Audit Hub:        {LOGGING_PROJECT_ID}")
    print(f"Target Region:    {LOCATION}")
    print(f"GKE Cluster:      {GKE_CLUSTER_NAME}")
    print(f"Target Resource:  {args.pod} (Namespace: {args.namespace})")
    print(f"Simulation Type:  {args.alert_type}")
    print("-" * 80)

    vertexai.init(project=PROJECT_ID, location=LOCATION)
    alert_msg = build_alert_message(args.alert_type, pod=args.pod, namespace=args.namespace)
    print(f"🚨 Ingesting Simulated Alert:\n   -> '{alert_msg}'\n")
    print(f"Connecting to SRE Investigator Agent URN:\n   -> {investigator_urn}...")

    try:
        investigator = reasoning_engines.ReasoningEngine(investigator_urn)
        response = investigator.query(
            message=alert_msg,
            user_id="sre-test-operator",
            session_id=f"test-session-{args.alert_type}",
        )
        print("=" * 80)
        print("🏆 PLATFORM EXECUTION RESPONSE RECEIVER")
        print("=" * 80)
        print(response)
        print("=" * 80)
    except Exception as e:
        print(f"\n❌ Execution failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
