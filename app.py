"""Tube Reliability Tracker: a Streamlit app built on the pipeline's tables.

Run it with:  streamlit run app.py
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import duckdb
import requests
import streamlit as st
from dotenv import load_dotenv

import checks
import load
import transform

load_dotenv()  # reads TFL_APP_KEY from .env when running locally

NORMAL_CODES = "(10, 18, 19, 20)"  # same "not a disruption" codes as transform.py
NAVY = "#0B1F4D"
GREY = "#5A6B8C"
TFL_BLUE = "#0019A8"
GOOD, WARN, BAD = "#00A86B", "#F5A623", "#DC241F"  # status colours

# Official TfL line colours, so everything matches the Tube map
LINE_COLOURS = {
    "Bakerloo": "#B36305",
    "Central": "#E32017",
    "Circle": "#FFD300",
    "District": "#00782A",
    "Hammersmith & City": "#F3A9BB",
    "Jubilee": "#A0A5A9",
    "Metropolitan": "#9B0056",
    "Northern": "#000000",
    "Piccadilly": "#003688",
    "Victoria": "#0098D4",
    "Waterloo & City": "#95CDBA",
}

st.set_page_config(page_title="Tube Reliability Tracker", page_icon="🚇", layout="wide")


# ---------------------------------------------------------------- data ----

@st.cache_resource(ttl=900, show_spinner="Loading the latest Tube data...")
def get_database():
    """Build a fresh in-memory database from the raw snapshot files.

    Reuses the pipeline's own load and transform steps, so the app always shows
    exactly what the pipeline produces. Rebuilt at most every 15 minutes.
    """
    db = duckdb.connect(":memory:")
    load.load_new_files(db)
    transform.build_tables(db)
    return db


@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_status():
    """Ask TfL for the current status of every line right now. Cached for 60 seconds."""
    key = os.getenv("TFL_APP_KEY")
    if not key:
        try:
            key = st.secrets["TFL_APP_KEY"]  # used when running on Streamlit Cloud
        except Exception:
            key = None
    params = {"app_key": key} if key else {}
    response = requests.get("https://api.tfl.gov.uk/Line/Mode/tube/Status",
                            params=params, timeout=10)
    response.raise_for_status()

    rows = []
    for line in response.json():
        codes = [s["statusSeverity"] for s in line["lineStatuses"]]
        status = " / ".join(sorted({s["statusSeverityDescription"] for s in line["lineStatuses"]}))
        is_disrupted = any(c not in (10, 18, 19, 20) for c in codes)
        is_severe = any(c in (1, 2, 3, 6, 16) for c in codes)
        rows.append((line["name"], status, is_disrupted, is_severe))
    return sorted(rows), datetime.now(ZoneInfo("Europe/London"))


def london(column):
    """SQL that converts a stored UTC timestamp column to London local time."""
    return f"timezone('Europe/London', {column}::TIMESTAMPTZ)"


def dot(colour):
    """A small coloured circle, used instead of an emoji."""
    return (f'<span style="display:inline-block; width:10px; height:10px; border-radius:50%; '
            f'background:{colour}; margin-right:7px;"></span>')


def card(title, value, note, colour):
    """A small white card with a coloured stripe, used for badges and live status."""
    title_html = (f'<div style="font-size:0.8rem; color:{GREY}; text-transform:uppercase; '
                  f'letter-spacing:0.04em;">{title}</div>') if title else ""
    return (
        f'<div style="background:white; border-left:8px solid {colour}; border-radius:10px; '
        f'padding:12px 16px; margin-bottom:12px; box-shadow:0 1px 4px rgba(0,0,0,0.10);">'
        f'{title_html}'
        f'<div style="font-size:1.25rem; font-weight:700; color:{NAVY};">{value}</div>'
        f'<div style="font-size:0.9rem; color:{NAVY};">{note}</div>'
        f'</div>'
    )


# Each visitor gets their own cursor on the shared database (safe for many users at once).
con = get_database().cursor()
con.execute("SET TimeZone = 'UTC'")  # stored times are UTC

lines = [row[0] for row in con.execute(
    "SELECT DISTINCT line_name FROM line_snapshot ORDER BY line_name").fetchall()]
snapshots, latest = con.execute(
    f"SELECT count(*), max({london('collected_at_utc')}) FROM raw_snapshots").fetchone()

# Live status from TfL, or the latest snapshot if TfL can't be reached
try:
    now_rows, now_time = fetch_live_status()
    now_label = f"Live from TfL, {now_time:%H:%M}"
except Exception:
    now_rows = con.execute("""
        SELECT line_name,
               STRING_AGG(DISTINCT status_description, ' / '),
               BOOL_OR(status_severity NOT IN (10, 18, 19, 20)),
               BOOL_OR(status_severity IN (1, 2, 3, 6, 16))
        FROM stg_line_status
        WHERE collected_at_utc = (SELECT max(collected_at_utc) FROM stg_line_status)
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    now_label = f"Latest snapshot, {latest:%H:%M}"

# ---------------------------------------------------------------- header ----

running_well = sum(1 for row in now_rows if not row[2])
total_lines = len(now_rows)
severe_now = sum(1 for row in now_rows if row[3])

if running_well == total_lines:
    mood, mood_colour, mood_text = "Good", GOOD, "Every line is running well right now."
elif severe_now >= 3:
    mood, mood_colour, mood_text = "Poor", BAD, f"{severe_now} lines have severe problems right now."
elif running_well >= total_lines - 2:
    mood, mood_colour, mood_text = "Good", GOOD, f"{running_well} of {total_lines} lines are running well."
else:
    mood, mood_colour, mood_text = "Mixed", WARN, f"Only {running_well} of {total_lines} lines are running well."

st.markdown(
    f"""
    <div style="background:linear-gradient(135deg, {TFL_BLUE} 0%, #00106B 100%);
                padding:26px 30px; border-radius:14px; margin-bottom:18px;">
      <h1 style="color:white; margin:0;">Tube Reliability Tracker</h1>
      <p style="color:#E6EAF5; margin:6px 0 14px 0;">
        How reliable is each London Underground line? Built from {snapshots} TfL status
        snapshots, collected about every 15 minutes.
      </p>
      <div style="background:rgba(255,255,255,0.12); border-radius:10px; padding:12px 16px;
                  color:white; font-size:1.05rem;">
        <span style="background:{mood_colour}; color:white; font-weight:700; padding:3px 10px;
                     border-radius:20px; margin-right:10px;">Network today: {mood}</span>
        {mood_text}
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------- live board ----

st.subheader(f"Right now  ·  {now_label}")
cols = st.columns(4)
for i, (name, status, is_disrupted, is_severe) in enumerate(now_rows):
    colour = BAD if is_severe else WARN if is_disrupted else GOOD
    cols[i % 4].markdown(card("", name, f"{dot(colour)}{status}", LINE_COLOURS.get(name, TFL_BLUE)),
                         unsafe_allow_html=True)

st.write("")

# ---------------------------------------------------------------- tabs ----

tab_league, tab_check, tab_patterns, tab_log, tab_health, tab_about = st.tabs(
    ["League table", "Should I travel?", "Patterns", "Disruption log", "Pipeline health", "About"]
)

# --- League table -----------------------------------------------------------
with tab_league:
    by_line = con.execute("""
        SELECT line_name AS Line,
               round(100 * avg(is_disrupted::INT), 1) AS "% of time disrupted"
        FROM line_snapshot
        GROUP BY line_name
        ORDER BY 2, 1
    """).df()

    best = by_line.iloc[0]
    worst = by_line.iloc[-1]
    longest = con.execute(f"""
        SELECT line_name, approx_duration_minutes, {london('first_seen_utc')}
        FROM disruption_events
        ORDER BY approx_duration_minutes DESC NULLS LAST
        LIMIT 1
    """).fetchone()

    b1, b2, b3 = st.columns(3)
    b1.markdown(card("Most reliable line", best["Line"],
                     f"Disrupted only {best['% of time disrupted']}% of the time",
                     LINE_COLOURS.get(best["Line"], TFL_BLUE)), unsafe_allow_html=True)
    b2.markdown(card("Least reliable line", worst["Line"],
                     f"Disrupted {worst['% of time disrupted']}% of the time",
                     LINE_COLOURS.get(worst["Line"], TFL_BLUE)), unsafe_allow_html=True)
    if longest and longest[1] is not None:
        b3.markdown(card("Longest disruption", f"{longest[1]} mins",
                         f"{longest[0]} line, from {longest[2]:%a %d %b %H:%M}",
                         LINE_COLOURS.get(longest[0], TFL_BLUE)), unsafe_allow_html=True)
    else:
        b3.markdown(card("Longest disruption", "–", "Not enough data yet", TFL_BLUE),
                    unsafe_allow_html=True)

    st.markdown("##### Which line is disrupted most of the time?")
    st.altair_chart(
        alt.Chart(by_line)
        .mark_bar(stroke=NAVY, strokeWidth=0.5, cornerRadiusEnd=4)
        .encode(
            x=alt.X("% of time disrupted:Q"),
            y=alt.Y("Line:N", sort="-x", title=None),  # worst line at the top
            color=alt.Color("Line:N",
                            scale=alt.Scale(domain=list(LINE_COLOURS),
                                            range=list(LINE_COLOURS.values())),
                            legend=None),
            tooltip=["Line", "% of time disrupted"],
        ),
        use_container_width=True,
    )

# --- Should I travel? -------------------------------------------------------
with tab_check:
    st.markdown("Pick your line and when you usually travel to see what the data says.")
    c1, c2 = st.columns(2)
    check_line = c1.selectbox("Your line", lines, key="check_line")
    check_hour = c2.select_slider("Your usual travel time", options=list(range(24)), value=8,
                                  format_func=lambda h: f"{h:02d}:00")

    n, pct_hour = con.execute(f"""
        SELECT count(*), round(100 * avg(is_disrupted::INT), 1)
        FROM line_snapshot
        WHERE line_name = ? AND hour({london('collected_at_utc')}) = ?
    """, [check_line, check_hour]).fetchone()
    pct_overall = con.execute("""
        SELECT round(100 * avg(is_disrupted::INT), 1) FROM line_snapshot WHERE line_name = ?
    """, [check_line]).fetchone()[0]

    time_label = f"{check_hour:02d}:00"
    if n == 0:
        st.info(f"Not enough data yet for the {check_line} line at {time_label}. Check back soon.")
    else:
        comparison = ("higher than" if pct_hour > pct_overall
                      else "lower than" if pct_hour < pct_overall else "the same as")
        detail = (f"Based on {n} snapshots, the {check_line} line has been disrupted "
                  f"{pct_hour}% of the time around {time_label}, {comparison} its overall {pct_overall}%.")
        if pct_hour == 0:
            st.success(f"**Go for it.** No disruptions recorded so far. {detail}")
        elif pct_hour < 15:
            st.success(f"**Usually reliable.** {detail}")
        elif pct_hour < 40:
            st.warning(f"**Sometimes disrupted.** Check TfL before you leave. {detail}")
        else:
            st.error(f"**Often disrupted.** Consider leaving early or another route. {detail}")
        if n < 8:
            st.caption("Early estimate: only a few snapshots for this hour so far. "
                       "It gets more reliable as more data is collected.")

# --- Patterns ---------------------------------------------------------------
with tab_patterns:
    selected = st.selectbox("Choose a line", ["All lines"] + lines)
    LINE_FILTER = "(? = 'All lines' OR line_name = ?)"
    params = [selected, selected]
    accent = LINE_COLOURS.get(selected, TFL_BLUE)

    events = con.execute(
        f"SELECT count(*) FROM disruption_events WHERE {LINE_FILTER}", params).fetchone()[0]
    pct_disrupted = con.execute(
        f"SELECT round(100 * avg(is_disrupted::INT), 1) FROM line_snapshot WHERE {LINE_FILTER}",
        params).fetchone()[0]

    m1, m2, m3 = st.columns(3)
    m1.metric("Disruptions found", events)
    m2.metric("Time disrupted", f"{pct_disrupted}%")
    m3.metric("History updated", f"{latest:%d %b %H:%M}")

    left, right = st.columns(2)
    with left:
        st.markdown(f"##### When are disruptions most likely? ({selected})")
        by_hour = con.execute(f"""
            SELECT hour({london('collected_at_utc')}) AS "Hour of day",
                   round(100 * avg(is_disrupted::INT), 1) AS "% of time disrupted"
            FROM line_snapshot WHERE {LINE_FILTER}
            GROUP BY 1 ORDER BY 1
        """, params).df()
        st.altair_chart(
            alt.Chart(by_hour).mark_bar(color=accent, cornerRadiusEnd=3)
            .encode(x=alt.X("Hour of day:O"), y=alt.Y("% of time disrupted:Q"),
                    tooltip=["Hour of day", "% of time disrupted"]),
            use_container_width=True,
        )
    with right:
        st.markdown(f"##### Most common problems ({selected})")
        by_status = con.execute(f"""
            SELECT status_description AS Status, count(*) AS Snapshots
            FROM stg_line_status
            WHERE status_severity NOT IN {NORMAL_CODES} AND {LINE_FILTER}
            GROUP BY 1
        """, params).df()
        if by_status.empty:
            st.info("No disruptions recorded for this line yet.")
        else:
            st.altair_chart(
                alt.Chart(by_status).mark_bar(color=accent, cornerRadiusEnd=3)
                .encode(x=alt.X("Snapshots:Q", title="Number of snapshots"),
                        y=alt.Y("Status:N", sort="-x", title=None),
                        tooltip=["Status", "Snapshots"]),
                use_container_width=True,
            )

# --- Disruption log ---------------------------------------------------------
with tab_log:
    log_line = st.selectbox("Show disruptions for", ["All lines"] + lines, key="log_line")
    all_events = con.execute(f"""
        SELECT line_name, disruption_type, {london('first_seen_utc')} AS started,
               approx_duration_minutes, still_ongoing, statuses, reasons
        FROM disruption_events
        WHERE (? = 'All lines' OR line_name = ?)
        ORDER BY first_seen_utc DESC
    """, [log_line, log_line]).df()

    st.dataframe(
        all_events,
        hide_index=True,
        use_container_width=True,
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
    st.download_button("Download as CSV", all_events.to_csv(index=False),
                       file_name="tube_disruptions.csv", mime="text/csv")

# --- Pipeline health --------------------------------------------------------
with tab_health:
    st.markdown("How the data pipeline behind this app is doing.")

    minutes_old, gaps, first_seen = con.execute(f"""
        WITH s AS (
            SELECT collected_at_utc,
                   collected_at_utc - LAG(collected_at_utc) OVER (ORDER BY collected_at_utc) AS gap
            FROM raw_snapshots
        )
        SELECT date_diff('minute', max(collected_at_utc), now()::TIMESTAMP),
               count(*) FILTER (WHERE gap > INTERVAL 60 MINUTE),
               min({london('collected_at_utc')})
        FROM s
    """).fetchone()

    healthy = minutes_old <= 45
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Collection status", "Healthy" if healthy else "Delayed")
    h2.metric("Last snapshot", f"{minutes_old} mins ago")
    h3.metric("Gaps over 1 hour", gaps)
    h4.metric("Collecting since", f"{first_seen:%d %b %H:%M}")

    st.markdown("##### Snapshots collected per day (target: 96, one every 15 minutes)")
    per_day = con.execute(f"""
        SELECT strftime(CAST({london('collected_at_utc')} AS DATE), '%a %d %b') AS Day,
               count(*) AS Snapshots
        FROM raw_snapshots
        GROUP BY CAST({london('collected_at_utc')} AS DATE)
        ORDER BY CAST({london('collected_at_utc')} AS DATE)
    """).df()
    target = alt.Chart().mark_rule(color=GREY, strokeDash=[4, 4]).encode(y=alt.datum(96))
    bars = alt.Chart().mark_bar(color=TFL_BLUE, cornerRadiusEnd=3).encode(
        x=alt.X("Day:N", sort=None, title=None),
        y=alt.Y("Snapshots:Q"),
        tooltip=["Day", "Snapshots"],
    )
    st.altair_chart(alt.layer(bars, target, data=per_day), use_container_width=True)

    st.markdown("##### Data quality checks")
    results = []
    for name, sql in checks.CHECKS.items():
        bad_rows = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        results.append({"Check": name,
                        "Result": "Pass" if bad_rows == 0 else f"Fail ({bad_rows} problem rows)"})
    st.dataframe(results, hide_index=True, use_container_width=True)

    st.caption("Early days show fewer snapshots because GitHub's built-in scheduler skipped "
               "many runs. Since adding cron-job.org as an external trigger, collection "
               "runs every 15 minutes.")

# --- About ------------------------------------------------------------------
with tab_about:
    st.markdown(f"""
**Why not just check the TfL website?** TfL shows what's happening right now, but
disruptions disappear once fixed and no history is published. This app collects the
status every 15 minutes to build that history, so it can show which lines are least
reliable, when problems happen and how long they last.

**Where the data comes from:** the TfL Unified API (powered by TfL Open Data).

**How it works:** a snapshot of every Tube line's status is collected about every
15 minutes. Snapshots are turned into **disruption events** with a start time,
approximate duration and TfL's reason. So far: **{snapshots} snapshots**.

**What counts as a disruption:** any status except Good Service, No Issues,
Information, or Service Closed (the normal overnight closure).

**Limits to keep in mind:**
- Times are approximate, because snapshots are about 15 minutes apart.
- Early days of the project have gaps in the data.
- Percentages for a single hour are less reliable when based on only a few snapshots.

**"Right now"** comes straight from TfL when you open the page (refreshed at most once a minute).
""")

con.close()