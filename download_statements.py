#!/usr/bin/env python3
"""Download the election statements listed in data/statements.csv.

    python3 download_statements.py [--out DIR] [--only Diocese ...] [--dry-run]

Files go to statements/<Diocese>/<GS number>-<surname>-<first name>.<ext> (the paths in the
`file` column), and documents that hold several members' statements are fetched once. Files
already present with the recorded SHA-256 are skipped. Some diocesan sites refuse requests
that do not come from a browser; those URLs are listed at the end so you can save them by hand.
Needs Python 3.8+ and the `requests` package (pip install requests)."""
import argparse, csv, hashlib, sys, time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

ROOT = Path(__file__).resolve().parent
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept": "application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/html;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-GB,en;q=0.9"}


def fetch(session, url):
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=60, allow_redirects=True)
        except requests.RequestException as e:
            return None, str(e)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1)); continue
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        body = r.content
        if body[:5] != b"%PDF-" and body[:2] != b"PK" and body[:4] != b"\xd0\xcf\x11\xe0" and b"<html" in body[:2000].lower():
            return None, "got a web page instead of a document"
        return body, ""
    return None, "HTTP 429 (rate limited)"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT), help="folder that will hold statements/ (default: next to this script)")
    ap.add_argument("--only", nargs="*", default=[], help="limit to these dioceses or constituencies")
    ap.add_argument("--dry-run", action="store_true", help="list what would be fetched and stop")
    ap.add_argument("--sleep", type=float, default=0.5, help="seconds between requests")
    args = ap.parse_args()
    rows = list(csv.DictReader(open(ROOT / "data" / "statements.csv", newline="", encoding="utf-8")))
    rows = [r for r in rows if r["status"] in ("downloaded", "compiled", "answers") and r["statement_url"]
            and (not args.only or r["diocese"] in args.only)]
    jobs = {}  # url -> (path, sha256, who)
    for r in rows:
        who = f"{r['gs_number']} {r['first_name']} {r['last_name']}"
        j = jobs.setdefault(r["statement_url"], [Path(args.out) / r["file"], r["sha256"], []])
        j[2].append(who)
    print(f"{len(rows)} statements in {len(jobs)} documents")
    if args.dry_run:
        for url, (path, sha, who) in jobs.items(): print(f"{path}  <-  {url}  ({len(who)} member{'s' if len(who) > 1 else ''})")
        return
    session = requests.Session()
    done = skipped = 0; failed = []
    for url, (path, sha, who) in jobs.items():
        if path.exists() and (not sha or hashlib.sha256(path.read_bytes()).hexdigest() == sha):
            skipped += 1; continue
        time.sleep(args.sleep)
        body, err = fetch(session, url)
        if body is None:
            failed.append((url, err, who, path)); print(f"FAIL {err}: {url}"); continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        if sha and hashlib.sha256(body).hexdigest() != sha:
            print(f"note: {path.name} differs from the copy recorded in statements.csv (the publisher may have replaced it)")
        done += 1; print(f"ok   {path.relative_to(Path(args.out))}")
    print(f"\ndownloaded {done}, already present {skipped}, failed {len(failed)}")
    if failed:
        print("\nThese could not be fetched by script. Open each URL in a browser and save it to the path shown:")
        for url, err, who, path in failed:
            print(f"  {url}\n      -> {path}   ({err}; {', '.join(who)})")
        sys.exit(1)


if __name__ == "__main__":
    main()
