from src.db import init_db, upsert_incident

SAMPLE_INCIDENTS = [
    {
        "source_id": "seed_drug_001",
        "category": "drug_bust",
        "reported_at": "2025-07-14",
        "province": "KwaZulu-Natal",
        "location_name": "Durban Harbour, Durban",
        "latitude": -29.8723,
        "longitude": 31.0247,
        "title": "Major Cocaine Seizure at Durban Port",
        "summary": "SAPS Hawks and Crime Intelligence intercepted bricks of pure cocaine concealed inside maritime cargo containers.",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/South_African_Police_Service_logo.svg/480px-South_African_Police_Service_logo.svg.png",
        "source_url": "https://x.com/SAPoliceService",
        "details": {
            "drug_type": "Cocaine",
            "street_value": "R42,000,000",
            "suspects_arrested": 3,
        },
    },
    {
        "source_id": "seed_hijack_001",
        "category": "hijacking",
        "reported_at": "2025-08-03",
        "province": "Gauteng",
        "location_name": "N1 North near Midrand",
        "latitude": -25.9992,
        "longitude": 28.1263,
        "title": "BOLO Alert: Hijacked White VW Polo",
        "summary": "Armed suspects forced driver off the N1 highway. Vehicle last seen heading toward Alexandra.",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6d/2018_Volkswagen_Polo_SE_TSI_1.0_Front.jpg/640px-2018_Volkswagen_Polo_SE_TSI_1.0_Front.jpg",
        "source_url": "https://x.com/search?q=BOLO%20hijacking",
        "details": {
            "vehicle": "White VW Polo TSI",
            "registration": "GP XX 99 GP",
            "status": "Active BOLO",
        },
    },
    {
        "source_id": "seed_cit_001",
        "category": "cit_robbery",
        "reported_at": "2025-09-19",
        "province": "Eastern Cape",
        "location_name": "N2 near Mthatha",
        "latitude": -31.5889,
        "longitude": 28.7844,
        "title": "Cash-in-Transit Heist on N2 Highway",
        "summary": "Armoured cash van rammed and bombed with explosives by heavily armed suspects using two getaway SUVs.",
        "image_url": None,
        "source_url": "https://x.com/SAPoliceService",
        "details": {
            "method": "Explosives / Ramming",
            "suspects": "Approx. 8 armed suspects",
        },
    },
]


def run_seed() -> None:
    init_db()
    count = 0
    for item in SAMPLE_INCIDENTS:
        if upsert_incident(item):
            count += 1
    print(f"[OK] Seeded {count} test incidents into Crime Radr.")


if __name__ == "__main__":
    run_seed()
