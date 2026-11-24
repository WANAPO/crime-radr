import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("data/crime_radr.db")
MIN_DATE = "2025-07-06"  # Madlanga Commission establishment date

VALID_CATEGORIES = ("drug_bust", "hijacking", "cit_robbery")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL CHECK (
                    category IN ('drug_bust', 'hijacking', 'cit_robbery')
                ),
                reported_at TEXT NOT NULL,
                province TEXT,
                location_name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                image_url TEXT,
                source_url TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(category);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_date ON incidents(reported_at);")


def upsert_incident(record: dict[str, Any]) -> bool:
    """Insert or update an incident if it occurred on or after 2025-07-06."""
    if record["category"] not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {record['category']}")

    if record["reported_at"] < MIN_DATE:
        return False

    details_str = json.dumps(record.get("details", {}), ensure_ascii=False)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO incidents (
                source_id, category, reported_at, province, location_name,
                latitude, longitude, title, summary, image_url, source_url, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                category = excluded.category,
                reported_at = excluded.reported_at,
                province = excluded.province,
                location_name = excluded.location_name,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                title = excluded.title,
                summary = excluded.summary,
                image_url = excluded.image_url,
                source_url = excluded.source_url,
                details_json = excluded.details_json;
            """,
            (
                record["source_id"],
                record["category"],
                record["reported_at"],
                record.get("province", "Unknown"),
                record["location_name"],
                float(record["latitude"]),
                float(record["longitude"]),
                record["title"],
                record["summary"],
                record.get("image_url"),
                record["source_url"],
                details_str,
            ),
        )
    return True


def fetch_all_incidents() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM incidents
            WHERE reported_at >= ?
            ORDER BY reported_at DESC, id DESC;
            """,
            (MIN_DATE,),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["details"] = json.loads(item["details_json"] or "{}")
        results.append(item)
    return results


if __name__ == "__main__":
    init_db()
    print(f"[OK] Crime Radr database ready at {DB_PATH}")
