"""Collect the current status of every Tube line from the TfL API
and save the raw response, unchanged, as a timestamped JSON file."""

import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

API_URL = "https://api.tfl.gov.uk/Line/Mode/tube/Status"
RAW_DIR = Path("data/raw/line_status")


def fetch_line_status(app_key):
    """Call the TfL API and return the raw response text."""
    response = requests.get(API_URL, params={"app_key": app_key}, timeout=30)
    response.raise_for_status()  # stop with an error if TfL didn't return success
    return response.text


def save_raw(text, collected_at):
    """Save the raw response in a folder per day, named by collection time (UTC)."""
    folder = RAW_DIR / collected_at.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"line_status_{collected_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(text, encoding="utf-8")
    return path


def main():
    load_dotenv()
    app_key = os.getenv("TFL_APP_KEY")
    if not app_key:
        raise SystemExit("TFL_APP_KEY is missing. Add it to your .env file.")

    collected_at = datetime.now(timezone.utc)
    text = fetch_line_status(app_key)
    path = save_raw(text, collected_at)
    print(f"Saved {path}")


if __name__ == "__main__":
    main()