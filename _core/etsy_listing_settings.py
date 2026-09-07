"""
Etsy listing settings preparation — auto-fills the Etsy "Selected
category" (taxonomy_id) plus the other shop-level settings every
physical Etsy draft listing needs (shipping profile, return policy,
processing/"readiness state" profile, and — where a good match
exists — a shop section).

Before this module existed, every one of these had to be looked up by
hand (get_seller_taxonomy_nodes(), get_shipping_profiles(), etc.) and
passed as CLI flags to create_etsy_draft.py every single time. This
module turns that one-off manual lookup into a reusable, cached
"preparation" step:

  python prepare_etsy_listing_settings.py --design-package-id DESIGN-0001

...and create_etsy_draft.py will automatically use the cached result
for that design package unless the operator overrides a field on the
command line.

This module only makes *read* calls to Etsy (seller-taxonomy, shipping
profiles, return policies, shop sections) plus one narrow, idempotent
write — createShopReadinessStateDefinition — which just registers a
reusable processing-profile on the seller's own shop (not a listing).
It never creates or modifies a listing itself.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pipeline_contracts import (
    DESIGN_FILE,
    OPPORTUNITY_FILE,
    STATE,
    load_json,
    next_id,
    save_json,
)


ETSY_LISTING_SETTINGS_FILE = STATE / "etsy_listing_settings.json"


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_by_id(records: List[Dict[str, Any]], record_id: str) -> Optional[Dict[str, Any]]:
    for record in records:
        if record.get("id") == record_id:
            return record
    return None


def keywords_for_design_package(design_package_id: str) -> List[str]:
    """
    Build a free-text keyword list for taxonomy matching out of a
    design package and its parent opportunity card — title, design
    concept, product_fit tags, product_category, and design_style all
    carry real signal about what kind of physical product this is.
    """
    designs = load_json(DESIGN_FILE, [])
    design = find_by_id(designs, design_package_id)

    if not design:
        return []

    keywords: List[str] = []
    keywords.append(design.get("title", ""))
    keywords.append(design.get("design_concept", ""))
    keywords.extend(design.get("product_fit", []) or [])

    opportunities = load_json(OPPORTUNITY_FILE, [])
    opportunity = find_by_id(opportunities, design.get("opportunity_id", ""))

    if opportunity:
        keywords.append(opportunity.get("product_category", ""))
        keywords.append(opportunity.get("design_style", ""))
        keywords.extend(opportunity.get("product_fit", []) or [])

    # Split multi-word free text into individual words too, since a
    # taxonomy path like "Art & Collectibles > Prints > Etchings &
    # Engravings" won't literally contain a whole design-concept
    # sentence, but will contain words like "print" or "engraving".
    expanded: List[str] = []
    for phrase in keywords:
        if not phrase:
            continue
        expanded.append(phrase)
        expanded.extend(w.strip(",.;:()") for w in str(phrase).split() if len(w.strip(",.;:()")) > 3)

    # De-dupe while preserving order, drop over-generic stopword-ish tokens.
    seen = set()
    deduped = []
    stopwords = {"with", "from", "this", "that", "based", "print", "the", "design", "product"}
    for word in expanded:
        lowered = word.lower()
        if lowered in seen or lowered in stopwords:
            continue
        seen.add(lowered)
        deduped.append(word)

    return deduped


def get_cached_settings(design_package_id: str) -> Optional[Dict[str, Any]]:
    settings = load_json(ETSY_LISTING_SETTINGS_FILE, [])
    matches = [s for s in settings if s.get("design_package_id") == design_package_id]
    return matches[-1] if matches else None


def prepare_listing_settings(
    design_package_id: str,
    readiness_state: str = "made_to_order",
    min_processing_days: int = 3,
    max_processing_days: int = 5,
    extra_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Do the live Etsy lookups once and cache the result for this design
    package. Returns the saved settings record (also appended to
    etsy_listing_settings.json). Raises whatever etsy_api_client raises
    if the connector/token isn't set up — callers should have already
    checked that (see prepare_etsy_listing_settings.py for the CLI
    gate, matching the pattern used by publishing_dock.py).
    """
    import etsy_api_client as etsy  # noqa: PLC0415 - see publishing_dock.py for why this is a lazy import

    keywords = keywords_for_design_package(design_package_id)
    keywords.extend(extra_keywords or [])

    taxonomy_nodes = etsy.get_seller_taxonomy_nodes()
    taxonomy_matches = etsy.suggest_taxonomy_matches(keywords, nodes=taxonomy_nodes, top_n=5)
    top_taxonomy = taxonomy_matches[0] if taxonomy_matches else None

    shipping_profile = etsy.get_default_shipping_profile()
    return_policy = etsy.get_default_return_policy()
    readiness = etsy.get_or_create_default_readiness_state(
        readiness_state=readiness_state,
        min_processing_time=min_processing_days,
        max_processing_time=max_processing_days,
    )
    shop_section = etsy.suggest_shop_section(keywords)

    settings_list = load_json(ETSY_LISTING_SETTINGS_FILE, [])

    record = {
        "id": next_id("ETSYPREP", settings_list),
        "type": "etsy_listing_settings",
        "design_package_id": design_package_id,
        "keywords_used": keywords,
        "taxonomy_id": top_taxonomy["id"] if top_taxonomy else None,
        "taxonomy_path": top_taxonomy["path"] if top_taxonomy else None,
        "taxonomy_confidence": "auto_suggested_needs_human_review",
        "taxonomy_alternatives": [
            {"id": m["id"], "path": m["path"], "score": m["score"]} for m in taxonomy_matches[1:]
        ],
        "shipping_profile_id": shipping_profile.get("shipping_profile_id") if shipping_profile else None,
        "shipping_profile_title": shipping_profile.get("title") if shipping_profile else None,
        "return_policy_id": return_policy.get("return_policy_id") if return_policy else None,
        "readiness_state_id": readiness.get("readiness_state_id"),
        "readiness_state": readiness.get("readiness_state"),
        "shop_section_id": shop_section.get("shop_section_id") if shop_section else None,
        "shop_section_title": shop_section.get("title") if shop_section else None,
        "issues": [],
        "created_at": now_stamp(),
    }

    if not top_taxonomy:
        record["issues"].append("no_taxonomy_match_found_choose_manually")
    if not shipping_profile:
        record["issues"].append("shop_has_no_shipping_profiles_create_one_in_seller_manager")
    if not return_policy:
        record["issues"].append("shop_has_no_return_policy_create_one_in_seller_manager")

    settings_list.append(record)
    save_json(ETSY_LISTING_SETTINGS_FILE, settings_list)

    return record


def get_or_prepare_settings(
    design_package_id: str,
    force_refresh: bool = False,
    readiness_state: str = "made_to_order",
    min_processing_days: int = 3,
    max_processing_days: int = 5,
) -> Dict[str, Any]:
    if not force_refresh:
        cached = get_cached_settings(design_package_id)
        if cached:
            return cached

    return prepare_listing_settings(
        design_package_id=design_package_id,
        readiness_state=readiness_state,
        min_processing_days=min_processing_days,
        max_processing_days=max_processing_days,
    )
