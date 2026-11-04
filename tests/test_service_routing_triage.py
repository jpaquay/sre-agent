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

"""GKE Service Routing Triage Integration & Skill Verification Test."""

import json
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
    print(f"\033[1;32m[TEST_RUNNER]\033[0m {msg}")


def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


# =========================================================================
# PYTEST UNIT TESTS
# =========================================================================
def test_service_routing_playbook_and_simulation_loaded():
    """Verify gke-service-routing-recovery playbook and gke-service-routing-break simulation are loaded."""
    assert "gke-service-routing-recovery" in investigator_agent._PLAYBOOK_SKILL_NAMES
    assert "gke-service-routing-break" in outage_simulator_agent._SIMULATION_SKILL_NAMES
    assert "gke-networking" in investigator_agent._DIAGNOSTIC_SKILL_NAMES

    pb_path = SRE_AGENT_ROOT / "app" / "skills" / "playbooks" / "gke-service-routing-recovery" / "SKILL.md"
    sim_path = SRE_AGENT_ROOT / "app" / "skills" / "simulations" / "gke-service-routing-break" / "SKILL.md"
    assert pb_path.is_file()
    assert sim_path.is_file()
    assert config.PROJECT_ID == "antigravity-web-hub-argolis"
    assert config.GKE_CLUSTER_REGION == "europe-west1"


def main():
    log(
        f"Starting GKE Service Routing Triage Integration Test Scenario in {config.PROJECT_ID} ({config.GKE_CLUSTER_REGION})"
    )

    log("Triggering local chaos simulation on GKE service routing...")
    patch_res = run_cmd(
        'kubectl patch service checkoutservice -p \'{"spec":{"selector":{"app":"broken-selector"}}}\''
    )
    if patch_res.returncode != 0:
        log(f"❌ Failed to patch service selector: {patch_res.stderr}")
        sys.exit(1)
    log("✅ Chaos simulation successfully triggered.")

    log("Verifying broken service selector on checkoutservice Service...")
    svc_res = run_cmd("kubectl get service checkoutservice -o jsonpath='{.spec.selector.app}'")
    if svc_res.stdout.strip() != "broken-selector":
        log(f"❌ Service selector is not broken: '{svc_res.stdout.strip()}'")
        run_cmd('kubectl patch service checkoutservice -p \'{"spec":{"selector":{"app":"checkoutservice"}}}\'')
        sys.exit(1)
    log("✅ Confirmed checkoutservice selector is broken (app=broken-selector).")

    alert_payload = (
        "CRITICAL ALERT: GKE Service 'checkoutservice' ingress routing in namespace default "
        "is dropping connections. Traffic cannot reach healthy pods."
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
            run_cmd('kubectl patch service checkoutservice -p \'{"spec":{"selector":{"app":"checkoutservice"}}}\'')
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

        log("Verifying that the Service selector of 'checkoutservice' was restored...")
        svc_res = run_cmd("kubectl get service checkoutservice -o jsonpath='{.spec.selector.app}'")
        if svc_res.stdout.strip() == "checkoutservice":
            log("✅ SUCCESS: Service selector of 'checkoutservice' has been restored and traffic is restored.")
        else:
            log(f"❌ FAILED: Service selector is still: '{svc_res.stdout.strip()}'")
            sys.exit(1)
    finally:
        run_cmd('kubectl patch service checkoutservice -p \'{"spec":{"selector":{"app":"checkoutservice"}}}\'')


if __name__ == "__main__":
    main()
