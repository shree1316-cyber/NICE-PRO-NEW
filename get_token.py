"""Create today's Zerodha Kite access token for NICE-PRO.

Run this file locally from the NICE-PRO project folder.  It opens Zerodha's
official Kite login page, exchanges the one-time ``request_token`` returned to
your registered redirect URL, and writes only ``KITE_ACCESS_TOKEN`` to your
untracked .env file.  It never prints or stores the API secret in source code.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv, set_key


PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"


def request_token_from_input(value: str) -> str:
    """Accept either the full redirect URL or the request token itself."""
    entered = value.strip()
    parsed = urlparse(entered)
    token = parse_qs(parsed.query).get("request_token", [""])[0].strip()
    return token or entered


def main() -> int:
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        print("Kite Connect is not installed. Run: .\\.venv\\Scripts\\python.exe -m pip install -e .")
        return 1

    if not ENV_FILE.exists():
        print("Missing .env. Copy .env.example to .env, then add KITE_API_KEY and KITE_API_SECRET.")
        return 1

    load_dotenv(ENV_FILE, override=True)
    from os import getenv

    api_key = (getenv("KITE_API_KEY") or "").strip()
    api_secret = (getenv("KITE_API_SECRET") or "").strip()
    if not api_key or not api_secret:
        print("KITE_API_KEY or KITE_API_SECRET is missing in .env.")
        return 1

    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()
    print("Opening the official Zerodha Kite login page in your browser...")
    print("After login, copy the complete redirect URL from the browser address bar.")
    print("Do not share the URL or its request_token with anyone.")
    try:
        webbrowser.open(login_url, new=2)
    except webbrowser.Error:
        print("Browser did not open automatically. Paste this URL into a browser:")
        print(login_url)

    redirect_url = input("\nPaste the complete redirect URL (or request_token) here: ").strip()
    request_token = request_token_from_input(redirect_url)
    if not request_token:
        print("No request_token was found. Login again and paste the returned redirect URL.")
        return 1

    try:
        session = kite.generate_session(request_token, api_secret=api_secret)
        access_token = str(session["access_token"])
    except Exception:
        print("Token exchange failed. Check the API key, API secret, one-time request_token, and network, then try again.")
        return 1

    set_key(str(ENV_FILE), "KITE_ACCESS_TOKEN", access_token, quote_mode="never")
    user_name = str(session.get("user_name") or session.get("user_id") or "Kite user")
    print(f"Success: access token saved to {ENV_FILE.name} for {user_name}.")
    print("Zerodha access tokens expire at 6 AM the next day. Run this script again on the next trading day.")
    print("NICE-PRO remains paper-only; this script does not place any order.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
