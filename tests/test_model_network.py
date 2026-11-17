"""Project-scoped model transport policy: no real network requests."""
import os

import httpx

from target import model_network


def test_direct_ignores_dead_inherited_proxy(monkeypatch):
    monkeypatch.setenv("TICKET_MODEL_PROXY_MODE", "direct")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:17015")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:17015")
    client = httpx.Client(**model_network.client_kwargs(timeout=1))
    try:
        assert client.trust_env is False
        assert model_network.describe()["proxy_configured"] is False
    finally:
        client.close()


def test_custom_requires_and_uses_explicit_proxy(monkeypatch):
    monkeypatch.setenv("TICKET_MODEL_PROXY_MODE", "custom")
    monkeypatch.setenv("TICKET_MODEL_PROXY_URL", "http://127.0.0.1:18993")
    kwargs = model_network.client_kwargs(timeout=1)
    assert kwargs["trust_env"] is False
    assert kwargs["proxy"] == "http://127.0.0.1:18993"


def test_system_mode_remains_opt_in(monkeypatch):
    monkeypatch.delenv("TICKET_MODEL_PROXY_URL", raising=False)
    monkeypatch.setenv("TICKET_MODEL_PROXY_MODE", "system")
    kwargs = model_network.client_kwargs(timeout=1)
    assert kwargs["trust_env"] is True
    assert "proxy" not in kwargs
