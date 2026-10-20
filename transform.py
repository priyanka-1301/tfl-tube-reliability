"""Transform raw TfL snapshots into clean, analysis-ready tables.

Tables built (all rebuilt from raw_snapshots every run, so always consistent):
  1. stg_line_status    - one row per line, per status, per snapshot
  2. line_snapshot      - one row per line, per snapshot, with an is_disrupted flag
  3. disruption_events  - consecutive disrupted snapshots merged into single events
"""

import duckdb

DB_PATH = "data/tube.duckdb"

# Status codes that mean "nothing wrong" (10 Good Service, 18 No Issues,
# 19 Information, 20 Service Closed overnight). Anything else is a disruption.
NORMAL_CODES = "(10, 18, 19, 20)"

# If snapshots are further apart than this, we don't assume a disruption
# continued through the gap (GitHub Actions sometimes skips scheduled runs).
MAX_GAP = "INTERVAL 60 MINUTE"

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

LINE_SNAPSHOT_SQL = f"""
CREATE OR REPLACE TABLE line_snapshot AS
SELECT
    collected_at_utc,
    line_id,
    line_name,
    -- Disrupted if ANY of the line's statuses is not a normal code
    BOOL_OR(status_severity NOT IN {NORMAL_CODES})       AS is_disrupted,
    STRING_AGG(DISTINCT status_description, ' / ')       AS status_descriptions,
    STRING_AGG(DISTINCT reason, ' | ')                   AS reasons,
    CASE
        WHEN BOOL_OR(disruption_category = 'RealTime')    THEN 'Unplanned'
        WHEN BOOL_OR(disruption_category = 'PlannedWork') THEN 'Planned'
    END                                                  AS disruption_type
FROM stg_line_status
GROUP BY collected_at_utc, line_id, line_name
"""

EVENTS_SQL = f"""
CREATE OR REPLACE TABLE disruption_events AS
WITH ordered AS (
    -- For each line, look at the snapshot before and after this one
    SELECT
        *,
        LAG(is_disrupted)      OVER w AS prev_disrupted,
        LAG(collected_at_utc)  OVER w AS prev_collected_at,
        LEAD(collected_at_utc) OVER w AS next_collected_at
    FROM line_snapshot
    WINDOW w AS (PARTITION BY line_id ORDER BY collected_at_utc)
),
flagged AS (
    -- Mark where a new disruption starts (the start of each "island")
    SELECT
        *,
        CASE
            WHEN prev_disrupted IS NOT TRUE                            THEN 1
            WHEN collected_at_utc - prev_collected_at > {MAX_GAP}      THEN 1
            ELSE 0
        END AS starts_new_event
    FROM ordered
    WHERE is_disrupted
),
numbered AS (
    -- Running total of starts gives each island its own event number
    SELECT
        *,
        SUM(starts_new_event) OVER (
            PARTITION BY line_id ORDER BY collected_at_utc
        ) AS event_number
    FROM flagged
),
events AS (
    SELECT
        line_id || '-' || event_number                 AS event_id,
        line_id,
        line_name,
        MIN(collected_at_utc)                          AS first_seen_utc,
        MAX(collected_at_utc)                          AS last_seen_utc,
        ARG_MAX(next_collected_at, collected_at_utc)   AS next_snapshot_utc,
        COUNT(*)                                       AS snapshots,
        STRING_AGG(DISTINCT status_descriptions, ' / ') AS statuses,
        STRING_AGG(DISTINCT reasons, ' | ')            AS reasons,
        ARG_MIN(disruption_type, collected_at_utc)     AS disruption_type
    FROM numbered
    GROUP BY line_id, line_name, event_number
)
SELECT
    event_id,
    line_id,
    line_name,
    disruption_type,
    first_seen_utc,
    -- The first snapshot showing it fixed, but only if it came soon after
    CASE
        WHEN next_snapshot_utc - last_seen_utc <= {MAX_GAP} THEN next_snapshot_utc
    END                                                AS cleared_by_utc,
    next_snapshot_utc IS NULL                          AS still_ongoing,
    DATE_DIFF(
        'minute',
        first_seen_utc,
        CASE
            WHEN next_snapshot_utc - last_seen_utc <= {MAX_GAP} THEN next_snapshot_utc
            ELSE last_seen_utc
        END
    )                                                  AS approx_duration_minutes,
    snapshots,
    statuses,
    reasons
FROM events
"""


def main():
    con = duckdb.connect(DB_PATH)

    for name, sql in [
        ("stg_line_status", STAGING_SQL),
        ("line_snapshot", LINE_SNAPSHOT_SQL),
        ("disruption_events", EVENTS_SQL),
    ]:
        con.execute(sql)
        rows = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        print(f"{name}: {rows} rows")

    print("\nDisruption events:")
    con.sql("""
        SELECT line_name, disruption_type, first_seen_utc,
               approx_duration_minutes, still_ongoing, statuses
        FROM disruption_events
        ORDER BY first_seen_utc, line_name
    """).show()

    con.close()


if __name__ == "__main__":
    main()