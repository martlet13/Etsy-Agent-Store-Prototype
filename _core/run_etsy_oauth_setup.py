"""
One-time (or re-run-when-expired) Etsy OAuth setup wizard.

Run this on your own machine, with your own ETSY_KEYSTRING /
ETSY_SHARED_SECRET / ETSY_SHOP_ID already in .env.local:

    python run_etsy_oauth_setup.py

It will:
  1. Print (and try to open) an Etsy authorization URL.
  2. Start a temporary local web server on your ETSY_REDIRECT_URI
     (default http://localhost:4522/callback) to catch the redirect.
  3. Exchange the returned code for an access + refresh token.
  4. Store the tokens locally, encrypted at rest (see etsy_api_client.py
     and docs/SECURITY.md).

This never sends your Etsy credentials or tokens anywhere but Etsy's own
API — there is no vendor server in this flow.
"""

import argparse
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import etsy_api_client as etsy


class _CallbackHandler(BaseHTTPRequestHandler):
    result = {}

    def do_GET(self):  # noqa: N802 (http.server API)
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        error = query.get("error", [None])[0]

        _CallbackHandler.result = {"code": code, "state": state, "error": error}

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if error:
            message = f"<h2>Etsy authorization failed: {error}</h2><p>You can close this tab and check the terminal.</p>"
        else:
            message = "<h2>Etsy authorization received.</h2><p>You can close this tab and go back to the terminal.</p>"

        self.wfile.write(message.encode("utf-8"))

    def log_message(self, format, *args):  # noqa: A002 - silence default request logging
        return


def run_callback_server(host: str, port: int, timeout_seconds: int = 300) -> dict:
    server = HTTPServer((host, port), _CallbackHandler)
    server.timeout = timeout_seconds

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    server.server_close()
    return _CallbackHandler.result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the one-time Etsy OAuth setup for your own shop.")
    parser.add_argument("--no-browser", action="store_true", help="Do not try to auto-open a browser; just print the URL.")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait for the browser redirect.")
    args = parser.parse_args()

    redirect_uri = etsy.get_redirect_uri()
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 4522

    auth = etsy.build_authorization_url()

    print()
    print("# Etsy OAuth Setup")
    print()
    print("1. Open this URL and approve access to YOUR OWN shop:")
    print()
    print(f"   {auth['url']}")
    print()
    print(f"2. Waiting for the redirect back to {redirect_uri} ...")
    print()

    if not args.no_browser:
        try:
            webbrowser.open(auth["url"])
        except Exception:
            pass

    result = run_callback_server(host, port, timeout_seconds=args.timeout)

    if not result or (not result.get("code") and not result.get("error")):
        print("Timed out waiting for the Etsy redirect. Run this script again.")
        return

    if result.get("error"):
        print(f"Etsy returned an error: {result['error']}")
        return

    tokens = etsy.exchange_code_for_tokens(result["code"], result["state"])

    print("Etsy is now connected.")
    print(f"Access token expires at (unix time): {tokens['expires_at']:.0f}")
    print()
    print("Next step: approve the 'etsy' connector so live draft creation is allowed:")
    print("  python set_api_connector_approval.py --connector-id etsy --user-approved true --live-actions-enabled true")
    print()


if __name__ == "__main__":
    main()
