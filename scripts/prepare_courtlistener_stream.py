#!/usr/bin/env python3
"""Stream-based CourtListener prep - no massive memory loads."""

import argparse
import bz2
import csv
import pathlib
import sys
import gzip

csv.field_size_limit(int(1e9))

def s(val):
    return (val or "").strip()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/courtlistener")
    parser.add_argument("--output", required=True)
    parser.add_argument("--rows", type=int, default=30000)
    return parser.parse_args()

def latest_file(input_dir: pathlib.Path, prefix: str) -> pathlib.Path:
    matches = sorted(input_dir.glob(f"{prefix}-*.csv.bz2"))
    return matches[-1] if matches else None

def main():
    args = parse_args()
    input_dir = pathlib.Path(args.input_dir)
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    courts_path = latest_file(input_dir, "courts")
    dockets_path = latest_file(input_dir, "dockets")
    clusters_path = latest_file(input_dir, "opinion-clusters")
    opinions_path = latest_file(input_dir, "opinions")

    # Load courts (small)
    print("Loading courts...")
    courts_map = {}
    with bz2.open(courts_path, "rt", encoding="utf-8", errors="ignore") as f:
        for row in csv.DictReader(f):
            try:
                court_id = s(row.get("id"))
                if court_id:
                    courts_map[court_id] = {
                        "issuer": s(row.get("full_name") or row.get("short_name")),
                        "state": s(row.get("jurisdiction")).lower(),
                    }
            except:
                pass
    print(f"  Loaded {len(courts_map):,} courts\n")

    # Load dockets (medium)
    print("Loading dockets...")
    dockets_map = {}
    with bz2.open(dockets_path, "rt", encoding="utf-8", errors="ignore") as f:
        for i, row in enumerate(csv.DictReader(f)):
            try:
                if i % 10000000 == 0 and i > 0:
                    print(f"  Read {i:,} dockets...", flush=True)
                docket_id = s(row.get("id"))
                if docket_id:
                    dockets_map[docket_id] = {
                        "court_id": s(row.get("court_id")),
                        "docket_number": s(row.get("docket_number") or row.get("docket_number_core")),
                        "date_filed": s(row.get("date_filed")),
                    }
            except:
                pass
    print(f"  Loaded {len(dockets_map):,} dockets\n")

    # Pre-load opinions into dict (keyed by cluster_id for fast lookup)
    print("Pre-loading opinions...")
    opinions_map = {}
    with bz2.open(opinions_path, "rt", encoding="utf-8", errors="ignore") as f:
        for i, row in enumerate(csv.DictReader(f)):
            try:
                if i % 50000000 == 0 and i > 0:
                    print(f"  Read {i:,} opinions, keeping {len(opinions_map):,}...", flush=True)
                cluster_id = s(row.get("cluster_id"))
                if cluster_id and cluster_id not in opinions_map:
                    text = s(row.get("plain_text") or row.get("html_with_citations") or row.get("html_lawbox") or row.get("html_columbia") or row.get("html"))
                    if text:
                        opinions_map[cluster_id] = text
            except:
                pass
    print(f"  Loaded {len(opinions_map):,} opinions\n")

    # Stream through clusters, write complete rows
    print(f"Combining and writing {args.rows:,} rows...")
    rows_written = 0
    with gzip.open(output_path, "wt", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(
            out_f,
            fieldnames=["id", "title", "citation", "docket_number", "state", "issuer", "document", "timestamp"],
        )
        writer.writeheader()

        with bz2.open(clusters_path, "rt", encoding="utf-8", errors="ignore") as f:
            for i, row in enumerate(csv.DictReader(f)):
                try:
                    if i % 5000000 == 0 and i > 0:
                        print(f"  Checked {i:,} clusters, written {rows_written:,}...", flush=True)

                    cluster_id = s(row.get("id"))
                    docket_id = s(row.get("docket_id"))

                    # Quick checks
                    if not cluster_id or not docket_id:
                        continue
                    if cluster_id not in opinions_map:
                        continue

                    docket = dockets_map.get(docket_id)
                    if not docket:
                        continue

                    court = courts_map.get(docket["court_id"])
                    if not court or not court["state"] or not court["issuer"]:
                        continue

                    # Write complete row
                    writer.writerow({
                        "id": cluster_id,
                        "title": s(row.get("case_name_full") or row.get("case_name") or row.get("case_name_short")),
                        "citation": "",
                        "docket_number": docket["docket_number"],
                        "state": court["state"],
                        "issuer": court["issuer"],
                        "document": opinions_map[cluster_id],
                        "timestamp": s(row.get("date_filed") or row.get("date_created")) or docket["date_filed"] or "",
                    })
                    rows_written += 1

                    if rows_written >= args.rows:
                        print(f"\n✓ Reached {args.rows:,} rows!\n")
                        break
                except Exception as e:
                    pass

    print(f"✓ Wrote {rows_written:,} rows to {output_path}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
