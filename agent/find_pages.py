"""Stage 1: for every diocese, find candidate web pages that carry the General Synod
election statements of its elected members. Writes data/sources.csv.

Methods, in order, per diocese:
  sitemap  - robots.txt Sitemap lines and /sitemap.xml, URLs containing 'synod'
  crawl    - home page, then links whose text or URL mention synod/election/governance,
             two levels deep, capped
  search   - DuckDuckGo HTML results for  site:<domain> "general synod" 2026
Every fetched page is scored: 3 per distinct elected surname found, plus keyword
bonuses, plus 1 per PDF link up to 5. The top pages per diocese are kept.
Usage: python3 agent/find_pages.py [--out FILE] [Diocese ...]
"""
import re, sys, urllib.parse
from bs4 import BeautifulSoup
from common import *

MAX_FETCH = 45
NAV_RE = re.compile(r"synod|election|governance|about|who-?s-?who|representatives|structure", re.I)
DEEP_RE = re.compile(r"synod|election|candidate|address|statement|results|elected", re.I)
KEYWORDS = [(r"general synod", 2), (r"election (address|statement)s?", 4), (r"candidate", 1),
            (r"elected", 1), (r"2026", 1), (r"proctors?|house of laity|house of clergy", 2)]


def same_site(url, domain):
    host = urllib.parse.urlparse(url).netloc.lower()
    return host.endswith(domain.lower())


def links(soup, base):
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(base, a["href"].strip())
        href = href.split("#")[0]
        if href.startswith("http"):
            yield href, a.get_text(" ", strip=True)


def score_page(text, soup, surnames):
    t = fold(text)
    found = sorted({s for s in surnames if re.search(rf"\b{re.escape(s)}\b", t)})
    sc = 3 * len(found)
    for pat, w in KEYWORDS:
        if re.search(pat, text, re.I):
            sc += w
    npdf = sum(1 for h, _ in links(soup, "http://x/") if h.lower().endswith(".pdf"))
    sc += min(npdf, 5)
    return sc, found, npdf


def sitemap_urls(home, domain):
    out = set()
    st, ct, body = fetch(urllib.parse.urljoin(home, "/robots.txt"))
    maps = re.findall(r"(?im)^sitemap:\s*(\S+)", body or "")
    maps.append(urllib.parse.urljoin(home, "/sitemap.xml"))
    seen = set()
    for sm in maps[:6]:
        if sm in seen: continue
        seen.add(sm)
        st, ct, body = fetch(sm)
        if not body or st != 200: continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
        subs = [l for l in locs if l.endswith(".xml")]
        for s in subs[:10]:
            st2, ct2, b2 = fetch(s)
            locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", b2 or "")
        out |= {l for l in locs if "synod" in l.lower() and same_site(l, domain)}
    return out


def ddg_search(domain):
    q = f'site:{domain} "general synod" 2026'
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)
    st, ct, body = fetch(url, sleep=1.5)
    if not body: return set()
    soup = BeautifulSoup(body, "lxml")
    out = set()
    for a in soup.select("a.result__a[href]"):
        href = a["href"]
        m = re.search(r"uddg=([^&]+)", href)
        if m: href = urllib.parse.unquote(m.group(1))
        if same_site(href, domain): out.add(href.split("#")[0])
    return out


def find(diocese, row, members):
    domain, home = row["domain"], row["home"]
    surnames = {fold(m["last_name"]) for m in members if m["last_name"]}
    log(f"== {diocese} ({domain}) {len(members)} members")
    queue, method, seen, results = [], {}, set(), []
    for u in sitemap_urls(home, domain):
        queue.append((u, 1)); method[u] = "sitemap"
    for u in ddg_search(domain):
        queue.append((u, 1)); method[u] = "search"
    queue.insert(0, (home, 0)); method[home] = "home"
    fetched = 0
    while queue and fetched < MAX_FETCH:
        url, depth = queue.pop(0)
        if url in seen or not same_site(url, domain): continue
        seen.add(url)
        if re.search(r"\.(pdf|docx?|jpe?g|png|zip|xml)$", url, re.I): continue
        st, ct, body = fetch(url)
        fetched += 1
        if not body or st != 200 or "html" not in (ct or ""):
            if st: log(f"    {st} {url}")
            continue
        soup = BeautifulSoup(body, "lxml")
        text = soup.get_text(" ", strip=True)
        sc, found, npdf = score_page(text, soup, surnames)
        title = (soup.title.get_text(strip=True) if soup.title else "")[:120]
        results.append(dict(diocese=diocese, url=url, score=sc, surnames_matched=len(found),
                            matched=" ".join(found), n_pdf=npdf, title=title, method=method.get(url, "crawl")))
        if sc >= 6: log(f"    {sc:3d} {len(found):2d} names {npdf:2d} pdfs  {url}")
        if depth < 2:
            pat = NAV_RE if depth == 0 else DEEP_RE
            for h, txt in links(soup, url):
                if h not in seen and same_site(h, domain) and (pat.search(h) or pat.search(txt)):
                    queue.append((h, depth + 1)); method.setdefault(h, "crawl")
    results.sort(key=lambda r: -r["score"])
    return results[:8]


def main():
    args = sys.argv[1:]
    out = DATA / "sources.csv"
    if "--out" in args:
        i = args.index("--out"); out = Path(args[i + 1]); del args[i:i + 2]
    want = set(args)
    members = diocesan_members()
    rows = []
    for row in load_dioceses():
        d = row["diocese"]
        if want and d not in want: continue
        rows += find(d, row, members.get(d, []))
    fields = ["diocese", "url", "score", "surnames_matched", "matched", "n_pdf", "title", "method"]
    if want and out.exists() and out.name == "sources.csv":  # merge into the existing file
        old = [r for r in read_csv(out) if r["diocese"] not in want]
        rows = old + rows
    rows.sort(key=lambda r: (r["diocese"], -int(r["score"])))
    write_csv(out, rows, fields)
    log(f"wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
