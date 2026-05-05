#!/usr/bin/env python3
"""Download Caselaw Access Project bulk files from static.case.law."""

from __future__ import annotations

import argparse
import pathlib
import sys
import urllib.error
import urllib.request

BASE_URL = "https://static.case.law"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; caselaw-downloader/1.0)",
}

METADATA_CHOICES = {
    "jurisdictions": "JurisdictionsMetadata.json",
    "reporters": "ReportersMetadata.json",
    "volumes": "VolumesMetadata.json",
}


def build_remote_path(args: argparse.Namespace) -> str:
    if args.url_path:
        return args.url_path.lstrip("/")

    if args.metadata:
        return METADATA_CHOICES[args.metadata]

    if args.reporter and args.volume:
        return f"{args.reporter}/{args.volume}.zip"

    raise SystemExit(
        "Provide one of: --metadata, --url-path, or both --reporter and --volume."
    )


def download_file(url: str, destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers=DEFAULT_HEADERS)

    with urllib.request.urlopen(request) as response, destination.open("wb") as handle:
        total = response.headers.get("Content-Length")
        expected = int(total) if total else None
        downloaded = 0

        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if expected:
                percent = downloaded * 100 / expected
                print(
                    f"\rDownloaded {downloaded:,} / {expected:,} bytes ({percent:5.1f}%)",
                    end="",
                    flush=True,
                )
            else:
                print(f"\rDownloaded {downloaded:,} bytes", end="", flush=True)

    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Caselaw Access Project bulk data from static.case.law."
    )
    parser.add_argument(
        "--metadata",
        choices=sorted(METADATA_CHOICES),
        help="Download one of the top-level metadata JSON files.",
    )
    parser.add_argument(
        "--reporter",
        help="Reporter slug, for example 'ark' or 'mass'. Must be used with --volume.",
    )
    parser.add_argument(
        "--volume",
        help="Volume number to download as a zip, for example '14'.",
    )
    parser.add_argument(
        "--url-path",
        help="Direct path under static.case.law, for example 'ark/14.zip'.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/caselaw",
        help="Directory to write downloaded files into. Default: %(default)s",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    remote_path = build_remote_path(args)
    url = f"{BASE_URL}/{remote_path}"
    output_path = pathlib.Path(args.output_dir) / remote_path

    print(f"Downloading {url}")
    print(f"Saving to {output_path}")

    try:
        download_file(url, output_path)
    except urllib.error.HTTPError as exc:
        print(f"HTTP error {exc.code} for {url}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Network error for {url}: {exc.reason}", file=sys.stderr)
        return 1

    print("Download complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
