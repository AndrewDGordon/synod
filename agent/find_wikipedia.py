#!/usr/bin/env python3
"""Find the English Wikipedia article, if any, for each member in data/members.csv.
Usage: python3 agent/find_wikipedia.py [--out data/wikipedia.csv]
For every member it searches Wikipedia for the exact name (and nickname variants), keeps
articles whose title is the member's name, and reads the article's opening paragraph. A hit
whose opening mentions the Church of England, Anglican ministry or the Synod is 'confirmed';
a title match about something else is 'possible' and needs a human look. Members of the
category 'Members of the General Synod of the Church of England' are matched too."""
import csv, re, sys, time, unicodedata
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://en.wikipedia.org/w/api.php"
S = requests.Session()
S.headers["User-Agent"] = "synod-statements-agent/1.0 (https://github.com/AndrewDGordon/synod)"
CHURCH = re.compile(r"church of england|anglican|general synod|bishop|archdeacon|\bdean\b|\bpriest|\bvicar|\brector\b|\bcanon\b|diocese|archbishop|\bclergy|chaplain|cathedral|theolog|religious (?:order|community|sister|brother)", re.I)
NICKNAMES = [("charlie","charles"),("nick","nicholas"),("nicky","nicholas"),("chris","christopher"),("kat","katherine"),("kat","kathryn"),("kate","katherine"),
             ("kate","catherine"),("katie","katherine"),("tim","timothy"),("tom","thomas"),("dan","daniel"),("danny","daniel"),("mike","michael"),("rob","robert"),("bob","robert"),
             ("rich","richard"),("dick","richard"),("jonny","jonathan"),("jon","jonathan"),("jo","joanna"),("jo","joanne"),("jo","josephine"),("becky","rebecca"),
             ("ben","benjamin"),("sam","samuel"),("sam","samantha"),("andy","andrew"),("steve","stephen"),("steve","steven"),("bill","william"),("will","william"),
             ("ed","edward"),("ted","edward"),("liz","elizabeth"),("beth","elizabeth"),("lizzie","elizabeth"),("pete","peter"),("matt","matthew"),("greg","gregory"),
             ("alex","alexander"),("alex","alexandra"),("jim","james"),("jamie","james"),("tony","anthony"),("vicky","victoria"),("vicki","victoria"),("jen","jennifer"),
             ("jenny","jennifer"),("jenn","jennifer"),("debbie","deborah"),("deb","deborah"),("sue","susan"),("suzie","susan"),("pat","patricia"),("pat","patrick"),
             ("gilli","gillian"),("gill","gillian"),("jill","gillian"),("joe","joseph"),("ian","iain"),("phil","philip"),("phil","phillip"),("fred","frederick"),
             ("ray","raymond"),("ron","ronald"),("ollie","oliver"),("olly","oliver"),("harry","henry"),("max","maximilian"),("josh","joshua"),("nat","nathan"),
             ("nat","natalie"),("mandy","amanda"),("sandy","alexander"),("rod","roderick"),("rod","rodney"),("rick","richard"),("rachael","rachel"),("abi","abigail"),
             ("tiffer","christopher"),("jess","jessica"),("maggie","margaret"),("peggy","margaret"),("meg","margaret"),("cathy","catherine"),("cathy","katherine"),
             ("ruth","ruth"),("tess","teresa"),("hannah","hannah"),("terry","terence"),("stewart","stuart"),("geoff","geoffrey"),("jeff","jeffrey"),("don","donald")]


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()


def first_variants(first):
    f = fold(first).split()
    base = f[0] if f else ""
    out = {base}
    for a, b in NICKNAMES:
        if base == a: out.add(b)
        if base == b: out.add(a)
    if f and len(f) > 1: out.add(" ".join(f))
    return {v for v in out if v}


import json, hashlib
CACHE = Path(__import__("os").environ.get("WIKI_CACHE", "/tmp/claude-1000/-home-adg-git-imprimatur/73178431-e48e-4baf-a226-c7cae7b74ceb/scratchpad/wikicache"))
CACHE.mkdir(parents=True, exist_ok=True)


def api(**params):
    params.update(format="json", formatversion=2)
    key = CACHE / (hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest() + ".json")
    if key.exists(): return json.loads(key.read_text())
    for attempt in range(3):
        try:
            r = S.get(API, params=params, timeout=30)
            if r.status_code == 200:
                key.write_text(r.text); return r.json()
        except requests.RequestException: pass
        time.sleep(2 * (attempt + 1))
    return {}


def title_matches(title, m):
    t = fold(re.sub(r"\s*\(.*?\)\s*$", "", title))
    sur = fold(m["last_name"])
    if not re.search(rf"\b{re.escape(sur)}\b", t): return False
    return any(re.search(rf"\b{re.escape(v)}\b", t) for v in first_variants(m["first_name"]))


ROLE = {"Rt Revd": r"bishop", "Most Revd": r"archbishop|bishop", "Very Revd": r"\bdean\b|provost|priest", "Ven": r"archdeacon|priest|chaplain",
        "Revd": r"priest|vicar|rector|chaplain|clergy|minister|curate|canon|theolog|archdeacon|\bdean\b|bishop"}
ANGLICAN = re.compile(r"church of england|anglican|episcopal|general synod|church commissioner|archbishops' council", re.I)
DEAD = re.compile(r"\(\s*(?:born\s+)?(?:\d{1,2}\s+\w+\s+)?\d{4}\s*[–-]\s*(?:\d{1,2}\s+\w+\s+)?\d{4}\s*\)|\bdied\b|\(d\.|^[^.]{0,200}\bwas (?:an?|the)\b", re.I)
BORN = re.compile(r"\b(?:born|b\.)\s+(?:\d{1,2}\s+\w+\s+)?(\d{4})|\((\d{4})\s*[–-]")


def assess(m, title, ex, in_cat):
    """Return (score, status) for a candidate article, or (None, None) to reject it."""
    head = ex[:1500]
    if re.search(r"may refer to|is a surname|is the name of|list of", head[:300], re.I): return None, None
    if DEAD.search(head[:400]): return None, None  # the members are alive and current
    yr = BORN.search(head[:400])
    if yr and int(yr.group(1) or yr.group(2)) < 1935: return None, None
    if re.search(r"roman catholic|methodist|baptist|presbyterian|church of scotland", head[:600], re.I) and not ANGLICAN.search(head): return None, None
    score = 0
    if in_cat: score += 10
    exact = fold(re.sub(r"\s*\(.*?\)\s*$", "", title)) in {f"{v} {fold(m['last_name'])}" for v in first_variants(m["first_name"])}
    if exact: score += 3
    anglican = bool(ANGLICAN.search(head))
    church = bool(CHURCH.search(head))
    key = next((k for k in ROLE if k in m["title"]), None)
    if key:  # ordained: the page must describe a cleric, and an Anglican one
        if not re.search(ROLE[key], head, re.I): return None, None
        if not (anglican or church): return None, None
        score += 4 + (2 if anglican else 0)
        return score, "confirmed"
    # lay member: a page about a cleric of that name is someone else; a page naming the Synod or the
    # Church of England is confirmed; anything else needs a human look
    if re.search(r"is an? (?:\w+ ){0,4}(?:bishop|priest|archdeacon|dean|vicar|clergyman|cleric)|ordained", head[:400], re.I) and not in_cat: return None, None
    if anglican or in_cat: return score + 4, "confirmed"
    return score, "possible"


def search(m):
    """Titles of articles that could be about this member."""
    sur = m["last_name"]
    titles = []
    queries = [f'"{v} {sur}"' for v in sorted(first_variants(m["first_name"]))]
    queries += [f'intitle:"{sur}" {v}' for v in sorted(first_variants(m["first_name"]))]
    for q in queries:
        res = api(action="query", list="search", srsearch=q, srlimit=25, srnamespace=0)
        for h in res.get("query", {}).get("search", []):
            if h["title"] not in titles: titles.append(h["title"])
        time.sleep(0.15)
    return [t for t in titles if title_matches(t, m)]


def extracts(titles):
    out = {}
    for i in range(0, len(titles), 20):
        res = api(action="query", prop="extracts|info", exintro=1, explaintext=1, exlimit=20, inprop="url", redirects=1, titles="|".join(titles[i:i + 20]))
        for p in res.get("query", {}).get("pages", []):
            out[p["title"]] = (p.get("extract", ""), p.get("fullurl", ""), "missing" in p, p.get("pageid"))
        time.sleep(0.2)
    return out


def full_text(title):
    res = api(action="query", prop="extracts", explaintext=1, redirects=1, titles=title)
    for p in res.get("query", {}).get("pages", []): return p.get("extract", "")
    return ""


REJECT = {("207", "Christopher Robinson (musician)"),  # checked by hand against the member's statement: a different person
          ("335", "Christopher Gill"), ("340", "John Wilson (bishop)")}
# checked by hand against the member's election statement or role: the article is about this member
ACCEPT = {"246": "James Cary (writer)", "301": "Andrew D. Gordon", "309": "Bijan Omrani", "462": "Caroline Spelman"}


def main():
    out_path = DATA / "wikipedia.csv"
    if "--out" in sys.argv: out_path = Path(sys.argv[sys.argv.index("--out") + 1])
    members = list(csv.DictReader(open(DATA / "members.csv", newline="", encoding="utf-8")))
    cat = api(action="query", list="categorymembers", cmtitle="Category:Members of the General Synod of the Church of England", cmlimit=500)
    cat_titles = [c["title"] for c in cat.get("query", {}).get("categorymembers", [])]
    rows = []
    for i, m in enumerate(members, 1):
        if not m["last_name"].strip(): continue
        cands = ([ACCEPT[m["gs_number"]]] if m["gs_number"] in ACCEPT else []) + [t for t in cat_titles if title_matches(t, m)] + search(m)
        cands = list(dict.fromkeys(cands))
        info = extracts(cands) if cands else {}
        best = None
        for t in cands:
            ex, url, missing, pid = info.get(t, ("", "", True, None))
            if missing or not ex: continue
            if (m["gs_number"], t) in REJECT: continue
            if ACCEPT.get(m["gs_number"]) == t: score, status = 20, "confirmed"
            else: score, status = assess(m, t, ex, t in cat_titles)
            if score is None: continue
            if status == "possible":  # the whole article may still mention the Synod or the Church
                body = full_text(t)
                if re.search(r"general synod", body, re.I): score, status = score + 6, "confirmed"
                elif re.search(r"church of england|anglican", body, re.I): score, status = score + 3, "likely"
            cand = (-score, t, url, status, ex)
            if best is None or cand < best: best = cand
        if best:
            _, t, url, status, ex = best
            rows.append(dict(gs_number=m["gs_number"], title=t, url=url, status=status, in_category="yes" if t in cat_titles else "",
                             summary=re.sub(r"\s+", " ", ex)[:300]))
            print(f"{m['gs_number']:>4} {m['first_name']} {m['last_name']}: {status} -> {t}", flush=True)
        else:
            rows.append(dict(gs_number=m["gs_number"], title="", url="", status="none", in_category="", summary=""))
        if i % 50 == 0: print(f"... {i}/{len(members)}", flush=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["gs_number", "title", "url", "status", "in_category", "summary"])
        w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(Counter(r["status"] for r in rows))
    for r in rows:
        if r["status"] in ("possible", "likely"): print(f"  {r['status']:8} {r['gs_number']:>4} {r['title']}")
    unmatched = [t for t in cat_titles if not any(r["title"] == t for r in rows)]
    print("category members not matched to the list:", unmatched)


if __name__ == "__main__":
    main()
