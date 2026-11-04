"""Download 8-K filing documents using the submissions files you already have.

Reads data/submissions/*.json (from fetch_submissions.py), picks 8-K filings
from the last two years whose item numbers usually carry real event text in
the main document, samples them across companies, and downloads each filing's
primary document from SEC EDGAR.

Why only some 8-K items?
    Many 8-Ks (especially earnings releases, item 2.02) are a few lines of
    boilerplate with the real content in an attached exhibit, so the main
    document has nothing useful to extract. The default items below usually
    describe the event in the main document itself:
      1.01 material agreement      1.02 agreement terminated
      1.05 cybersecurity incident  2.01 acquisition/disposal completed
      2.05 exit/restructuring costs 3.01 listing notice
      4.01 auditor change          5.02 executive/director changes
      5.07 shareholder vote results

Outputs
    data/filings/<ticker>_<accession>.<ext>   raw filing documents
    data/filings_index.csv                    one row per selected filing

Usage
    python fetch_8k_filings.py --user-agent "Your Name your.email@example.com" --dry-run
    python fetch_8k_filings.py --user-agent "Your Name your.email@example.com"

Rerunning is safe: files already on disk are skipped.
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests

ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"
DEFAULT_ITEMS = "1.01,1.02,1.05,2.01,2.05,3.01,4.01,5.02,5.07"


def parse_args():
    p = argparse.ArgumentParser(description="Download 8-K primary documents.")
    p.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"),
                   help='Required by SEC, e.g. "Your Name your.email@example.com"')
    p.add_argument("--data", default="data", help="Folder used by fetch_submissions.py (default: data)")
    p.add_argument("--items", default=DEFAULT_ITEMS,
                   help='Comma-separated 8-K item numbers to keep, or "all" (default: %(default)s)')
    p.add_argument("--since", default=(date.today() - timedelta(days=730)).isoformat(),
                   help="Earliest filing date, YYYY-MM-DD (default: two years ago)")
    p.add_argument("--per-company", type=int, default=4,
                   help="Max filings per company (default 4)")
    p.add_argument("--total", type=int, default=600,
                   help="Max filings overall (default 600)")
    p.add_argument("--seed", type=int, default=42, help="Random seed for sampling (default 42)")
    p.add_argument("--rate", type=float, default=4.0,
                   help="Max requests per second (default 4; SEC's limit is 10)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be downloaded, without downloading")
    return p.parse_args()


def check_user_agent(ua):
    if not ua or "@" not in ua or len(ua.split()) < 2:
        sys.exit('Please provide a User-Agent with your name and email, e.g. '
                 '--user-agent "Your Name your.email@example.com"')


def load_tickers(data_dir):
    path = data_dir / "manifest.csv"
    tickers = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                tickers[row["cik"]] = row["ticker"]
    return tickers


def find_candidates(data_dir, since, wanted_items, tickers):
    sub_dir = data_dir / "submissions"
    files = sorted(sub_dir.glob("CIK*.json"))
    if not files:
        sys.exit(f"No submissions files found in {sub_dir}. Run fetch_submissions.py first.")

    out = []
    for path in files:
        d = json.loads(path.read_text(encoding="utf-8"))
        cik = f"{int(d['cik']):010d}"
        rec = d.get("filings", {}).get("recent", {})
        accs = rec.get("accessionNumber", [])
        forms = rec.get("form", [])
        dates = rec.get("filingDate", [])
        docs = rec.get("primaryDocument", [])
        items = rec.get("items", [])
        for i in range(len(accs)):
            if forms[i] != "8-K" or dates[i] < since or not docs[i]:
                continue
            item_str = items[i] if i < len(items) else ""
            item_list = [x.strip() for x in (item_str or "").split(",") if x.strip()]
            if wanted_items is not None and not (set(item_list) & wanted_items):
                continue
            ticker = tickers.get(cik) or (d.get("tickers") or [cik])[0]
            out.append({
                "cik": cik,
                "ticker": ticker,
                "company": d.get("name", ""),
                "accession": accs[i],
                "filing_date": dates[i],
                "items": ",".join(item_list),
                "primary_doc": docs[i],
            })
    return out


def sample(candidates, per_company, total, seed):
    rng = random.Random(seed)
    groups = defaultdict(list)
    for c in candidates:
        groups[c["cik"]].append(c)
    picked = []
    for cik in sorted(groups):
        group = groups[cik]
        rng.shuffle(group)
        picked.extend(group[:per_company])
    if len(picked) > total:
        picked = rng.sample(picked, total)
    picked.sort(key=lambda c: (c["cik"], c["filing_date"]))
    return picked


def fetch_bytes(session, url, delay, max_retries=5):
    for attempt in range(max_retries):
        time.sleep(delay)
        try:
            r = session.get(url, timeout=60)
        except requests.RequestException as e:
            wait = 2 ** attempt
            print(f"  network error ({e}); retrying in {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 200:
            return r.content
        if r.status_code == 404:
            return None
        if r.status_code == 403 and attempt >= 2:
            sys.exit("Got HTTP 403 repeatedly. Check your User-Agent, wait 10+ minutes "
                     "if you were rate limited, then rerun (downloaded files are kept).")
        if r.status_code in (403, 429, 503):
            wait = min(60, 5 * 2 ** attempt)
            print(f"  HTTP {r.status_code}; waiting {wait}s before retry")
            time.sleep(wait)
            continue
        r.raise_for_status()
    return None


def main():
    args = parse_args()
    data_dir = Path(args.data)
    wanted = None if args.items.strip().lower() == "all" else {x.strip() for x in args.items.split(",")}

    tickers = load_tickers(data_dir)
    candidates = find_candidates(data_dir, args.since, wanted, tickers)
    chosen = sample(candidates, args.per_company, args.total, args.seed)

    item_counts = Counter(i for c in chosen for i in c["items"].split(",") if i)
    print(f"8-Ks matching filters: {len(candidates)}")
    print(f"Selected after sampling: {len(chosen)} filings from {len({c['cik'] for c in chosen})} companies")
    print("Item mix in selection: " + ", ".join(f"{k}: {v}" for k, v in sorted(item_counts.items())))

    if not chosen:
        sys.exit("Nothing selected. Try --items all, or an earlier --since date. "
                 "Also open one submissions file and check that 'items' exists under filings > recent.")

    delay = 1.0 / max(0.1, min(args.rate, 10.0))
    print(f"Estimated download time: about {len(chosen) * delay / 60:.1f} minutes")

    out_dir = data_dir / "filings"
    out_dir.mkdir(parents=True, exist_ok=True)

    for c in chosen:
        ext = Path(c["primary_doc"]).suffix or ".htm"
        acc_nodash = c["accession"].replace("-", "")
        c["url"] = ARCHIVE_URL.format(cik_int=int(c["cik"]), acc_nodash=acc_nodash, doc=c["primary_doc"])
        c["path"] = str(out_dir / f"{c['ticker']}_{acc_nodash}{ext}")

    index_path = data_dir / "filings_index.csv"
    fields = ["cik", "ticker", "company", "accession", "filing_date", "items", "primary_doc", "url", "path"]
    with index_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(chosen)
    print(f"Index written: {index_path}")

    if args.dry_run:
        print("Dry run: nothing downloaded.")
        return

    session = requests.Session()
    session.headers.update({"User-Agent": args.user_agent, "Accept-Encoding": "gzip, deflate"})

    downloaded = cached = failed = 0
    for n, c in enumerate(chosen, start=1):
        path = Path(c["path"])
        if path.exists() and path.stat().st_size > 0:
            cached += 1
            continue
        content = fetch_bytes(session, c["url"], delay)
        if content is None:
            failed += 1
            print(f"[{n}/{len(chosen)}] {c['ticker']} {c['accession']}: failed")
            continue
        path.write_bytes(content)
        downloaded += 1
        if downloaded % 25 == 0 or n == len(chosen):
            print(f"[{n}/{len(chosen)}] downloaded so far: {downloaded}")

    print(f"\nDone. downloaded={downloaded} already_on_disk={cached} failed={failed}")
    print(f"Files: {out_dir}")


if __name__ == "__main__":
    main()