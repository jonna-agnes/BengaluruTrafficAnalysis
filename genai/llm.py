"""Minimal OpenRouter chat client (OpenAI-compatible API).

Reads OPENROUTER_API_KEY and OPENROUTER_MODEL from the environment or the
repo-root .env file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict], *, model: str | None = None, max_tokens: int = 4000,
         temperature: float = 0.3, timeout: int = 180) -> str:
    """Send a chat completion. Reasoning effort comes from OPENROUTER_REASONING_EFFORT
    (default "low"): hidden reasoning tokens count against max_tokens."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY is not set (put it in .env)")

    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "Bengaluru Traffic Intelligence",
        },
        json={
            "model": model or os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "reasoning": {"effort": os.getenv("OPENROUTER_REASONING_EFFORT", "low")},
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise LLMError(f"OpenRouter {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    if "error" in data:
        raise LLMError(f"OpenRouter error: {data['error']}")
    choice = data["choices"][0]
    content = (choice.get("message") or {}).get("content")
    if not content:
        raise LLMError(
            f"empty response (finish_reason={choice.get('finish_reason')}, "
            f"native={choice.get('native_finish_reason')}, "
            f"refusal={(choice.get('message') or {}).get('refusal')})")
    if choice.get("finish_reason") == "length":
        print(f"[warn] response truncated at max_tokens={max_tokens}", file=sys.stderr)
    return content.strip()
