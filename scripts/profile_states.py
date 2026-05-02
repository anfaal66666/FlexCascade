#!/opt/anaconda3/bin/python
"""Profile state and issuer counts in HFforLegal/case-law."""

from __future__ import annotations

from collections import Counter, defaultdict

from datasets import load_dataset


def main() -> None:
    ds = load_dataset(
        "HFforLegal/case-law",
        split="us",
        cache_dir="data/hf_cache",
        verification_mode="no_checks",
    )
    state_counter = Counter()
    issuer_counter = defaultdict(Counter)

    for row in ds:
        state = (row.get("state") or "").strip()
        issuer = (row.get("issuer") or "").strip()
        document = (row.get("document") or "").strip()
        if state and issuer and document:
            state_counter[state] += 1
            issuer_counter[state][issuer] += 1

    print("state\trows\tissuers")
    for state, count in state_counter.most_common():
        print(f"{state}\t{count}\t{len(issuer_counter[state])}")


if __name__ == "__main__":
    main()
