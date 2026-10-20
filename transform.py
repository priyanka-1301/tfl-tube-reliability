"""Transform raw TfL snapshots into a clean staging table.

Builds stg_line_status: one row per line, per status, per snapshot.
The table is rebuilt from raw_snapshots every time, so it is always
consistent with the raw data and safe to re-run.
"""

import duckdb

DB_PATH = "data/tube.duckdb"

STAGING_SQL = """
CREATE OR REPLACE TABLE stg_line_status AS
WITH lines AS (
    -- Each snapshot is a JSON list of lines: split it into one row per line
    SELECT
        file_name,
        collected_at_utc,
        unnest(from_json(payload, '["JSON"]')) AS line
    FROM raw_snapshots
),
statuses AS (
    -- Each line has a list of statuses: split it into one row per status
    SELECT
        file_name,
        collected_at_utc,
        line ->> 'id'   AS line_id,
        line ->> 'name' AS line_name,
        unnest(from_json(line -> 'lineStatuses', '["JSON"]')) AS status
    FROM lines
)
SELECT
    file_name,
    collected_at_utc,
    line_id,
    line_name,
    CAST(status ->> 'statusSeverity' AS INTEGER) AS status_severity,
    status ->> 'statusSeverityDescription'       AS status_description,
    NULLIF(TRIM(status ->> 'reason'), '')        AS reason,
    status -> 'disruption' ->> 'category'        AS disruption_category
FROM statuses
"""


def main():
    con = duckdb.connect(DB_PATH)
    con.execute(STAGING_SQL)

    rows = con.execute("SELECT count(*) FROM stg_line_status").fetchone()[0]
    print(f"stg_line_status rebuilt with {rows} rows\n")

    # Show a preview so we can check it looks right
    con.sql("""
        SELECT collected_at_utc, line_name, status_severity, status_description
        FROM stg_line_status
        ORDER BY collected_at_utc, line_name
    """).show()

    con.close()


if __name__ == "__main__":
    main()