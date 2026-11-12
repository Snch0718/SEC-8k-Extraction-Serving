"""Apply the three label fixes found by the second pass.

Makes a backup first (data/labels/test_labels_before_fixes.jsonl), then:
  1. UBER_0001552781-25-000201: Gore-Coty effective_date -> 2025-06-02
  2. ICE_0001104659-25-091292:  name -> "Lord Hill of Oareford"
  3. PANW_0001193125-25-315915: category other -> compensation

Safe to run twice: a fix that is already applied is reported and skipped.

Usage
    python apply_label_fixes.py
"""

import json
import shutil
from pathlib import Path

PATH = Path("data/labels/test_labels.jsonl")
STAMP = "fixed 2026-11-12 after second pass"


def main():
    shutil.copy(PATH, PATH.with_name("test_labels_before_fixes.jsonl"))
    rows = [json.loads(line) for line in PATH.open(encoding="utf-8") if line.strip()]
    by_id = {r["id"]: r for r in rows}

    def note(r, text):
        r["notes"] = (r.get("notes", "") + f" | {STAMP}: {text}").strip(" |")

    # 1. Gore-Coty effective date
    r = by_id.get("UBER_0001552781-25-000201")
    if r is None:
        print("1. Uber filing not found")
    else:
        for e in r["events"]:
            if e["who"] == "Pierre-Dimitri Gore-Coty":
                if e["effective_date"] == "2025-06-02":
                    print("1. already applied")
                else:
                    print(f"1. Gore-Coty effective_date {e['effective_date']} -> 2025-06-02")
                    e["effective_date"] = "2025-06-02"
                    note(r, "trailing 'effective immediately' covers both events in the sentence")

    # 2. Lord Hill name
    r = by_id.get("ICE_0001104659-25-091292")
    if r is None:
        print("2. ICE filing not found")
    else:
        for e in r["events"]:
            if e["who"] == "Lord Hill of Oareford CBE":
                print("2. name 'Lord Hill of Oareford CBE' -> 'Lord Hill of Oareford'")
                e["who"] = "Lord Hill of Oareford"
                note(r, "post-nominals dropped from name")
            elif e["who"] == "Lord Hill of Oareford":
                print("2. already applied")

    # 3. PANW plan approval
    r = by_id.get("PANW_0001193125-25-315915")
    if r is None:
        print("3. PANW filing not found")
    elif r["category"] == "compensation":
        print("3. already applied")
    else:
        print(f"3. category {r['category']} -> compensation")
        r["category"] = "compensation"
        note(r, "plan approvals are compensation")

    with PATH.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(rows)} labels to {PATH} (backup: test_labels_before_fixes.jsonl)")


if __name__ == "__main__":
    main()