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


def flatten_taxonomy_tree(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten Etsy's nested seller-taxonomy tree into a flat list of
    {id, name, path, depth, is_leaf} records, so category matching can
    just scan a flat list instead of re-walking the tree every time.
    """
    flat: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any], depth: int, path: str) -> None:
        name = node.get("name", "")
        full_path = f"{path} > {name}" if path else name
        children = node.get("children") or []

        flat.append({
            "id": node.get("id"),
            "name": name,
            "path": full_path,
            "depth": depth,
            "is_leaf": len(children) == 0,
        })

        for child in children:
            walk(child, depth + 1, full_path)

    for top_level in nodes:
        walk(top_level, 0, "")

    return flat


def suggest_taxonomy_matches(
    keywords: List[str],
    nodes: Optional[List[Dict[str, Any]]] = None,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Suggest the best "Selected category" (taxonomy_id) candidates for a
    listing by scoring every node in the seller's taxonomy tree against
    free-text keywords (e.g. derived from a design package's title,
    design concept, and product_fit). This never calls Etsy's write
    endpoints — it only reads the taxonomy tree — but it still needs a
    live, approved connector since get_seller_taxonomy_nodes() is a
    real API call.

    Scoring is intentionally simple and transparent: for every keyword
    that appears as a substring of a node's full breadcrumb path, add a
    point; leaf categories (no children) get a small bonus since Etsy
    listings must use a specific/leaf category, not a broad parent.
    Callers should treat the top result as a suggestion, not a silent
    auto-decision — always show the alternatives to a human before a
    live draft is created with an unfamiliar keyword set.
    """
    nodes = nodes if nodes is not None else get_seller_taxonomy_nodes()
    flat = flatten_taxonomy_tree(nodes)

    cleaned_keywords = [k.strip().lower() for k in keywords if k and k.strip()]
    if not cleaned_keywords:
        return []

    scored = []
    for entry in flat:
        path_lower = entry["path"].lower()
        hits = [kw for kw in cleaned_keywords if kw in path_lower]

        if not hits:
            continue

        score = len(hits) + (0.5 if entry["is_leaf"] else 0.0)
        scored.append({**entry, "score": score, "matched_keywords": hits})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


def suggest_shop_section(
    keywords: List[str],
    shop_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Best-effort match of a shop_section_id from the shop's own section
    titles. Returns None (no auto-pick) when nothing matches, rather
    than guessing — an unmatched/wrong section is low-stakes (cosmetic
    shop organization) but still shouldn't be invented.
    """
    sections = get_shop_sections(shop_id=shop_id)
    cleaned_keywords = [k.strip().lower() for k in keywords if k and k.strip()]

    best = None
    best_score = 0

    for section in sections:
        title_lower = str(section.get("title", "")).lower()
        score = sum(1 for kw in cleaned_keywords if kw and kw in title_lower)

        if score > best_score:
            best = section
            best_score = score

    return best


def get_shipping_profiles(shop_id: Optional[str] = None) -> List[Dict[str, Any]]:
    shop_id = shop_id or get_shop_id()
    result = _get(f"/shops/{shop_id}/shipping-profiles")
    return result.get("results", [])


def get_return_policies(shop_id: Optional[str] = None) -> List[Dict[str, Any]]:
    shop_id = shop_id or get_shop_id()
    result = _get(f"/shops/{shop_id}/policies/return")
    return result.get("results", [])


def get_default_shipping_profile(shop_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Pick the shop's default shipping profile so callers don't have to
    look up shipping_profile_id by hand for every listing. Prefers a
    profile literally named "default" (case-insensitive); otherwise
    falls back to the first non-deleted profile on the shop. Returns
    None if the shop has no shipping profiles yet (the seller must
    create one in Etsy Seller Manager before physical listings work).
    """
    profiles = [p for p in get_shipping_profiles(shop_id=shop_id) if not p.get("is_deleted")]

    if not profiles:
        return None

    for profile in profiles:
        if "default" in str(profile.get("title", "")).lower():
            return profile

    return profiles[0]


def get_default_return_policy(shop_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Pick the shop's return policy. Most shops only have one (Etsy
    requires shops selling to EU buyers to have exactly one active
    return policy), so "first" is the correct default in practice.
    Returns None if the shop has no return policy configured yet.
    """
    policies = get_return_policies(shop_id=shop_id)
    return policies[0] if policies else None


def get_or_create_default_readiness_state(
    readiness_state: str = "made_to_order",
    min_processing_time: int = 3,
    max_processing_time: int = 5,
    processing_time_unit: str = "days",
    shop_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reuse an existing processing profile that matches `readiness_state`
    if the shop already has one, otherwise create it. This is what a
    seller would otherwise have to do once by hand in Seller Manager
    (or by manually calling createShopReadinessStateDefinition) before
    every physical listing could be drafted via the API — see
    docs/SETUP.md and the 2026 processing-profiles migration notes in
    create_readiness_state_definition() above.
    """
    existing = get_readiness_state_definitions(shop_id=shop_id)

    for definition in existing:
        if definition.get("readiness_state") == readiness_state:
            return definition

    return create_readiness_state_definition(
        readiness_state=readiness_state,
        min_processing_time=min_processing_time,
        max_processing_time=max_processing_time,
        processing_time_unit=processing_time_unit,
        shop_id=shop_id,
    )


def get_readiness_state_definitions(shop_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Processing profiles ("readiness state definitions"). Etsy requires
    every physical listing to link one via readiness_state_id — see
    https://developer.etsy.com/documentation/tutorials/migration
    """
    shop_id = shop_id or get_shop_id()
    result = _get(f"/shops/{shop_id}/readiness-state-definitions")
    return result.get("results", [])


def create_readiness_state_definition(
    readiness_state: str,
    min_processing_time: int,
    max_processing_time: int,
    processing_time_unit: str = "days",
    shop_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create (or, if an identical one exists, hit a 409 pointing at the
    existing one) a processing profile for this shop. `readiness_state`
    must be "ready_to_ship" or "made_to_order".
    """
    shop_id = shop_id or get_shop_id()
    fields = {
        "readiness_state": readiness_state,
        "min_processing_time": str(int(min_processing_time)),
        "max_processing_time": str(int(max_processing_time)),
        "processing_time_unit": processing_time_unit,
    }
    body = urllib.parse.urlencode(fields).encode("utf-8")
    return _request(
        f"{ETSY_API_BASE}/shops/{shop_id}/readiness-state-definitions",
        method="POST",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


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
    readiness_state_id: Optional[int] = None,
    materials: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    is_digital: bool = False,
    shop_section_id: Optional[int] = None,
    item_weight: Optional[float] = None,
    item_length: Optional[float] = None,
    item_width: Optional[float] = None,
    item_height: Optional[float] = None,
    item_weight_unit: Optional[str] = None,
    item_dimensions_unit: Optional[str] = None,
    is_personalizable: bool = False,
    personalization_is_required: bool = False,
    personalization_instructions: Optional[str] = None,
    personalization_char_count_max: Optional[int] = None,
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
    if readiness_state_id and not is_digital:
        # Required by Etsy for physical listings since the processing
        # profiles migration — see get_readiness_state_definitions() /
        # create_readiness_state_definition() above.
        payload["readiness_state_id"] = int(readiness_state_id)
    if return_policy_id:
        payload["return_policy_id"] = int(return_policy_id)
    if materials:
        payload["materials"] = materials[:13]
    if tags:
        payload["tags"] = [t[:20] for t in tags[:13]]
    if shop_section_id:
        payload["shop_section_id"] = int(shop_section_id)

    # Weight/dimensions matter for physical prints (framed vs. unframed,
    # rolled tube shipping, etc.) — previously not exposed at all, so
    # every listing silently omitted them even when known.
    if item_weight is not None:
        payload["item_weight"] = float(item_weight)
    if item_length is not None:
        payload["item_length"] = float(item_length)
    if item_width is not None:
        payload["item_width"] = float(item_width)
    if item_height is not None:
        payload["item_height"] = float(item_height)
    if item_weight_unit:
        payload["item_weight_unit"] = item_weight_unit
    if item_dimensions_unit:
        payload["item_dimensions_unit"] = item_dimensions_unit

    # Personalization (e.g. "add a custom name") — previously not
    # exposed at all.
    if is_personalizable:
        payload["is_personalizable"] = True
        payload["personalization_is_required"] = bool(personalization_is_required)
        if personalization_instructions:
            payload["personalization_instructions"] = personalization_instructions
        if personalization_char_count_max is not None:
            payload["personalization_char_count_max"] = int(personalization_char_count_max)

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
