from src.db import init_db
from src.ingest import run_ingestion
from src.map_builder import generate_map


def main() -> None:
    init_db()
    ingested = run_ingestion()
    output_path = generate_map()
    print(f"[OK] Pipeline complete | New/updated incidents: {ingested} | Map: {output_path}")


if __name__ == "__main__":
    main()
