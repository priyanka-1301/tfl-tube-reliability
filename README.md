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
cron-job.org ──▶ GitHub Actions ──▶ collect.py ──▶ raw JSON files ──▶ load.py ──▶ DuckDB ──▶ transform.py ──▶ checks.py ──▶ app.py
(every 15 mins)   (runs the job)     (calls TfL)    (saved unchanged)                       (clean tables)   (quality)    (Streamlit)
```

1. **Collect** (`collect.py`): calls the API and saves the raw response **unchanged**
   as a JSON file named with the UTC collection time. A GitHub Actions workflow
   (`.github/workflows/collect.yml`) runs this every 15 minutes and commits each new
   file to the repo.
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
5. **App** (`app.py`): a Streamlit app where you can choose a line and see:
   - which lines are disrupted for the largest share of the time
   - which hours of the day disruptions are most likely
   - the most common types of problem (e.g. Minor Delays, Severe Delays)
   - every disruption event, with its start time, approximate duration and TfL's reason

`pipeline.py` runs steps 2 to 4 with one command.

## Key decisions

- **Raw data is kept unchanged**, so the database can always be rebuilt from scratch
  if the cleaning logic changes. The DuckDB file itself is not committed.
- **Times are stored in UTC** to avoid problems when the clocks change, and are only
  converted to London time when shown in the app.
- **What counts as a disruption:** any status except Good Service (10), No Issues (18),
  Information (19) and Service Closed (20, normal overnight closure). These codes were
  chosen after profiling the real data.
- **Reliable scheduling:** GitHub Actions' built-in scheduler skipped most runs
  (only 12 of about 190 expected over two days), so I added **cron-job.org** as an
  external trigger. It calls GitHub's API every 15 minutes to start the workflow,
  using a fine-grained token that can only run workflows in this repo. The GitHub
  schedule is kept as a backup, and `concurrency` stops two runs overlapping.
  If snapshots are still more than 60 minutes apart, a disruption isn't assumed
  to have continued through the gap, so durations are never overstated.
- **Fast collection runs:** the workflow installs only the two packages the collector
  needs (`requests`, `python-dotenv`), which cut a run from over 30 minutes to about
  20 seconds.
- **"% of time disrupted" as the main measure:** counting disruption events alone
  would treat a 3-hour disruption the same as a 10-minute one, so the app ranks lines
  by the share of snapshots in which they were disrupted.
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
- Early in the project GitHub Actions skipped many scheduled runs, so the first days
  of data have gaps.
- Only Tube lines are included (not buses, DLR or Overground).

## Future improvements

- Host the app online (e.g. Streamlit Community Cloud) so it updates automatically
- Add other modes such as the Elizabeth line, DLR and Overground
- Show disruptions by day of the week as more data builds up
- Categorise free-text reasons (e.g. signal failure, staff shortage, customer incident)

## Resources

- **University course materials:** teaching and examples from my studies at the
  University of Greenwich, which I drew on for the Python and SQL techniques used here
- **TfL API Portal** (api-portal.tfl.gov.uk): to register for an API key and find the
  line status endpoint
- **Python.org:** to download Python 3.13
- **Visual Studio Code:** code editor
- **GitHub and GitHub Actions:** version control, and running the collector
- **cron-job.org:** triggering the collector reliably every 15 minutes

## How AI helped


-GitHub Copilot in VS Code suggested code completions as I typed.

-Grammarly checked the spelling and grammar of this README..

I made the decisions about the topic, the app and how to handle problems. For example,
when DuckDB wouldn't install on Python 3.15, I switched to Python 3.13; when I noticed
GitHub was skipping most scheduled runs, I measured the problem and added a reliable
external trigger; and I profiled the real status codes before deciding what counts as
a disruption. I can explain how every part of the pipeline works.