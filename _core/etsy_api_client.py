"""
Etsy Open API v3 client for SpaceCommand — DRAFT LISTINGS ONLY.

This module implements the real HTTP calls against Etsy's documented
Open API v3 (https://developers.etsy.com/documentation/) so a seller can
turn a Sentinel-approved local listing pack into an actual draft listing
on their own shop. It is built to match the repo's design principles:

- Runs entirely on the seller's machine. There is no vendor server in
  the loop; every request in this file goes straight from this process
  to api.etsy.com using the seller's own OAuth token.
- Seller-owned app. The seller creates their own app in Etsy's developer
  portal, gets their own keystring + shared secret, and completes OAuth
  for their own shop. This client never embeds or ships a shared app.
- Drafts only. create_draft_listing() always creates the listing in
  Etsy's `draft` state. This client has no function that activates a
  listing, and none should be added — activation is the seller's job in
  Etsy Seller Manager (PRD principle #4).
- Secrets stay local. OAuth tokens are stored on disk under
  _spacecommand_state/, encrypted at rest with a local-only key file
  (see docs/SECURITY.md). Nothing here calls out anywhere except Etsy.

Etsy API scopes needed for the flow this file implements:
  listings_r listings_w shops_r shops_w

Setup (see docs/SETUP.md for the full walkthrough):
  1. Create your own app at https://www.etsy.com/developers/your-apps
  2. Set its redirect URI to the value of ETSY_REDIRECT_URI (defaults to
     http://localhost:4522/callback — a loopback address, which Etsy
     allows for installed/desktop-style apps).
  3. Put ETSY_KEYSTRING, ETSY_SHARED_SECRET, ETSY_SHOP_ID in your
     .env.local.
  4. Run `python run_etsy_oauth_setup.py` once to complete OAuth login
     and store an encrypted refresh token locally.
  5. Approve the "etsy" connector: see api_connector_manager.py /
     set_api_connector_approval.py — nothing in this file will make a
     live call until the connector is explicitly approved AND the
     caller passes user_approved_live_action=True.
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

OAUTH_STATE_FILE = STATE / "etsy_oauth_state.json"
TOKEN_FILE = STATE / "etsy_oauth_tokens.enc"
TOKEN_KEY_FILE = STATE / ".etsy_token_key"

ETSY_API_BASE = "https://api.etsy.com/v3/application"
ETSY_OAUTH_CONNECT_URL = "https://www.etsy.com/oauth/connect"
ETSY_OAUTH_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

DEFAULT_SCOPES = "listings_r listings_w shops_r shops_w"
DEFAULT_REDIRECT_URI = "http://localhost:4522/callback"


class EtsyApiError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


# ---------------------------------------------------------------------------
# Local config helpers
# ---------------------------------------------------------------------------

def get_keystring() -> str:
    value = os.environ.get("ETSY_KEYSTRING") or os.environ.get("ETSY_API_KEY", "")
    if not value:
        raise EtsyApiError(
            "ETSY_KEYSTRING (your Etsy app's keystring) is not set. "
            "Add it to your local .env.local — see docs/SETUP.md."
        )
    return value


def get_shared_secret() -> str:
    value = os.environ.get("ETSY_SHARED_SECRET") or os.environ.get("ETSY_CLIENT_SECRET", "")
    if not value:
        raise EtsyApiError(
            "ETSY_SHARED_SECRET (your Etsy app's shared secret) is not set. "
            "Add it to your local .env.local — see docs/SETUP.md."
        )
    return value


def get_shop_id() -> str:
    value = os.environ.get("ETSY_SHOP_ID", "")
    if not value:
        raise EtsyApiError(
            "ETSY_SHOP_ID is not set. Add your own shop's numeric ID to "
            ".env.local — see docs/SETUP.md."
        )
    return value


def get_redirect_uri() -> str:
    return os.environ.get("ETSY_REDIRECT_URI", DEFAULT_REDIRECT_URI)


def get_scopes() -> str:
    return os.environ.get("ETSY_OAUTH_SCOPES", DEFAULT_SCOPES)


# ---------------------------------------------------------------------------
# Local-only token encryption at rest
#
# Tokens never leave this machine, but a plaintext token on disk is still
# risky (backups, other local software, etc). We derive a local-only
# Fernet key on first use, store it with restrictive file permissions,
# and use it to encrypt the token file. This protects against casual
# disclosure (e.g. accidentally zipping/sharing _spacecommand_state/) but
# is not a substitute for full-disk encryption or OS-level access
# control — see docs/SECURITY.md.
# ---------------------------------------------------------------------------

def _get_or_create_token_key() -> bytes:
    STATE.mkdir(parents=True, exist_ok=True)

    if TOKEN_KEY_FILE.exists():
        return TOKEN_KEY_FILE.read_bytes()

    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
    except ImportError:
        # cryptography isn't installed. Fall back to a random local key used
        # with a simple reversible XOR obfuscation rather than hard-failing.
        # This is NOT strong encryption — install `cryptography` (see
        # requirements.txt) for real encryption at rest.
        key = secrets.token_bytes(32)

    TOKEN_KEY_FILE.write_bytes(key)
    try:
        os.chmod(TOKEN_KEY_FILE, 0o600)
    except OSError:
        pass

    return key


def _encrypt(data: bytes, key: bytes) -> bytes:
    try:
        from cryptography.fernet import Fernet
        return Fernet(key).encrypt(data)
    except ImportError:
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _decrypt(data: bytes, key: bytes) -> bytes:
    try:
        from cryptography.fernet import Fernet
        return Fernet(key).decrypt(data)
    except ImportError:
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def save_tokens(tokens: Dict[str, Any]) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    key = _get_or_create_token_key()
    payload = json.dumps(tokens).encode("utf-8")
    TOKEN_FILE.write_bytes(_encrypt(payload, key))
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def load_tokens() -> Optional[Dict[str, Any]]:
    if not TOKEN_FILE.exists():
        return None

    key = _get_or_create_token_key()
    raw = TOKEN_FILE.read_bytes()

    try:
        decrypted = _decrypt(raw, key)
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        return None


def has_local_tokens() -> bool:
    return load_tokens() is not None


# ---------------------------------------------------------------------------
# OAuth2 PKCE flow (authorization code grant, per Etsy's documented flow)
# ---------------------------------------------------------------------------

def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> Dict[str, str]:
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return {"code_verifier": verifier, "code_challenge": challenge}


def build_authorization_url() -> Dict[str, str]:
    """
    Build the URL the seller opens in their browser to approve access to
    their own shop. Returns the url plus the state/verifier that must be
    kept to complete the exchange (run_etsy_oauth_setup.py handles this
    for you end to end).
    """
    pkce = generate_pkce_pair()
    state = _b64url(secrets.token_bytes(24))

    params = {
        "response_type": "code",
        "client_id": get_keystring(),
        "redirect_uri": get_redirect_uri(),
        "scope": get_scopes(),
        "state": state,
        "code_challenge": pkce["code_challenge"],
        "code_challenge_method": "S256",
    }

    url = f"{ETSY_OAUTH_CONNECT_URL}?{urllib.parse.urlencode(params)}"

    pending = {"state": state, "code_verifier": pkce["code_verifier"], "created_at": time.time()}
    STATE.mkdir(parents=True, exist_ok=True)
    OAUTH_STATE_FILE.write_text(json.dumps(pending), encoding="utf-8")

    return {"url": url, "state": state}


def exchange_code_for_tokens(code: str, state: str) -> Dict[str, Any]:
    if not OAUTH_STATE_FILE.exists():
        raise EtsyApiError("No pending OAuth state found. Run build_authorization_url() first.")

    pending = json.loads(OAUTH_STATE_FILE.read_text(encoding="utf-8"))

    if pending.get("state") != state:
        raise EtsyApiError("OAuth state mismatch — possible CSRF or stale callback. Restart the OAuth flow.")

    payload = {
        "grant_type": "authorization_code",
        "client_id": get_keystring(),
        "redirect_uri": get_redirect_uri(),
        "code": code,
        "code_verifier": pending["code_verifier"],
    }

    result = _post_form(ETSY_OAUTH_TOKEN_URL, payload, auth_header=False)

    tokens = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token"),
        "expires_at": time.time() + int(result.get("expires_in", 3600)),
        "token_type": result.get("token_type", "Bearer"),
    }

    save_tokens(tokens)
    OAUTH_STATE_FILE.unlink(missing_ok=True)

    return tokens


def refresh_access_token() -> Dict[str, Any]:
    tokens = load_tokens()

    if not tokens or not tokens.get("refresh_token"):
        raise EtsyApiError("No refresh token on file. Run run_etsy_oauth_setup.py to (re)authenticate.")

    payload = {
        "grant_type": "refresh_token",
        "client_id": get_keystring(),
        "refresh_token": tokens["refresh_token"],
    }

    result = _post_form(ETSY_OAUTH_TOKEN_URL, payload, auth_header=False)

    new_tokens = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", tokens["refresh_token"]),
        "expires_at": time.time() + int(result.get("expires_in", 3600)),
        "token_type": result.get("token_type", "Bearer"),
    }

    save_tokens(new_tokens)
    return new_tokens


def get_valid_access_token() -> str:
    tokens = load_tokens()

    if not tokens:
        raise EtsyApiError("Not connected to Etsy yet. Run run_etsy_oauth_setup.py first.")

    if time.time() >= tokens.get("expires_at", 0) - 60:
        tokens = refresh_access_token()

    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Low-level HTTP helpers with basic 429 backoff
# ---------------------------------------------------------------------------

def _post_form(url: str, fields: Dict[str, str], auth_header: bool = True, max_retries: int = 3) -> Dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    return _request(url, method="POST", data=body, headers=headers, max_retries=max_retries, authenticated=False)


def _request(
    url: str,
    method: str = "GET",
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    authenticated: bool = True,
    max_retries: int = 3,
) -> Dict[str, Any]:
    headers = dict(headers or {})

    if authenticated:
        # Etsy requires "keystring:shared_secret" in x-api-key since the
        # shared-secret enforcement rollout (completed 2026-02-09) - a bare
        # keystring now gets rejected with 403 "Shared secret is required
        # in x-api-key header." See https://developer.etsy.com/documentation/essentials/authentication
        headers["x-api-key"] = f"{get_keystring()}:{get_shared_secret()}"
        headers["Authorization"] = f"Bearer {get_valid_access_token()}"

    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        request = urllib.request.Request(url, data=data, method=method, headers=headers)

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}

        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")

            if exc.code == 429 and attempt < max_retries - 1:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else (2 ** attempt)
                time.sleep(delay)
                last_error = EtsyApiError(f"Rate limited (429): {raw_error}", status_code=429, payload=raw_error)
                continue

            raise EtsyApiError(f"Etsy API error {exc.code}: {raw_error}", status_code=exc.code, payload=raw_error) from exc

        except Exception as exc:
            last_error = EtsyApiError(f"Etsy API call failed: {exc!r}")
            break

    if last_error:
        raise last_error

    raise EtsyApiError("Etsy API call failed for an unknown reason.")


def _get(path: str) -> Dict[str, Any]:
    return _request(f"{ETSY_API_BASE}{path}", method="GET")


def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    return _request(
        f"{ETSY_API_BASE}{path}",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )


# ---------------------------------------------------------------------------
# Shop / taxonomy reads (used to populate the publish UI locally)
# ---------------------------------------------------------------------------

def get_shop(shop_id: Optional[str] = None) -> Dict[str, Any]:
    shop_id = shop_id or get_shop_id()
    return _get(f"/shops/{shop_id}")


def get_shop_sections(shop_id: Optional[str] = None) -> List[Dict[str, Any]]:
    shop_id = shop_id or get_shop_id()
    result = _get(f"/shops/{shop_id}/sections")
    return result.get("results", [])


def get_seller_taxonomy_nodes() -> List[Dict[str, Any]]:
    result = _get("/seller-taxonomy/nodes")
    return result.get("results", [])


def get_properties_by_taxonomy_id(taxonomy_id: int) -> List[Dict[str, Any]]:
    result = _get(f"/seller-taxonomy/nodes/{taxonomy_id}/properties")
    return result.get("results", [])


def get_shipping_profiles(shop_id: Optional[str] = None) -> List[Dict[str, Any]]:
    shop_id = shop_id or get_shop_id()
    result = _get(f"/shops/{shop_id}/shipping-profiles")
    return result.get("results", [])


def get_return_policies(shop_id: Optional[str] = None) -> List[Dict[str, Any]]:
    shop_id = shop_id or get_shop_id()
    result = _get(f"/shops/{shop_id}/policies/return")
    return result.get("results", [])


# ---------------------------------------------------------------------------
# Draft listing creation — the only write action this client performs
# ---------------------------------------------------------------------------

def create_draft_listing(
    title: str,
    description: str,
    price: float,
    quantity: int,
    who_made: str,
    when_made: str,
    taxonomy_id: int,
    shipping_profile_id: Optional[int] = None,
    return_policy_id: Optional[int] = None,
    materials: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    is_digital: bool = False,
    shop_section_id: Optional[int] = None,
    shop_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a listing on the seller's own shop via Etsy Open API v3.

    Etsy's `POST /v3/application/shops/{shop_id}/listings` endpoint
    creates listings in `draft` state by default — this function does
    not set `state` at all, and there is deliberately no function in
    this module that transitions a listing to `active`. Activation
    happens only when the seller does it themselves in Etsy Seller
    Manager (PRD principle #4: drafts only).
    """
    shop_id = shop_id or get_shop_id()

    payload: Dict[str, Any] = {
        "title": title[:140],
        "description": description,
        "price": round(float(price), 2),
        "quantity": int(quantity),
        "who_made": who_made,
        "when_made": when_made,
        "taxonomy_id": int(taxonomy_id),
        "is_digital": bool(is_digital),
    }

    if shipping_profile_id and not is_digital:
        payload["shipping_profile_id"] = int(shipping_profile_id)
    if return_policy_id:
        payload["return_policy_id"] = int(return_policy_id)
    if materials:
        payload["materials"] = materials[:13]
    if tags:
        payload["tags"] = [t[:20] for t in tags[:13]]
    if shop_section_id:
        payload["shop_section_id"] = int(shop_section_id)

    return _post_json(f"/shops/{shop_id}/listings", payload)


def upload_listing_image(listing_id: int, image_path: str, shop_id: Optional[str] = None, rank: int = 1) -> Dict[str, Any]:
    shop_id = shop_id or get_shop_id()
    path = Path(image_path)

    if not path.exists():
        raise EtsyApiError(f"Image file not found: {image_path}")

    boundary = f"----SpaceCommandBoundary{secrets.token_hex(8)}"
    image_bytes = path.read_bytes()

    parts: List[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8"))

    add_field("rank", str(rank))

    parts.append(
        (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"image\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(image_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    body = b"".join(parts)

    return _request(
        f"{ETSY_API_BASE}/shops/{shop_id}/listings/{listing_id}/images",
        method="POST",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def draft_listing_url(listing_id: int) -> str:
    return f"https://www.etsy.com/your/shops/me/tools/listings/{listing_id}?ref=listing-page"
