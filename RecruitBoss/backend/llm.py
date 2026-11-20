"""Local Ollama client. No cloud calls, no API keys. Uses plain HTTP so there are no extra packages."""
from __future__ import annotations

import json
import os
import re

import requests

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))


def status() -> dict:
    """Is Ollama up, and which models are installed?"""
    try:
        r = requests.get(f"{BASE_URL}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"online": True, "models": models, "default": DEFAULT_MODEL if DEFAULT_MODEL in models or not models else models[0]}
    except Exception as exc:  # noqa: BLE001
        return {"online": False, "models": [], "default": DEFAULT_MODEL, "error": str(exc)[:200]}


def chat_json(model: str, system: str, user: str, timeout: int | None = None) -> dict | None:
    """Ask for a JSON answer. Returns None on any failure so the caller can fall back to rules."""
    try:
        r = requests.post(
            f"{BASE_URL}/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0, "num_ctx": 4096},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout=timeout or TIMEOUT,
        )
        r.raise_for_status()
        return parse_json(r.json()["message"]["content"])
    except Exception:  # noqa: BLE001
        return None


def parse_json(text: str) -> dict | None:
    """Models sometimes wrap JSON in prose or code fences; pull out the first object."""
    if not text:
        return None
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            v = json.loads(m.group(0))
            return v if isinstance(v, dict) else None
        except Exception:  # noqa: BLE001
            return None
    return None


def chat_stream(model: str, system: str, user: str):
    """Yield text chunks as the model writes them."""
    with requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "model": model,
            "stream": True,
            "options": {"temperature": 0.4, "num_ctx": 4096},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        },
        stream=True,
        timeout=TIMEOUT,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            piece = obj.get("message", {}).get("content", "")
            if piece:
                yield piece
            if obj.get("done"):
                break
