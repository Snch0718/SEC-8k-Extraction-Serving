"""Score model predictions against the hand-labeled test set.

A predictions file is JSONL with one row per filing. Each row needs an "id" and
one of:
    "output": the raw model text (the script finds and parses the JSON in it)
    "parsed": an already-parsed {"category": ..., "events": [...]} object
    or top-level "category" and "events" keys (the same format as the label file)

What it reports
    valid-output rate     output parses and follows the schema (invalid outputs score as "no events")
    category accuracy     leadership_change / compensation / other
    event-level P / R / F1 at three strictness levels:
        core:   right person (name match tolerant of middle initials) and right action
        full:   core plus role (fuzzy) and effective_date correct
        strict: full plus event_date correct (event_date is the least reliable field in the
                labels, so it is reported separately and kept out of the headline "full" score)
    field accuracy        role / event_date / effective_date, among events that passed the core match
    false alarms          on filings whose gold category is not leadership_change, how often the
                          model still returned events
    95% confidence intervals from resampling companies (not filings), because filings from the
    same company share wording

Usage
    python score.py --pred predictions/frontier_baseline.jsonl
    python score.py --pred data/labels/test_labels.jsonl                 # sanity check: should be 100%
    python score.py --pred data/labels/test_labels_pass2.jsonl           # your own agreement between passes
    python score.py --pred preds.jsonl --errors-out results/errors.jsonl # per-filing mistakes for the failure taxonomy
"""

import argparse
import datetime
import difflib
import json
import random
import re
from collections import defaultdict
from pathlib import Path

CATEGORIES = {"leadership_change", "compensation", "other"}
ACTIONS = {"appointed", "elected", "resigned", "retired", "terminated",
           "not_standing_for_reelection", "departed"}
KEYS = {"who", "role", "action", "event_date", "effective_date"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "cbe", "obe", "mbe", "kbe", "dbe",
            "phd", "md", "cpa", "esq", "the"}


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).open(encoding="utf-8") if line.strip()]


def extract_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None


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


def is_valid(obj):
    if not isinstance(obj, dict) or obj.get("category") not in CATEGORIES:
        return False
    events = obj.get("events")
    if not isinstance(events, list):
        return False
    for e in events:
        if not isinstance(e, dict) or set(e) != KEYS:
            return False
        if not isinstance(e["who"], str) or not e["who"].strip():
            return False
        if e["action"] not in ACTIONS:
            return False
        if e["role"] is not None and not isinstance(e["role"], str):
            return False
        if not valid_date(e["event_date"]) or not valid_date(e["effective_date"]):
            return False
    return True


def get_pred_obj(row):
    if "output" in row:
        return extract_json(row["output"]) if isinstance(row["output"], str) else row["output"]
    if "parsed" in row:
        return row["parsed"]
    if "category" in row:
        return {"category": row["category"], "events": row.get("events")}
    return None


def name_tokens(s):
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return [t for t in s.split() if t not in SUFFIXES]


def names_match(a, b):
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if ta[-1] != tb[-1]:
        return False
    fa, fb = ta[0], tb[0]
    return fa == fb or (len(fa) == 1 and fb.startswith(fa)) or (len(fb) == 1 and fa.startswith(fb))


def norm_role(s):
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def role_sim(a, b):
    na, nb = norm_role(a), norm_role(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def match_events(gold, pred):
    used, matches = set(), []
    for pi, p in enumerate(pred):
        best, best_score = None, -1.0
        for gi, g in enumerate(gold):
            if gi in used or g["action"] != p["action"] or not names_match(g["who"], p["who"]):
                continue
            s = role_sim(g["role"], p["role"])
            if s > best_score:
                best, best_score = gi, s
        if best is not None:
            used.add(best)
            matches.append((best, pi))
    return matches


def score_filing(gold, pred_obj):
    valid = is_valid(pred_obj)
    pred_events = pred_obj["events"] if valid else []
    pred_cat = pred_obj["category"] if valid else None
    gold_events = gold["events"]

    matches = match_events(gold_events, pred_events)
    role_ok = ed_ok = ef_ok = full_tp = strict_tp = 0
    issues = []
    for gi, pi in matches:
        g, p = gold_events[gi], pred_events[pi]
        r = role_sim(g["role"], p["role"]) >= 0.85
        d1 = g["event_date"] == p["event_date"]
        d2 = g["effective_date"] == p["effective_date"]
        role_ok += r
        ed_ok += d1
        ef_ok += d2
        full_tp += (r and d2)
        strict_tp += (r and d1 and d2)
        if not r:
            issues.append(f"role_mismatch: {g['who']}")
        if not d1:
            issues.append(f"event_date_mismatch: {g['who']}")
        if not d2:
            issues.append(f"effective_date_mismatch: {g['who']}")

    matched_g = {gi for gi, _ in matches}
    matched_p = {pi for _, pi in matches}
    for gi, g in enumerate(gold_events):
        if gi not in matched_g:
            issues.append(f"missed_event: {g['who']} / {g['action']}")
    for pi, p in enumerate(pred_events):
        if pi not in matched_p:
            issues.append(f"extra_event: {p['who']} / {p['action']}")
    if not valid:
        issues.insert(0, "invalid_output")
    if valid and pred_cat != gold["category"]:
        issues.insert(0, f"wrong_category: gold={gold['category']} pred={pred_cat}")

    negative = gold["category"] != "leadership_change"
    return {
        "n": 1, "valid": int(valid), "cat_ok": int(pred_cat == gold["category"]),
        "core_tp": len(matches), "full_tp": full_tp, "strict_tp": strict_tp,
        "n_gold": len(gold_events), "n_pred": len(pred_events),
        "role_ok": role_ok, "ed_ok": ed_ok, "ef_ok": ef_ok,
        "neg_n": int(negative), "neg_alarm": int(negative and len(pred_events) > 0),
    }, issues


def f1(tp, n_pred, n_gold):
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def metrics(s):
    core_p, core_r, core_f = f1(s["core_tp"], s["n_pred"], s["n_gold"])
    full_p, full_r, full_f = f1(s["full_tp"], s["n_pred"], s["n_gold"])
    _, _, strict_f = f1(s["strict_tp"], s["n_pred"], s["n_gold"])
    m = s["core_tp"]
    return {
        "valid": s["valid"] / s["n"], "category_acc": s["cat_ok"] / s["n"],
        "core_p": core_p, "core_r": core_r, "core_f1": core_f,
        "full_p": full_p, "full_r": full_r, "full_f1": full_f, "strict_f1": strict_f,
        "role_acc": s["role_ok"] / m if m else 0.0,
        "event_date_acc": s["ed_ok"] / m if m else 0.0,
        "effective_date_acc": s["ef_ok"] / m if m else 0.0,
        "false_alarm": s["neg_alarm"] / s["neg_n"] if s["neg_n"] else 0.0,
    }


def add(a, b):
    return {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)}


def bootstrap(by_company, reps, seed):
    rng = random.Random(seed)
    companies = list(by_company)
    out = defaultdict(list)
    for _ in range(reps):
        total = {}
        for c in (rng.choice(companies) for _ in companies):
            total = add(total, by_company[c])
        m = metrics(total)
        for k in ("valid", "category_acc", "core_f1", "full_f1", "strict_f1"):
            out[k].append(m[k])
    ci = {}
    for k, v in out.items():
        v.sort()
        ci[k] = (v[int(0.025 * (len(v) - 1))], v[int(0.975 * (len(v) - 1))])
    return ci


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gold", default="data/labels/test_labels.jsonl")
    p.add_argument("--pred", required=True)
    p.add_argument("--require-all", action="store_true",
                   help="Count gold filings with no prediction as invalid outputs (default: score only filings present in --pred)")
    p.add_argument("--errors-out", help="Write per-filing mistakes to this JSONL file")
    p.add_argument("--reps", type=int, default=2000, help="Bootstrap resamples (default 2000)")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    gold = {r["id"]: r for r in read_jsonl(args.gold)}
    preds = {r["id"]: r for r in read_jsonl(args.pred)}
    ids = sorted(gold) if args.require_all else sorted(i for i in gold if i in preds)
    if not ids:
        raise SystemExit("No overlapping ids between gold and predictions.")

    total, by_company, errors = {}, defaultdict(dict), []
    for i in ids:
        row = preds.get(i)
        obj = get_pred_obj(row) if row else None
        counts, issues = score_filing(gold[i], obj)
        total = add(total, counts)
        by_company[i.split("_")[0]] = add(by_company[i.split("_")[0]], counts)
        if issues:
            errors.append({"id": i, "issues": issues, "gold": {"category": gold[i]["category"], "events": gold[i]["events"]},
                           "pred": obj})

    m = metrics(total)
    ci = bootstrap(by_company, args.reps, args.seed)

    def line(label, key):
        lo, hi = ci[key]
        print(f"  {label:<22s} {m[key]:.3f}   (95% CI {lo:.3f} to {hi:.3f})")

    print(f"Scored {len(ids)} filings from {len(by_company)} companies "
          f"({len(preds)} predictions in file, {len(gold)} gold labels)\n")
    line("valid-output rate", "valid")
    line("category accuracy", "category_acc")
    line("event F1, core", "core_f1")
    line("event F1, full", "full_f1")
    line("event F1, strict", "strict_f1")
    print(f"\n  core  precision {m['core_p']:.3f}  recall {m['core_r']:.3f}")
    print(f"  full  precision {m['full_p']:.3f}  recall {m['full_r']:.3f}")
    print(f"\n  Among events that passed the core match ({total['core_tp']}):")
    print(f"    role accuracy {m['role_acc']:.3f}   event_date {m['event_date_acc']:.3f}   effective_date {m['effective_date_acc']:.3f}")
    neg = total["neg_n"]
    print(f"\n  False alarms: {total['neg_alarm']} of {neg} non-leadership filings got events "
          f"({m['false_alarm']:.1%})")
    if neg and total["neg_alarm"] == 0:
        print(f"    0 of {neg} is still compatible with a true rate up to about {3 / neg:.0%} (rule of three).")
    print("\n  Note: events with no match count against precision and recall; invalid outputs score as 'no events'.")

    if args.errors_out:
        out = Path(args.errors_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for e in errors:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"\n  {len(errors)} filings with at least one issue written to {out}")


if __name__ == "__main__":
    main()