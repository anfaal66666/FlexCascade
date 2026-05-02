#!/usr/bin/env python3
"""Prepare a flat CourtListener case-law table for the R training pipeline.

Fully DuckDB-based pipeline for efficient processing of 50GB+ datasets.
Replaces all Python CSV scanning with native DuckDB reads and SQL joins.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

import duckdb
import pandas as pd
from typing import Iterable

STATE_NAMES = [
    "Alabama",
    "Alaska",
    "Arizona",
    "Arkansas",
    "California",
    "Colorado",
    "Connecticut",
    "Delaware",
    "District of Columbia",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Illinois",
    "Indiana",
    "Iowa",
    "Kansas",
    "Kentucky",
    "Louisiana",
    "Maine",
    "Maryland",
    "Massachusetts",
    "Michigan",
    "Minnesota",
    "Mississippi",
    "Missouri",
    "Montana",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Ohio",
    "Oklahoma",
    "Oregon",
    "Pennsylvania",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Utah",
    "Vermont",
    "Virginia",
    "Washington",
    "West Virginia",
    "Wisconsin",
    "Wyoming",
]
STATE_TO_SLUG = {name: name.lower().replace(" ", "-") for name in STATE_NAMES}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/courtlistener")
    parser.add_argument("--output", required=True)
    parser.add_argument("--aggregate-level", choices=("cluster", "opinion"), default="cluster")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--sample-frac", type=float, default=None)
    parser.add_argument("--states", nargs="*", default=None)
    parser.add_argument("--top-n-states", type=int, default=None)
    parser.add_argument("--include-states", nargs="*", default=None)
    parser.add_argument("--require-state", action="store_true")
    return parser.parse_args()


def latest_file(input_dir: pathlib.Path, prefix: str) -> pathlib.Path:
    matches = sorted(input_dir.glob(f"{prefix}-*.csv.bz2"))
    if not matches:
        raise FileNotFoundError(f"Missing {prefix}-*.csv.bz2 in {input_dir}")
    return matches[-1]


def derive_state_slug(row: pd.Series) -> str:
    text = " ".join(
        [
            str(row.get("full_name") or ""),
            str(row.get("short_name") or ""),
            str(row.get("citation_string") or ""),
            str(row.get("url") or ""),
        ]
    )
    lowered = text.lower()
    for state_name, slug in STATE_TO_SLUG.items():
        if state_name.lower() in lowered:
            return slug
    return ""


def build_courts_table(path: pathlib.Path) -> pd.DataFrame:
    courts = pd.read_csv(
        path,
        compression="bz2",
        dtype=str,
        usecols=[
            "id",
            "short_name",
            "full_name",
            "url",
            "jurisdiction",
            "citation_string",
            "parent_court_id",
        ],
    ).fillna("")
    courts["issuer"] = courts["full_name"].where(courts["full_name"] != "", courts["short_name"])
    courts["state"] = courts.apply(derive_state_slug, axis=1)
    courts["jurisdiction"] = courts["jurisdiction"].str.strip()
    return courts[["id", "issuer", "state", "jurisdiction", "parent_court_id"]]




def prepare_dataset_duckdb(
    args: argparse.Namespace,
    courts: pd.DataFrame,
    dockets_path: pathlib.Path,
    clusters_path: pathlib.Path,
    opinions_path: pathlib.Path,
    output_path: pathlib.Path,
) ->int:
    """Prepare dataset using DuckDB pipeline with streaming decompression.

    Decompresses bz2 files to temporary uncompressed CSVs in a streaming fashion,
    then uses DuckDB to read those uncompressed files for fast joins and filtering.
    Avoids loading large datasets into memory while still getting DuckDB performance.
    """
    import tempfile
    import shutil

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = pathlib.Path(tempfile.mkdtemp(dir=output_path.parent, prefix="courtlistener_prep_"))

    try:
        print("Decompressing data files (streaming)...")

        # Decompress bz2 files in streaming fashion
        def decompress_bz2(src: pathlib.Path, dst: pathlib.Path) -> None:
            """Decompress bz2 file without loading entire file into memory."""
            import bz2
            with bz2.open(src, "rb") as src_f, open(dst, "wb") as dst_f:
                while True:
                    chunk = src_f.read(8192 * 1024)  # 8MB chunks
                    if not chunk:
                        break
                    dst_f.write(chunk)

        clusters_csv = temp_dir / "clusters.csv"
        dockets_csv = temp_dir / "dockets.csv"
        opinions_csv = temp_dir / "opinions.csv"

        print(f"  Decompressing clusters...")
        decompress_bz2(clusters_path, clusters_csv)
        print(f"  Decompressing dockets...")
        decompress_bz2(dockets_path, dockets_csv)
        print(f"  Decompressing opinions (this may take a while)...")
        decompress_bz2(opinions_path, opinions_csv)

        con = duckdb.connect(
            config={
                "threads": os.cpu_count(),
                "memory_limit": "8GB",
                "temp_directory": str(temp_dir),
            }
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Register courts in DuckDB
        con.register("courts_df", courts[["id", "issuer", "state"]])
        con.execute("CREATE TABLE courts AS SELECT * FROM courts_df")

        print("Processing data with DuckDB...")

    # Build sampling condition (SQL)
    sample_condition = ""
    if args.sample_frac is not None:
        if not (0 < float(args.sample_frac) <= 1):
            raise ValueError("--sample-frac must be in (0, 1].")
        threshold = int(round(float(args.sample_frac) * 1000000))
        sample_condition = f"AND (abs(hash(CAST(cluster_id AS VARCHAR) || '|{args.seed}')) % 1000000) < {threshold}"

    # Build require-state condition
    require_state_condition = "AND courts.state <> ''" if args.require_state else ""

    # Build state filter condition
    state_filter_condition = ""
    if args.states:
        clean_states = [s.strip().lower() for s in args.states if s.strip()]
        if clean_states:
            quoted = ", ".join(f"'{s}'" for s in clean_states)
            state_filter_condition = f"AND courts.state IN ({quoted})"

    # HTML stripping function (regex: strip tags, collapse whitespace)
    def strip_html(col: str) -> str:
        return f"trim(regexp_replace(regexp_replace(COALESCE({col}, ''), '<[^>]+>', ' ', 'g'), '\\s+', ' ', 'g'))"

    # Build COALESCE for opinion text priority (plain_text > html_with_citations > ... > '')
    opinion_fields = [
        "plain_text",
        "html_with_citations",
        "html_lawbox",
        "html_columbia",
        "html",
        "html_anon_2020",
        "xml_harvard",
        "xml_scan",
    ]
    coalesce_parts = ", ".join(f"NULLIF({strip_html(f)}, '')" for f in opinion_fields)
    opinion_text_expr = f"COALESCE({coalesce_parts}, '')"

    # Main pipeline query
    # 1. Read clusters, apply sampling and basic filtering
    # 2. Read dockets
    # 3. Join clusters + dockets + courts
    # 4. Apply state filters and handle top-n-states
    # 5. Read opinions, strip HTML, aggregate per cluster
    # 6. Final join and document assembly

    top_states_cte = ""
    filter_to_top_states = ""

    if args.top_n_states is not None and args.top_n_states > 0:
        include_states = {s.strip().lower() for s in (args.include_states or []) if s.strip()}
        include_quoted = ", ".join(f"'{s}'" for s in include_states) if include_states else ""
        include_union = f"UNION ALL SELECT {include_quoted}" if include_quoted else ""

        top_states_cte = f"""
        ,top_states_cte AS (
            WITH state_counts AS (
                SELECT state, COUNT(*) AS cnt FROM metadata
                GROUP BY state
            ),
            ranked AS (
                SELECT state, ROW_NUMBER() OVER (ORDER BY cnt DESC, state) AS rn
                FROM state_counts
            )
            SELECT state FROM ranked WHERE rn <= {args.top_n_states}
            {include_union}
        )
        """
        filter_to_top_states = "AND metadata.state IN (SELECT state FROM top_states_cte)"

    # Limit condition
    limit_condition = ""
    if args.max_rows is not None:
        limit_condition = f"LIMIT {args.max_rows}"

        # Read CSV files into DuckDB (now uncompressed, so read_csv will work well)
        con.execute(f"CREATE TABLE clusters AS SELECT * FROM read_csv('{clusters_csv.as_posix()}', delim=',', quote='\"', escape='\"', header=true, ignore_errors=true, null_padding=true)")
        con.execute(f"CREATE TABLE dockets AS SELECT * FROM read_csv('{dockets_csv.as_posix()}', delim=',', quote='\"', escape='\"', header=true, ignore_errors=true, null_padding=true)")
        con.execute(f"CREATE TABLE opinions AS SELECT * FROM read_csv('{opinions_csv.as_posix()}', delim=',', quote='\"', escape='\"', header=true, ignore_errors=true, null_padding=true)")

        query = f"""
        WITH clusters_raw AS (
            SELECT
                id AS cluster_id,
                docket_id,
                COALESCE(NULLIF(case_name_full, ''), NULLIF(case_name, ''), NULLIF(case_name_short, ''), '') AS title,
                COALESCE(NULLIF(date_filed, ''), NULLIF(date_created, ''), '') AS ts,
                trim(regexp_replace(
                    COALESCE(NULLIF(headmatter, ''), '') || ' ' ||
                    COALESCE(NULLIF(summary, ''), '') || ' ' ||
                    COALESCE(NULLIF(syllabus, ''), '') || ' ' ||
                    COALESCE(NULLIF(headnotes, ''), ''),
                    '\\s+', ' ', 'g'
                )) AS cluster_context
            FROM clusters
            WHERE id IS NOT NULL AND docket_id IS NOT NULL
            {sample_condition}
        ),
        dockets_raw AS (
            SELECT
                id AS docket_id,
                court_id,
                COALESCE(
                    NULLIF(docket_number, ''),
                    NULLIF(docket_number_core, ''),
                    NULLIF(docket_number_raw, ''),
                    ''
                ) AS docket_number,
                COALESCE(NULLIF(date_filed, ''), '') AS docket_date_filed
            FROM dockets
            WHERE id IS NOT NULL AND court_id IS NOT NULL
        ),
    metadata AS (
        SELECT
            c.cluster_id,
            c.title,
            d.docket_number,
            courts.state,
            courts.issuer,
            COALESCE(NULLIF(c.ts, ''), NULLIF(d.docket_date_filed, '')) AS timestamp,
            c.cluster_context,
            d.court_id
        FROM clusters_raw c
        JOIN dockets_raw d ON c.docket_id = d.docket_id
        JOIN courts ON d.court_id = courts.id
        WHERE courts.issuer <> ''
        {require_state_condition}
        {state_filter_condition}
    )
    {top_states_cte}
    ,opinions_raw AS (
        SELECT
            cluster_id,
            {opinion_text_expr} AS opinion_text
        FROM opinions
        WHERE cluster_id IS NOT NULL
    ),
    opinions_filtered AS (
        SELECT
            cluster_id,
            opinion_text
        FROM opinions_raw
        WHERE opinion_text <> ''
    ),
    opinions_agg AS (
        SELECT
            cluster_id,
            string_agg(opinion_text, '\\n\\n===== OPINION =====\\n\\n')
                FILTER (WHERE opinion_text <> '') AS opinion_document
        FROM opinions_filtered
        GROUP BY cluster_id
    ),
    filtered_metadata AS (
        SELECT * FROM metadata
        {filter_to_top_states}
        {limit_condition}
    ),
    final_join AS (
        SELECT
            m.cluster_id AS id,
            m.title,
            '' AS citation,
            m.docket_number,
            m.state,
            m.issuer,
            trim(regexp_replace(
                concat_ws(' ',
                    nullif(m.cluster_context, ''),
                    nullif(o.opinion_document, '')
                ),
                '\\s+', ' ', 'g'
            )) AS document,
            m.timestamp
        FROM filtered_metadata m
        LEFT JOIN opinions_agg o ON m.cluster_id = o.cluster_id
        WHERE trim(coalesce(o.opinion_document, '')) <> ''
    )
    SELECT * FROM final_join
    ORDER BY state, issuer, timestamp, id
    """

        # Execute query and write output
        con.execute(
            f"""
            COPY (
                {query}
            ) TO '{output_path.as_posix()}'
            (FORMAT CSV, HEADER, COMPRESSION GZIP)
            """
        )

        # Count rows written (single pass, more efficient than separate count query)
        row_count = con.execute(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]

        con.close()

        return row_count

    finally:
        # Clean up temporary files
        print(f"Cleaning up temporary files...")
        shutil.rmtree(temp_dir, ignore_errors=True)


def write_empty_output(output_path: pathlib.Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as handle:
        import gzip
        with gzip.GzipFile(fileobj=handle, mode="wb") as gz_handle:
            gz_handle.write(b"id,title,citation,docket_number,state,issuer,document,timestamp\n")


def main() -> int:
    args = parse_args()
    input_dir = pathlib.Path(args.input_dir)
    output_path = pathlib.Path(args.output)

    if args.aggregate_level != "cluster":
        raise NotImplementedError("Only cluster aggregation is currently supported for CourtListener preparation.")

    courts_path = latest_file(input_dir, "courts")
    dockets_path = latest_file(input_dir, "dockets")
    clusters_path = latest_file(input_dir, "opinion-clusters")
    opinions_path = latest_file(input_dir, "opinions")

    courts = build_courts_table(courts_path)

    row_count = prepare_dataset_duckdb(
        args=args,
        courts=courts,
        dockets_path=dockets_path,
        clusters_path=clusters_path,
        opinions_path=opinions_path,
        output_path=output_path,
    )

    if row_count > 0:
        print(f"Wrote {row_count:,} rows to {output_path}")
    else:
        print(f"No data to write (0 rows passed all filters)")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModuleNotFoundError as exc:
        print(f"Missing Python dependency: {exc}. Install with: python3 -m pip install duckdb pandas", file=sys.stderr)
        raise
