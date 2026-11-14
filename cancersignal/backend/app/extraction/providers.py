"""OpenAI-compatible transport, explicit opt-in to network use, no implicit retries."""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.contracts.common import ComponentProvenance
from app.extraction.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from app.extraction.schema import output_schema
from app.schemas.records import NonEmpty


class ProviderError(Exception):
    """Safe error codes/messages only; no patient text or provider error bodies."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CompletionProvider(Protocol):
    @property
    def provenance(self) -> ComponentProvenance: ...

    def complete(self, messages: list[dict[str, str]], schema: dict) -> str: ...


class ProviderSettings(BaseSettings):
    # Environment or explicitly supplied _env_file; no automatic .env discovery.
    model_config = SettingsConfigDict(env_prefix="EXTRACTION_", extra="forbid", frozen=True)
    provider: Literal["verda", "openai"] = "verda"
    model: NonEmpty
    api_key: SecretStr = SecretStr("")
    base_url: str | None = None
    response_format: Literal["json_schema", "json_object"] = "json_schema"
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = None
    max_output_tokens: int = Field(default=4096, ge=1, le=65536)
    context_window_tokens: int | None = Field(default=None, ge=1)
    max_input_bytes: int = Field(default=60000, ge=1)
    timeout_seconds: float = Field(default=55, gt=0, le=300)
    max_response_bytes: int = Field(default=1000000, ge=1)

    @model_validator(mode="after")
    def valid_endpoint(self):
        if self.base_url is not None:
            parsed = urlsplit(self.base_url)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment):
                raise ValueError("base_url must be an HTTPS endpoint without embedded credentials/query/fragment.")
        if self.context_window_tokens is not None and self.max_output_tokens >= self.context_window_tokens:
            raise ValueError("Output budget must be smaller than the model context window.")
        return self

    @property
    def endpoint(self) -> str:
        return self.base_url or {
            "verda": "https://inference.verda.com/v1",
            "openai": "https://api.openai.com/v1",
        }[self.provider]


class ChatCompletionsProvider:
    def __init__(self, settings: ProviderSettings, *, allow_live: bool = False, transport=None):
        self.settings = settings
        self.allow_live = allow_live
        self.transport = transport

    @property
    def provenance(self) -> ComponentProvenance:
        config = self.settings.model_dump(mode="json", exclude={"api_key"})
        config.update(prompt=SYSTEM_PROMPT, schema=output_schema())
        digest = sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        return ComponentProvenance(name="clinical-extraction", version="1.0", method="llm",
                                   provider=self.settings.provider, model=self.settings.model,
                                   prompt_version=PROMPT_VERSION, configuration_digest=digest)

    def request_body(self, messages: list[dict[str, str]], schema: dict) -> dict:
        settings = self.settings
        # Count the actual serialized input plus framing conservatively. This is
        # a byte budget, NOT a model-specific tokenizer or an exact token count.
        size = len(json.dumps({"messages": messages, "schema": schema}, ensure_ascii=False).encode("utf-8"))
        if size > settings.max_input_bytes:
            raise ProviderError("input_limit", "Input exceeds the configured byte budget; no sources were truncated.")
        if (settings.context_window_tokens is not None
                and size + 256 + settings.max_output_tokens > settings.context_window_tokens):
            raise ProviderError("context_limit", "Conservative context budget exceeded; supply a smaller retrieval context.")
        body = {"model": settings.model, "messages": messages, "stream": False}
        token_field = "max_completion_tokens" if settings.provider == "openai" else "max_tokens"
        body[token_field] = settings.max_output_tokens
        if settings.reasoning_effort is not None:
            body["reasoning_effort"] = settings.reasoning_effort
        if settings.response_format == "json_schema":
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "clinical_extraction", "strict": True, "schema": schema,
            }}
        else:
            # Explicit capability choice, never a silent downgrade after a failed call.
            body["response_format"] = {"type": "json_object"}
        if settings.provider == "openai":
            body["store"] = False
        return body

    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        body = self.request_body(messages, schema)
        if not self.allow_live and self.transport is None:
            raise ProviderError("live_calls_disabled", "Live LLM calls require explicit authorization and allow_live=True.")
        # An injected transport must be an in-memory mock, never a real HTTP transport.
        import httpx

        if self.transport is not None and not isinstance(self.transport, httpx.MockTransport):
            raise ProviderError("invalid_transport", "Only httpx.MockTransport may bypass live-call authorization.")
        if self.transport is None and not self.settings.api_key.get_secret_value():
            raise ProviderError("missing_api_key", "Set EXTRACTION_API_KEY for the selected provider.")
        try:
            with httpx.Client(transport=self.transport, timeout=self.settings.timeout_seconds,
                              follow_redirects=False, trust_env=False) as client:
                with client.stream("POST", self.settings.endpoint.rstrip("/") + "/chat/completions",
                                   json=body, headers={"Authorization": "Bearer " + self.settings.api_key.get_secret_value()}) as response:
                    if response.is_error:
                        self._raise_http_error(response)
                    if response.status_code != 200:
                        raise ProviderError("provider_http_error", "Provider returned an unexpected HTTP status.")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.settings.max_response_bytes:
                            raise ProviderError("response_limit", "Provider response exceeds the configured byte limit.")
                        chunks.append(chunk)
            return self._content(b"".join(chunks))
        except httpx.TimeoutException:
            raise ProviderError("provider_timeout", "Provider request timed out; no automatic retry was made.") from None
        except httpx.HTTPError:
            raise ProviderError("provider_transport_error", "Provider connection failed; no automatic retry was made.") from None

    @staticmethod
    def _raise_http_error(response):
        # Do not echo a remote error message: it can contain notes or credentials.
        status = response.status_code
        codes = {400: "provider_request_rejected", 401: "provider_authentication", 402: "provider_billing",
                 403: "provider_access_denied", 404: "provider_model_or_endpoint", 413: "context_limit",
                 422: "provider_request_rejected", 429: "provider_rate_limit"}
        code = codes.get(status, "provider_unavailable" if status >= 500 else "provider_http_error")
        # Status 400 includes unsupported reasoning/schema parameters and context
        # overflow. Callers get an explicit rejection, never an unannounced retry.
        raise ProviderError(code, f"Provider rejected the request (HTTP {status}); check model capabilities, parameters and limits.")

    @staticmethod
    def _content(raw: bytes) -> str:
        try:
            envelope = json.loads(raw)
            choices = envelope["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            choice = choices[0]
            message = choice["message"]
            if message.get("refusal") or choice.get("finish_reason") == "content_filter":
                raise ProviderError("provider_refusal", "Provider refused extraction.")
            if choice.get("finish_reason") == "length":
                raise ProviderError("output_limit", "Output token limit reached; incomplete extraction was discarded.")
            if choice.get("finish_reason") != "stop" or message.get("tool_calls"):
                raise ProviderError("provider_incomplete", "Provider did not return a complete extraction response.")
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError
            return content
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            raise ProviderError("invalid_provider_response", "Provider returned a malformed response envelope.") from None


@dataclass(frozen=True)
class FixtureProvider:
    """Explicit synthetic replay, never an automatic fallback for failed live calls."""
    response: str

    @property
    def provenance(self) -> ComponentProvenance:
        return ComponentProvenance(name="clinical-extraction", version="1.0", method="manual",
                                   provider="synthetic-fixture", model="hand-authored-v1",
                                   prompt_version=PROMPT_VERSION,
                                   configuration_digest=sha256(self.response.encode()).hexdigest())

    def complete(self, messages: list[dict[str, str]], schema: dict) -> str:
        return self.response
