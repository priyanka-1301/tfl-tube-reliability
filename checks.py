"""Data quality checks.

Each check is a SQL query that looks for problem rows.
If a query returns 0 rows the check passes; otherwise it fails.
"""

import duckdb

DB_PATH = "data/tube.duckdb"

CHECKS = {
    "Every staging row has a line and a status code": """
        SELECT * FROM stg_line_status
        WHERE line_id IS NULL OR line_name IS NULL OR status_severity IS NULL
    """,
    "Only one row per line per snapshot": """
        SELECT collected_at_utc, line_id, count(*) AS n
        FROM line_snapshot
        GROUP BY ALL
        HAVING count(*) > 1
    """,
    "Every snapshot contains all 11 Tube lines": """
        SELECT collected_at_utc, count(DISTINCT line_id) AS lines
        FROM line_snapshot
        GROUP BY ALL
        HAVING count(DISTINCT line_id) <> 11
    """,
    "Disruption event IDs are unique": """
        SELECT event_id, count(*) AS n
        FROM disruption_events
        GROUP BY ALL
        HAVING count(*) > 1
    """,
    "No disruption has a negative duration": """
        SELECT * FROM disruption_events
        WHERE approx_duration_minutes < 0
    """,
}


def main():
    """Run every check, print the results, and return how many failed."""
    con = duckdb.connect(DB_PATH)
    failures = 0

    for name, sql in CHECKS.items():
        bad_rows = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        if bad_rows == 0:
            print(f"  PASS  {name}")
        else:
            print(f"  FAIL  {name} ({bad_rows} problem rows)")
            failures += 1

    con.close()
    return failures


if __name__ == "__main__":
    main()