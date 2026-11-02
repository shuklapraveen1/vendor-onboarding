"""Optional LLM layer (OpenAI or Anthropic, auto-detected).

Used only for: (1) extracting fields from documents whose layout the
deterministic parser couldn't read, and (2) wording human-facing messages.
It never decides a status. Every call has a timeout and any failure returns
None so callers fall back to the deterministic path.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from . import config

log = logging.getLogger("vendor_onboarding.llm")


def provider() -> Optional[str]:
    choice = config.LLM_PROVIDER
    if choice == "none":
        return None
    if choice == "openai":
        return "openai" if config.OPENAI_API_KEY else None
    if choice == "anthropic":
        return "anthropic" if config.ANTHROPIC_API_KEY else None
    if config.OPENAI_API_KEY:
        return "openai"
    if config.ANTHROPIC_API_KEY:
        return "anthropic"
    return None


def describe() -> Dict[str, Any]:
    p = provider()
    model = None
    if p == "openai":
        model = config.OPENAI_MODEL
    elif p == "anthropic":
        model = config.ANTHROPIC_MODEL
    return {"enabled": p is not None, "provider": p, "model": model}


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _call(system: str, user: str, want_json: bool, max_tokens: int = 700) -> Optional[str]:
    p = provider()
    if not p:
        return None
    try:
        with httpx.Client(timeout=config.LLM_TIMEOUT_SECONDS) as client:
            if p == "openai":
                body: Dict[str, Any] = {
                    "model": config.OPENAI_MODEL,
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                }
                if want_json:
                    body["response_format"] = {"type": "json_object"}
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                    json=body,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            resp = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": config.ANTHROPIC_MODEL,
                    "max_tokens": max_tokens,
                    "temperature": 0,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            resp.raise_for_status()
            parts = resp.json().get("content", [])
            return "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    except Exception as exc:  # network, auth, quota, schema — all fall back
        log.warning("LLM call failed (%s): %s", p, exc)
        return None


def complete_json(system: str, user: str) -> Optional[Dict[str, Any]]:
    raw = _call(system, user, want_json=True)
    return _extract_json(raw) if raw else None


def complete_text(system: str, user: str, max_tokens: int = 400) -> Optional[str]:
    raw = _call(system, user, want_json=False, max_tokens=max_tokens)
    return raw.strip() if raw else None
