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

CRIME_TOPICS = '("drug bust" OR "drugs seized" OR "street value" OR "hijacking" OR "hijacked" OR "BOLO" OR "cash-in-transit" OR "CIT heist" OR "CIT robbery" OR "cash van")'

SOURCE_FEEDS: list[tuple[str, str]] = [
    ("x_social", f'site:x.com {CRIME_TOPICS} (SAPS OR Gauteng OR KZN OR Durban OR Johannesburg OR "Cape Town" OR Pretoria OR Abramjee OR ReactionUnitSA)'),
    ("sabc_news", f'site:sabcnews.com {CRIME_TOPICS}'),
    ("ecr_news_traffic", f'site:ecr.co.za ({CRIME_TOPICS} OR traffic OR highway OR N2 OR N3 OR M4 OR hijacking OR heist)'),
    ("north_coast_courier", f'site:northcoastcourier.co.za ({CRIME_TOPICS} OR crime OR hijacking OR arrest OR police OR Ballito OR Tongaat OR Umhlanga)'),
    ("phoenix_tabloid", f'site:phoenixtabloid.co.za ({CRIME_TOPICS} OR crime OR hijacking OR police OR Phoenix OR Durban)'),
    ("pretoria_news", f'(site:iol.co.za/pretoria-news OR "Pretoria News") {CRIME_TOPICS}'),
    ("iol_news", f'site:iol.co.za {CRIME_TOPICS}'),
    ("sa_newspapers", f'{CRIME_TOPICS} ("South Africa" OR SAPS) (site:news24.com OR site:timeslive.co.za OR site:citizen.co.za OR site:ewn.co.za OR site:sowetanlive.co.za OR site:dispatchlive.co.za OR site:heraldlive.co.za OR site:capetimes.co.za OR site:dailynews.co.za OR site:witness.co.za OR site:mg.co.za)'),
]

DIRECT_TARGET_PAGES: list[tuple[str, str]] = [
    ("sabc_news", "https://www.sabcnews.com/sabcnews/"),
    ("north_coast_courier", "https://www.northcoastcourier.co.za/"),
    ("phoenix_tabloid", "https://phoenixtabloid.co.za/"),
    ("arrive_alive", "https://www.arrivealive.co.za/"),
]

SAPS_SEARCH_URL = "https://www.saps.gov.za/newsroom/news_search.php"
SAPS_BASE_URL = "https://www.saps.gov.za/newsroom/"

INCIDENT_KEYWORDS = (
    "hijack",
    "hijacked",
    "bolo",
    "stolen vehicle",
    "cash-in-transit",
    "cash in transit",
    "cit heist",
    "cit robbery",
    "armoured",
    "cash van",
    "drug bust",
    "drugs seized",
    "cocaine",
    "heroin",
    "mandrax",
    "methamphetamine",
    "tik",
    "crystal meth",
    "dagga",
    "narcotics",
    "street value",
    "drug lab",
    "drug laboratory",
)

BAD_IMAGE_TOKENS = (
    "logo",
    "banner",
    "partner",
    "icon",
    "advert",
    "avatar",
    "sprite",
    "placeholder",
    "facebook",
    "twitter",
    "whatsapp",
    "instagram",
    "youtube",
    "sabc-logo",
    "ecr-logo",
    "iol-logo",
)


def _is_valid_photo_url(url: str | None) -> bool:
    if not url:
        return False
    low = url.lower()
    if low.startswith("data:"):
        return False
    if any(tok in low for tok in BAD_IMAGE_TOKENS):
        return False
    return True


def _parse_rss_date(pub_date: str) -> str:
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")


def _extract_date_from_text(text: str) -> str:
    iso_match = re.search(r"\b(202[56])[-/](\d{2})[-/](\d{2})\b", text)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}-{iso_match.group(3)}"

    named_match = re.search(
        r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(202[56])\b",
        text,
        re.I,
    )
    if named_match:
        try:
            dt = datetime.strptime(
                f"{named_match.group(1)} {named_match.group(2)[:3]} {named_match.group(3)}",
                "%d %b %Y",
            )
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    return datetime.utcnow().strftime("%Y-%m-%d")


def _clean_summary(headline: str, body: str) -> str:
    cleaned_body = re.sub(r"\s+", " ", body).strip()
    if not cleaned_body:
        return headline.strip()
    # Avoid repeating the exact headline twice at the start of the summary
    norm_head = re.sub(r"[^a-z0-9]+", " ", headline.lower()).strip()
    norm_body = re.sub(r"[^a-z0-9]+", " ", cleaned_body[: len(headline) + 30].lower()).strip()
    if norm_head and norm_head in norm_body:
        parts = re.split(r"(?<=[.!?])\s+", cleaned_body)
        if len(parts) > 1:
            cleaned_body = " ".join(parts[1:])
    return cleaned_body[:240].strip() or headline.strip()


def crawl_google_rss() -> list[dict[str, Any]]:
    """Fetch X/Twitter headers and South African news/radio/newspaper headlines via Google News RSS."""
    posts: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for tag, query in SOURCE_FEEDS:
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-ZA&gl=ZA&ceid=ZA:en"
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
        except Exception as exc:
            print(f"[WARN] Google RSS ({tag}) failed: {exc}")
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
            short_desc = _clean_summary(title, desc_text)
            combined_text = f"{title}. {short_desc}".strip()

            source_id = f"{tag}_" + hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]
            posts.append(
                {
                    "source_id": source_id,
                    "reported_at": reported_at,
                    "text": combined_text,
                    "source_url": link,
                    "image_url": None,
                }
            )
    return posts


def _extract_images_from_soup(soup: BeautifulSoup, base_url: str) -> list[str]:
    found: list[str] = []

    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        cand = urljoin(base_url, og_img["content"].strip())
        if _is_valid_photo_url(cand):
            found.append(cand)

    for img in soup.find_all("img", src=True):
        src = img["src"].strip()
        cand = urljoin(base_url, src)
        if not _is_valid_photo_url(cand):
            continue
        if cand not in found:
            found.append(cand)
        if len(found) >= 3:
            break

    return found


def _fetch_article_body_and_images(article_url: str) -> tuple[str, list[str]]:
    """Fetch concise article text and up to 3 image URLs."""
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=15, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        images = _extract_images_from_soup(soup, article_url)
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 35]
        body = " ".join(paragraphs[:4])
        return body, images
    except Exception:
        return "", []


def crawl_media_outlets(max_per_page: int = 8) -> list[dict[str, Any]]:
    """Scrape SABC News, North Coast Courier, Phoenix Tabloid & Arrive Alive with images."""
    posts: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for source_tag, page_url in DIRECT_TARGET_PAGES:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=18, verify=False)
            resp.raise_for_status()
        except Exception as exc:
            print(f"[WARN] Direct crawl ({source_tag}) failed on {page_url}: {exc}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        candidates: list[tuple[str, str, str | None]] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                continue

            full_url = urljoin(page_url, href)
            if full_url in seen_urls:
                continue

            headline = anchor.get_text(" ", strip=True)
            context_text = anchor.parent.get_text(" ", strip=True) if anchor.parent else headline
            haystack = f"{headline} {context_text}".lower()

            if len(headline) < 14 or not any(kw in haystack for kw in INCIDENT_KEYWORDS):
                continue

            seen_urls.add(full_url)

            thumb = None
            img_tag = anchor.find("img", src=True) or (anchor.parent.find("img", src=True) if anchor.parent else None)
            if img_tag:
                cand_thumb = urljoin(full_url, img_tag["src"].strip())
                if _is_valid_photo_url(cand_thumb):
                    thumb = cand_thumb

            candidates.append((headline, full_url, thumb))

        for headline, full_url, thumb in candidates[:max_per_page]:
            body, page_imgs = _fetch_article_body_and_images(full_url)
            reported_at = _extract_date_from_text(f"{headline} {body}")
            if reported_at < MIN_DATE:
                continue

            gallery = list(page_imgs)
            if thumb and thumb not in gallery:
                gallery.insert(0, thumb)

            short_summary = _clean_summary(headline, body)
            combined_text = f"{headline}. {short_summary}".strip()
            source_id = f"{source_tag}_" + hashlib.sha256(full_url.encode("utf-8")).hexdigest()[:16]
            posts.append(
                {
                    "source_id": source_id,
                    "reported_at": reported_at,
                    "text": combined_text,
                    "source_url": full_url,
                    "image_url": gallery[0] if gallery else None,
                    "gallery": gallery[:3],
                }
            )

    return posts


def _fetch_saps_detail(detail_url: str) -> tuple[str, list[str]]:
    """Fetch concise SAPS media statement body and photo URLs."""
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        images: list[str] = []
        skip_saps = ("crest", "badge", "footer", "header", "nav", "menu", "button", "flag", "gov", "search", "print", "email")
        for img in soup.find_all("img", src=True):
            src = img["src"].strip()
            full_img = urljoin(detail_url, src)
            low = full_img.lower()
            if not any(ext in low for ext in (".jpg", ".jpeg", ".png", ".webp")):
                continue
            if any(tok in low for tok in skip_saps):
                continue
            if _is_valid_photo_url(full_img) and full_img not in images:
                images.append(full_img)
            if len(images) >= 3:
                break

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
        body = " ".join(paragraphs[:4])
        return body, images
    except Exception:
        return "", []


def crawl_saps_statements(max_items: int = 30) -> list[dict[str, Any]]:
    """Scrape recent official SAPS Media Statements >= 2025-07-06."""
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
        if "selnewsdetail.php" not in href:
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
        body, imgs = _fetch_saps_detail(full_url)
        short_summary = _clean_summary(headline, body)
        combined_text = f"{headline}. {short_summary}".strip()
        source_id = "saps_" + hashlib.sha256(full_url.encode("utf-8")).hexdigest()[:16]
        posts.append(
            {
                "source_id": source_id,
                "reported_at": reported_at,
                "text": combined_text,
                "source_url": full_url,
                "image_url": imgs[0] if imgs else None,
                "gallery": imgs[:3],
            }
        )

    return posts


if __name__ == "__main__":
    rss_hits = crawl_google_rss()
    print(f"[OK] Google RSS feeds returned {len(rss_hits)} candidate posts.")
    media_hits = crawl_media_outlets(max_per_page=5)
    print(f"[OK] Direct media outlets returned {len(media_hits)} candidate posts.")
    saps_hits = crawl_saps_statements(max_items=10)
    print(f"[OK] SAPS Media Statements returned {len(saps_hits)} candidate posts.")
