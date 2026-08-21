"""`auth` writes the refresh token into .env atomically — never into stdout."""
from __future__ import annotations

import argparse
import os

from gads.commands import auth as auth_cmd


def test_write_creates_env_from_example_with_600(tmp_path):
    (tmp_path / ".env.example").write_text("GOOGLE_ADS_DEVELOPER_TOKEN=\nGOOGLE_ADS_REFRESH_TOKEN=\n")
    action = auth_cmd._write_refresh_token("GOOGLE_ADS_REFRESH_TOKEN", "1//tok")
    env = tmp_path / ".env"
    assert action == "aktualizován"
    assert "GOOGLE_ADS_REFRESH_TOKEN=1//tok\n" in env.read_text()
    assert "GOOGLE_ADS_DEVELOPER_TOKEN=\n" in env.read_text()
    assert oct(env.stat().st_mode & 0o777) == "0o600"


def test_write_replaces_existing_value_and_backs_up(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GOOGLE_ADS_DEVELOPER_TOKEN=abc\nGOOGLE_ADS_REFRESH_TOKEN=old\n")
    auth_cmd._write_refresh_token("GOOGLE_ADS_REFRESH_TOKEN", "new")
    text = env.read_text()
    assert "GOOGLE_ADS_REFRESH_TOKEN=new" in text and "old" not in text
    assert text.count("GOOGLE_ADS_REFRESH_TOKEN=") == 1
    bak = tmp_path / ".env.bak"
    assert "GOOGLE_ADS_REFRESH_TOKEN=old" in bak.read_text()
    assert oct(bak.stat().st_mode & 0o777) == "0o600"


def test_write_appends_named_account_var(tmp_path):
    env = tmp_path / ".env"
    env.write_text("GOOGLE_ADS_REFRESH_TOKEN=default-token")
    action = auth_cmd._write_refresh_token("GOOGLE_ADS_REFRESH_TOKEN_KLIENTB", "b-token")
    assert action == "přidán"
    lines = env.read_text().splitlines()
    assert lines == ["GOOGLE_ADS_REFRESH_TOKEN=default-token",
                     "GOOGLE_ADS_REFRESH_TOKEN_KLIENTB=b-token"]


def test_cmd_auth_writes_by_default_and_never_prints_token(monkeypatch, tmp_path, capsys):
    (tmp_path / ".env").write_text("GOOGLE_ADS_CLIENT_ID=x\nGOOGLE_ADS_CLIENT_SECRET=y\n")

    class FakeCreds:
        refresh_token = "1//SECRET-REFRESH"

    class FakeFlow:
        @classmethod
        def from_client_config(cls, cfg, scopes):
            assert cfg["installed"]["client_id"] == "fake.apps.googleusercontent.com"
            return cls()

        def run_local_server(self, **kw):
            return FakeCreds()

    import google_auth_oauthlib.flow as flow_mod
    monkeypatch.setattr(flow_mod, "InstalledAppFlow", FakeFlow)
    auth_cmd.cmd_auth(argparse.Namespace(account="klientb", json=False, print_token=False))
    out = capsys.readouterr().out
    assert "SECRET-REFRESH" not in out and "zapsán" in out or "přidán" in out
    assert "GOOGLE_ADS_REFRESH_TOKEN_KLIENTB=1//SECRET-REFRESH" in (tmp_path / ".env").read_text()


def test_cmd_auth_print_mode_does_not_touch_env(monkeypatch, tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("GOOGLE_ADS_CLIENT_ID=x\n")
    before = env.read_text()

    class FakeCreds:
        refresh_token = "1//PRINTME"

    class FakeFlow:
        @classmethod
        def from_client_config(cls, cfg, scopes):
            return cls()

        def run_local_server(self, **kw):
            return FakeCreds()

    import google_auth_oauthlib.flow as flow_mod
    monkeypatch.setattr(flow_mod, "InstalledAppFlow", FakeFlow)
    auth_cmd.cmd_auth(argparse.Namespace(account=None, json=False, print_token=True))
    assert "GOOGLE_ADS_REFRESH_TOKEN=1//PRINTME" in capsys.readouterr().out
    assert env.read_text() == before
    assert not os.path.exists(tmp_path / ".env.bak")
