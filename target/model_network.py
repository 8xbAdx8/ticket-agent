"""Project-scoped HTTP transport for model endpoints.

Only model clients import this module.  Windows/WinHTTP/Edge and other
processes are never modified: the client either ignores inherited proxy
environment variables or uses an explicitly configured project proxy.
"""
from __future__ import annotations

import os
from typing import Any

MODES = ("system", "direct", "custom")


def settings() -> dict[str, Any]:
    mode = (os.getenv("TICKET_MODEL_PROXY_MODE") or "system").strip().lower()
    if mode not in MODES:
        raise ValueError("TICKET_MODEL_PROXY_MODE must be system, direct or custom")
    url = (os.getenv("TICKET_MODEL_PROXY_URL") or "").strip()
    if mode == "custom" and not url:
        raise ValueError("TICKET_MODEL_PROXY_URL is required in custom mode")
    no_proxy = (os.getenv("TICKET_MODEL_NO_PROXY") or "").strip()
    return {"mode": mode, "proxy_url": url or None,
            "trust_env": mode == "system", "no_proxy": no_proxy or None}


def client_kwargs(timeout: float = 30.0, **extra: Any) -> dict[str, Any]:
    """Return kwargs for httpx.Client/OpenAI without touching os.environ.

    system: retain httpx's documented env-proxy behaviour.
    direct: trust_env=False, no proxy at all.
    custom: trust_env=False and one explicit proxy for every scheme.
    """
    s = settings()
    kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": s["trust_env"]}
    if s["mode"] == "custom":
        kwargs["proxy"] = s["proxy_url"]
    kwargs.update(extra)
    return kwargs


def client(timeout: float = 30.0, **extra: Any):
    import httpx
    return httpx.Client(**client_kwargs(timeout=timeout, **extra))


def describe() -> dict[str, Any]:
    """Safe, non-secret description for developer diagnostics."""
    try:
        s = settings()
        return {"mode": s["mode"], "trust_env": s["trust_env"],
                "proxy_configured": bool(s["proxy_url"]),
                "no_proxy_configured": bool(s["no_proxy"])}
    except ValueError as exc:
        return {"mode": "invalid", "error": str(exc), "proxy_configured": False,
                "no_proxy_configured": False}
