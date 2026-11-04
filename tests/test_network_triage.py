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

"""Unified SRE Investigator (Network & Argolis Shared VPC Domain) Integration & Skill Test."""

import os
import pathlib
import re
import subprocess
import sys
import urllib.request

SRE_AGENT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(SRE_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(SRE_AGENT_ROOT))

import app.config as config
import app.investigator_agent as investigator_agent
import app.outage_simulator_agent as outage_simulator_agent


def log(msg):
    print(f"\033[1;34m[TEST_RUNNER]\033[0m {msg}")


def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


# =========================================================================
# PYTEST UNIT TESTS
# =========================================================================
def test_network_triage_playbooks_and_simulations_loaded():
    """Verify GKE & Argolis network playbooks and simulations are loaded and configured for europe-west1."""
    network_playbooks = [
        "gke-dns-recovery",
        "gke-network-firewall-recovery",
        "gcp-nat-port-recovery",
        "argolis-sharedvpc-logsink-recovery",
    ]
    network_simulations = [
        "gke-dns-outage",
        "gke-network-firewall-block",
        "gcp-nat-port-drop",
        "argolis-sharedvpc-logsink-lag",
    ]

    for pb in network_playbooks:
        assert pb in investigator_agent._PLAYBOOK_SKILL_NAMES
        pb_md = SRE_AGENT_ROOT / "app" / "skills" / "playbooks" / pb / "SKILL.md"
        assert pb_md.is_file(), f"Missing network playbook: {pb_md}"

    for sim in network_simulations:
        assert sim in outage_simulator_agent._SIMULATION_SKILL_NAMES
        sim_md = SRE_AGENT_ROOT / "app" / "skills" / "simulations" / sim / "SKILL.md"
        assert sim_md.is_file(), f"Missing network simulation: {sim_md}"

    assert config.PROJECT_ID == "antigravity-web-hub-argolis"
    assert config.LOGGING_PROJECT_ID == "argodev-prod-audit-logs-0"
    assert config.SHARED_VPC_HOST_PROJECT == "cs-host-78e19ed8055b4c6980cce9"
    assert config.GKE_CLUSTER_REGION == "europe-west1"


def main():
    log(
        f"Starting Unified SRE Investigator (Network Domain) Integration Test in {config.PROJECT_ID} ({config.GKE_CLUSTER_REGION})"
    )

    log("Applying restrictive NetworkPolicy 'chaos-block-checkoutservice' in default namespace...")
    policy_manifest = """apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: chaos-block-checkoutservice
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: checkoutservice
  policyTypes:
  - Ingress
  - Egress
"""
    temp_policy = SRE_AGENT_ROOT / "temp_policy.yaml"
    temp_policy.write_text(policy_manifest, encoding="utf-8")

    res = run_cmd(f"kubectl apply -f {temp_policy}")
    if temp_policy.exists():
        temp_policy.unlink()
    if res.returncode != 0:
        log(f"❌ Failed to apply NetworkPolicy: {res.stderr}")
        sys.exit(1)
    log("✅ NetworkPolicy successfully applied.")

    alert_payload = (
        "CRITICAL ALERT: NetworkPolicy 'chaos-block-checkoutservice' in namespace default "
        "is dropping ingress/egress connections"
    )
    log(f"Spawning SRE Supervisor process with alert: '{alert_payload}'")

    env = os.environ.copy()
    env["GCP_PROJECT_ID"] = config.PROJECT_ID
    env["LOGGING_PROJECT_ID"] = config.LOGGING_PROJECT_ID
    env["GOOGLE_CLOUD_REGION"] = config.GKE_CLUSTER_REGION
    env["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"
    env["GOOGLE_API_USE_MTLS_ENDPOINT"] = "never"
    cmd = [sys.executable, "-u", "-m", "app.sre_supervisor", "--alert", alert_payload]
    proc = subprocess.Popen(
        cmd,
        cwd=str(SRE_AGENT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    session_id = None
    hitl_detected = False

    try:
        for line in proc.stdout:
            print(line, end="")
            match = re.search(r"http://127\.0\.0\.1:8000/callback/([a-f0-9\-]+)\?decision=APPROVED", line)
            if match:
                session_id = match.group(1)
                log(f"Detected HITL Session ID: {session_id}")
            if "Awaiting operator callback" in line:
                hitl_detected = True
                break

        if not hitl_detected or not session_id:
            log("❌ HITL Safety Gate was not activated or session ID was not found.")
            proc.kill()
            run_cmd("kubectl delete networkpolicy chaos-block-checkoutservice -n default --ignore-not-found=true")
            sys.exit(1)

        log(f"Approving remediation action for session {session_id}...")
        url = f"http://127.0.0.1:8000/callback/{session_id}?decision=APPROVED"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req) as response:
            resp_data = response.read().decode("utf-8")
            log(f"Callback Response: {resp_data}")

        for line in proc.stdout:
            print(line, end="")
        proc.wait()

        log("Verifying that the NetworkPolicy 'chaos-block-checkoutservice' was successfully deleted...")
        check_res = run_cmd("kubectl get networkpolicy chaos-block-checkoutservice -n default")
        if "NotFound" in check_res.stderr or check_res.returncode != 0:
            log("✅ SUCCESS: NetworkPolicy 'chaos-block-checkoutservice' has been deleted and traffic is restored.")
        else:
            log("❌ FAILED: NetworkPolicy 'chaos-block-checkoutservice' is still present in the cluster.")
            sys.exit(1)
    finally:
        run_cmd("kubectl delete networkpolicy chaos-block-checkoutservice -n default --ignore-not-found=true")


if __name__ == "__main__":
    main()
