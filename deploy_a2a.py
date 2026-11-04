import os
import sys
import time
import json
import shutil
import subprocess
import importlib
import google.auth

# Ensure app.config is imported first to activate resilient auth and CLOUD_ML_PROJECT_ID
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app.config as _novasre_config

import vertexai
from google.cloud import resourcemanager_v3
from google.iam.v1 import policy_pb2
from google.adk.sessions.in_memory_session_service import InMemorySessionService


class AutoCreatingInMemorySessionService(InMemorySessionService):
    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config=None,
    ):
        session = await super().get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            config=config,
        )
        if not session:
            session = await self.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )
        return session


# =========================================================================
# SDK MONKEYPATCH: Fix Pydantic AgentCard Serialization in vertexai SDK
# =========================================================================
from google.protobuf import json_format
from pydantic import BaseModel

original_message_to_json = json_format.MessageToJson


def patched_message_to_json(message, *args, **kwargs):
    if isinstance(message, BaseModel):
        return message.model_dump_json()
    elif isinstance(message, dict):
        return json.dumps(message)
    try:
        return original_message_to_json(message, *args, **kwargs)
    except AttributeError:
        return json.dumps(message)


json_format.MessageToJson = patched_message_to_json
# =========================================================================

# Load environment variables
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "antigravity-web-hub-argolis")
LOGGING_PROJECT_ID = os.environ.get("LOGGING_PROJECT_ID", "argodev-prod-audit-logs-0")
SHARED_VPC_HOST_PROJECT = os.environ.get("SHARED_VPC_HOST_PROJECT", "cs-host-78e19ed8055b4c6980cce9")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", os.environ.get("GOOGLE_CLOUD_REGION", "europe-west1"))
GKE_CLUSTER_NAME = os.environ.get("GKE_CLUSTER_NAME", "online-boutique")
GKE_CLUSTER_REGION = os.environ.get("GKE_CLUSTER_REGION", "europe-west1")

_raw_model = (
    os.environ.get("GEMINI_MODEL")
    or os.environ.get("GOOGLE_GENAI_MODEL")
    or os.environ.get("MODEL_NAME")
    or os.environ.get("MODEL_ID")
    or "gemini-2.5-flash"
)
GEMINI_MODEL = "gemini-2.5-flash" if _raw_model == "gemini-3.7-flash" else _raw_model
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-3.1-pro-preview")

PROJECT_NUMBER = (
    os.environ.get("NOVASRE_PROJECT_NUMBER")
    or getattr(_novasre_config, "PROJECT_NUMBER", None)
    or "723040006558"
)

DEFAULT_SERVICE_ACCOUNT = os.environ.get(
    "REASONING_ENGINE_SERVICE_ACCOUNT",
    f"{PROJECT_NUMBER}-compute@developer.gserviceaccount.com",
)
INVESTIGATOR_SA = os.environ.get(
    "INVESTIGATOR_SA",
    f"sre-investigator-sa@{PROJECT_ID}.iam.gserviceaccount.com",
)
REMEDIATOR_SA = os.environ.get(
    "REMEDIATOR_SA",
    f"sre-remediator-sa@{PROJECT_ID}.iam.gserviceaccount.com",
)
REPORTER_SA = os.environ.get(
    "REPORTER_SA",
    f"sre-reporter-sa@{PROJECT_ID}.iam.gserviceaccount.com",
)
SIMULATOR_SA = os.environ.get(
    "SIMULATOR_SA",
    f"sre-simulator-sa@{PROJECT_ID}.iam.gserviceaccount.com",
)

PER_AGENT_SERVICE_ACCOUNTS = {
    "rca-telemetry-expert": INVESTIGATOR_SA,
    "remediation-executor": REMEDIATOR_SA,
    "incident-report-writer": REPORTER_SA,
    "outage-simulator": SIMULATOR_SA,
}

STAGING_BUCKET = os.environ.get("STAGING_BUCKET", f"gs://{PROJECT_ID}-telemetry")
PLAYBOOKS_BUCKET = os.environ.get("PLAYBOOKS_BUCKET", f"gs://{PROJECT_ID}-sre-playbooks")
DEPLOYED_URNS_FILE = os.path.join(os.path.dirname(__file__), "deployed_urns.json")

print(f"Using Runtime Host Project: {PROJECT_ID} (Number: {PROJECT_NUMBER})")
print(f"Using Central Audit Hub:    {LOGGING_PROJECT_ID}")
print(f"Using Location:             {LOCATION}")
print(f"Using Gemini Model:         {GEMINI_MODEL} (Pro Escalation: {GEMINI_PRO_MODEL})")
print(f"Using Staging Bucket:       {STAGING_BUCKET}")
print(f"Per-Agent Service Accounts: {json.dumps(PER_AGENT_SERVICE_ACCOUNTS, indent=2)}")

from vertexai import agent_engines
from vertexai.preview import reasoning_engines


def deploy_agent(
    display_name: str,
    module_name: str,
    entrypoint_object: str,
    service_account: str = None,
    env_vars: dict = None,
    check_existing: bool = True,
):
    target_sa = service_account or PER_AGENT_SERVICE_ACCOUNTS.get(display_name) or DEFAULT_SERVICE_ACCOUNT
    print(f"\n🚀 Deploying {display_name} with SA={target_sa}...")
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    module = importlib.import_module(module_name)
    agent_instance = getattr(module, entrypoint_object)

    merged_env_vars = {
        "GOOGLE_CLOUD_REGION": LOCATION,
        "GOOGLE_CLOUD_LOCATION": LOCATION,
        "GCP_PROJECT_ID": PROJECT_ID,
        "PROJECT_NUMBER": str(PROJECT_NUMBER),
        "LOGGING_PROJECT_ID": LOGGING_PROJECT_ID,
        "SHARED_VPC_HOST_PROJECT": SHARED_VPC_HOST_PROJECT,
        "GKE_CLUSTER_NAME": GKE_CLUSTER_NAME,
        "GKE_CLUSTER_REGION": GKE_CLUSTER_REGION,
        "GEMINI_MODEL": GEMINI_MODEL,
        "GEMINI_PRO_MODEL": GEMINI_PRO_MODEL,
        "GEMINI_MODEL_LOCATION": "global",
        "TELEMETRY_BUCKET": STAGING_BUCKET,
        "PLAYBOOKS_BUCKET": PLAYBOOKS_BUCKET,
        "BQ_RECENT_RELEASES_TABLE": f"{LOGGING_PROJECT_ID}.sre_releases.recent_releases",
        "BQ_POSTMORTEMS_TABLE": f"{LOGGING_PROJECT_ID}.sre_releases.incident_postmortems",
        "PAM_ENABLED": "true",
        "PAM_ENTITLEMENT_NAME": f"projects/{PROJECT_ID}/locations/global/entitlements/gke-editor",
        "MODEL_ARMOR_ENABLED": "true",
        "MODEL_ARMOR_FLOOR_SETTING": "INSPECT_AND_BLOCK",
        "GOOGLE_GENAI_USE_VERTEXAI": "1",
        "GOOGLE_GENAI_LOCATION": "global",
        "GOOGLE_API_USE_CLIENT_CERTIFICATE": "false",
        "GOOGLE_API_USE_MTLS_ENDPOINT": "never",
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
        "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED": "true",
        "OTEL_INSTRUMENTATION_A2A_SDK_ENABLED": "false",
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "SPAN_AND_EVENT",
        "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH": STAGING_BUCKET,
        "OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT": "jsonl",
        "OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK": "upload",
        "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
    }
    if env_vars:
        merged_env_vars.update(env_vars)

    from vertexai.preview.reasoning_engines import A2aAgent

    if isinstance(agent_instance, (agent_engines.AdkApp, A2aAgent)):
        app = agent_instance
        if isinstance(app, agent_engines.AdkApp):
            app._tmpl_attrs["enable_tracing"] = True
            app._tmpl_attrs["session_service_builder"] = lambda **kwargs: InMemorySessionService()
    else:
        app = agent_engines.AdkApp(
            agent=agent_instance,
            enable_tracing=True,
            session_service_builder=lambda **kwargs: InMemorySessionService(),
        )

    if check_existing:
        try:
            existing = list(reasoning_engines.ReasoningEngine.list())
            matching = [a for a in existing if a.display_name == display_name]
            if matching:
                print(f"Agent {display_name} already exists ({matching[0].resource_name}). Deleting first...")
                try:
                    matching[0].delete()
                    time.sleep(5)
                except Exception as e:
                    print(f"Warning: Failed to delete existing agent {display_name}: {e}")
        except Exception as list_err:
            print(f"Notice listing existing reasoning engines: {list_err}")

    requirements_list = [
        "google-cloud-aiplatform[agent_engines]>=1.130.0",
        "google-adk[a2a,agent-identity]>=2.0.0",
        "a2a-sdk>=0.3.26,<1.0.0",
        "protobuf>=6.30.0",
        "cloudpickle>=3.1.0",
        "pydantic>=2.10.0",
        "google-genai>=1.75.0",
        "python-dotenv>=1.0.1",
        "httpx>=0.28.1",
        "google-auth>=2.35.0",
        "opentelemetry-sdk>=1.30.0",
        "opentelemetry-exporter-gcp-trace>=1.9.0",
        "opentelemetry-instrumentation-google-genai",
        "opentelemetry-instrumentation-httpx",
        "opentelemetry-instrumentation-grpc",
        "kubernetes>=30.0.0",
        "google-cloud-container>=2.50.0",
        "google-cloud-bigquery>=3.25.0",
        "google-cloud-storage>=2.18.0",
        "google-cloud-logging>=3.10.0",
        "google-cloud-privilegedaccessmanager>=0.4.1",
        "a2ui-agent-sdk>=0.6.0",
        "requests>=2.31.0",
        "fastapi>=0.110.0",
        "uvicorn>=0.28.0",
        "mcp>=1.20.0",
    ]

    try:
        remote_app = agent_engines.create(
            agent_engine=app,
            display_name=display_name,
            gcs_dir_name=display_name,
            requirements=requirements_list,
            extra_packages=["./app"],
            service_account=target_sa,
            env_vars=merged_env_vars,
        )
    except Exception as sa_err:
        if target_sa != DEFAULT_SERVICE_ACCOUNT:
            print(
                f"⚠️ Deployment with custom SA {target_sa} encountered error ({sa_err}). "
                f"Falling back to {DEFAULT_SERVICE_ACCOUNT}..."
            )
            remote_app = agent_engines.create(
                agent_engine=app,
                display_name=display_name,
                gcs_dir_name=display_name,
                requirements=requirements_list,
                extra_packages=["./app"],
                service_account=DEFAULT_SERVICE_ACCOUNT,
                env_vars=merged_env_vars,
            )
        else:
            raise

    print(f"✅ Deployment completed for {display_name}. Agent URN: {remote_app.resource_name}")
    return remote_app


def save_deployed_urns(deployed_urns: dict):
    payload = {
        "project_id": PROJECT_ID,
        "project_number": str(PROJECT_NUMBER),
        "logging_project_id": LOGGING_PROJECT_ID,
        "location": LOCATION,
        "gemini_model": GEMINI_MODEL,
        "gemini_pro_model": GEMINI_PRO_MODEL,
        "gke_cluster_name": GKE_CLUSTER_NAME,
        "gke_cluster_region": GKE_CLUSTER_REGION,
        "rca-telemetry-expert": deployed_urns.get("rca-telemetry-expert", ""),
        "remediation-executor": deployed_urns.get("remediation-executor", ""),
        "outage-simulator": deployed_urns.get("outage-simulator", ""),
        "incident-report-writer": deployed_urns.get("incident-report-writer", ""),
        "NOVASRE_RCA_URN": deployed_urns.get("rca-telemetry-expert", ""),
        "NOVASRE_REMEDIATOR_URN": deployed_urns.get("remediation-executor", ""),
        "NOVASRE_SIMULATOR_URN": deployed_urns.get("outage-simulator", ""),
        "NOVASRE_REPORTER_URN": deployed_urns.get("incident-report-writer", ""),
        "INVESTIGATOR_AGENT_URN": deployed_urns.get("rca-telemetry-expert", ""),
        "REMEDIATION_AGENT_URN": deployed_urns.get("remediation-executor", ""),
        "OUTAGE_SIMULATOR_URN": deployed_urns.get("outage-simulator", ""),
        "INCIDENT_REPORT_WRITER_URN": deployed_urns.get("incident-report-writer", ""),
        "service_accounts": PER_AGENT_SERVICE_ACCOUNTS,
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(DEPLOYED_URNS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"📄 Saved deployed Reasoning Engine URNs to {DEPLOYED_URNS_FILE}")


def main():
    from concurrent.futures import ThreadPoolExecutor, as_completed

    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)

    if len(sys.argv) > 1 and sys.argv[1] == "inv":
        inv_app = deploy_agent(
            display_name="rca-telemetry-expert",
            module_name="app.investigator_agent",
            entrypoint_object="agent_engine",
            service_account=INVESTIGATOR_SA,
        )
        print(f"\n🚀 Newly deployed Investigator Agent URN: {inv_app.resource_name}")
        return

    agents_to_deploy = [
        ("remediation-executor", "app.remediation_agent", "agent_engine", REMEDIATOR_SA),
        ("outage-simulator", "app.outage_simulator_agent", "agent_engine", SIMULATOR_SA),
        ("incident-report-writer", "app.investigator_agent", "incident_report_writer_engine", REPORTER_SA),
        ("rca-telemetry-expert", "app.investigator_agent", "agent_engine", INVESTIGATOR_SA),
    ]

    # Pre-import modules and clean up any pre-existing agents on main thread
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for _, mod_name, _, _ in agents_to_deploy:
        importlib.import_module(mod_name)

    target_names = {s[0] for s in agents_to_deploy}
    try:
        existing = list(reasoning_engines.ReasoningEngine.list())
        for eng in existing:
            if eng.display_name in target_names:
                print(f"🧹 Deleting existing Reasoning Engine {eng.display_name} ({eng.resource_name})...")
                try:
                    eng.delete()
                except Exception as del_err:
                    print(f"Warning deleting {eng.display_name}: {del_err}")
    except Exception as list_err:
        print(f"Notice checking existing engines: {list_err}")

    deployed_urns = {}
    print(f"\n⚡ Deploying 4 NovaSRE Reasoning Engines in parallel to {PROJECT_ID} ({LOCATION})...")

    def _deploy_with_retries(idx_and_spec):
        idx, (display_name, module_name, entrypoint, sa_email) = idx_and_spec
        if idx > 0:
            time.sleep(idx * 6)
        for attempt in range(1, 4):
            try:
                print(f"Deploying {display_name} (Attempt {attempt}/3)...")
                remote_app = deploy_agent(
                    display_name=display_name,
                    module_name=module_name,
                    entrypoint_object=entrypoint,
                    service_account=sa_email,
                    check_existing=False,
                )
                return display_name, remote_app.resource_name
            except Exception as e:
                print(f"⚠️ Attempt {attempt} failed for {display_name}: {e}")
                time.sleep(5)
        raise RuntimeError(f"Failed to deploy {display_name} after 3 attempts.")

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_deploy_with_retries, (idx, spec)): spec[0]
            for idx, spec in enumerate(agents_to_deploy)
        }
        for fut in as_completed(futures):
            name, urn = fut.result()
            deployed_urns[name] = urn
            save_deployed_urns(deployed_urns)

    print(f"\n🚀 Remediation Executor URN:   {deployed_urns.get('remediation-executor')}")
    print(f"🚀 Outage Simulator URN:       {deployed_urns.get('outage-simulator')}")
    print(f"🚀 Incident Report Writer URN: {deployed_urns.get('incident-report-writer')}")
    print(f"🚀 RCA Telemetry Expert URN:   {deployed_urns.get('rca-telemetry-expert')}")
    print("\n🎉 ALL 4 AGENTS DEPLOYED SUCCESSFULLY TO VERTEX AI REASONING ENGINES IN EUROPE-WEST1!")


if __name__ == "__main__":
    main()
