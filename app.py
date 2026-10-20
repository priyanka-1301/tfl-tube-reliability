"""Tube Reliability Tracker: a Streamlit app built on the pipeline's DuckDB tables.

Run it with:  streamlit run app.py
"""

import altair as alt
import duckdb
import streamlit as st

DB_PATH = "data/tube.duckdb"

st.set_page_config(page_title="Tube Reliability Tracker", page_icon="🚇", layout="wide")
st.title("🚇 Tube Reliability Tracker")
st.caption("How reliable is each London Underground line? "
           "Built from TfL status snapshots collected about every 15 minutes.")

# Open the database read-only: the app only looks at the data, never changes it
con = duckdb.connect(DB_PATH, read_only=True)

# --- Headline numbers ---
snapshots, first, last = con.execute("""
    SELECT count(*), min(collected_at_utc), max(collected_at_utc)
    FROM raw_snapshots
""").fetchone()
events = con.execute("SELECT count(*) FROM disruption_events").fetchone()[0]

col1, col2, col3 = st.columns(3)
col1.metric("Snapshots collected", snapshots)
col2.metric("Disruptions found", events)
col3.metric("Latest snapshot (UTC)", f"{last:%d %b %H:%M}")

# --- Which line is disrupted most often? ---
st.subheader("Disruptions by line")
by_line = con.execute("""
    SELECT line_name AS Line, count(*) AS Disruptions
    FROM disruption_events
    GROUP BY line_name
    ORDER BY Disruptions DESC
""").df()

chart = (
    alt.Chart(by_line)
    .mark_bar()
    .encode(
        x=alt.X("Disruptions:Q", title="Number of disruptions"),
        y=alt.Y("Line:N", sort="-x", title=None),  # most disrupted line at the top
    )
)
st.altair_chart(chart)

# --- Every disruption event ---
st.subheader("All disruption events")
all_events = con.execute("""
    SELECT line_name, disruption_type, first_seen_utc,
           approx_duration_minutes, still_ongoing, statuses, reasons
    FROM disruption_events
    ORDER BY first_seen_utc DESC
""").df()

st.dataframe(
    all_events,
    hide_index=True,
    column_config={
        "line_name": "Line",
        "disruption_type": "Type",
        "first_seen_utc": st.column_config.DatetimeColumn("Started (UTC)", format="D MMM, HH:mm"),
        "approx_duration_minutes": "Approx. duration (mins)",
        "still_ongoing": "Ongoing?",
        "statuses": "Status",
        "reasons": "TfL reason",
    },
)

con.close()