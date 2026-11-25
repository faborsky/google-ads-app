"""Keyless mode: no refresh token or key file required,
tokens come from gcloud impersonation."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from gads import api


def test_config_does_not_require_oauth_keys(monkeypatch):
    for key in ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
                "GOOGLE_ADS_JSON_KEY_FILE_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("GOOGLE_ADS_DEVELOPER_TOKEN", raising=False)
    monkeypatch.setenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "905-065-6850")
    monkeypatch.setenv("GOOGLE_ADS_IMPERSONATE_SERVICE_ACCOUNT", "sa@example.iam.gserviceaccount.com")
    cfg = api._config_dict(None)
    assert cfg["login_customer_id"] == "9050656850"
    assert "refresh_token" not in cfg and "json_key_file_path" not in cfg


def test_refresh_uses_gcloud_and_never_keeps_stderr(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, timeout, check):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="ya29.token\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    creds = api._GcloudImpersonatedCredentials("sa@x.iam.gserviceaccount.com", "me@x.cz", api.SCOPES)
    creds.refresh(None)
    assert creds.token == "ya29.token" and creds.expiry is not None
    assert "--impersonate-service-account=sa@x.iam.gserviceaccount.com" in calls[0]
    assert "--account=me@x.cz" in calls[0]


def test_refresh_failure_is_a_refresh_error(monkeypatch):
    from google.auth.exceptions import RefreshError

    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="Reauthentication failed"),
    )
    creds = api._GcloudImpersonatedCredentials("sa@x.iam.gserviceaccount.com", "me@x.cz", api.SCOPES)
    with pytest.raises(RefreshError, match="Reauthentication"):
        creds.refresh(None)


def test_client_builds_without_developer_token(monkeypatch):
    for key in ("GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
                "GOOGLE_ADS_JSON_KEY_FILE_PATH", "GOOGLE_ADS_DEVELOPER_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GOOGLE_ADS_IMPERSONATE_SERVICE_ACCOUNT", "sa@x.iam.gserviceaccount.com")
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: pytest.fail("building the client must not call gcloud"),
    )
    client = api._get_client(None)
    assert client.credentials.__class__.__name__ == "_Impl"
    assert not client.developer_token
