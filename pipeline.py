"""Run the whole pipeline with one command:  python pipeline.py

  1. Load    - new raw snapshot files into DuckDB
  2. Transform - build the staging, snapshot and disruption event tables
  3. Check   - run data quality checks, and stop with an error if any fail
"""

import sys

import checks
import load
import transform


def main():
    print("Step 1/3: Loading raw snapshots")
    load.main()

    print("\nStep 2/3: Transforming")
    transform.main()

    print("\nStep 3/3: Running data quality checks")
    failures = checks.main()

    if failures:
        sys.exit(f"\nPipeline stopped: {failures} check(s) failed")
    print("\nPipeline finished successfully")


if __name__ == "__main__":
    main()