import re
from typing import Any
from src.geocode import geocode_with_precision

DRUG_WORDS = (
    "drug bust",
    "drugs seized",
    "cocaine",
    "heroin",
    "mandrax",
    "methamphetamine",
    "crystal meth",
    "tik",
    "dagga",
    "narcotics",
    "drug lab",
    "drug laboratory",
    "street value",
)

HIJACK_WORDS = (
    "hijack",
    "hijacked",
    "bolo",
    "stolen vehicle",
    "carjacking",
)

CIT_WORDS = (
    "cash-in-transit",
    "cash in transit",
    "cit heist",
    "cit robbery",
    "armoured",
    "cash van",
)


def _classify_category(text_lower: str) -> str | None:
    if any(w in text_lower for w in CIT_WORDS):
        return "cit_robbery"
    if any(w in text_lower for w in HIJACK_WORDS):
        return "hijacking"
    if any(w in text_lower for w in DRUG_WORDS):
        return "drug_bust"
    return None


def _detect_source_outlet(source_id: str, url: str, text: str) -> str:
    sid = (source_id or "").lower()
    low = f"{url} {text}".lower()
    if sid.startswith("saps") or "saps.gov.za" in low:
        return "SAPS"
    if sid.startswith("arrive_alive") or sid.startswith("aa_") or "arrivealive.co.za" in low:
        return "Arrive Alive"
    if sid.startswith("sabc_news") or "sabcnews.com" in low or "sabc news" in low:
        return "SABC News"
    if sid.startswith("ecr_news_traffic") or "ecr.co.za" in low:
        return "ECR News & Traffic"
    if sid.startswith("north_coast_courier") or "northcoastcourier.co.za" in low:
        return "North Coast Courier"
    if sid.startswith("phoenix_tabloid") or "phoenixtabloid.co.za" in low:
        return "Phoenix Tabloid"
    if sid.startswith("pretoria_news") or "pretoria news" in low:
        return "Pretoria News"
    if sid.startswith("iol_news") or "iol.co.za" in low:
        return "IOL"
    if sid.startswith("x_") or sid.startswith("x_social") or "x.com" in low or "twitter.com" in low:
        return "X / Social"
    if "news24" in low:
        return "News24"
    if "timeslive" in low:
        return "TimesLIVE"
    if "citizen.co.za" in low:
        return "The Citizen"
    return "SA Press"


def _extract_suspects(text: str) -> str:
    m = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|several|multiple)\s+suspects?\b",
        text,
        re.I,
    )
    if m:
        return m.group(0).strip()
    if re.search(r"\bsuspects?\s+(arrested|sought|fled|wanted)\b", text, re.I):
        return "Suspect(s) mentioned"
    return "N/A"


def _extract_value(text: str) -> str:
    m = re.search(
        r"(?:R\s?\d[\d\s,.]*(?:\s?(?:million|billion|thousand|m|bn|k))?|\d[\d\s,.]*\s?(?:million|billion)\s*(?:rand|rands)?)",
        text,
        re.I,
    )
    return m.group(0).strip() if m else "N/A"


def _extract_vehicle_or_case_numbers(text: str) -> str:
    plate = re.search(
        r"\b[A-Z]{2,3}\s?\d{2,4}(?:-\d{2,4})?\s?(?:GP|ZN|KZN|EC|WC|FS|LP|MP|NW|NC)?\b",
        text,
    )
    if plate:
        return plate.group(0).strip()
    case_no = re.search(r"\b(?:CAS|BOLO|CR)\s*#?\s*\d{2,8}/\d{1,4}/\d{4}\b", text, re.I)
    if case_no:
        return case_no.group(0).strip()
    return "N/A"


def _extract_contact(text: str) -> str:
    phone = re.search(r"\b0\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b|\b08600\s?10111\b", text)
    if phone:
        return phone.group(0).strip()
    if "crime stop" in text.lower():
        return "08600 10111 (Crime Stop)"
    return "N/A"


def _deduplicate_sentences(raw_text: str) -> tuple[str, str]:
    cleaned = re.sub(r"\s+", " ", raw_text).strip()
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", cleaned) if p.strip()]
    unique_parts: list[str] = []
    seen_norm: set[str] = set()

    for part in parts:
        norm = re.sub(r"\s*[-–|]\s*(SABC News|News24|TimesLIVE|IOL|Citizen|EWN).*$", "", part, flags=re.I)
        norm = re.sub(r"[^a-z0-9]+", " ", norm.lower()).strip()
        if not norm or norm in seen_norm:
            continue
        # Skip if this segment is a near-duplicate substring of an already kept segment
        if any(norm in prev or prev in norm for prev in seen_norm):
            continue
        seen_norm.add(norm)
        unique_parts.append(part)

    if not unique_parts:
        title = cleaned[:95].strip()
        return title, title[:150].strip()

    title = re.sub(r"\s*[-–|]\s*(SABC News|News24|TimesLIVE|IOL|Citizen|EWN)$", "", unique_parts[0], flags=re.I)
    title = title[:95].strip()
    summary = " ".join(unique_parts[1:])[:155].strip() if len(unique_parts) > 1 else ""
    return title, summary


def parse_post(post: dict[str, Any]) -> dict[str, Any] | None:
    text = (post.get("text") or "").strip()
    if not text:
        return None

    category = _classify_category(text.lower())
    if not category:
        return None

    geo = geocode_with_precision(text)
    if not geo:
        return None

    title, summary = _deduplicate_sentences(text)
    source_outlet = _detect_source_outlet(post.get("source_id", ""), post.get("source_url", ""), text)

    gallery: list[str] = []
    if isinstance(post.get("gallery"), list):
        gallery.extend([u for u in post["gallery"] if u])
    if post.get("image_url") and post["image_url"] not in gallery:
        gallery.insert(0, post["image_url"])

    if category == "drug_bust":
        details: dict[str, Any] = {
            "location": geo["location_name"],
            "suspects": _extract_suspects(text),
            "value": _extract_value(text),
        }
    elif category == "hijacking":
        details = {
            "numbers": _extract_vehicle_or_case_numbers(text),
            "location": geo["location_name"],
            "contact": _extract_contact(text),
        }
    else:
        details = {
            "location": geo["location_name"],
            "suspects": _extract_suspects(text),
            "value": _extract_value(text),
            "contact": _extract_contact(text),
        }

    details["source"] = source_outlet
    details["precision"] = geo["precision"]
    if gallery:
        details["gallery"] = gallery[:3]

    return {
        "source_id": post["source_id"],
        "category": category,
        "title": title,
        "summary": summary,
        "location_name": geo["location_name"],
        "province": geo["province"],
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "reported_at": post["reported_at"],
        "source_url": post["source_url"],
        "image_url": gallery[0] if gallery else None,
        "details": details,
    }
