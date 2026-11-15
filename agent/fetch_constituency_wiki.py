#!/usr/bin/env python3
"""Record the Wikipedia article for every constituency (dioceses from data/dioceses.csv, the
others from a table here) and for the three Houses: title, URL, lead-image thumbnail and the
opening sentences, for the site's links and hover cards. Writes data/constituency-wikipedia.csv.
Usage: python3 agent/fetch_constituency_wiki.py"""
import csv, re, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://en.wikipedia.org/w/api.php"
S = requests.Session()
S.headers["User-Agent"] = "synod-statements-agent/1.0 (https://github.com/AndrewDGordon/synod)"
SPECIAL_DIOCESES = {"Europe": "Diocese in Europe", "Sodor and Man": "Diocese of Sodor and Man", "St Albans": "Diocese of St Albans",
                    "St Eds and Ipswich": "Diocese of St Edmundsbury and Ipswich", "Southwell & Nottingham": "Diocese of Southwell and Nottingham"}
OTHERS = {"Suffragan Bishop": "Suffragan bishop", "Deans": "Dean (Christianity)", "Religious Communities": "Anglican religious order",
          "Universities and TEIs": "Theological college", "Archbishops' Council": "Archbishops' Council", "Ex Officio": "Ex officio member",
          "Ecumenical Representatives": "Ecumenism", "Salisbury - Channel Islands": "Channel Islands", "St Eds & Ipswich": "Diocese of St Edmundsbury and Ipswich",
          "house:Bishops": "House of Bishops (Church of England)", "house:Clergy": "House of Clergy", "house:Laity": "House of Laity"}


def api(**params):
    params.update(format="json", formatversion=2)
    for attempt in range(3):
        try:
            r = S.get(API, params=params, timeout=30)
            if r.status_code == 200: return r.json()
        except requests.RequestException: pass
        time.sleep(2)
    return {}


def main():
    dioceses = list(csv.DictReader(open(DATA / "dioceses.csv", newline="", encoding="utf-8")))
    want = {d["diocese"]: SPECIAL_DIOCESES.get(d["diocese"], f"Diocese of {d['diocese']}") for d in dioceses}
    want.update(OTHERS)
    titles = sorted(set(want.values()))
    info = {}
    for i in range(0, len(titles), 20):
        res = api(action="query", prop="info|pageimages|extracts", inprop="url", piprop="thumbnail", pithumbsize=240, redirects=1,
                  exintro=1, explaintext=1, exsentences=3, exlimit=20, titles="|".join(titles[i:i + 20]))
        q = res.get("query", {})
        red = {x["from"]: x["to"] for x in q.get("redirects", [])}
        norm = {x["from"]: x["to"] for x in q.get("normalized", [])}
        pages = {p["title"]: p for p in q.get("pages", [])}
        for t in titles[i:i + 20]:
            p = pages.get(red.get(norm.get(t, t), norm.get(t, t)), {})
            if p and "missing" not in p:
                info[t] = dict(title=p["title"], url=p.get("fullurl", ""), thumb_url=p.get("thumbnail", {}).get("source", "").split("?")[0],
                               abstract=re.sub(r"\s+", " ", p.get("extract", "")).strip()[:600])
        time.sleep(0.2)
    rows = []
    for k, t in want.items():
        if t in info: rows.append(dict(constituency=k, **info[t]))
        else: print("no article:", k, "->", t)
    with open(DATA / "constituency-wikipedia.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["constituency", "title", "url", "thumb_url", "abstract"]); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} constituencies and houses with articles, {sum(1 for r in rows if r['thumb_url'])} with images")


if __name__ == "__main__":
    main()
