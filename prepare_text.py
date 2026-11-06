"""Turn downloaded 8-K HTML filings into clean, cropped text for labeling and training.

Reads data/filings_index.csv and data/filings/*, keeps filings that include a
chosen 8-K item (default 5.02), converts the HTML to plain text, crops each
filing to just that item's section (dropping the cover page and signatures),
adds a rough keyword tag for planning, and writes:

    data/corpus.jsonl       one JSON object per filing
    data/samples/*.txt      readable examples, spread across the tag groups

The tags are a crude keyword heuristic used only to see what kinds of filings
you have. They are NOT labels. The tagging is written for item 5.02.

Usage
    pip install beautifulsoup4 lxml
    python prepare_text.py
    python prepare_text.py --samples 12
"""

import argparse
import csv
import json
import re
import statistics
import warnings
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

TAG_KEYWORDS = {
    "compensation": [
        "base salary", "incentive plan", "equity award", "equity grant",
        "restricted stock unit", "stock option", "performance share",
        "change in control", "change of control", "severance", "retention",
        "bonus", "employment agreement", "compensation",
    ],
    "departure": [
        "resign", "retire", "step down", "stepping down", "terminat",
        "not stand for re-election", "will not stand", "not be standing",
        "leave the company", "depart",
    ],
    "appointment": [
        "appointed", "appointment of", "elected to the board", "was elected",
        "has been elected", "will serve as", "to succeed", "succeed",
        "will join", "joined the",
    ],
}

# The item heading text, which contains words like "Departure" in every filing.
TITLE_RE = re.compile(
    r"Departure\s+of\s+Directors.*?Compensatory\s+Arrangements\s+of\s+Certain\s+Officers\.?",
    re.I | re.S,
)


def html_to_text(raw: bytes, suffix: str) -> str:
    if suffix.lower() == ".txt":
        text = raw.decode("utf-8", errors="ignore")
    else:
        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style", "head"]):
            tag.decompose()
        for tag in soup.find_all("ix:header"):
            tag.decompose()
        for tag in soup.find_all(style=re.compile(r"display\s*:\s*none", re.I)):
            tag.decompose()
        text = soup.get_text("\n")

    text = text.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    cleaned, blank = [], 0
    for ln in lines:
        if ln:
            cleaned.append(ln)
            blank = 0
        else:
            blank += 1
            if blank == 1:
                cleaned.append("")
    return "\n".join(cleaned).strip()


def extract_item_section(text: str, item: str):
    """Return (section_text, found). Falls back to the full text if the heading is not found."""
    start = re.search(rf"^\s*Item\.?\s+{re.escape(item)}\b", text, re.I | re.M)
    if not start:
        return text, False
    rest = text[start.start():]
    head_len = len(start.group(0))
    end = re.search(r"^\s*(Item\.?\s+\d\.\d{2}\b|Section\s+\d+\s*[-–—]|SIGNATURES?\b)", rest[head_len:], re.I | re.M)
    section = rest[: head_len + end.start()] if end else rest
    return section.strip(), True


def tag_section(section: str):
    body = TITLE_RE.sub(" ", section, count=1).lower()
    tags = [name for name, words in TAG_KEYWORDS.items() if any(w in body for w in words)]
    return tags or ["other"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data")
    p.add_argument("--item", default="5.02", help="8-K item to keep (default 5.02)")
    p.add_argument("--min-chars", type=int, default=200,
                   help="Drop sections with less text than this (default 200)")
    p.add_argument("--samples", type=int, default=12,
                   help="How many readable sample files to write (default 12)")
    args = p.parse_args()

    data_dir = Path(args.data)
    index_path = data_dir / "filings_index.csv"
    if not index_path.exists():
        raise SystemExit(f"{index_path} not found. Run fetch_8k_filings.py first.")

    rows = list(csv.DictReader(index_path.open(encoding="utf-8")))
    kept = []
    skipped_item = skipped_missing = skipped_short = not_cropped = 0

    for r in rows:
        items = [i for i in r["items"].split(",") if i]
        if args.item not in items:
            skipped_item += 1
            continue
        path = Path(r["path"])
        if not path.exists():
            skipped_missing += 1
            continue

        full = html_to_text(path.read_bytes(), path.suffix)
        section, found = extract_item_section(full, args.item)
        if not found:
            not_cropped += 1
        if len(section) < args.min_chars:
            skipped_short += 1
            continue

        kept.append({
            "id": f"{r['ticker']}_{r['accession']}",
            "ticker": r["ticker"],
            "cik": r["cik"],
            "company": r["company"],
            "accession": r["accession"],
            "filing_date": r["filing_date"],
            "items": r["items"],
            "url": r["url"],
            "tags": tag_section(section),
            "cropped": found,
            "n_chars_full": len(full),
            "n_chars": len(section),
            "text": section,
        })

    corpus_path = data_dir / "corpus.jsonl"
    with corpus_path.open("w", encoding="utf-8") as f:
        for k in kept:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")

    print(f"Kept {len(kept)} filings containing item {args.item}")
    print(f"Skipped: wrong item={skipped_item}, file missing={skipped_missing}, too short={skipped_short}")
    print(f"Item heading not found (full text kept instead): {not_cropped}")
    if not kept:
        return

    full_len = sorted(k["n_chars_full"] for k in kept)
    sec_len = sorted(k["n_chars"] for k in kept)
    p90 = sec_len[int(0.9 * (len(sec_len) - 1))]
    print(f"\nCharacters, full filing: median={int(statistics.median(full_len))}")
    print(f"Characters, cropped section: median={int(statistics.median(sec_len))}, "
          f"p90={p90}, max={sec_len[-1]}")
    print(f"Rough tokens (chars/4), cropped: median={int(statistics.median(sec_len) / 4)}, p90={p90 // 4}")

    single, combos = Counter(), Counter()
    by_combo = defaultdict(list)
    for k in kept:
        for t in k["tags"]:
            single[t] += 1
        combo = "+".join(sorted(k["tags"]))
        combos[combo] += 1
        by_combo[combo].append(k)

    print("\nKeyword tags (a filing can have several):")
    for t, n in single.most_common():
        print(f"  {t}: {n}  ({n / len(kept):.0%})")
    print("\nTag combinations:")
    for c, n in combos.most_common():
        print(f"  {c}: {n}")

    samples_dir = data_dir / "samples"
    samples_dir.mkdir(exist_ok=True)
    for old in samples_dir.glob("*.txt"):
        old.unlink()
    chosen, round_no = [], 0
    while len(chosen) < args.samples and round_no < 5:
        for combo, group in by_combo.items():
            if round_no < len(group) and len(chosen) < args.samples:
                chosen.append((combo, group[round_no]))
        round_no += 1
    for combo, k in chosen:
        header = (f"{k['company']} | {k['filing_date']} | tags: {combo}\n{k['url']}\n\n")
        (samples_dir / f"{combo}__{k['id']}.txt").write_text(header + k["text"], encoding="utf-8")

    print(f"\nCorpus: {corpus_path}")
    print(f"Readable samples (spread across tag groups): {samples_dir}")


if __name__ == "__main__":
    main()