import re
import time
from typing import Optional
import requests
from src.db import get_connection

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "CrimeRadrZA/1.0 (https://github.com/WANAPO/crime-radr)"

# Fast lookup for major SA metros, hubs, and key highways
SA_KNOWN_PLACES: dict[str, tuple[float, float, str]] = {
    "johannesburg": (-26.2041, 28.0473, "Gauteng"),
    "joburg": (-26.2041, 28.0473, "Gauteng"),
    "pretoria": (-25.7479, 28.2293, "Gauteng"),
    "tshwane": (-25.7479, 28.2293, "Gauteng"),
    "midrand": (-25.9992, 28.1263, "Gauteng"),
    "sandton": (-26.1076, 28.0567, "Gauteng"),
    "soweto": (-26.2485, 27.8540, "Gauteng"),
    "ekurhuleni": (-26.1752, 28.3462, "Gauteng"),
    "kempton park": (-26.1000, 28.2333, "Gauteng"),
    "or tambo": (-26.1367, 28.2411, "Gauteng"),
    "durban": (-29.8587, 31.0218, "KwaZulu-Natal"),
    "ethekwini": (-29.8587, 31.0218, "KwaZulu-Natal"),
    "umhlanga": (-29.7253, 31.0858, "KwaZulu-Natal"),
    "pietermaritzburg": (-29.6006, 30.3794, "KwaZulu-Natal"),
    "richards bay": (-28.7807, 32.0383, "KwaZulu-Natal"),
    "cape town": (-33.9249, 18.4241, "Western Cape"),
    "mitchells plain": (-34.0486, 18.6177, "Western Cape"),
    "khayelitsha": (-34.0378, 18.6673, "Western Cape"),
    "bellville": (-33.9000, 18.6333, "Western Cape"),
    "gqeberha": (-33.9608, 25.6022, "Eastern Cape"),
    "port elizabeth": (-33.9608, 25.6022, "Eastern Cape"),
    "east london": (-33.0153, 27.9116, "Eastern Cape"),
    "mthatha": (-31.5889, 28.7844, "Eastern Cape"),
    "bloemfontein": (-29.0852, 26.1596, "Free State"),
    "polokwane": (-23.9045, 29.4689, "Limpopo"),
    "mbombela": (-25.4753, 30.9694, "Mpumalanga"),
    "nelspruit": (-25.4753, 30.9694, "Mpumalanga"),
    "rustenburg": (-25.6544, 27.2559, "North West"),
    "kimberley": (-28.7282, 24.7499, "Northern Cape"),
}


def init_geocode_cache() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geocode_cache (
                query_key TEXT PRIMARY KEY,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                province TEXT
            );
            """
        )


def extract_location_from_text(text: str) -> Optional[str]:
    """Find a known SA town/city/suburb or 'in/near/along <Place>' phrase."""
    lower = text.lower()
    for place in sorted(SA_KNOWN_PLACES.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(place)}\b", lower):
            return place.title()

    match = re.search(
        r"\b(?:in|at|near|along)\s+([A-Z][a-zA-Z0-9\s\-]{2,30}?)(?:,|\.|;|\s+on|\s+where|\s+after|\s+during|$)",
        text,
    )
    if match:
        return match.group(1).strip()
    return None


def geocode_sa(place_name: str) -> Optional[tuple[float, float, str]]:
    """Resolve a South African location name to (lat, lon, province)."""
    if not place_name:
        return None

    key = place_name.strip().lower()
    if key in SA_KNOWN_PLACES:
        return SA_KNOWN_PLACES[key]

    init_geocode_cache()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT latitude, longitude, province FROM geocode_cache WHERE query_key = ?;",
            (key,),
        ).fetchone()
        if row:
            return (float(row["latitude"]), float(row["longitude"]), row["province"] or "Unknown")

    try:
        time.sleep(1.1)  # Respect Nominatim 1 req/sec policy
        resp = requests.get(
            NOMINATIM_URL,
            params={
                "q": f"{place_name}, South Africa",
                "format": "json",
                "countrycodes": "za",
                "limit": 1,
                "addressdetails": 1,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        province = data[0].get("address", {}).get("state", "Unknown")

        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO geocode_cache (query_key, latitude, longitude, province) VALUES (?, ?, ?, ?);",
                (key, lat, lon, province),
            )
        return (lat, lon, province)
    except Exception:
        return None


if __name__ == "__main__":
    print("Durban ->", geocode_sa("Durban"))
    print("Verulam ->", geocode_sa("Verulam"))
