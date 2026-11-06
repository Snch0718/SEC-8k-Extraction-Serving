"""Split data/corpus.jsonl into train / validation / test, grouped by company.

Whole companies go to one split only, so the test set contains filings from
companies the model never saw in training. This matters because companies reuse
the same boilerplate wording year after year, which would otherwise leak
answers from training into testing.

Outputs
    data/splits/train.jsonl, val.jsonl, test.jsonl   full records
    splits/split_ids.json                            just the ids, small enough to commit

Usage
    python split_data.py
    python split_data.py --test 100 --val 60 --seed 42

Freeze the test set: once you have created it, do not rerun with different
settings after you start labeling. The seed makes the split reproducible.
"""

import argparse
import hashlib
import json
import random
import re
from collections import defaultdict
from pathlib import Path


def norm_hash(text: str) -> str:
    return hashlib.md5(re.sub(r"\W+", " ", text.lower()).strip().encode()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data")
    p.add_argument("--test", type=int, default=100, help="Target number of test filings")
    p.add_argument("--val", type=int, default=60, help="Target number of validation filings")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-chars", type=int, default=16000,
                   help="Drop filings longer than this (about 4,000 tokens); default 16000")
    args = p.parse_args()

    data_dir = Path(args.data)
    records = [json.loads(line) for line in (data_dir / "corpus.jsonl").open(encoding="utf-8")]
    print(f"Loaded {len(records)} filings")

    # Drop exact duplicates (same text after normalizing) and very long filings.
    seen, kept, dups, too_long = set(), [], 0, 0
    for r in records:
        if r["n_chars"] > args.max_chars:
            too_long += 1
            continue
        h = norm_hash(r["text"])
        if h in seen:
            dups += 1
            continue
        seen.add(h)
        kept.append(r)
    print(f"Dropped {dups} exact duplicates and {too_long} filings over {args.max_chars} characters")

    by_company = defaultdict(list)
    for r in kept:
        by_company[r["cik"]].append(r)
    companies = sorted(by_company)
    random.Random(args.seed).shuffle(companies)

    splits = {"test": [], "val": [], "train": []}
    for cik in companies:
        group = by_company[cik]
        if len(splits["test"]) < args.test:
            splits["test"].extend(group)
        elif len(splits["val"]) < args.val:
            splits["val"].extend(group)
        else:
            splits["train"].extend(group)

    out_dir = data_dir / "splits"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, recs in splits.items():
        recs.sort(key=lambda r: (r["cik"], r["filing_date"]))
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ids_path = Path("splits") / "split_ids.json"
    ids_path.parent.mkdir(exist_ok=True)
    ids_path.write_text(json.dumps(
        {"seed": args.seed, **{name: [r["id"] for r in recs] for name, recs in splits.items()}},
        indent=1), encoding="utf-8")

    print("\nSplit summary")
    for name in ("train", "val", "test"):
        recs = splits[name]
        dates = sorted(r["filing_date"] for r in recs)
        print(f"  {name:5s} filings={len(recs):4d} companies={len({r['cik'] for r in recs}):4d} "
              f"dates={dates[0] if dates else '-'} to {dates[-1] if dates else '-'}")
    overlap = ({r["cik"] for r in splits["test"]} & {r["cik"] for r in splits["train"]}) | \
              ({r["cik"] for r in splits["val"]} & {r["cik"] for r in splits["train"]}) | \
              ({r["cik"] for r in splits["test"]} & {r["cik"] for r in splits["val"]})
    print(f"  companies appearing in more than one split: {len(overlap)} (should be 0)")
    print(f"\nWrote {out_dir} and {ids_path} (commit the ids file, not the data)")


if __name__ == "__main__":
    main()