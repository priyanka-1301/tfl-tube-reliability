# 🚇 Tube Reliability Tracker

How reliable is each London Underground line? TfL only publishes the **current**
status of each line, not a history. This project builds that history itself by
collecting a snapshot of every Tube line's status about every 15 minutes, then
turns those snapshots into individual **disruption events** with a start time,
duration and reason.

**Audience:** London commuters who want to know which lines are least reliable,
when disruptions usually happen, and why.

## Data source

- **TfL Unified API**, endpoint `/Line/Mode/tube/Status`
  (free, open data, powered by TfL Open Data)
- Authentication with a free app key (raises the rate limit from 50 to 500 requests per minute)
- The API returns **live status only**, so history has to be collected over time

## How the pipeline works

```
TfL API ──▶ collect.py ──▶ raw JSON files ──▶ load.py ──▶ DuckDB ──▶ transform.py ──▶ checks.py ──▶ app.py
          (every ~15 mins,   (saved unchanged)                       (clean tables)   (quality)    (Streamlit)
           GitHub Actions)
```

1. **Collect** (`collect.py`): calls the API and saves the raw response **unchanged**
   as a JSON file named with the UTC collection time. GitHub Actions runs this on a
   schedule and commits each new file to the repo.
2. **Load** (`load.py`): loads new raw files into the `raw_snapshots` table in DuckDB.
   Files already loaded are skipped, and `file_name` is a primary key, so re-running
   never creates duplicates.
3. **Transform** (`transform.py`): builds three tables from the raw data:
   - `stg_line_status`: the JSON unpacked, one row per line, per status, per snapshot
     (a line can have more than one status at once)
   - `line_snapshot`: one row per line per snapshot, with an `is_disrupted` flag
   - `disruption_events`: consecutive disrupted snapshots merged into single events
     using a "gaps and islands" approach
4. **Check** (`checks.py`): data quality checks (no missing values, no duplicates,
   all 11 lines in every snapshot, no negative durations). The pipeline stops if any fail.
5. **App** (`app.py`): a Streamlit app showing which lines are disrupted most and
   every disruption event.

## Key decisions

- **Raw data is kept unchanged**, so the database can always be rebuilt from scratch
  if the cleaning logic changes. The DuckDB file itself is not committed.
- **Times are stored in UTC** to avoid problems when the clocks change.
- **What counts as a disruption:** any status except Good Service (10), No Issues (18),
  Information (19) and Service Closed (20, normal overnight closure). These codes were
  chosen after profiling the real data.
- **Gaps in collection:** GitHub Actions scheduled runs are not guaranteed and can be
  delayed or skipped. If snapshots are more than 60 minutes apart, a disruption is not
  assumed to have continued through the gap, so durations are never overstated.
- **Python 3.13** is used because DuckDB did not yet have a ready-made installer for
  Python 3.15.

## How to run it

```bash
git clone https://github.com/priyanka-1301/tfl-tube-reliability.git
cd tfl-tube-reliability
python -m venv .venv
.venv\Scripts\activate          # Windows (use source .venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
```

Create a `.env` file with your free TfL key (from https://api-portal.tfl.gov.uk):

```
TFL_APP_KEY=your-key-here
```

Then:

```bash
python collect.py     # optional: collect a fresh snapshot
python pipeline.py    # load, transform and check all snapshots
streamlit run app.py  # open the app
```

## Limitations

- Snapshots are roughly every 15 minutes, so start and end times are approximate.
- GitHub Actions can skip scheduled runs, which leaves gaps in the data.
- Only Tube lines are included (not buses, DLR or Overground).

## Future improvements

- Host the app online (e.g. Streamlit Community Cloud) so it updates automatically
- Add other modes such as the Elizabeth line, DLR and Overground
- Show disruptions by time of day and day of week
- Categorise free-text reasons (e.g. signal failure, staff shortage, customer incident)
- Send an alert when a chosen line becomes disrupted

## Resources

University course materials: teaching and examples from my studies at the University of Greenwich, which I drew on for the Python and SQL techniques used here
TfL API Portal (api-portal.tfl.gov.uk): to register for an API key and find the line status endpoint
Python.org: to download Python 3.13
Visual Studio Code: code editor
GitHub and GitHub Actions: version control, and running the collector on a schedule.
## How Ai helped


-GitHub Copilot in VS Code suggested code completions as I typed.

-Grammarly checked the spelling and grammar of this README.