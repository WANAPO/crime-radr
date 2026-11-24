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
        "cit attack",
        "armoured vehicle",
        "armored vehicle",
        "armoured cash",
        "cash van",
        "money truck",
        "money van",
        "bullion van",
    ],
    "hijacking": [
        "hijacking",
        "hijacked",
        "carjacking",
        "bolo",
        "stolen vehicle",
        "stolen car",
        "missing vehicle",
        "vehicle stolen",
        "car stolen",
        "vehicle recovered",
        "theft of motor vehicle",
        "motor vehicle theft",
        "car theft",
        "chop shop",
        "vehicle syndicate",
    ],
    "drug_bust": [
        "drug bust",
        "drugs seized",
        "drug haul",
        "drug raid",
        "drug lab",
        "drug laboratory",
        "clandestine lab",
        "clandestine drug",
        "drug den",
        "drug manufacturing",
        "drug syndicate",
        "drug trafficking",
        "narcotics",
        "street value",
        "cocaine",
        "crystal meth",
        "methamphetamine",
        "tik",
        "mandrax",
        "heroin",
        "dagga",
    ],
}

DRUG_NAMES = (
    "cocaine",
    "crystal meth",
    "methamphetamine",
    "tik",
    "mandrax",
    "heroin",
    "dagga",
    "cannabis",
    "ecstasy",
    "fentanyl",
)

MONTH_MAP = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}


def classify_category(text: str) -> Optional[str]:
    lower = text.lower()
    # Priority: CIT/Money truck -> Hijacking/Stolen Vehicle -> Drug Bust/Lab/Den
    for category in ("cit_robbery", "hijacking", "drug_bust"):
        for kw in CATEGORY_KEYWORDS[category]:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                return category
    return None


def extract_incident_date(text: str, fallback_date: str) -> str:
    """Extract explicit 'stolen/hijacked on <Date>' or YYYY-MM-DD from text, falling back to post date."""
    iso_match = re.search(r"\b(202[5-9]-\d{2}-\d{2})\b", text)
    if iso_match and iso_match.group(1) >= MIN_DATE:
        return iso_match.group(1)

    dmy_match = re.search(
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(202[5-9])\b",
        text,
        re.IGNORECASE,
    )
    if dmy_match:
        day = dmy_match.group(1).zfill(2)
        month = MONTH_MAP[dmy_match.group(2).lower()]
        year = dmy_match.group(3)
        candidate = f"{year}-{month}-{day}"
        if candidate >= MIN_DATE:
            return candidate

    return fallback_date


def extract_video_url(text: str, source_url: str, raw_video_url: Optional[str] = None) -> Optional[str]:
    if raw_video_url:
        return raw_video_url

    yt_match = re.search(r"(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[^\s\"'<>]+)", text)
    if yt_match:
        return yt_match.group(1)

    if any(tag in text.lower() for tag in ("watch:", "video:", "footage", "caught on camera", "dashcam", "cctv")):
        return source_url

    return None


def extract_drug_details(text: str) -> dict[str, Any]:
    details: dict[str, Any] = {}
    lower = text.lower()

    if any(k in lower for k in ("drug lab", "drug laboratory", "clandestine lab", "clandestine drug", "drug manufacturing")):
        details["site_type"] = "Clandestine Drug Lab"
    elif "drug den" in lower:
        details["site_type"] = "Drug Den"
    elif "syndicate" in lower:
        details["site_type"] = "Drug Syndicate"

    val_match = re.search(
        r"(R\s?\d[\d\s,\.]*(?:\s?(?:million|billion|thousand|m|k))?)",
        text,
        re.IGNORECASE,
    )
    if val_match:
        details["street_value"] = re.sub(r"\s+", " ", val_match.group(1)).strip()

    sus_match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+suspects?\b",
        text,
        re.IGNORECASE,
    )
    if sus_match:
        details["suspects"] = sus_match.group(1)

    found_drugs = [d.title() for d in DRUG_NAMES if re.search(rf"\b{re.escape(d)}\b", text, re.IGNORECASE)]
    if found_drugs:
        details["drug_type"] = ", ".join(dict.fromkeys(found_drugs))

    return details


def extract_hijacking_details(text: str, incident_date: str, location_name: str) -> dict[str, Any]:
    details: dict[str, Any] = {
        "date_stolen_or_hijacked": incident_date,
        "last_seen_location": location_name,
    }
    lower = text.lower()

    if "recovered" in lower:
        details["status"] = "Recovered"
    elif "bolo" in lower:
        details["status"] = "Active BOLO"
    elif "hijack" in lower or "carjack" in lower:
        details["status"] = "Hijacked"
    else:
        details["status"] = "Stolen / Missing Vehicle"

    plate_match = re.search(
        r"\b([A-Z]{2,3}\s?\d{2,3}[\s\-]?[A-Z0-9]{2,4}(?:\s?(?:GP|ZN|EC|WC|MP|LP|NW|FS|NC))?)\b",
        text,
    )
    if plate_match:
        details["registration"] = plate_match.group(1).strip()

    veh_match = re.search(
        r"\b((?:white|black|silver|grey|gray|blue|red|gold|maroon|green|brown)\s+"
        r"(?:vw|volkswagen|toyota|ford|bmw|audi|mercedes|hyundai|kia|nissan|isuzu|mazda|suzuki|renault|haval|chery|"
        r"polo|hilux|fortuner|ranger|corolla|etios|yaris|amarok|navara|np200)[a-zA-Z0-9\s\-]{0,22})",
        text,
        re.IGNORECASE,
    )
    if veh_match:
        details["vehicle"] = veh_match.group(1).strip()

    return details


def extract_cit_details(text: str) -> dict[str, Any]:
    details: dict[str, Any] = {}
    lower = text.lower()

    if "explosive" in lower or "bombed" in lower:
        details["method"] = "Explosives / Bombing"
    elif "rammed" in lower:
        details["method"] = "Vehicle Ramming"
    elif "shootout" in lower or "gunfire" in lower:
        details["method"] = "Armed Ambush / Shootout"

    sus_match = re.search(r"\b(\d+|several|multiple)\s+(?:armed\s+)?suspects?\b", lower)
    if sus_match:
        details["suspects"] = f"{sus_match.group(1)} suspects"

    return details


def parse_post(raw_post: dict[str, Any]) -> Optional[dict[str, Any]]:
    fallback_date = raw_post.get("reported_at", "")[:10]
    if not fallback_date or fallback_date < MIN_DATE:
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
    incident_date = extract_incident_date(text, fallback_date)
    source_url = raw_post["source_url"]

    if category == "drug_bust":
        details = extract_drug_details(text)
    elif category == "hijacking":
        details = extract_hijacking_details(text, incident_date, location_name)
    else:
        details = extract_cit_details(text)

    # Preserve gallery of images & video URL inside details JSON
    gallery: list[str] = list(dict.fromkeys(raw_post.get("gallery") or []))
    primary_img = raw_post.get("image_url") or (gallery[0] if gallery else None)
    if primary_img and primary_img not in gallery:
        gallery.insert(0, primary_img)
    if gallery:
        details["gallery"] = gallery[:6]

    video_url = extract_video_url(text, source_url, raw_post.get("video_url"))
    if video_url:
        details["video_url"] = video_url

    first_line = text.splitlines()[0][:95]
    title = first_line if len(first_line) > 15 else f"{category.replace('_', ' ').title()} - {location_name}"

    return {
        "source_id": str(raw_post["source_id"]),
        "category": category,
        "reported_at": incident_date,
        "province": province,
        "location_name": location_name,
        "latitude": lat,
        "longitude": lon,
        "title": title,
        "summary": text[:450],
        "image_url": primary_img,
        "source_url": source_url,
        "details": details,
    }


if __name__ == "__main__":
    sample = {
        "source_id": "test_lab_01",
        "reported_at": "2026-11-20",
        "text": "SAPS dismantled a clandestine drug lab in Kranskop worth R100 million seizing Mandrax tablets. 1 suspect arrested.",
        "source_url": "https://www.saps.gov.za",
        "gallery": ["https://example.com/lab1.jpg", "https://example.com/lab2.jpg"],
    }
    print(parse_post(sample))
