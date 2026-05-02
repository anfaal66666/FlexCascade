#!/usr/bin/env python3
"""Final version: smart streaming with real-time progress."""

import argparse, bz2, csv, pathlib, sys, gzip, time
csv.field_size_limit(int(1e9))

def log(m):
    print(m, flush=True)
    sys.stdout.flush()

def s(v):
    return (v or "").strip()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", default="data/courtlistener")
    p.add_argument("--output", required=True)
    p.add_argument("--rows", type=int, default=30000, help="Output rows to write")
    p.add_argument("--max-dockets", type=int, default=None, help="Max dockets to load (None = all)")
    p.add_argument("--max-opinions", type=int, default=None, help="Max opinions to load (None = all)")
    return p.parse_args()

def latest(d, prefix):
    m = sorted(d.glob(f"{prefix}-*.csv.bz2"))
    return m[-1] if m else None

def main():
    args = parse_args()
    d = pathlib.Path(args.input_dir)
    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Load courts
    log("Loading courts...")
    courts = {}
    with bz2.open(latest(d, "courts"), "rt", errors="ignore") as f:
        for r in csv.DictReader(f):
            try:
                cid = s(r.get("id"))
                if cid:
                    courts[cid] = {
                        "issuer": s(r.get("full_name") or r.get("short_name")),
                        "state": s(r.get("jurisdiction")).lower(),
                    }
            except: pass
    log(f"  ✓ Loaded {len(courts):,} courts")

    # Load dockets
    log(f"Loading dockets{f' (max {args.max_dockets:,})' if args.max_dockets else ''}...")
    dockets = {}
    with bz2.open(latest(d, "dockets"), "rt", errors="ignore") as f:
        for i, r in enumerate(csv.DictReader(f)):
            try:
                if args.max_dockets and i >= args.max_dockets:
                    break
                if i % 1000000 == 0 and i: log(f"  Scanned {i:,} dockets...")
                did = s(r.get("id"))
                if did:
                    dockets[did] = {
                        "court_id": s(r.get("court_id")),
                        "docket_number": s(r.get("docket_number") or r.get("docket_number_core")),
                        "date_filed": s(r.get("date_filed")),
                    }
            except: pass
    log(f"  ✓ Loaded {len(dockets):,} dockets\n")

    # Find clusters that have valid dockets
    log("Pass 1: Finding valid clusters...")
    needed_clusters = set()
    with bz2.open(latest(d, "opinion-clusters"), "rt", errors="ignore") as f:
        for i, r in enumerate(csv.DictReader(f)):
            try:
                if i % 1000000 == 0 and i: log(f"  Scanned {i:,} clusters...")
                cid = s(r.get("id"))
                did = s(r.get("docket_id"))
                if cid and did and did in dockets:
                    needed_clusters.add(cid)
            except: pass
    log(f"  ✓ Found {len(needed_clusters):,} valid clusters\n")

    # Load only matching opinions
    log(f"Pass 2: Loading matching opinions{f' (max {args.max_opinions:,})' if args.max_opinions else ''}...")
    opinions = {}
    with bz2.open(latest(d, "opinions"), "rt", errors="ignore") as f:
        for i, r in enumerate(csv.DictReader(f)):
            try:
                if args.max_opinions and i >= args.max_opinions:
                    break
                if i % 10000000 == 0 and i: log(f"  Scanned {i:,}, found {len(opinions):,}...")
                cid = s(r.get("cluster_id"))
                if cid in needed_clusters and cid not in opinions:
                    text = s(r.get("plain_text") or r.get("html_with_citations") or r.get("html_lawbox") or r.get("html_columbia") or r.get("html"))
                    if text:
                        opinions[cid] = text
            except: pass
    log(f"  ✓ Found {len(opinions):,} matching opinions\n")

    # Write complete rows
    limit_text = f"{args.rows:,} rows" if args.rows > 0 else "all possible rows"
    log(f"Pass 3: Writing {limit_text}...")
    written = 0
    with gzip.open(out, "wt", encoding="utf-8", newline="") as of:
        writer = csv.DictWriter(of, fieldnames=["id", "title", "citation", "docket_number", "state", "issuer", "document", "timestamp"])
        writer.writeheader()

        with bz2.open(latest(d, "opinion-clusters"), "rt", errors="ignore") as f:
            for i, r in enumerate(csv.DictReader(f)):
                try:
                    if i % 500000 == 0 and i:
                        progress = f"{written:,}/{args.rows:,}" if args.rows > 0 else f"{written:,}"
                        log(f"  Checked {i:,} clusters → written {progress} rows...")

                    cid = s(r.get("id"))
                    did = s(r.get("docket_id"))

                    if cid not in opinions or did not in dockets:
                        continue

                    docket = dockets[did]
                    court = courts.get(docket["court_id"])
                    if not court or not court["state"] or not court["issuer"]:
                        continue

                    writer.writerow({
                        "id": cid,
                        "title": s(r.get("case_name_full") or r.get("case_name") or r.get("case_name_short")),
                        "citation": "",
                        "docket_number": docket["docket_number"],
                        "state": court["state"],
                        "issuer": court["issuer"],
                        "document": opinions[cid],
                        "timestamp": s(r.get("date_filed") or r.get("date_created")) or docket["date_filed"] or "",
                    })
                    written += 1
                    if args.rows > 0 and written >= args.rows:
                        log(f"\n✓ Wrote {args.rows:,} rows to {out}\n")
                        return 0
                except: pass

    log(f"\n✓ Wrote {written:,} rows to {out}\n")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"Error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
