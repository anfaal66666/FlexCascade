#!/usr/bin/env python3
"""Download the full machine-readable CAP bulk corpus as reporter volume zip files."""

from __future__ import annotations

import concurrent.futures
import json
import pathlib
import threading
import time
import urllib.error
import urllib.request

BASE_URL = "https://static.case.law"
METADATA_URL = f"{BASE_URL}/VolumesMetadata.json"
OUTPUT_DIR = pathlib.Path("data/caselaw_full")
STATE_PATH = OUTPUT_DIR / "download_state.json"
LOG_EVERY = 25
WORKERS = 4
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; caselaw-bulk-downloader/1.0)",
}

state_lock = threading.Lock()


def fetch_volume_list() -> list[dict]:
    request = urllib.request.Request(METADATA_URL, headers=HEADERS)
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"completed": [], "failed": {}, "started_at": int(time.time())}
    with STATE_PATH.open() as handle:
        return json.load(handle)


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".tmp")
    with temp_path.open("w") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
    temp_path.replace(STATE_PATH)


def remote_size(url: str) -> int | None:
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


def download_volume(item: dict) -> tuple[str, str]:
    reporter = item["reporter_slug"]
    volume = item["volume_folder"]
    relative_path = f"{reporter}/{volume}.zip"
    url = f"{BASE_URL}/{relative_path}"
    destination = OUTPUT_DIR / relative_path

    expected_size = remote_size(url)
    if destination.exists() and expected_size and destination.stat().st_size == expected_size:
        return relative_path, "skipped"

    try:
        download_file(url, destination)
    except Exception as exc:  # noqa: BLE001
        return relative_path, f"failed: {exc}"

    if expected_size and destination.stat().st_size != expected_size:
        return relative_path, "failed: size mismatch"

    return relative_path, "downloaded"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading CAP volume metadata...")
    volumes = fetch_volume_list()
    state = load_state()
    completed = set(state.get("completed", []))
    failed = dict(state.get("failed", {}))

    todo = []
    for item in volumes:
        relative_path = f"{item['reporter_slug']}/{item['volume_folder']}.zip"
        if relative_path not in completed:
            todo.append(item)

    print(f"Found {len(volumes):,} total volumes.")
    print(f"{len(completed):,} already completed.")
    print(f"{len(todo):,} remaining.")
    if failed:
        print(f"{len(failed):,} previous failures will be retried.")

    progress = 0
    started = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(download_volume, item): item for item in todo}
        for future in concurrent.futures.as_completed(futures):
            relative_path, status = future.result()
            with state_lock:
                progress += 1
                if status in {"downloaded", "skipped"}:
                    completed.add(relative_path)
                    failed.pop(relative_path, None)
                else:
                    failed[relative_path] = status

                if progress % LOG_EVERY == 0 or progress == len(todo):
                    elapsed = time.time() - started
                    rate = progress / elapsed if elapsed else 0
                    print(
                        f"[{progress:,}/{len(todo):,}] "
                        f"completed={len(completed):,} failed={len(failed):,} "
                        f"rate={rate:.2f} files/s last={relative_path} {status}"
                    )
                    save_state(
                        {
                            "completed": sorted(completed),
                            "failed": failed,
                            "started_at": state.get("started_at", int(started)),
                            "updated_at": int(time.time()),
                        }
                    )

    save_state(
        {
            "completed": sorted(completed),
            "failed": failed,
            "started_at": state.get("started_at", int(started)),
            "updated_at": int(time.time()),
        }
    )

    print(f"Finished with {len(failed):,} failed downloads.")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
