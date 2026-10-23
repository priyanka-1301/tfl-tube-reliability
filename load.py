"""Load raw TfL snapshot files into DuckDB.

Each raw JSON file becomes one row in the raw_snapshots table.
Files that are already loaded are skipped, so running this again
never creates duplicates (it is safe to re-run).
"""

from datetime import datetime
from pathlib import Path

import duckdb

RAW_DIR = Path("data/raw/line_status")
DB_PATH = "data/tube.duckdb"


def collected_at_from_name(path):
    """Read the UTC collection time from a name like line_status_20261020T172816Z.json."""
    stamp = path.stem.replace("line_status_", "")
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")


def load_new_files(con):
    """Load any raw files not yet in raw_snapshots. Returns (new_files_loaded, total_snapshots)."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS raw_snapshots (
            file_name         VARCHAR PRIMARY KEY,
            collected_at_utc  TIMESTAMP NOT NULL,
            payload           JSON NOT NULL
        )
    """)

    # Find which files are already in the database
    already_loaded = {
        row[0] for row in con.execute("SELECT file_name FROM raw_snapshots").fetchall()
    }

    # Only load files we haven't seen before
    new_files = [
        path for path in sorted(RAW_DIR.rglob("*.json"))
        if path.name not in already_loaded
    ]

    for path in new_files:
        con.execute(
            "INSERT INTO raw_snapshots VALUES (?, ?, ?)",
            [path.name, collected_at_from_name(path), path.read_text(encoding="utf-8")],
        )

    total = con.execute("SELECT count(*) FROM raw_snapshots").fetchone()[0]
    return len(new_files), total


def main():
    con = duckdb.connect(DB_PATH)
    loaded, total = load_new_files(con)
    print(f"Loaded {loaded} new file(s). Total snapshots in database: {total}")
    con.close()


if __name__ == "__main__":
    main()