"""Tube Reliability Tracker: a Streamlit app built on the pipeline's DuckDB tables.

Run it with:  streamlit run app.py
"""

import altair as alt
import duckdb
import streamlit as st

DB_PATH = "data/tube.duckdb"
NORMAL_CODES = "(10, 18, 19, 20)"  # same "not a disruption" codes as transform.py

st.set_page_config(page_title="Tube Reliability Tracker", page_icon="🚇", layout="wide")
st.title("🚇 Tube Reliability Tracker")
st.caption("How reliable is each London Underground line? "
           "Built from TfL status snapshots collected about every 15 minutes. "
           "Times are shown in London time.")

# Open the database read-only: the app only looks at the data, never changes it.
con = duckdb.connect(DB_PATH, read_only=True)
# Stored times are UTC; this setting lets us convert them correctly to London time.
con.execute("SET TimeZone = 'UTC'")


def london(column):
    """SQL that converts a stored UTC timestamp column to London local time."""
    return f"timezone('Europe/London', {column}::TIMESTAMPTZ)"


# --- Line filter ---
lines = [row[0] for row in con.execute(
    "SELECT DISTINCT line_name FROM line_snapshot ORDER BY line_name").fetchall()]
selected = st.selectbox("Choose a line", ["All lines"] + lines)

# Reusable filter: matches every line when "All lines" is chosen
LINE_FILTER = "(? = 'All lines' OR line_name = ?)"
params = [selected, selected]

# --- Headline numbers ---
snapshots, latest = con.execute(f"""
    SELECT count(*), max({london('collected_at_utc')}) FROM raw_snapshots
""").fetchone()

events = con.execute(
    f"SELECT count(*) FROM disruption_events WHERE {LINE_FILTER}", params
).fetchone()[0]

pct_disrupted = con.execute(f"""
    SELECT round(100 * avg(is_disrupted::INT), 1)
    FROM line_snapshot WHERE {LINE_FILTER}
""", params).fetchone()[0]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Snapshots collected", snapshots)
col2.metric("Disruptions found", events)
col3.metric("Time disrupted", f"{pct_disrupted}%")
col4.metric("Latest snapshot", f"{latest:%d %b %H:%M}")

# --- Which line is disrupted for the most time? (always shows all lines) ---
st.subheader("Which line is disrupted most of the time?")
by_line = con.execute("""
    SELECT line_name AS Line,
           round(100 * avg(is_disrupted::INT), 1) AS "% of time disrupted"
    FROM line_snapshot
    GROUP BY line_name
""").df()

st.altair_chart(
    alt.Chart(by_line)
    .mark_bar()
    .encode(
        x=alt.X("% of time disrupted:Q"),
        y=alt.Y("Line:N", sort="-x", title=None),  # worst line at the top
    )
)

left, right = st.columns(2)

# --- When do disruptions happen? ---
with left:
    st.subheader(f"When are disruptions most likely? ({selected})")
    by_hour = con.execute(f"""
        SELECT hour({london('collected_at_utc')}) AS "Hour of day",
               round(100 * avg(is_disrupted::INT), 1) AS "% of time disrupted"
        FROM line_snapshot
        WHERE {LINE_FILTER}
        GROUP BY 1
        ORDER BY 1
    """, params).df()

    st.altair_chart(
        alt.Chart(by_hour)
        .mark_bar()
        .encode(
            x=alt.X("Hour of day:O"),
            y=alt.Y("% of time disrupted:Q"),
        )
    )

# --- What kind of disruptions? ---
with right:
    st.subheader(f"Most common problems ({selected})")
    by_status = con.execute(f"""
        SELECT status_description AS Status, count(*) AS Snapshots
        FROM stg_line_status
        WHERE status_severity NOT IN {NORMAL_CODES}
          AND {LINE_FILTER}
        GROUP BY status_description
    """, params).df()

    if by_status.empty:
        st.info("No disruptions recorded for this line yet.")
    else:
        st.altair_chart(
            alt.Chart(by_status)
            .mark_bar()
            .encode(
                x=alt.X("Snapshots:Q", title="Number of snapshots"),
                y=alt.Y("Status:N", sort="-x", title=None),
            )
        )

# --- Every disruption event ---
st.subheader(f"Disruption events ({selected})")
all_events = con.execute(f"""
    SELECT line_name,
           disruption_type,
           {london('first_seen_utc')} AS started,
           approx_duration_minutes,
           still_ongoing,
           statuses,
           reasons
    FROM disruption_events
    WHERE {LINE_FILTER}
    ORDER BY first_seen_utc DESC
""", params).df()

st.dataframe(
    all_events,
    hide_index=True,
    column_config={
        "line_name": "Line",
        "disruption_type": "Type",
        "started": st.column_config.DatetimeColumn("Started", format="ddd D MMM, HH:mm"),
        "approx_duration_minutes": "Approx. duration (mins)",
        "still_ongoing": "Ongoing?",
        "statuses": "Status",
        "reasons": "TfL reason",
    },
)

con.close()