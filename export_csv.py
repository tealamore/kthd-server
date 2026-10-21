"""Export one row per decision (with its reward, if any) to CSV for analysis.

Usage: python export_csv.py [path/to/jitai.db] [out.csv]
Context keys are flattened into columns prefixed with ctx_.
"""
import csv
import json
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "data/jitai.db"
out_path = sys.argv[2] if len(sys.argv) > 2 else "decisions_export.csv"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """SELECT d.decision_id, d.participant_id, d.occurred_at, d.received_at, d.available,
              d.arm, d.probability, d.policy_version, d.context,
              r.reward, r.occurred_at AS reward_occurred_at
       FROM decisions d LEFT JOIN rewards r ON r.decision_id = d.decision_id
       ORDER BY d.participant_id, d.received_at"""
).fetchall()

records, ctx_keys = [], []
for row in rows:
    rec = dict(row)
    ctx = json.loads(rec.pop("context"))
    for k, v in ctx.items():
        col = f"ctx_{k}"
        if col not in ctx_keys:
            ctx_keys.append(col)
        rec[col] = json.dumps(v) if isinstance(v, (dict, list)) else v
    records.append(rec)

base_cols = ["decision_id", "participant_id", "occurred_at", "received_at", "available", "arm",
             "probability", "policy_version", "reward", "reward_occurred_at"]
with open(out_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=base_cols + ctx_keys)
    writer.writeheader()
    writer.writerows(records)

print(f"Wrote {len(records)} decisions to {out_path}")
