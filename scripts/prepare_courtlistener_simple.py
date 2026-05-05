#!/usr/bin/env python3
"""Simple CourtListener data preparation - streaming to avoid memory issues."""

import argparse
import bz2
import csv
import pathlib
import sys
import gzip

csv.field_size_limit(int(1e9))  # Allow large fields (legal documents can be huge)

def s(val):
    """Safe string conversion and strip."""
    return (val or "").strip()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/courtlistener")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--states", nargs="*", default=None)
    parser.add_argument("--require-state", action="store_true", default=True)
    return parser.parse_args()

def latest_file(input_dir: pathlib.Path, prefix: str) -> pathlib.Path:
    matches = sorted(input_dir.glob(f"{prefix}-*.csv.bz2"))
    if not matches:
        raise FileNotFoundError(f"Missing {prefix}-*.csv.bz2 in {input_dir}")
    return matches[-1]

def main():
    args = parse_args()
    input_dir = pathlib.Path(args.input_dir)
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    courts_path = latest_file(input_dir, "courts")
    dockets_path = latest_file(input_dir, "dockets")
    clusters_path = latest_file(input_dir, "opinion-clusters")
    opinions_path = latest_file(input_dir, "opinions")

    print("Loading courts...")
    courts_map = {}
    with bz2.open(courts_path, "rt", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                court_id = s(row.get("id"))
                if court_id:
                    courts_map[court_id] = {
                        "issuer": s(row.get("full_name") or row.get("short_name")),
                        "state": s(row.get("jurisdiction")).lower(),
                    }
            except:
                pass
    print(f"  Loaded {len(courts_map):,} courts")

    print("First pass: collecting needed cluster/docket IDs...")
    needed_docket_ids = set()
    clusters_data = {}
    rows_seen = 0

    with bz2.open(clusters_path, "rt", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows_seen += 1
                if rows_seen % 100000 == 0:
                    print(f"  Processed {rows_seen:,} clusters...")

                cluster_id = s(row.get("id"))
                docket_id = s(row.get("docket_id"))

                if cluster_id and docket_id:
                    title = s(row.get("case_name_full") or row.get("case_name") or row.get("case_name_short"))
                    timestamp = s(row.get("date_filed") or row.get("date_created"))

                    clusters_data[cluster_id] = {
                        "docket_id": docket_id,
                        "title": title,
                        "timestamp": timestamp,
                    }
                    needed_docket_ids.add(docket_id)
            except:
                pass

    print(f"  Found {len(clusters_data):,} clusters, need {len(needed_docket_ids):,} dockets")

    print("Second pass: loading needed dockets...")
    dockets_map = {}
    rows_seen = 0

    with bz2.open(dockets_path, "rt", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows_seen += 1
                if rows_seen % 100000 == 0:
                    print(f"  Scanned {rows_seen:,} dockets, kept {len(dockets_map):,}...")

                docket_id = s(row.get("id"))
                if docket_id in needed_docket_ids:
                    dockets_map[docket_id] = {
                        "court_id": s(row.get("court_id")),
                        "docket_number": s(row.get("docket_number") or row.get("docket_number_core")),
                        "date_filed": s(row.get("date_filed")),
                    }
            except:
                pass

    print(f"  Loaded {len(dockets_map):,} dockets")

    print("Third pass: collecting needed opinions...")
    needed_cluster_ids = {cid for cid in clusters_data if dockets_map.get(clusters_data[cid]["docket_id"])}
    opinions_map = {}
    rows_seen = 0

    with bz2.open(opinions_path, "rt", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows_seen += 1
                if rows_seen % 1000000 == 0:
                    print(f"  Scanned {rows_seen:,} opinions, kept {len(opinions_map):,}...")

                cluster_id = s(row.get("cluster_id"))
                if cluster_id in needed_cluster_ids and cluster_id not in opinions_map:
                    text = s(
                        row.get("plain_text") or
                        row.get("html_with_citations") or
                        row.get("html_lawbox") or
                        row.get("html_columbia") or
                        row.get("html")
                    )
                    if text:
                        opinions_map[cluster_id] = text
            except:
                pass

    print(f"  Found {len(opinions_map):,} opinions")

    print("Fourth pass: combining and writing output...")
    rows_written = 0

    with gzip.open(output_path, "wt", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(
            out_f,
            fieldnames=["id", "title", "citation", "docket_number", "state", "issuer", "document", "timestamp"],
        )
        writer.writeheader()

        for cluster_id, cluster in clusters_data.items():
            if cluster_id not in opinions_map:
                continue

            docket = dockets_map.get(cluster["docket_id"])
            if not docket:
                continue

            court = courts_map.get(docket["court_id"])
            if not court:
                continue

            state = court["state"]
            if args.require_state and not state:
                continue

            if args.states and state not in args.states:
                continue

            issuer = court["issuer"]
            if not issuer:
                continue

            writer.writerow({
                "id": cluster_id,
                "title": cluster["title"],
                "citation": "",
                "docket_number": docket["docket_number"],
                "state": state,
                "issuer": issuer,
                "document": opinions_map[cluster_id],
                "timestamp": cluster["timestamp"] or docket["date_filed"] or "",
            })
            rows_written += 1

            if args.max_rows and rows_written >= args.max_rows:
                break

    print(f"\n✓ Wrote {rows_written:,} rows to {output_path}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
