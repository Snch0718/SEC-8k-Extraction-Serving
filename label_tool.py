"""Terminal tool for hand-labeling filings according to labeling_guide.md.

Shows one filing at a time, asks for the category and events, and appends each
answer to a JSONL file. Quit any time with q; rerun to resume where you stopped.

Usage
    # label the test set (default)
    python label_tool.py

    # second pass for the agreement check, a few days later: 20 random filings
    # you already labeled, written to a separate file
    python label_tool.py --only-from data/labels/test_labels.jsonl --limit 20 \
        --out data/labels/test_labels_pass2.jsonl

Label the test set BEFORE looking at any model output.
"""

import argparse
import datetime
import json
import os
import random
import re
import textwrap
from pathlib import Path

ACTIONS = ["appointed", "elected", "resigned", "retired", "terminated", "not_standing_for_reelection","departed"]
CATEGORIES = {"1": "leadership_change", "2": "compensation", "3": "other"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def ask_date(prompt):
    while True:
        v = input(prompt).strip()
        if not v:
            return None
        if DATE_RE.match(v):
            try:
                datetime.date.fromisoformat(v)
                return v
            except ValueError:
                pass
        print("  Use YYYY-MM-DD, or press Enter for null.")


def ask_event():
    who = ""
    while not who:
        who = input("  who (full name, no Mr./Ms.): ").strip()
    role = input("  role (as written): ").strip() or None
    for i, a in enumerate(ACTIONS, 1):
        print(f"    {i}) {a}")
    action = None
    while action is None:
        c = input("  action number: ").strip()
        if c.isdigit() and 1 <= int(c) <= len(ACTIONS):
            action = ACTIONS[int(c) - 1]
    event_date = ask_date("  event_date YYYY-MM-DD (Enter = null): ")
    effective_date = ask_date("  effective_date YYYY-MM-DD (Enter = null): ")
    return {"who": who, "role": role, "action": action,
            "event_date": event_date, "effective_date": effective_date}


def show(rec, n, total):
    clear()
    print(f"[{n}/{total}] {rec['company']} | filed {rec['filing_date']} | {rec['id']}")
    print("-" * 100)
    for para in rec["text"].split("\n"):
        print(textwrap.fill(para, width=100) if para.strip() else "")
    print("-" * 100)


def label_one(rec, n, total):
    while True:
        show(rec, n, total)
        c = input("category: 1) leadership_change  2) compensation  3) other   (s = skip, q = quit): ").strip().lower()
        if c == "q":
            return "quit"
        if c == "s":
            return None
        if c not in CATEGORIES:
            continue
        category = CATEGORIES[c]
        events = []
        if category == "leadership_change":
            while True:
                print(f"\nEvent {len(events) + 1}:")
                events.append(ask_event())
                if input("another event in this filing? (y/N): ").strip().lower() != "y":
                    break
        notes = input("notes (optional, e.g. a rule you had to invent): ").strip()
        out = {"id": rec["id"], "category": category, "events": events, "notes": notes,
               "labeled_at": datetime.datetime.now().isoformat(timespec="seconds")}
        print("\n" + json.dumps({"category": category, "events": events}, indent=1))
        if input("Enter = save, r = redo this filing: ").strip().lower() != "r":
            return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="data/splits/test.jsonl")
    p.add_argument("--out", default="data/labels/test_labels.jsonl")
    p.add_argument("--only-from", help="Only filings whose ids appear in this labels file")
    p.add_argument("--limit", type=int, help="Randomly pick at most this many filings")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    records = read_jsonl(args.input)
    if not records:
        raise SystemExit(f"No records in {args.input}. Run split_data.py first.")

    if args.only_from:
        allowed = {r["id"] for r in read_jsonl(args.only_from)}
        records = [r for r in records if r["id"] in allowed]
    random.Random(args.seed).shuffle(records)
    if args.limit:
        records = records[: args.limit]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = {r["id"] for r in read_jsonl(out_path)}
    todo = [r for r in records if r["id"] not in done]
    print(f"{len(records)} filings in scope, {len(done & {r['id'] for r in records})} already labeled, {len(todo)} to go")

    for n, rec in enumerate(todo, start=len(records) - len(todo) + 1):
        result = label_one(rec, n, len(records))
        if result == "quit":
            break
        if result:
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

    labeled = read_jsonl(out_path)
    from collections import Counter
    print(f"\nLabeled so far in {out_path}: {len(labeled)}")
    print("Category mix:", dict(Counter(r["category"] for r in labeled)))


if __name__ == "__main__":
    main()