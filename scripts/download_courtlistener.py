#!/usr/bin/env python3
"""Download CourtListener bulk case-law files with resume/skip support."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

BUCKET_URL = "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/"
LIST_PREFIX = "bulk-data/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; courtlistener-downloader/1.0)",
}
CORE_PREFIXES = (
    "courts-",
    "dockets-",
    "opinion-clusters-",
    "opinions-",
)
EXTRA_PREFIXES = (
    "citation-map-",
    "parentheticals-",
    "fjc-integrated-database-",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download CourtListener bulk case-law files into the local repository."
    )
    parser.add_argument(
        "--output-dir",
        default="data/courtlistener",
        help="Directory to write downloaded files into. Default: %(default)s",
    )
    parser.add_argument(
        "--include-extras",
        action="store_true",
        help="Also download citation-map, parentheticals, and integrated-database files.",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Optional custom path for the JSON download state file.",
    )
    return parser.parse_args()


def list_bulk_files() -> list[tuple[str, int]]:
    marker = ""
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    items: list[tuple[str, int]] = []

    while True:
        query = f"?prefix={LIST_PREFIX}&marker={marker}&max-keys=1000"
        request = urllib.request.Request(f"{BUCKET_URL}{query}", headers=HEADERS)
        with urllib.request.urlopen(request) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        contents = root.findall("s3:Contents", namespace)
        if not contents:
            break

        for entry in contents:
            key = entry.find("s3:Key", namespace)
            size = entry.find("s3:Size", namespace)
            if key is None or size is None:
                continue
            items.append((key.text, int(size.text)))

        is_truncated = root.find("s3:IsTruncated", namespace)
        if is_truncated is None or is_truncated.text != "true":
            break
        marker = contents[-1].find("s3:Key", namespace).text

    return items


def pick_latest_files(include_extras: bool) -> dict[str, tuple[str, int]]:
    prefixes = list(CORE_PREFIXES)
    if include_extras:
        prefixes.extend(EXTRA_PREFIXES)

    latest: dict[str, tuple[str, int]] = {}
    for key, size in list_bulk_files():
        name = key.split("/")[-1]
        for prefix in prefixes:
            if name.startswith(prefix) and name.endswith(".csv.bz2"):
                latest[prefix] = (key, size)

    missing = [prefix for prefix in prefixes if prefix not in latest]
    if missing:
        raise RuntimeError(f"Could not find latest bulk files for prefixes: {missing}")

    return latest


def load_state(state_path: pathlib.Path) -> dict:
    if not state_path.exists():
        return {"completed": {}, "failed": {}, "started_at": int(time.time())}
    with state_path.open() as handle:
        return json.load(handle)


def save_state(state_path: pathlib.Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_suffix(".tmp")
    with temp_path.open("w") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
    temp_path.replace(state_path)


def head_size(url: str) -> int | None:
    request = urllib.request.Request(url, headers=HEADERS, method="HEAD")
    try:
        with urllib.request.urlopen(request) as response:
            length = response.headers.get("Content-Length")
            return int(length) if length else None
    except urllib.error.HTTPError:
        return None


def download_file(url: str, destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


def main() -> int:
    args = parse_args()
    output_dir = pathlib.Path(args.output_dir)
    state_path = pathlib.Path(args.state_file) if args.state_file else output_dir / "download_state.json"

    print("Discovering latest CourtListener bulk files...")
    targets = pick_latest_files(include_extras=args.include_extras)
    state = load_state(state_path)
    completed = dict(state.get("completed", {}))
    failed = dict(state.get("failed", {}))

    total_bytes = sum(size for _, size in targets.values())
    print(f"Selected {len(targets)} files totaling {total_bytes / 1024**3:.2f} GiB.")

    for prefix, (key, expected_size) in targets.items():
        name = key.split("/")[-1]
        destination = output_dir / name
        url = f"{BUCKET_URL}{key}"

        if destination.exists() and destination.stat().st_size == expected_size:
            completed[name] = {
                "path": str(destination),
                "size": expected_size,
                "url": url,
                "status": "skipped",
            }
            failed.pop(name, None)
            print(f"Skipping existing file: {name}")
            continue

        remote_size = head_size(url)
        if remote_size and expected_size != remote_size:
            print(
                f"Warning: listing size {expected_size} differs from HEAD size {remote_size} for {name}",
                file=sys.stderr,
            )
            expected_size = remote_size

        print(f"Downloading {name} -> {destination}")
        try:
            download_file(url, destination)
        except Exception as exc:  # noqa: BLE001
            failed[name] = str(exc)
            save_state(
                state_path,
                {
                    "completed": completed,
                    "failed": failed,
                    "started_at": state.get("started_at", int(time.time())),
                    "updated_at": int(time.time()),
                },
            )
            print(f"Failed: {name}: {exc}", file=sys.stderr)
            continue

        final_size = destination.stat().st_size
        if expected_size and final_size != expected_size:
            failed[name] = f"size mismatch: expected {expected_size}, got {final_size}"
            print(f"Failed size check: {name}", file=sys.stderr)
        else:
            completed[name] = {
                "path": str(destination),
                "size": final_size,
                "url": url,
                "status": "downloaded",
            }
            failed.pop(name, None)
            print(f"Finished {name} ({final_size / 1024**3:.2f} GiB)")

        save_state(
            state_path,
            {
                "completed": completed,
                "failed": failed,
                "started_at": state.get("started_at", int(time.time())),
                "updated_at": int(time.time()),
            },
        )

    print(f"Done. completed={len(completed)} failed={len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
