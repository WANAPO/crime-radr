import json
import os
from pathlib import Path
from typing import Any
import requests
from src.db import MIN_DATE, init_db, upsert_incident
from src.parser import parse_post

X_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
MANUAL_FEED_PATH = Path("data/manual_feed.json")

X_QUERY = (
    '("drug bust" OR "drugs seized" OR "street value" OR '
    '"hijacking" OR "BOLO" OR "hijacked" OR '
    '"cash-in-transit" OR "CIT heist" OR "CIT robbery") '
    '(SAPS OR "South Africa" OR Gauteng OR KZN OR Durban OR Johannesburg OR "Cape Town") '
    '-is:retweet'
)


def fetch_from_x_api(bearer_token: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": X_QUERY,
        "max_results": 50,
        "tweet.fields": "created_at,attachments",
        "expansions": "attachments.media_keys",
        "media.fields": "url,preview_image_url",
    }
    resp = requests.get(X_SEARCH_URL, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    media_map: dict[str, str] = {}
    for media in payload.get("includes", {}).get("media", []):
        m_url = media.get("url") or media.get("preview_image_url")
        if m_url:
            media_map[media["media_key"]] = m_url

    raw_posts = []
    for tweet in payload.get("data", []):
        tid = tweet["id"]
        created = tweet.get("created_at", "")[:10]
        if created < MIN_DATE:
            continue

        image_url = None
        media_keys = tweet.get("attachments", {}).get("media_keys", [])
        if media_keys and media_keys[0] in media_map:
            image_url = media_map[media_keys[0]]

        raw_posts.append(
            {
                "source_id": f"x_{tid}",
                "reported_at": created,
                "text": tweet["text"],
                "source_url": f"https://x.com/i/web/status/{tid}",
                "image_url": image_url,
            }
        )
    return raw_posts


def fetch_from_local_feed() -> list[dict[str, Any]]:
    if not MANUAL_FEED_PATH.exists():
        return []
    with open(MANUAL_FEED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_ingestion() -> int:
    init_db()
    raw_posts: list[dict[str, Any]] = []

    token = os.getenv("X_BEARER_TOKEN", "").strip()
    if token:
        try:
            raw_posts.extend(fetch_from_x_api(token))
        except Exception as exc:
            print(f"[WARN] X API fetch failed: {exc}")

    raw_posts.extend(fetch_from_local_feed())

    saved = 0
    for post in raw_posts:
        parsed = parse_post(post)
        if parsed and upsert_incident(parsed):
            saved += 1
    return saved


if __name__ == "__main__":
    count = run_ingestion()
    print(f"[OK] Ingested/updated {count} incidents.")
