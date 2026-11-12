"""Validate and summarize the hand labels in data/labels/test_labels.jsonl.

Checks that
  - every test filing has exactly one label (no missing, duplicate or unknown ids)
  - each label follows the schema in labeling_guide.md
  - the labels follow the formatting rules from the guide's rule log
and prints a summary: category mix, events per filing, action counts, how often
dates are null, and how many labels carry notes (your hard cases).

Usage
    python check_labels.py
    python check_labels.py --show-notes       # also list every filing that has a note
"""

import argparse
import datetime
import json
import re
from collections import Counter
from pathlib import Path

CATEGORIES = {"leadership_change", "compensation", "other"}
ACTIONS = {"appointed", "elected", "resigned", "retired", "terminated",
           "not_standing_for_reelection", "departed"}
EVENT_KEYS = {"who", "role", "action", "event_date", "effective_date"}
MAX_EVENTS = 8


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).open(encoding="utf-8") if line.strip()]


def valid_date(v):
    if v is None:
        return True
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return False
    try:
        datetime.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--splits", default="data/splits/test.jsonl")
    p.add_argument("--labels", default="data/labels/test_labels.jsonl")
    p.add_argument("--show-notes", action="store_true")
    args = p.parse_args()

    test = read_jsonl(args.splits)
    labels = read_jsonl(args.labels)
    test_ids = {r["id"] for r in test}

    errors, warnings = [], []

    # Coverage
    counts = Counter(l["id"] for l in labels)
    missing = sorted(test_ids - set(counts))
    duplicates = sorted(i for i, n in counts.items() if n > 1)
    unknown = sorted(set(counts) - test_ids)
    if missing:
        errors.append(f"{len(missing)} test filings have no label, e.g. {missing[:3]}")
    if duplicates:
        errors.append(f"{len(duplicates)} ids labeled more than once: {duplicates[:5]}")
    if unknown:
        errors.append(f"{len(unknown)} labeled ids are not in the test set: {unknown[:5]}")

    # Per-label checks
    for l in labels:
        i = l["id"]
        cat = l.get("category")
        events = l.get("events")
        if cat not in CATEGORIES:
            errors.append(f"{i}: bad category {cat!r}")
            continue
        if not isinstance(events, list):
            errors.append(f"{i}: events is not a list")
            continue
        if cat == "leadership_change" and not events:
            errors.append(f"{i}: leadership_change with no events")
        if cat != "leadership_change" and events:
            errors.append(f"{i}: category {cat} must have no events")
        if len(events) > MAX_EVENTS:
            warnings.append(f"{i}: {len(events)} events (guide says set aside above {MAX_EVENTS})")

        for e in events:
            if set(e) != EVENT_KEYS:
                errors.append(f"{i}: event keys {sorted(e)} do not match the schema")
                continue
            if not e["who"]:
                errors.append(f"{i}: empty 'who'")
            if e["action"] not in ACTIONS:
                errors.append(f"{i}: bad action {e['action']!r}")
            for k in ("event_date", "effective_date"):
                if not valid_date(e[k]):
                    errors.append(f"{i}: bad {k} {e[k]!r}")
            who, role = e["who"] or "", e["role"] or ""
            if re.match(r"(Mr|Ms|Mrs|Dr|Admiral|General|Hon)\.?\s", who):
                warnings.append(f"{i}: title in name {who!r}")
            if '"' in who or "“" in who or "(" in who:
                warnings.append(f"{i}: nickname or parentheses in name {who!r}")
            if "&" in role or "–" in role or "—" in role:
                warnings.append(f"{i}: '&' or long dash in role {role!r}")
            if "committee" in role.lower():
                warnings.append(f"{i}: committee wording in role {role!r}")
            if not e["role"]:
                warnings.append(f"{i}: empty role for {who!r}")
            if e["event_date"] and e["effective_date"] and e["effective_date"] < e["event_date"]:
                warnings.append(f"{i}: effective_date before event_date for {who!r} (fine if the filing says so; check the note)")

        # Duplicate events within a filing
        seen = Counter((e.get("who"), e.get("role"), e.get("action")) for e in events if isinstance(e, dict))
        for key, n in seen.items():
            if n > 1:
                errors.append(f"{i}: duplicate event {key}")

    # Summary
    by_cat = Counter(l["category"] for l in labels if l.get("category") in CATEGORIES)
    all_events = [e for l in labels if isinstance(l.get("events"), list) for e in l["events"] if isinstance(e, dict)]
    leadership = [l for l in labels if l.get("category") == "leadership_change"]
    companies = {i.split("_")[0] for i in counts}

    print(f"Test filings: {len(test_ids)}   labeled: {len(counts)}   companies: {len(companies)}")
    print("\nCategory mix:")
    for c, n in by_cat.most_common():
        print(f"  {c}: {n}")
    if leadership:
        per = Counter(len(l["events"]) for l in leadership)
        print("\nEvents per leadership filing:", dict(sorted(per.items())))
    print(f"Total events: {len(all_events)}")
    print("\nActions:")
    for a, n in Counter(e.get("action") for e in all_events).most_common():
        print(f"  {a}: {n}")
    if all_events:
        n_ev = sum(1 for e in all_events if e.get("event_date") is None)
        n_ef = sum(1 for e in all_events if e.get("effective_date") is None)
        print(f"\nevent_date null: {n_ev}/{len(all_events)}   effective_date null: {n_ef}/{len(all_events)}")
    with_notes = [l for l in labels if l.get("notes")]
    print(f"Labels with notes (hard cases or invented rules): {len(with_notes)}")
    if args.show_notes:
        for l in with_notes:
            print(f"  {l['id']}: {l['notes']}")

    print(f"\nERRORS: {len(errors)}")
    for e in errors:
        print("  " + e)
    print(f"WARNINGS: {len(warnings)}")
    for w in warnings:
        print("  " + w)
    if not errors:
        print("\nNo errors. Fix or confirm each warning, then freeze the labels.")


if __name__ == "__main__":
    main()