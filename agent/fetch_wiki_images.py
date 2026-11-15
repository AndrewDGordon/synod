#!/usr/bin/env python3
"""For each member with a Wikipedia article (data/wikipedia.csv), record the article's lead image
(a thumbnail URL on upload.wikimedia.org, the Commons file page, the author and the licence, so the
site can show the photo with its credit) and the opening sentences of the article for the hover
card. Writes data/wikipedia-images.csv.
Usage: python3 agent/fetch_wiki_images.py"""
import csv, re, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
S = requests.Session()
S.headers["User-Agent"] = "synod-statements-agent/1.0 (https://github.com/AndrewDGordon/synod)"
THUMB = 240


def api(url, **params):
    params.update(format="json", formatversion=2)
    for attempt in range(3):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 200: return r.json()
        except requests.RequestException: pass
        time.sleep(2)
    return {}


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def main():
    rows = [r for r in csv.DictReader(open(DATA / "wikipedia.csv", newline="", encoding="utf-8")) if r["status"] in ("confirmed", "likely")]
    out = []
    for i in range(0, len(rows), 20):
        batch = rows[i:i + 20]
        res = api(API, action="query", prop="pageimages|extracts", piprop="thumbnail|name", pithumbsize=THUMB, redirects=1,
                  exintro=1, explaintext=1, exsentences=3, exlimit=20, titles="|".join(r["title"] for r in batch))
        pages = {p["title"]: p for p in res.get("query", {}).get("pages", [])}
        redirects = {x["from"]: x["to"] for x in res.get("query", {}).get("redirects", [])}
        for r in batch:
            p = pages.get(redirects.get(r["title"], r["title"]), {})
            thumb = p.get("thumbnail", {}).get("source", "").split("?")[0]
            fname = p.get("pageimage", "")
            abstract = re.sub(r"\s+", " ", p.get("extract", "")).strip()[:600]
            rec = dict(gs_number=r["gs_number"], title=r["title"], thumb_url=thumb, file="File:" + fname if fname else "",
                       file_page="", artist="", licence="", licence_url="", abstract=abstract)
            if fname:
                info = api(COMMONS, action="query", prop="imageinfo", iiprop="extmetadata|url", titles="File:" + fname)
                for q in info.get("query", {}).get("pages", []):
                    ii = (q.get("imageinfo") or [{}])[0]
                    em = ii.get("extmetadata", {})
                    rec.update(file_page=ii.get("descriptionurl", ""), artist=strip_html(em.get("Artist", {}).get("value", ""))[:120],
                               licence=em.get("LicenseShortName", {}).get("value", ""), licence_url=em.get("LicenseUrl", {}).get("value", ""))
                if not rec["file_page"]:  # the file is on English Wikipedia itself, not Commons
                    info = api(API, action="query", prop="imageinfo", iiprop="extmetadata|url", titles="File:" + fname)
                    for q in info.get("query", {}).get("pages", []):
                        ii = (q.get("imageinfo") or [{}])[0]
                        em = ii.get("extmetadata", {})
                        rec.update(file_page=ii.get("descriptionurl", ""), artist=strip_html(em.get("Artist", {}).get("value", ""))[:120],
                                   licence=em.get("LicenseShortName", {}).get("value", ""), licence_url=em.get("LicenseUrl", {}).get("value", ""))
                time.sleep(0.2)
            out.append(rec)
            print(f"{r['gs_number']:>4} {r['title']}: {'image' if thumb else 'no image'} {rec['licence']}")
    with open(DATA / "wikipedia-images.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
    print(f"{sum(1 for r in out if r['thumb_url'])} images for {len(out)} members")


if __name__ == "__main__":
    main()
