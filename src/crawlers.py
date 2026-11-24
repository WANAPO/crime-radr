from datetime import datetime
from email.utils import parsedate_to_datetime
import hashlib
import re
from typing import Any
from urllib.parse import quote_plus, urljoin
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import requests
import urllib3
from src.db import MIN_DATE

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}

# Expanded Google News RSS queries: X/Twitter accounts, SA news sites, videos, drug labs/dens, stolen cars
GOOGLE_RSS_QUERIES = [
    # 1. X/Twitter hijackings, stolen/missing vehicles & BOLO alerts from known SA accounts
    'site:x.com ("hijacking" OR "hijacked" OR "stolen vehicle" OR "stolen car" OR "missing vehicle" OR "BOLO" OR "vehicle recovered") '
    '(SAPoliceService OR Abramjee OR stolencarRSA OR ReactionUnitSA OR Tracker_SA OR CartrackZA OR NetstarSA OR BlueSecurityDBN OR MarshallSecDBN OR VisionTactical OR TMPDSafety OR JoburgMPD)',
    # 2. SA news sites covering hijackings, chop shops & stolen vehicles
    '("hijacking" OR "hijacked" OR "stolen vehicle" OR "chop shop" OR "vehicle syndicate") ("South Africa" OR SAPS OR Gauteng OR KZN OR Durban OR Johannesburg OR "Cape Town") '
    '(site:news24.com OR site:timeslive.co.za OR site:citizen.co.za OR site:iol.co.za OR site:ewn.co.za OR site:sabcnews.com OR site:sanews.gov.za)',
    # 3. X/Twitter & News on Drug Labs, Drug Dens & Major Drug Busts
    '("drug bust" OR "drug lab" OR "drug laboratory" OR "clandestine lab" OR "drug den" OR "drugs seized" OR "street value") '
    '("South Africa" OR SAPS OR Hawks OR Gauteng OR KZN OR Durban OR Johannesburg OR "Cape Town")',
    # 4. CIT Heists, Money Truck Robberies & Video Footage
    '("cash-in-transit" OR "CIT heist" OR "CIT robbery" OR "money truck" OR "cash van") '
    '("South Africa" OR SAPS OR Abramjee OR WATCH OR video OR footage)',
    # 5. Direct YouTube video reports on SA CIT heists & money truck robberies
    'site:youtube.com ("cash-in-transit" OR "CIT heist" OR "CIT robbery" OR "money truck") ("South Africa" OR SAPS OR KZN OR Gauteng)',
]

SAPS_SEARCH_URL = "https://www.saps.gov.za/newsroom/news_search.php"
SAPS_BASE_URL = "https://www.saps.gov.za/newsroom/"


def _parse_rss_date(pub_date: str) -> str:
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def _extract_article_media(url: str) -> tuple[list[str], str | None]:
    """Attempt to extract gallery images and video embeds from non-X news pages."""
    if "x.com/" in url or "twitter.com/" in url or "news.google.com/" in url:
        return [], None
    if "youtube.com/" in url or "youtu.be/" in url:
        return [], url

    try:
        verify_ssl = ".gov.za" not in url.lower()
        resp = requests.get(url, headers=HEADERS, timeout=10, verify=verify_ssl)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        gallery: list[str] = []
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            gallery.append(urljoin(url, og_img["content"]))

        for img in soup.find_all("img", src=True):
            full_src = urljoin(url, img["src"])
            low = full_src.lower()
            if any(ext in low for ext in (".jpg", ".jpeg", ".png", ".webp")):
                if not any(skip in low for skip in ("logo", "icon", "avatar", "banner", "spinner", "pixel")):
                    if full_src not in gallery:
                        gallery.append(full_src)
            if len(gallery) >= 5:
                break

        video_url = None
        for iframe in soup.find_all("iframe", src=True):
            if "youtube.com" in iframe["src"] or "youtu.be" in iframe["src"]:
                video_url = iframe["src"]
                break

        return gallery, video_url
    except Exception:
        return [], None


def crawl_google_rss() -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for query in GOOGLE_RSS_QUERIES:
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-ZA&gl=ZA&ceid=ZA:en"
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
        except Exception as exc:
            print(f"[WARN] Google RSS query failed: {exc}")
            continue

        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            desc_el = item.find("description")

            if title_el is None or link_el is None:
                continue

            title = (title_el.text or "").strip()
            link = (link_el.text or "").strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)

            reported_at = _parse_rss_date(pub_el.text or "") if pub_el is not None else ""
            if reported_at < MIN_DATE:
                continue

            desc_html = desc_el.text or "" if desc_el is not None else ""
            desc_text = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
            combined_text = f"{title}. {desc_text}".strip()

            video_url = link if ("youtube.com" in link or "youtu.be" in link) else None
            source_id = "grss_" + hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]

            posts.append(
                {
                    "source_id": source_id,
                    "reported_at": reported_at,
                    "text": combined_text,
                    "source_url": link,
                    "image_url": None,
                    "gallery": [],
                    "video_url": video_url,
                }
            )
    return posts


def _fetch_saps_detail(detail_url: str) -> tuple[str, list[str], str | None]:
    """Fetch full SAPS media statement body, image gallery, and any video link."""
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        gallery: list[str] = []
        for img in soup.find_all("img", src=True):
            src = img["src"]
            low = src.lower()
            if any(token in low for token in ("news", "media", "upload", "seiz", "drug", "photo", ".jpg", ".jpeg", ".png")):
                if not any(skip in low for skip in ("logo", "banner", "icon", "header", "footer")):
                    full_img = src if src.startswith("http") else f"https://www.saps.gov.za/{src.lstrip('/')}"
                    if full_img not in gallery:
                        gallery.append(full_img)

        video_url = None
        for a in soup.find_all("a", href=True):
            if "youtube.com" in a["href"] or "youtu.be" in a["href"]:
                video_url = a["href"]
                break

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 35]
        body = " ".join(paragraphs[:8])
        return body, gallery[:6], video_url
    except Exception:
        return "", [], None


def crawl_saps_statements(max_items: int = 45) -> list[dict[str, Any]]:
    """Scrape recent official SAPS Media Statements >= 2025-07-06 with image galleries."""
    posts: list[dict[str, Any]] = []
    try:
        resp = requests.get(SAPS_SEARCH_URL, headers=HEADERS, timeout=20, verify=False)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[WARN] SAPS statements fetch failed: {exc}")
        return posts

    soup = BeautifulSoup(resp.text, "html.parser")
    candidates = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "selnewsdetail.php" not in href and "msspeechdetail.php" not in href:
            continue

        headline = link.get_text(" ", strip=True)
        if not headline:
            continue

        parent_text = link.parent.get_text(" ", strip=True) if link.parent else ""
        date_match = re.search(r"(\d{4})[/\-](\d{2})[/\-](\d{2})", parent_text)
        reported_at = (
            f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
            if date_match
            else datetime.utcnow().strftime("%Y-%m-%d")
        )
        if reported_at < MIN_DATE:
            continue

        full_url = href if href.startswith("http") else f"{SAPS_BASE_URL}{href.lstrip('/')}"
        candidates.append((headline, reported_at, full_url))

    for headline, reported_at, full_url in candidates[:max_items]:
        body, gallery, video_url = _fetch_saps_detail(full_url)
        combined_text = f"{headline}. {body}".strip()
        source_id = "saps_" + hashlib.sha256(full_url.encode("utf-8")).hexdigest()[:16]
        posts.append(
            {
                "source_id": source_id,
                "reported_at": reported_at,
                "text": combined_text,
                "source_url": full_url,
                "image_url": gallery[0] if gallery else None,
                "gallery": gallery,
                "video_url": video_url,
            }
        )

    return posts


if __name__ == "__main__":
    rss_hits = crawl_google_rss()
    print(f"[OK] Google RSS returned {len(rss_hits)} candidate posts.")
    saps_hits = crawl_saps_statements(max_items=15)
    print(f"[OK] SAPS Media Statements returned {len(saps_hits)} candidate posts.")
