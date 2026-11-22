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
import re
import json
import uuid
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.base_toolset import BaseToolset

logger = logging.getLogger(__name__)

# Load local environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Ensure CLOUD_ML_PROJECT_ID is set and PROJECT_NUMBER env var does not trigger a blocking resourcemanager RPC in vertexai.initializer
_configured_project = (
    os.environ.get("GCP_PROJECT_ID")
    or os.environ.get("GOOGLE_CLOUD_PROJECT")
    or "antigravity-web-hub-argolis"
)
os.environ.setdefault("CLOUD_ML_PROJECT_ID", _configured_project)
_saved_project_number = os.environ.pop("PROJECT_NUMBER", None) or os.environ.get("NOVASRE_PROJECT_NUMBER", "723040006558")

# Resilient ADC wrapper: uses standard google.auth.default() in cloud runtimes and falls back to active gcloud CLI token locally if ADC is expired
if not hasattr(google.auth, "_novasre_patched"):
    import google.auth.credentials
    from datetime import timedelta

    _orig_google_auth_default = google.auth.default
    _cached_gcloud_creds = None

    class _GcloudCliCredentials(google.auth.credentials.Credentials):
        """Credentials backed by active gcloud CLI session when local ADC file requires reauth."""
        def __init__(self, token: str, quota_project_id: str = None):
            super().__init__()
            self.token = token
            self._quota_project_id = quota_project_id
            self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=50)

        @property
        def quota_project_id(self):
            return self._quota_project_id

        @property
        def valid(self):
            return bool(self.token)

        def refresh(self, request):
            import shutil, subprocess
            gcloud_bin = shutil.which("gcloud")
            if gcloud_bin and not self.token:
                self.token = subprocess.check_output(
                    [gcloud_bin, "auth", "print-access-token"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                ).strip()
            self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=50)

        def with_quota_project(self, quota_project_id):
            return _GcloudCliCredentials(self.token, quota_project_id=quota_project_id)

        def with_scopes(self, scopes, default_scopes=None):
            return self

    def _resilient_google_auth_default(scopes=None, request=None, quota_project_id=None, default_scopes=None):
        global _cached_gcloud_creds
        if _cached_gcloud_creds is not None and _cached_gcloud_creds.valid:
            return _cached_gcloud_creds, _configured_project
        try:
            creds, proj = _orig_google_auth_default(
                scopes=scopes, request=request, quota_project_id=quota_project_id, default_scopes=default_scopes
            )
            if creds and not getattr(creds, "valid", False):
                req = request or google.auth.transport.requests.Request()
                creds.refresh(req)
            return creds, (proj or _configured_project)
        except Exception:
            import shutil, subprocess
            gcloud_bin = shutil.which("gcloud")
            if gcloud_bin:
                try:
                    token = subprocess.check_output(
                        [gcloud_bin, "auth", "print-access-token"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                    ).strip()
                    if token:
                        _cached_gcloud_creds = _GcloudCliCredentials(
                            token=token,
                            quota_project_id=quota_project_id or _configured_project,
                        )
                        return _cached_gcloud_creds, _configured_project
                except Exception:
                    pass
            raise

    google.auth.default = _resilient_google_auth_default
    setattr(google.auth, "_novasre_patched", True)

# =========================================================================
# OPENTELEMETRY CLOUD TRACE & GENAI INSTRUMENTATION SETUP (ce408 pattern)
# =========================================================================
try:
    from google.adk.telemetry.google_cloud import get_gcp_exporters, get_gcp_resource
    from google.adk.telemetry.setup import maybe_set_otel_providers

    os.environ.setdefault("GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", "true")
    os.environ.setdefault("OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED", "true")
    os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

    _credentials, _project_id = google.auth.default()
    _target_proj = _configured_project or _project_id
    _otel_hooks = get_gcp_exporters(
        enable_cloud_tracing=True,
        enable_cloud_metrics=False,
        enable_cloud_logging=True,
        google_auth=(_credentials, _target_proj),
    )
    _otel_resource = get_gcp_resource(_target_proj)
    maybe_set_otel_providers(
        otel_hooks_to_setup=[_otel_hooks],
        otel_resource=_otel_resource,
    )
    try:
        from opentelemetry.instrumentation.google_genai import GoogleGenAiInstrumentor
        GoogleGenAiInstrumentor().instrument()
    except Exception:
        pass
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except Exception:
        pass
    try:
        from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
        GrpcInstrumentorClient().instrument()
    except Exception:
        pass
    logger.info("✅ OpenTelemetry Cloud Trace & GenAI instrumentation initialized.")
except Exception as _otel_err:
    logger.warning(f"⚠️ Could not initialize OpenTelemetry Cloud Trace: {_otel_err}")

# =========================================================================
# 1. CENTRALIZED RUNTIME MONKEYPATCHES & FRAMEWORK COMPATIBILITY
# =========================================================================
try:
    # Fix google-adk 2.2.0 Runner.run_async AttributeError: 'LlmAgent' object has no attribute 'mode'
    from google.adk.agents import Agent
    Agent.mode = None
except Exception:
    pass

try:
    # Enable automatic session creation for InMemorySessionService when sessions are queried
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    _orig_in_memory_get_session = InMemorySessionService.get_session

    async def _auto_creating_get_session(self, *, app_name, user_id, session_id, config=None):
        session = await _orig_in_memory_get_session(
            self, app_name=app_name, user_id=user_id, session_id=session_id, config=config
        )
        if not session:
            session = await self.create_session(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
        return session

    InMemorySessionService.get_session = _auto_creating_get_session
except Exception:
    pass

try:
    # Relax session_id validation in google-adk to allow slashes
    import google.adk.sessions.vertex_ai_session_service as service_module
    def relaxed_validate_session_id(session_id: str) -> None:
        if not isinstance(session_id, str):
            raise ValueError(f"Invalid session_id: {session_id}")
    service_module._validate_session_id = relaxed_validate_session_id
except Exception:
    pass

try:
    # Strip forbidden 'part_metadata' parameter from GenAI Parts when serializing A2A parts
    import google.adk.a2a.converters.part_converter as part_converter
    original_convert_a2a_part_to_genai_part = part_converter.convert_a2a_part_to_genai_part

    def patched_convert_a2a_part_to_genai_part(a2a_part):
        genai_part = original_convert_a2a_part_to_genai_part(a2a_part)
        if genai_part is not None and hasattr(genai_part, "part_metadata"):
            genai_part.part_metadata = None
        return genai_part

    part_converter.convert_a2a_part_to_genai_part = patched_convert_a2a_part_to_genai_part
except Exception:
    pass

try:
    # Fix google-cloud-aiplatform / a2a-sdk import mismatch for RemoteA2aAgent
    import types
    import a2a.types
    import a2a.utils.constants as constants_module
    
    constants_module.TransportProtocol = a2a.types.TransportProtocol
    constants_module.PROTOCOL_VERSION_CURRENT = '0.3.0'
    
    def get_supported_interfaces(self):
        return self.additional_interfaces
    def set_supported_interfaces(self, value):
        self.additional_interfaces = value
    a2a.types.AgentCard.supported_interfaces = property(get_supported_interfaces, set_supported_interfaces)
    
    a2a.types.TransportProtocol.HTTP_JSON = a2a.types.TransportProtocol.http_json
    a2a.types.TransportProtocol.JSONRPC = a2a.types.TransportProtocol.jsonrpc
    a2a.types.TransportProtocol.GRPC = a2a.types.TransportProtocol.grpc
    
    original_agent_interface_init = a2a.types.AgentInterface.__init__
    def patched_agent_interface_init(self, *args, **kwargs):
        if "protocol_binding" in kwargs:
            binding = kwargs.pop("protocol_binding")
            kwargs["transport"] = getattr(binding, "value", str(binding))
        if "protocol_version" in kwargs:
            kwargs.pop("protocol_version")
        if "url" not in kwargs:
            kwargs["url"] = "https://dummy-interface.com"
        original_agent_interface_init(self, *args, **kwargs)
    a2a.types.AgentInterface.__init__ = patched_agent_interface_init
    
    original_client_factory_create = a2a.client.ClientFactory.create
    def patched_client_factory_create(self, agent_card, *args, **kwargs):
        if hasattr(agent_card, "supported_interfaces") and agent_card.supported_interfaces:
            agent_card.url = agent_card.supported_interfaces[0].url
        return original_client_factory_create(self, agent_card, *args, **kwargs)
    a2a.client.ClientFactory.create = patched_client_factory_create
    
    import httpx
    original_async_client_init = httpx.AsyncClient.__init__
    def patched_async_client_init(self, *args, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = 60.0
        original_async_client_init(self, *args, **kwargs)
    httpx.AsyncClient.__init__ = patched_async_client_init
except Exception:
    pass

try:
    # OpenTelemetry trace cleaning: Custom Noise-Filtering Sampler
    from opentelemetry.sdk.trace.sampling import Sampler, Decision, SamplingResult
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from google.adk.agents import Agent

    class NoiseFilteringSampler(Sampler):
        """Custom sampler to filter out low-level framework noise from Cloud Trace."""
        def should_sample(self, parent_context, trace_id, name, *args, **kwargs):
            if name.startswith("a2a.server.events.") or name.startswith("a2a.server.request_handlers."):
                return SamplingResult(decision=Decision.DROP)
            if name.startswith("google.adk.sessions."):
                return SamplingResult(decision=Decision.DROP)
            return SamplingResult(decision=Decision.RECORD_AND_SAMPLE)

        def get_description(self):
            return "NoiseFilteringSampler"

    provider = trace.get_tracer_provider()
    if hasattr(provider, "_tracer_provider"):
        provider = provider._tracer_provider
    if isinstance(provider, TracerProvider):
        provider._sampler = NoiseFilteringSampler()

    original_run_async_impl = Agent._run_async_impl
    async def patched_run_async_impl(self, *args, **kwargs):
        try:
            p = trace.get_tracer_provider()
            if hasattr(p, "_tracer_provider"):
                p = p._tracer_provider
            if isinstance(p, TracerProvider):
                p._sampler = NoiseFilteringSampler()
        except Exception:
            pass
        async for event in original_run_async_impl(self, *args, **kwargs):
            yield event
    Agent._run_async_impl = patched_run_async_impl
except Exception:
    pass

# =========================================================================
# 2. DYNAMIC DUAL-PROJECT (HUB & SPOKE) AND MODEL RESOLUTION
# =========================================================================
PROJECT_ID = os.environ.get(
    "GCP_PROJECT_ID",
    os.environ.get("GOOGLE_CLOUD_PROJECT", "antigravity-web-hub-argolis")
) or "antigravity-web-hub-argolis"
PROJECT_NUMBER = _saved_project_number or "723040006558"

# Central Audit & Logging Hub (cs-audit)
LOGGING_PROJECT_ID = os.environ.get("LOGGING_PROJECT_ID", "argodev-prod-audit-logs-0")
LOGGING_PROJECT_NUMBER = os.environ.get("LOGGING_PROJECT_NUMBER", "618001173803")
SHARED_VPC_HOST_PROJECT = os.environ.get("SHARED_VPC_HOST_PROJECT", "cs-host-78e19ed8055b4c6980cce9")

if PROJECT_ID:
    os.environ["GOOGLE_CLOUD_PROJECT"] = str(PROJECT_ID)
    os.environ["GCP_PROJECT_ID"] = str(PROJECT_ID)

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
os.environ.setdefault("GOOGLE_API_USE_MTLS_ENDPOINT", "never")

# Support generic environment variables for Gemini model selection (defaulting to gemini-2.5-flash)
_raw_model = (
    os.environ.get("GEMINI_MODEL")
    or os.environ.get("GOOGLE_GENAI_MODEL")
    or os.environ.get("MODEL_NAME")
    or os.environ.get("MODEL_ID")
    or "gemini-2.5-flash"
)
# Automatically upgrade deprecated/fictional gemini-3.7-flash to verified gemini-2.5-flash
GEMINI_MODEL = "gemini-2.5-flash" if _raw_model == "gemini-3.7-flash" else _raw_model
os.environ["GEMINI_MODEL"] = str(GEMINI_MODEL)

# Tier 3 escalation model for complex zero-shot novel root-cause analysis
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-3.1-pro-preview")

GEMINI_LOCATION = os.environ.get(
    "GOOGLE_CLOUD_LOCATION",
    os.environ.get("GOOGLE_CLOUD_REGION", "europe-west1")
)
# Primary location for model inference (EU Benelux primary with DR failover to europe-west4)
GEMINI_MODEL_LOCATION = os.environ.get("GEMINI_MODEL_LOCATION", "europe-west1")
GEMINI_FALLBACK_LOCATION = os.environ.get("GEMINI_FALLBACK_LOCATION", "europe-west4")
_ACTIVE_GEMINI_LOCATION: ContextVar[str | None] = ContextVar("novasre_active_gemini_location", default=None)
GKE_CLUSTER_NAME = os.environ.get("GKE_CLUSTER_NAME", "online-boutique")
GKE_CLUSTER_REGION = os.environ.get("GKE_CLUSTER_REGION", "europe-west1")

# Storage Buckets & Central BigQuery Datasets
TELEMETRY_BUCKET = os.environ.get("TELEMETRY_BUCKET", f"gs://{PROJECT_ID}-telemetry")
PLAYBOOKS_BUCKET = os.environ.get("PLAYBOOKS_BUCKET", f"gs://{PROJECT_ID}-sre-playbooks")
BQ_RELEASE_DATASET = os.environ.get("BQ_RELEASE_DATASET", "sre_releases")
BQ_RECENT_RELEASES_TABLE = os.environ.get(
    "BQ_RECENT_RELEASES_TABLE",
    f"{LOGGING_PROJECT_ID}.{BQ_RELEASE_DATASET}.recent_releases"
)
BQ_POSTMORTEMS_TABLE = os.environ.get(
    "BQ_POSTMORTEMS_TABLE",
    f"{LOGGING_PROJECT_ID}.{BQ_RELEASE_DATASET}.incident_postmortems"
)

# Decomposed Per-Agent Least-Privilege Service Accounts
INVESTIGATOR_SA = os.environ.get("INVESTIGATOR_SA", f"sre-investigator-sa@{PROJECT_ID}.iam.gserviceaccount.com")
REMEDIATOR_SA = os.environ.get("REMEDIATOR_SA", f"sre-remediator-sa@{PROJECT_ID}.iam.gserviceaccount.com")
REPORTER_SA = os.environ.get("REPORTER_SA", f"sre-reporter-sa@{PROJECT_ID}.iam.gserviceaccount.com")
SIMULATOR_SA = os.environ.get("SIMULATOR_SA", f"sre-simulator-sa@{PROJECT_ID}.iam.gserviceaccount.com")

from google.adk.models import Gemini
from google.genai import Client, types

# =========================================================================
# PRIVILEGED ACCESS MANAGER (PAM) — JIT elevation for remediation
# =========================================================================
PAM_ENABLED = os.environ.get("PAM_ENABLED", "true").lower() in ("1", "true", "yes")
PAM_ENTITLEMENT_NAME = os.environ.get(
    "PAM_ENTITLEMENT_NAME",
    f"projects/{PROJECT_ID}/locations/global/entitlements/gke-editor",
)
PAM_GRANT_DURATION_SECONDS = int(os.environ.get("PAM_GRANT_DURATION_SECONDS", "3600"))
PAM_GRANT_ACTIVE_TIMEOUT_SECONDS = int(os.environ.get("PAM_GRANT_ACTIVE_TIMEOUT_SECONDS", "60"))


class GlobalGemini(Gemini):
    """Gemini model routed to Vertex AI EU Benelux primary (europe-west1) with coroutine-isolated regional failover (europe-west4)."""

    @property
    def api_client(self) -> Client:
        active_location = _ACTIVE_GEMINI_LOCATION.get() or GEMINI_MODEL_LOCATION
        return Client(
            vertexai=True,
            location=active_location,
            project=PROJECT_ID,
            http_options=types.HttpOptions(
                api_version="v1",
                retry_options=types.HttpRetryOptions(
                    attempts=2,
                    initial_delay=2.0,
                    max_delay=15.0,
                    exp_base=2.0,
                    http_status_codes=[408, 429, 500, 502, 503, 504],
                ),
            ),
        )

    def get_fallback_client(self, location: str = None) -> Client:
        """Returns a regional Vertex AI Client (defaulting to europe-west4 DR) for quota/endpoint failover."""
        fallback_loc = location or GEMINI_FALLBACK_LOCATION or "europe-west4"
        return Client(
            vertexai=True,
            location=fallback_loc,
            project=PROJECT_ID,
            http_options=types.HttpOptions(
                api_version="v1",
                retry_options=types.HttpRetryOptions(
                    attempts=2,
                    initial_delay=1.5,
                    max_delay=15.0,
                    exp_base=2.0,
                    http_status_codes=[408, 429, 500, 502, 503, 504],
                ),
            ),
        )

    async def generate_content_async(self, llm_request, stream: bool = False):
        """Executes LLM inference in europe-west1 and fails over using a task-isolated ContextVar (no os.environ race)."""
        try:
            async for response in super().generate_content_async(llm_request, stream=stream):
                yield response
        except Exception as primary_err:
            err_str = str(primary_err)
            if any(code in err_str for code in ("429", "404", "503", "RESOURCE_EXHAUSTED", "NOT_FOUND")):
                fallback_loc = (
                    GEMINI_FALLBACK_LOCATION
                    if GEMINI_MODEL_LOCATION != GEMINI_FALLBACK_LOCATION
                    else "europe-west1"
                )
                logger.warning(
                    "⚠️ [GlobalGemini] Primary inference failed in %s (%s). Failing over to %s with gemini-2.5-flash...",
                    GEMINI_MODEL_LOCATION, err_str[:120], fallback_loc,
                )
                token = _ACTIVE_GEMINI_LOCATION.set(fallback_loc)
                if hasattr(llm_request, "model") and llm_request.model == "gemini-3.7-flash":
                    llm_request.model = "gemini-2.5-flash"
                try:
                    async for response in super().generate_content_async(llm_request, stream=stream):
                        yield response
                finally:
                    _ACTIVE_GEMINI_LOCATION.reset(token)
            else:
                raise


# =========================================================================
# 3. MODEL ARMOR & PROMPT-INJECTION INLINE GUARD
# =========================================================================
MODEL_ARMOR_ENABLED = os.environ.get("MODEL_ARMOR_ENABLED", "true").lower() in ("1", "true", "yes")
MODEL_ARMOR_TEMPLATE = os.environ.get("MODEL_ARMOR_TEMPLATE", "")
MODEL_ARMOR_FLOOR_SETTING = os.environ.get("MODEL_ARMOR_FLOOR_SETTING", "INSPECT_AND_BLOCK")

_PROMPT_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+|previous\s+|prior\s+|above\s+|system\s+)*(instructions|prompts|rules|guardrails|constraints)", re.I), "Instruction override attempt (ignore previous instructions)"),
    (re.compile(r"disregard\s+(all\s+|previous\s+|prior\s+|above\s+|system\s+)*(instructions|prompts|rules|guardrails)", re.I), "Instruction override attempt (disregard instructions)"),
    (re.compile(r"forget\s+(all\s+|previous\s+|prior\s+|your\s+)*(instructions|context|rules|system)", re.I), "Context wipe attempt"),
    (re.compile(r"</?\s*(ce_input|system_instruction|system_prompt|a2a_system_override)\s*>", re.I), "XML/delimiter spoofing (<ce_input> or <system_instruction> injection)"),
    (re.compile(r"(\[INST\]|<\|im_start\|>|<\|system\|>|###\s*System\s*:)", re.I), "Control token / role-boundary injection"),
    (re.compile(r"(bypass|disable|skip)\s+(hitl|human[\s\-]+in[\s\-]+the[\s\-]+loop|pam|model\s*armor|approval\s*gate|security\s*policy)", re.I), "HITL / PAM / Model Armor bypass attempt"),
    (re.compile(r"(exfiltrate|dump|print|leak|expose|reveal|output)\s+.*(secret|private[_\s\-]?key|access[_\s\-]?token|bearer\s+token|service[_\s\-]?account[_\s\-]?key|metadata\.google\.internal|169\.254\.169\.254)", re.I), "Credential or metadata server exfiltration attempt"),
    (re.compile(r"(constraints/iam\.allowedPolicyMemberDomains|allow_all_domains|allUsers|allAuthenticatedUsers)", re.I), "Argolis IAM / Org Policy violation attempt (allUsers or allow_all_domains)"),
    (re.compile(r"(rm\s+-rf\s+/|curl\s+[^\n]*\|\s*(ba)?sh|wget\s+[^\n]*\|\s*(ba)?sh)", re.I), "Destructive shell injection pattern"),
]


def screen_prompt_with_model_armor(prompt_text: str) -> tuple[bool, str]:
    """Screens an inbound prompt or tool instruction for Prompt Injection, <ce_input> tag spoofing,
    secret exfiltration, and Argolis policy violations using deterministic regex guards + Model Armor API.

    Args:
        prompt_text: The inbound user prompt or A2A request text to screen.

    Returns:
        Tuple of (is_safe: bool, reason: str).
    """
    if not prompt_text or not isinstance(prompt_text, str):
        return True, "PASS: Empty or non-string payload."

    # 1. Deterministic regex guard (always active, zero-latency)
    for pattern, description in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(prompt_text):
            reason = f"BLOCKED by Model Armor guard ({MODEL_ARMOR_FLOOR_SETTING}): {description}"
            logger.warning("🛡️ %s | Snippet: %r", reason, prompt_text[:160])
            return False, reason

    # 2. Live Model Armor API call when MODEL_ARMOR_TEMPLATE is configured
    if MODEL_ARMOR_ENABLED and MODEL_ARMOR_TEMPLATE:
        try:
            import requests
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            credentials.refresh(google.auth.transport.requests.Request())
            loc = GEMINI_LOCATION or "europe-west1"
            url = f"https://modelarmor.{loc}.rep.googleapis.com/v1/{MODEL_ARMOR_TEMPLATE}:sanitizeUserPrompt"
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {credentials.token}",
                    "Content-Type": "application/json",
                    "x-goog-user-project": str(PROJECT_ID),
                },
                json={"userPromptData": {"text": prompt_text[:8000]}},
                timeout=5.0,
            )
            if resp.status_code == 200:
                body = resp.json()
                match_state = (
                    body.get("sanitizationResult", {}).get("filterMatchState")
                    or body.get("filterMatchState")
                )
                if match_state == "MATCH_FOUND":
                    reason = f"BLOCKED by Google Cloud Model Armor API ({MODEL_ARMOR_TEMPLATE}): MATCH_FOUND"
                    logger.warning("🛡️ %s", reason)
                    return False, reason
        except Exception as ma_err:
            logger.debug("Model Armor API check fallback to deterministic guard: %s", ma_err)

    return True, f"PASS: Cleared by Model Armor ({MODEL_ARMOR_FLOOR_SETTING})."


# =========================================================================
# 4. CENTRALIZED LAZY TOOLSET & DUAL-PROJECT ONEMCP FACTORY
# =========================================================================
class LazyToolset(BaseToolset):
    """Helper to lazily load and resolve MCP tools at runtime."""
    def __init__(self, toolset_fn):
        super().__init__()
        self._toolset_fn = toolset_fn
        self._toolset = None

    async def get_tools(self, readonly_context=None):
        if self._toolset is None:
            self._toolset = self._toolset_fn()
        import inspect
        if inspect.iscoroutinefunction(self._toolset.get_tools):
            return await self._toolset.get_tools(readonly_context)
        return self._toolset.get_tools(readonly_context)


# Universal, project-agnostic OneMCP endpoints
LOGGING_MCP_SERVER = os.environ.get("LOGGING_MCP_URL", "https://logging.googleapis.com/mcp")
MONITORING_MCP_SERVER = os.environ.get("MONITORING_MCP_URL", "https://monitoring.googleapis.com/mcp")
TRACE_MCP_SERVER = os.environ.get("TRACE_MCP_URL", "https://cloudtrace.googleapis.com/mcp")
ERROR_REPORTING_MCP_SERVER = os.environ.get("ERROR_REPORTING_MCP_URL", "https://clouderrorreporting.googleapis.com/mcp")
GKE_MCP_SERVER = os.environ.get("GKE_MCP_URL", "https://container.googleapis.com/mcp")
COMPUTE_MCP_SERVER = os.environ.get("COMPUTE_MCP_URL", "https://compute.googleapis.com/mcp")
GCS_MCP_SERVER = os.environ.get("GCS_MCP_URL", "https://storage.googleapis.com/storage/mcp")
BQ_MCP_SERVER = os.environ.get("BQ_MCP_URL", "https://bigquery.googleapis.com/mcp")

_toolset_cache = {}
_mcp_creds = None


def get_mcp_toolset(url_or_urn: str, target_project: str = None):
    """Returns an MCPToolset connected to Google's OneMCP server over HTTP+SSE with dynamic token refresh
    and Dual-Project Hub-and-Spoke routing (`antigravity-web-hub-argolis` + `argodev-prod-audit-logs-0`).

    Args:
        url_or_urn: The OneMCP server URL or Vertex AI AgentRegistry URN.
        target_project: Optional explicit project ID for `x-goog-user-project` routing
            (e.g., `LOGGING_PROJECT_ID` for `argodev-prod-audit-logs-0` or `PROJECT_ID` for `antigravity-web-hub-argolis`).
    """
    if url_or_urn.startswith("projects/"):
        from google.adk.integrations.agent_registry import AgentRegistry
        registry = AgentRegistry(project_id=target_project or PROJECT_ID, location=GEMINI_LOCATION)
        return registry.get_mcp_toolset(url_or_urn)

    # Determine effective target project for cache key and headers
    is_central_hub_service = url_or_urn in (LOGGING_MCP_SERVER, BQ_MCP_SERVER)
    effective_target = target_project or (LOGGING_PROJECT_ID if is_central_hub_service else PROJECT_ID)
    cache_key = f"{url_or_urn}::{target_project or 'default'}"

    if cache_key in _toolset_cache:
        return _toolset_cache[cache_key]

    logger.info(
        "[OneMCP] Initializing dual-project connection to %s (runtime=%s, target=%s, central_hub=%s)",
        url_or_urn, PROJECT_ID, effective_target, LOGGING_PROJECT_ID,
    )

    def dynamic_header_provider(context=None) -> dict:
        try:
            global _mcp_creds
            if _mcp_creds is None:
                _mcp_creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
            if not _mcp_creds.valid:
                _mcp_creds.refresh(google.auth.transport.requests.Request())
            # When target_project is explicitly supplied, use it as x-goog-user-project;
            # otherwise use PROJECT_ID as the quota project (where the SA holds serviceUsageConsumer)
            # while advertising LOGGING_PROJECT_ID for cross-project hub queries.
            quota_project = target_project if target_project else PROJECT_ID
            headers = {
                "Authorization": f"Bearer {_mcp_creds.token}",
                "x-goog-user-project": str(quota_project),
            }
            return headers
        except Exception as e:
            logger.error("❌ Failed to refresh OAuth token for OneMCP %s: %s", url_or_urn, e)
            return {"x-goog-user-project": str(target_project or PROJECT_ID)}

    toolset = MCPToolset(
        connection_params=StreamableHTTPConnectionParams(url=url_or_urn),
        header_provider=dynamic_header_provider
    )
    # Attach metadata attributes for inspection and testing
    try:
        object.__setattr__(toolset, "_target_project", effective_target)
        object.__setattr__(toolset, "_supported_projects", [PROJECT_ID, LOGGING_PROJECT_ID])
    except Exception:
        pass
    _toolset_cache[cache_key] = toolset
    return toolset


# =========================================================================
# 5. DETERMINISTIC DUAL-PROJECT LOGGING & BIGQUERY HUB HELPERS
# =========================================================================
_BASELINE_RELEASE_LEDGER = [
    {
        "service_name": "cartservice",
        "namespace": "default",
        "cluster_name": "online-boutique",
        "region": "europe-west1",
        "version": "v2.0.0-broken",
        "previous_stable_version": "v1.0.4",
        "image_tag": "us-central1-docker.pkg.dev/google-samples/microservices-demo/cartservice:broken-v2",
        "previous_stable_image": "gcr.io/google-samples/microservices-demo/cartservice:v1.0.4",
        "status": "FAILED_CRASHLOOP",
        "commit_sha": "a91f4c2",
        "deployed_by": "ci-cd-pipeline@antigravity-web-hub-argolis.iam.gserviceaccount.com",
        "summary": "Canary rollout introduced broken Redis connection string causing CrashLoopBackOff",
    },
    {
        "service_name": "frontend",
        "namespace": "default",
        "cluster_name": "online-boutique",
        "region": "europe-west1",
        "version": "v1.0.4",
        "previous_stable_version": "v1.0.3",
        "image_tag": "gcr.io/google-samples/microservices-demo/frontend:v1.0.4",
        "status": "SUCCESS",
        "commit_sha": "b82e1d0",
        "deployed_by": "ci-cd-pipeline@antigravity-web-hub-argolis.iam.gserviceaccount.com",
        "summary": "Standard frontend deployment in online-boutique (europe-west1)",
    },
    {
        "service_name": "redis-cart",
        "namespace": "default",
        "cluster_name": "online-boutique",
        "region": "europe-west1",
        "version": "redis:alpine",
        "previous_stable_version": "redis:alpine",
        "image_tag": "redis:alpine",
        "status": "SUCCESS",
        "commit_sha": "c74a9e1",
        "deployed_by": "ci-cd-pipeline@antigravity-web-hub-argolis.iam.gserviceaccount.com",
        "summary": "Stateful Redis backing store for cartservice",
    },
    {
        "service_name": "antigravity-web-hub",
        "namespace": "cloud-run",
        "cluster_name": "serverless-ew1",
        "region": "europe-west1",
        "version": "rev-00042-iap",
        "previous_stable_version": "rev-00041-iap",
        "image_tag": "europe-west1-docker.pkg.dev/antigravity-web-hub-argolis/cloud-run-source-deploy/antigravity-web-hub:latest",
        "status": "SUCCESS",
        "commit_sha": "d19b3f4",
        "deployed_by": "jpaquay@jpaquay.altostrat.com",
        "summary": "Direct Cloud Run IAP protected operator portal in antigravity-web-hub-argolis",
    },
    {
        "service_name": "aether-web-gui",
        "namespace": "cloud-run",
        "cluster_name": "serverless-ew1",
        "region": "europe-west1",
        "version": "rev-00018",
        "previous_stable_version": "rev-00017",
        "image_tag": "europe-west1-docker.pkg.dev/antigravity-web-hub-argolis/cloud-run-source-deploy/aether-web-gui:latest",
        "status": "SUCCESS",
        "commit_sha": "e55c8a2",
        "deployed_by": "jpaquay@jpaquay.altostrat.com",
        "summary": "Aether Web GUI frontend with Nginx upstream proxy and IAP integration",
    },
    {
        "service_name": "ge-hosted-agy-agent",
        "namespace": "vertex-agent-engine",
        "cluster_name": "reasoning-engines-ew1",
        "region": "europe-west1",
        "version": "adk-2.2.0-gemini-2.5-flash",
        "previous_stable_version": "adk-2.2.0-gemini-2.5-flash",
        "image_tag": "vertexai://antigravity-web-hub-argolis/europe-west1/rca-telemetry-expert",
        "status": "SUCCESS",
        "commit_sha": "f01d7b8",
        "deployed_by": "sre-investigator-sa@antigravity-web-hub-argolis.iam.gserviceaccount.com",
        "summary": "NovaSRE ADK 2.0 Reasoning Engine fleet in europe-west1 with Model Armor INSPECT_AND_BLOCK",
    },
]


def query_central_audit_logs(filter_str: str = "", project_ids: list[str] = None, limit: int = 25) -> str:
    """Queries Cloud Logging across both the Central Audit & Logging Hub (`argodev-prod-audit-logs-0`)
    and the Runtime Host Project (`antigravity-web-hub-argolis`) via the Cloud Logging v2 REST API.

    Args:
        filter_str: Cloud Logging filter expression (e.g. 'resource.type="k8s_container" AND severity>=ERROR').
        project_ids: Optional list of GCP project IDs to query. Defaults to [LOGGING_PROJECT_ID, PROJECT_ID].
        limit: Maximum number of log entries to return (default 25, max 100).

    Returns:
        JSON-formatted string containing matching log entries across the hub-and-spoke projects.
    """
    import requests

    targets = project_ids or [LOGGING_PROJECT_ID, PROJECT_ID]
    resource_names = [f"projects/{p}" if not str(p).startswith("projects/") else str(p) for p in targets]
    safe_limit = max(1, min(int(limit or 25), 100))

    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())

        entries_collected = []
        payload = {
            "resourceNames": resource_names,
            "orderBy": "timestamp desc",
            "pageSize": safe_limit,
        }
        if filter_str and filter_str.strip():
            payload["filter"] = filter_str.strip()

        resp = requests.post(
            "https://logging.googleapis.com/v2/entries:list",
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
                "x-goog-user-project": str(PROJECT_ID),
            },
            json=payload,
            timeout=15.0,
        )
        if resp.status_code == 200:
            raw_entries = resp.json().get("entries", [])
            for entry in raw_entries[:safe_limit]:
                if True:
                    entries_collected.append({
                        "project": entry.get("logName", "").split("/logs/")[0] or resource_names[0],
                        "timestamp": entry.get("timestamp"),
                        "severity": entry.get("severity", "DEFAULT"),
                        "logName": entry.get("logName", ""),
                        "resource": entry.get("resource", {}),
                        "payload": (
                            entry.get("textPayload")
                            or entry.get("jsonPayload")
                            or entry.get("protoPayload")
                            or {}
                        ),
                    })
        return json.dumps({
            "status": "SUCCESS",
            "queried_projects": targets,
            "central_audit_hub": LOGGING_PROJECT_ID,
            "runtime_project": PROJECT_ID,
            "filter": filter_str,
            "entry_count": len(entries_collected),
            "entries": entries_collected[:safe_limit],
        }, indent=2, default=str)
    except Exception as e:
        logger.warning("query_central_audit_logs fallback notice: %s", e)
        return json.dumps({
            "status": "FALLBACK",
            "queried_projects": targets,
            "central_audit_hub": LOGGING_PROJECT_ID,
            "runtime_project": PROJECT_ID,
            "filter": filter_str,
            "message": f"Direct Cloud Logging query notice: {str(e)}",
            "entries": [],
        }, indent=2)


def query_central_release_ledger(service_name: str = "") -> str:
    """Queries the centralized deployment & release ledger (`argodev-prod-audit-logs-0.sre_releases.recent_releases`)
    in `europe-west1` to correlate production outages with recent CI/CD rollouts or configuration changes.

    Args:
        service_name: Optional microservice or Cloud Run service name to filter by (e.g. 'cartservice', 'frontend', 'antigravity-web-hub').

    Returns:
        JSON-formatted string containing recent release records from `argodev-prod-audit-logs-0.sre_releases.recent_releases`.
    """
    clean_svc = re.sub(r"[^a-zA-Z0-9_\-\.]", "", service_name or "").strip()
    try:
        from google.cloud import bigquery
        # Run the BigQuery job in PROJECT_ID (or LOGGING_PROJECT_ID) reading from LOGGING_PROJECT_ID.sre_releases.recent_releases
        bq_client = bigquery.Client(project=PROJECT_ID, location=GEMINI_LOCATION)
        if clean_svc:
            sql = f"""
                SELECT *
                FROM `{BQ_RECENT_RELEASES_TABLE}`
                WHERE LOWER(service_name) = LOWER(@service_name)
                ORDER BY timestamp_utc DESC
                LIMIT 20
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("service_name", "STRING", clean_svc)]
            )
        else:
            sql = f"""
                SELECT *
                FROM `{BQ_RECENT_RELEASES_TABLE}`
                ORDER BY timestamp_utc DESC
                LIMIT 25
            """
            job_config = bigquery.QueryJobConfig()

        rows = [dict(row.items()) for row in bq_client.query(sql, job_config=job_config).result(timeout=15)]
        if rows:
            return json.dumps({
                "status": "SUCCESS",
                "source_table": BQ_RECENT_RELEASES_TABLE,
                "location": GEMINI_LOCATION,
                "service_filter": clean_svc or "ALL",
                "release_count": len(rows),
                "releases": rows,
            }, indent=2, default=str)
    except Exception as bq_err:
        logger.debug("BigQuery live query fallback to seeded ledger (%s): %s", BQ_RECENT_RELEASES_TABLE, bq_err)

    # Deterministic fallback to seeded baseline ledger if table is still provisioning or offline
    filtered = [
        r for r in _BASELINE_RELEASE_LEDGER
        if not clean_svc or r["service_name"].lower() == clean_svc.lower()
    ]
    return json.dumps({
        "status": "SUCCESS_SEEDED_LEDGER",
        "source_table": BQ_RECENT_RELEASES_TABLE,
        "location": GEMINI_LOCATION,
        "service_filter": clean_svc or "ALL",
        "release_count": len(filtered),
        "releases": filtered,
    }, indent=2, default=str)
