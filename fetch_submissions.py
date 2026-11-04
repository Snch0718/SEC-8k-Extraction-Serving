"""Download SEC EDGAR "submissions" JSON files for a set of companies.

What it does
------------
1. Gets SEC's ticker -> CIK table (company_tickers.json).
2. Picks companies: either the tickers in a text file you provide, or the
   first N companies in SEC's table (the table appears to be ordered roughly
   by company size, which gives you large filers with plenty of 8-Ks;
   check the sectors in manifest.csv afterwards).
3. Downloads https://data.sec.gov/submissions/CIK##########.json for each one.
4. Saves each file to data/submissions/ and writes data/manifest.csv.

It follows SEC fair-access rules: a declared User-Agent (name + email), a
conservative request rate (default 4 per second, SEC's maximum is 10), retries
with backoff, and caching (files already on disk are never fetched again).

Usage
-----
    pip install requests

    # first 200 companies from SEC's table
    python fetch_submissions.py --user-agent "Your Name your.email@example.com"

    # or your own list, one ticker per line
    python fetch_submissions.py --user-agent "Your Name your.email@example.com" --tickers tickers.txt

You can also set the SEC_USER_AGENT environment variable instead of passing
--user-agent.
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def parse_args():
    p = argparse.ArgumentParser(description="Download SEC submissions JSON files.")
    p.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"),
                   help='Required by SEC, e.g. "Your Name your.email@example.com"')
    p.add_argument("--tickers", help="Text file with one ticker per line (optional)")
    p.add_argument("--count", type=int, default=200,
                   help="How many companies to take from SEC's table if no --tickers file (default 200)")
    p.add_argument("--out", default="data", help="Output folder (default: data)")
    p.add_argument("--rate", type=float, default=4.0,
                   help="Max requests per second (default 4; SEC's limit is 10)")
    return p.parse_args()


def check_user_agent(ua):
    if not ua or "@" not in ua or len(ua.split()) < 2:
        sys.exit('Please provide a User-Agent with your name and email, e.g. '
                 '--user-agent "Your Name your.email@example.com"')


def get_json(session, url, delay, max_retries=5):
    """GET a URL and return parsed JSON, or None if the file does not exist."""
    for attempt in range(max_retries):
        time.sleep(delay)
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException as e:
            wait = 2 ** attempt
            print(f"  network error ({e}); retrying in {wait}s")
            time.sleep(wait)
            continue

        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        if r.status_code == 403:
            # Usually a missing/invalid User-Agent or a temporary block.
            if attempt >= 2:
                sys.exit("Got HTTP 403 repeatedly. Check your User-Agent, "
                         "wait 10+ minutes if you were rate limited, then rerun "
                         "(files already downloaded are kept).")
        if r.status_code in (403, 429, 503):
            wait = min(60, 5 * 2 ** attempt)
            print(f"  HTTP {r.status_code}; waiting {wait}s before retry")
            time.sleep(wait)
            continue
        r.raise_for_status()

    print(f"  giving up on {url}")
    return None


def load_company_table(session, delay):
    data = get_json(session, TICKER_URL, delay)
    if not data:
        sys.exit("Could not download SEC's ticker table.")
    # {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    return list(data.values())


def choose_companies(table, tickers_file, count):
    if tickers_file:
        wanted = [t.strip().upper() for t in Path(tickers_file).read_text().splitlines()
                  if t.strip() and not t.startswith("#")]
        by_ticker = {row["ticker"].upper(): row for row in table}
        chosen, missing = [], []
        for t in wanted:
            if t in by_ticker:
                chosen.append(by_ticker[t])
            else:
                missing.append(t)
        if missing:
            print(f"Tickers not found in SEC's table (skipped): {', '.join(missing)}")
    else:
        chosen = table

    # One entry per company (some companies have several tickers).
    seen, unique = set(), []
    for row in chosen:
        cik = int(row["cik_str"])
        if cik not in seen:
            seen.add(cik)
            unique.append(row)
        if not tickers_file and len(unique) >= count:
            break
    return unique


def main():
    args = parse_args()
    check_user_agent(args.user_agent)
    delay = 1.0 / max(0.1, min(args.rate, 10.0))

    out_dir = Path(args.out)
    sub_dir = out_dir / "submissions"
    sub_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": args.user_agent, "Accept-Encoding": "gzip, deflate"})

    table = load_company_table(session, delay)
    companies = choose_companies(table, args.tickers, args.count)
    print(f"Fetching submissions for {len(companies)} companies "
          f"(about {len(companies) * delay / 60:.1f} minutes at the chosen rate)")

    manifest = []
    downloaded = cached = failed = 0

    for i, row in enumerate(companies, start=1):
        cik = f"{int(row['cik_str']):010d}"
        path = sub_dir / f"CIK{cik}.json"

        if path.exists():
            cached += 1
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = get_json(session, SUBMISSIONS_URL.format(cik=cik), delay)
            if data is None:
                failed += 1
                print(f"[{i}/{len(companies)}] {row['ticker']}: failed")
                continue
            path.write_text(json.dumps(data), encoding="utf-8")
            downloaded += 1
            print(f"[{i}/{len(companies)}] {row['ticker']}: saved")

        forms = data.get("filings", {}).get("recent", {}).get("form", [])
        manifest.append({
            "cik": cik,
            "ticker": row["ticker"],
            "name": data.get("name", row.get("title", "")),
            "sic": data.get("sic", ""),
            "sic_description": data.get("sicDescription", ""),
            "recent_8k_count": sum(1 for f in forms if f == "8-K"),
            "recent_10k_count": sum(1 for f in forms if f == "10-K"),
        })

    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "cik", "ticker", "name", "sic", "sic_description",
            "recent_8k_count", "recent_10k_count"])
        writer.writeheader()
        writer.writerows(manifest)

    print(f"\nDone. downloaded={downloaded} already_on_disk={cached} failed={failed}")
    print(f"Files: {sub_dir}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()