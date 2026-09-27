"""Proposal providers. Both return raw text that goes through the same parser.

- ``MockProvider``: returns a hand-authored fixture for a known sample source.
  No network, no cost, and never described as an LLM.
- ``AnthropicProvider``: a genuine Claude call via the official SDK. Needs the
  optional ``anthropic`` package and an explicit ``ANTHROPIC_API_KEY``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .workspace import redact

DEFAULT_MODEL = "claude-opus-5"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURES = REPO_ROOT / "examples" / "scenario" / "mock_responses"

# JSON Schema for structured output; mirrors schema/WIKI_SCHEMA.md section 4.
PROPOSAL_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "source_title": {"type": "string"},
        "interpretation": {"type": "string"},
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "string"},
                    "existing_claim": {"type": "string"},
                    "new_evidence": {"type": "string"},
                    "proposed_resolution": {"type": "string"},
                },
                "required": ["page", "existing_claim", "new_evidence", "proposed_resolution"],
                "additionalProperties": False,
            },
        },
        "security_notes": {"type": "array", "items": {"type": "string"}},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "update"]},
                    "page_id": {"type": "string"},
                    "page_type": {"type": "string", "enum": ["concept", "source"]},
                    "rationale": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["action", "page_id", "page_type", "rationale", "content"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["source_title", "interpretation", "contradictions", "security_notes", "changes"],
    "additionalProperties": False,
}


class ProviderError(RuntimeError):
    pass


@dataclass
class ProposalRequest:
    system: str
    user: str
    source_stem: str
    source_sha256: str
    page_hashes: dict = field(default_factory=dict)  # page id -> sha256 of current file


@dataclass
class ProviderResult:
    text: str
    mode: str  # "mock" | "llm"
    provider: str
    model: str | None = None
    usage: dict | None = None


class MockProvider:
    mode = "mock"

    def __init__(self, fixtures_dir: Path | None = None):
        self.fixtures_dir = Path(fixtures_dir or os.environ.get("BRAIN_MOCK_FIXTURES") or DEFAULT_FIXTURES)

    def describe(self) -> str:
        return "MOCK — deterministic hand-authored fixture, no LLM call"

    def propose(self, req: ProposalRequest) -> ProviderResult:
        path = self.fixtures_dir / f"{req.source_stem}.json"
        if not path.is_file():
            raise ProviderError(
                f"mock mode has no fixture for source '{req.source_stem}' (looked for {path}). "
                "Mock mode only covers the bundled sample scenario; use --mode llm for other sources."
            )
        fixture = json.loads(path.read_text(encoding="utf-8"))
        guard = fixture.get("_mock", {})
        if guard.get("for_source_sha256") != req.source_sha256:
            raise ProviderError("mock fixture was written for a different version of this source (sha256 mismatch)")
        for page_id, expected in guard.get("base_page_sha256", {}).items():
            if req.page_hashes.get(page_id) != expected:
                raise ProviderError(
                    f"mock fixture was written for a different wiki state (page '{page_id}' differs); "
                    "reset the demo workspace or use --mode llm"
                )
        return ProviderResult(
            text=json.dumps(fixture["response"], ensure_ascii=False),
            mode=self.mode,
            provider="mock-fixture",
            model=None,
        )


class AnthropicProvider:
    mode = "llm"

    def __init__(self, model: str | None = None, effort: str | None = None, client=None):
        self.model = model or os.environ.get("BRAIN_LLM_MODEL") or DEFAULT_MODEL
        self.effort = effort or os.environ.get("BRAIN_LLM_EFFORT") or "high"
        self._client = client  # injectable for tests

    def describe(self) -> str:
        return f"LLM — Anthropic Messages API, model {self.model}"

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ProviderError(
                "LLM mode needs an explicit ANTHROPIC_API_KEY environment variable. "
                "Nothing was sent. Use --mode mock for the no-cost demo."
            )
        try:
            import anthropic
        except ImportError:
            raise ProviderError("LLM mode needs the optional SDK: pip install -r requirements-llm.txt") from None
        return anthropic.Anthropic(max_retries=2, timeout=600)

    def propose(self, req: ProposalRequest) -> ProviderResult:
        client = self._get_client()
        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=req.system,
            messages=[{"role": "user", "content": req.user}],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": PROPOSAL_JSON_SCHEMA},
            },
        )
        if self.model.startswith(("claude-opus-5", "claude-fable-5")):
            # Server-side refusal fallback, routed by Anthropic's default policy.
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        try:
            response = client.beta.messages.create(**kwargs)
        except ProviderError:
            raise
        except Exception as exc:  # SDK errors: auth, rate limit, network, bad request
            raise ProviderError(redact(f"LLM request failed: {type(exc).__name__}: {exc}")) from None

        if response.stop_reason == "refusal":
            raise ProviderError("the model declined to produce a proposal (stop_reason=refusal)")
        if response.stop_reason == "max_tokens":
            raise ProviderError("the proposal was truncated (stop_reason=max_tokens); nothing was staged")
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        usage = getattr(response, "usage", None)
        return ProviderResult(
            text=text,
            mode=self.mode,
            provider="anthropic",
            model=getattr(response, "model", self.model),
            usage={
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
            if usage
            else None,
        )


def get_provider(mode: str, **kwargs):
    if mode == "mock":
        return MockProvider(kwargs.get("fixtures_dir"))
    if mode == "llm":
        return AnthropicProvider(model=kwargs.get("model"))
    raise ProviderError(f"unknown mode {mode!r} (expected 'mock' or 'llm')")
