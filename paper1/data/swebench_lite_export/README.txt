SWE-bench Lite Dataset Export
================================

Source: https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite
Downloaded: 2026-05-26

Files in this directory:
------------------------
test.parquet  (1.1 MB)  - Test split, 300 instances, Apache Parquet format
dev.parquet   (104 KB)  - Dev split, 23 instances, Apache Parquet format
test.jsonl    (2.6 MB)  - Test split as JSON Lines (one JSON object per line)
dev.jsonl     (264 KB)  - Dev split as JSON Lines

Columns (all splits):
---------------------
  repo                      - GitHub repo (e.g., "django/django")
  instance_id               - Unique instance ID
  base_commit               - Base commit SHA before fix
  patch                     - Ground-truth patch (diff)
  test_patch                - Test patch to validate the fix
  problem_statement         - Issue description
  hints_text                - Optional hints
  created_at                - Timestamp
  version                   - Dataset version
  FAIL_TO_PASS              - Tests that should pass after fix
  PASS_TO_PASS              - Tests that should still pass
  environment_setup_commit  - Environment setup commit

How to read on Linux (recommended methods):
-------------------------------------------

Python (JSONL - easiest):
  import pandas as pd
  df = pd.read_json("test.jsonl", lines=True)
  print(df.head())

Python (Parquet - smaller file, faster):
  import pandas as pd
  df = pd.read_parquet("test.parquet")
  print(df.head())

Command line:
  head -5 test.jsonl | python3 -m json.tool --no-ensure-ascii  # view first 5
  wc -l test.jsonl                                             # count rows

SQL-like queries with DuckDB:
  duckdb -c "SELECT repo, count(*) FROM 'test.parquet' GROUP BY repo"

scp to Linux machine:
  scp -r swebench_lite_export user@linux-machine:~/path/
