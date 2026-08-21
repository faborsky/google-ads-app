"""One-time OAuth2 flow → refresh token, written straight into .env.

The token never has to pass through a terminal, a chat window or an agent's
context: by default `auth` writes GOOGLE_ADS_REFRESH_TOKEN[_<ACCOUNT>] into
.env atomically (backup in .env.bak, both chmod 600). `--print` shows the
token instead, for people who keep their .env elsewhere.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil

from gads.api import BASE_DIR, ENV_FILE, SCOPES, _atomic_write_text, _env
from gads.formatting import _die, _err, _output_json


def _write_refresh_token(var_name: str, token: str) -> str:
    """Replace or append `var_name=token` in .env (creating it from
    .env.example when missing). Returns what happened."""
    example = BASE_DIR / ".env.example"
    if not ENV_FILE.exists():
        if example.exists():
            shutil.copyfile(example, ENV_FILE)
        else:
            ENV_FILE.write_text("")
        os.chmod(ENV_FILE, 0o600)
    original = ENV_FILE.read_text(encoding="utf-8")
    backup = BASE_DIR / ".env.bak"
    _atomic_write_text(backup, original, mode=0o600)

    pattern = re.compile(rf"^{re.escape(var_name)}=.*$", re.M)
    line = f"{var_name}={token}"
    if pattern.search(original):
        updated = pattern.sub(line, original, count=1)
        action = "aktualizován"
    else:
        updated = original.rstrip("\n") + ("\n" if original.strip() else "") + line + "\n"
        action = "přidán"
    _atomic_write_text(ENV_FILE, updated, mode=0o600)
    return action


def cmd_auth(args: argparse.Namespace) -> None:
    """One-time OAuth2 flow → refresh token → .env (or --print)."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        _die("google-auth-oauthlib není nainstalovaná. Spusť ./setup.sh.")

    client_id = _env("GOOGLE_ADS_CLIENT_ID", args.account)
    client_secret = _env("GOOGLE_ADS_CLIENT_SECRET", args.account)
    if not client_id or not client_secret:
        _die("Nejdřív vyplň GOOGLE_ADS_CLIENT_ID a GOOGLE_ADS_CLIENT_SECRET v .env "
             "(OAuth klient typu „Desktop app“ z Cloud Console) — pak spusť auth znovu.")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    _err("Otevírám prohlížeč pro autorizaci přístupu ke Google Ads…")
    _err("Přihlas se Google účtem, který má přístup k tvému Google Ads / MCC účtu.\n")
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        _die("Google nevrátil refresh token. Zkontroluj, že máš v OAuth consent screen "
             "sebe jako Test user (režim Testing), nebo appku publikovanou (In production).")

    suffix = "" if not args.account or args.account == "default" else f"_{args.account.upper()}"
    var_name = f"GOOGLE_ADS_REFRESH_TOKEN{suffix}"

    if args.print_token:
        if args.json:
            _output_json({"refresh_token": creds.refresh_token, "env_var": var_name})
        else:
            print(f"\n✅ Hotovo. Vlož do .env tenhle řádek:\n\n{var_name}={creds.refresh_token}\n")
        return

    action = _write_refresh_token(var_name, creds.refresh_token)
    if args.json:
        _output_json({"env_var": var_name, "written_to": str(ENV_FILE), "action": action})
        return
    print(f"\n✅ Refresh token {action} v .env ({var_name}); záloha původního .env v .env.bak.")
    print("   Token se nikde nevypisuje — je jen v .env (chmod 600).")
    print("   Tip: v Cloud Console přepni OAuth consent screen na „In production“, jinak token "
          "v režimu Testing vyprší po 7 dnech.")
    print("   Ověř: ./run.sh accounts")
