import argparse
import html
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from research_connector_registry import get_connector, connector_is_available


ROOT = Path.home() / "Documents" / "Instance" / "SpaceCommand"
STATE = ROOT / "_spacecommand_state"

SNAPSHOTS_FILE = STATE / "public_source_snapshots.json"


def now_stamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path, fallback):
    if not path.exists():
        return fallback

    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()

    if not text:
        return fallback

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def next_id(prefix, records):
    highest = 0

    for item in records:
        raw = str(item.get("id", ""))

        if raw.startswith(prefix + "-"):
            try:
                highest = max(highest, int(raw.split("-")[1]))
            except Exception:
                pass

    return f"{prefix}-{highest + 1:04d}"


def clean_html(raw_html):
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)

    title_match = re.search(r"(?is)<title.*?>(.*?)</title>", text)
    title = ""

    if title_match:
        title = html.unescape(re.sub(r"\s+", " ", title_match.group(1))).strip()

    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return title, text


def fetch_public_url(url, timeout_seconds=20):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "SpaceCommandLocalResearch/0.1 public-read-only",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        status_code = getattr(response, "status", 200)
        content_type = response.headers.get("content-type", "")
        raw_bytes = response.read()

    raw_text = raw_bytes.decode("utf-8", errors="replace")

    return {
        "status_code": status_code,
        "content_type": content_type,
        "raw_text": raw_text,
    }


def create_snapshot(connector_id, url, query, theme, time_window, max_chars):
    connector = get_connector(connector_id)

    snapshots = load_json(SNAPSHOTS_FILE, [])

    if connector is None:
        snapshot = {
            "id": next_id("SNAP", snapshots),
            "type": "public_source_snapshot",
            "status": "blocked_unknown_connector",
            "success": False,
            "connector_id": connector_id,
            "url": url,
            "query": query,
            "theme": theme,
            "time_window": time_window,
            "notes": "Unknown connector.",
            "created_at": now_stamp(),
        }

        snapshots.append(snapshot)
        save_json(SNAPSHOTS_FILE, snapshots)
        return snapshot

    if not connector_is_available(connector):
        snapshot = {
            "id": next_id("SNAP", snapshots),
            "type": "public_source_snapshot",
            "status": "blocked_connector_not_public_safe",
            "success": False,
            "connector_id": connector_id,
            "connector_name": connector.get("name"),
            "permission_level": connector.get("permission_level"),
            "url": url,
            "query": query,
            "theme": theme,
            "time_window": time_window,
            "notes": "Connector is not available for local-safe public fetching.",
            "created_at": now_stamp(),
        }

        snapshots.append(snapshot)
        save_json(SNAPSHOTS_FILE, snapshots)
        return snapshot

    try:
        fetched = fetch_public_url(url)
        title, clean_text = clean_html(fetched["raw_text"])

        snapshot = {
            "id": next_id("SNAP", snapshots),
            "type": "public_source_snapshot",
            "status": "fetched_public_source",
            "success": True,
            "connector_id": connector_id,
            "connector_name": connector.get("name"),
            "source_type": connector.get("source_type"),
            "permission_level": connector.get("permission_level"),
            "url": url,
            "query": query,
            "theme": theme,
            "time_window": time_window,
            "status_code": fetched["status_code"],
            "content_type": fetched["content_type"],
            "source_title": title,
            "text_char_count": len(clean_text),
            "text_excerpt": clean_text[:max_chars],
            "created_at": now_stamp(),
        }

    except Exception as exc:
        snapshot = {
            "id": next_id("SNAP", snapshots),
            "type": "public_source_snapshot",
            "status": "fetch_failed",
            "success": False,
            "connector_id": connector_id,
            "connector_name": connector.get("name"),
            "permission_level": connector.get("permission_level"),
            "url": url,
            "query": query,
            "theme": theme,
            "time_window": time_window,
            "error": repr(exc),
            "created_at": now_stamp(),
        }

    snapshots.append(snapshot)
    save_json(SNAPSHOTS_FILE, snapshots)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Fetch a public source for Nova local-safe research.")
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--theme", required=True)
    parser.add_argument("--time-window", choices=["daily", "weekly", "monthly", "unknown"], default="unknown")
    parser.add_argument("--max-chars", type=int, default=6000)

    args = parser.parse_args()

    snapshot = create_snapshot(
        connector_id=args.connector_id,
        url=args.url,
        query=args.query,
        theme=args.theme,
        time_window=args.time_window,
        max_chars=args.max_chars,
    )

    print()
    print("# Public Source Snapshot")
    print()
    print(f"ID: {snapshot['id']}")
    print(f"Status: {snapshot['status']}")
    print(f"Success: {snapshot['success']}")
    print(f"Connector: {snapshot.get('connector_id')}")
    print(f"URL: {snapshot.get('url')}")

    if snapshot.get("source_title"):
        print(f"Source Title: {snapshot.get('source_title')}")

    if snapshot.get("error"):
        print(f"Error: {snapshot.get('error')}")

    print()


if __name__ == "__main__":
    main()
