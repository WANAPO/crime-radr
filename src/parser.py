import re
from typing import Any
from src.geocode import extract_location_from_text, geocode_sa

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


def _resolve_geo(text: str) -> dict[str, Any] | None:
    place = extract_location_from_text(text)
    if not place:
        return None
    coords = geocode_sa(place)
    if not coords:
        return None
    lat, lon, province = coords
    return {
        "location_name": place,
        "province": province or "South Africa",
        "latitude": float(lat),
        "longitude": float(lon),
    }


def _extract_suspects(text: str) -> str:
    m = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|\bseveral\b|\bmultiple\b)\s+suspects?\b",
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


def _short_title(text: str) -> str:
    first_part = text.split(". ", 1)[0].strip()
    first_part = re.sub(
        r"\s*[-–|]\s*(SABC News|News24|TimesLIVE|IOL|Citizen|EWN)$",
        "",
        first_part,
        flags=re.I,
    )
    return first_part[:95].strip()


def _short_summary(text: str, title: str) -> str:
    rem = text[len(title) :].lstrip(". ").strip() if text.startswith(title) else text
    rem = re.sub(r"\s+", " ", rem).strip()
    return rem[:160].strip() if rem else title[:160].strip()


def parse_post(post: dict[str, Any]) -> dict[str, Any] | None:
    text = (post.get("text") or "").strip()
    if not text:
        return None

    category = _classify_category(text.lower())
    if not category:
        return None

    geo = _resolve_geo(text)
    if not geo:
        return None

    title = _short_title(text)
    summary = _short_summary(text, title)

    gallery: list[str] = []
    if isinstance(post.get("gallery"), list):
        gallery.extend([u for u in post["gallery"] if u])
    if post.get("image_url") and post["image_url"] not in gallery:
        gallery.insert(0, post["image_url"])

    if category == "drug_bust":
        details = {
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
    else:  # cit_robbery
        details = {
            "location": geo["location_name"],
            "suspects": _extract_suspects(text),
            "value": _extract_value(text),
            "contact": _extract_contact(text),
        }

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
