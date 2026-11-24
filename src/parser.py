import re
from typing import Any, Optional
from src.db import MIN_DATE
from src.geocode import extract_location_from_text, geocode_sa

CATEGORY_KEYWORDS = {
    "cit_robbery": [
        "cash-in-transit",
        "cash in transit",
        "cit heist",
        "cit robbery",
        "armoured vehicle",
        "cash van",
    ],
    "hijacking": [
        "hijacking",
        "hijacked",
        "bolo",
        "stolen vehicle",
        "carjacking",
    ],
    "drug_bust": [
        "drug bust",
        "drugs seized",
        "street value",
        "cocaine",
        "crystal meth",
        "tik",
        "mandrax",
        "heroin",
        "dagga",
        "narcotics",
    ],
}

DRUG_NAMES = ("cocaine", "crystal meth", "methamphetamine", "tik", "mandrax", "heroin", "dagga", "ecstasy")


def classify_category(text: str) -> Optional[str]:
    lower = text.lower()
    # Priority order: CIT heist -> Hijacking/BOLO -> Drug bust
    for category in ("cit_robbery", "hijacking", "drug_bust"):
        for kw in CATEGORY_KEYWORDS[category]:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                return category
    return None


def extract_drug_details(text: str) -> dict[str, Any]:
    details: dict[str, Any] = {}

    # Match R42,000,000 | R1.5 million | R500k | R2 billion
    val_match = re.search(
        r"(R\s?\d[\d\s,\.]*(?:\s?(?:million|billion|thousand|m|k))?)",
        text,
        re.IGNORECASE,
    )
    if val_match:
        details["street_value"] = re.sub(r"\s+", " ", val_match.group(1)).strip()

    # Match suspect counts (e.g., "3 suspects", "two suspects arrested")
    sus_match = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+suspects?\b", text, re.IGNORECASE)
    if sus_match:
        details["suspects"] = sus_match.group(1)

    found_drugs = [d.title() for d in DRUG_NAMES if re.search(rf"\b{re.escape(d)}\b", text, re.IGNORECASE)]
    if found_drugs:
        details["drug_type"] = ", ".join(dict.fromkeys(found_drugs))

    return details


def extract_hijacking_details(text: str) -> dict[str, Any]:
    details: dict[str, Any] = {}

    # Common SA plate formats: AB 12 CD GP | CA 123-456 | ND 123 456 | KZN 123 GP
    plate_match = re.search(
        r"\b([A-Z]{2,3}\s?\d{2,3}[\s\-]?[A-Z0-9]{2,4}(?:\s?(?:GP|ZN|EC|WC|MP|LP|NW|FS|NC))?)\b",
        text,
    )
    if plate_match:
        details["registration"] = plate_match.group(1).strip()

    # Vehicle make/color snippet
    veh_match = re.search(
        r"\b((?:white|black|silver|grey|gray|blue|red|gold)\s+(?:vw|volkswagen|toyota|ford|bmw|audi|mercedes|hyundai|kia|nissan|isuzu|polo|hilux|fortuner|ranger)[a-zA-Z0-9\s\-]{0,20})",
        text,
        re.IGNORECASE,
    )
    if veh_match:
        details["vehicle"] = veh_match.group(1).strip()

    if "bolo" in text.lower():
        details["alert_type"] = "BOLO"

    return details


def extract_cit_details(text: str) -> dict[str, Any]:
    details: dict[str, Any] = {}
    lower = text.lower()
    if "explosive" in lower or "bombed" in lower:
        details["method"] = "Explosives"
    elif "rammed" in lower:
        details["method"] = "Vehicle Ramming"

    sus_match = re.search(r"\b(\d+|several|multiple)\s+(?:armed\s+)?suspects?\b", lower)
    if sus_match:
        details["suspects"] = f"{sus_match.group(1)} suspects"
    return details


def parse_post(raw_post: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Convert a normalized raw post into a Crime Radr incident dictionary.
    Expected keys in raw_post: source_id, reported_at (YYYY-MM-DD), text, source_url, image_url (optional).
    """
    reported_at = raw_post.get("reported_at", "")[:10]
    if not reported_at or reported_at < MIN_DATE:
        return None

    text = raw_post.get("text", "").strip()
    if not text:
        return None

    category = classify_category(text)
    if not category:
        return None

    location_name = raw_post.get("location_hint") or extract_location_from_text(text)
    if not location_name:
        return None

    coords = geocode_sa(location_name)
    if not coords:
        return None

    lat, lon, province = coords

    if category == "drug_bust":
        details = extract_drug_details(text)
    elif category == "hijacking":
        details = extract_hijacking_details(text)
    else:
        details = extract_cit_details(text)

    first_line = text.splitlines()[0][:90]
    title = first_line if len(first_line) > 15 else f"{category.replace('_', ' ').title()} - {location_name}"

    return {
        "source_id": str(raw_post["source_id"]),
        "category": category,
        "reported_at": reported_at,
        "province": province,
        "location_name": location_name,
        "latitude": lat,
        "longitude": lon,
        "title": title,
        "summary": text[:400],
        "image_url": raw_post.get("image_url"),
        "source_url": raw_post["source_url"],
        "details": details,
    }


if __name__ == "__main__":
    sample = {
        "source_id": "test_tweet_999",
        "reported_at": "2025-10-12",
        "text": "SAPS Hawks seized cocaine with an estimated street value of R18 million in Umhlanga. 2 suspects arrested.",
        "source_url": "https://x.com/SAPoliceService",
        "image_url": None,
    }
    print(parse_post(sample))
