"""One-time OAuth2 flow → refresh token for .env."""
from __future__ import annotations

import argparse

from gads.api import SCOPES, _env
from gads.formatting import _die, _output_json


def cmd_auth(args: argparse.Namespace) -> None:
    """One-time OAuth2 flow → generates a refresh token to paste into .env."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        _die("google-auth-oauthlib not installed. Run ./setup.sh first.")

    client_id = _env("GOOGLE_ADS_CLIENT_ID", args.account)
    client_secret = _env("GOOGLE_ADS_CLIENT_SECRET", args.account)
    if not client_id or not client_secret:
        _die("Set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET in .env before running auth.")

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
    print("Opening your browser to authorize access to Google Ads…")
    print("Sign in with the Google account that has access to your Google Ads / MCC.\n")
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        _die("No refresh token returned. Make sure the OAuth consent screen has you as a Test user.")

    suffix = "" if not args.account or args.account == "default" else f"_{args.account.upper()}"
    print("\n✅ Success! Add this line to your .env:\n")
    print(f"GOOGLE_ADS_REFRESH_TOKEN{suffix}={creds.refresh_token}\n")
    if args.json:
        _output_json({"refresh_token": creds.refresh_token})
