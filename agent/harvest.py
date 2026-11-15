"""Stage 2: from the candidate pages in data/sources.csv (and any hand-added pages in
data/sources-manual.csv), find each elected member's election statement, download it to
statements/<Diocese>/, and record the result in data/statements.csv and data/coverage.md.

Matching: an anchor is a candidate statement for a member when the member's surname
appears in the anchor text, its parent element's text, or the link's filename. Where two
members of a diocese share a surname the first name must appear too. PDFs and Word files
are downloaded; a same-site HTML link is followed one level and either yields a PDF or is
saved as an HTML statement when it is a substantial page about the member.
Usage: python3 agent/harvest.py [Diocese ...]        (--sources FILE to use a test file)
"""
import re, sys, hashlib, datetime, urllib.parse
from bs4 import BeautifulSoup
from common import *

MIN_SCORE, MIN_NAMES, PAGES_PER_DIOCESE = 12, 2, 4
DOC_RE = re.compile(r"\.(pdf|docx?|odt|rtf)(\?|$)", re.I)
HINT_RE = re.compile(r"address|statement|candidate|profile|manifesto|biography|bio\b|about|read more|download|view", re.I)
SKIP_RE = re.compile(r"results?|cookie|privacy|policy|safeguard|minutes|agenda|facebook|twitter|mailto:", re.I)
STATEMENTS = ROOT / "statements"
FIELDS = ["gs_number", "diocese", "constituency", "house", "title", "first_name", "last_name", "status",
          "statement_url", "source_page", "file", "content_type", "bytes", "sha256", "fetched_at", "note"]


def choose_pages(sources, diocese):
    rows = [r for r in sources if r["diocese"] == diocese]
    manual = [r["url"] for r in rows if r.get("method") == "manual"]
    auto = [r["url"] for r in rows if r.get("method") != "manual"
            and int(r["score"]) >= MIN_SCORE and int(r["surnames_matched"]) >= MIN_NAMES]
    out = []
    for u in manual + auto:
        if u not in out: out.append(u)
    return out[:PAGES_PER_DIOCESE + len(manual)]


def anchors(soup, base):
    """(href, anchor text, wider context, filename) for every link; context = parent text."""
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(base, a["href"].strip()).split("#")[0]
        if not href.startswith("http"): continue
        atext = a.get_text(" ", strip=True)
        parent, ctx = a.parent, atext
        for _ in range(2):
            if parent is None: break
            ptxt = parent.get_text(" ", strip=True)
            if len(ptxt) < 300: ctx = ctx + " " + ptxt; parent = parent.parent
            else: break
        fname = urllib.parse.unquote(urllib.parse.urlparse(href).path.rsplit("/", 1)[-1])
        yield href, atext, ctx, fname


NICKNAMES = [("charlie", "charles"), ("nick", "nicholas"), ("chris", "christopher"), ("kate", "katherine", "catherine", "kathryn"),
             ("debbie", "deborah"), ("becky", "bex", "rebecca"), ("jan", "janette", "janet"), ("jonny", "jon", "jonathan"),
             ("sam", "samuel", "samantha", "sammi"), ("mike", "michael"), ("dave", "david"), ("liz", "elizabeth", "lizzie"),
             ("jo", "joanna", "joanne", "josephine"), ("tom", "thomas"), ("dan", "daniel"), ("andy", "andrew"),
             ("rick", "richard"), ("matt", "matthew"), ("steve", "stephen", "steven"), ("pete", "peter"), ("rob", "bob", "robert"),
             ("jim", "james"), ("bill", "will", "william"), ("ben", "benjamin"), ("mel", "melanie"), ("sue", "susan"),
             ("tim", "timothy"), ("ed", "edward"), ("ali", "alison"), ("izzy", "isabel", "isobel"), ("jess", "jessica"),
             ("jenny", "jennifer", "jenni"), ("phil", "philip"), ("ian", "iain"), ("ken", "kenneth"), ("alex", "alexandra", "alexander")]


def first_names(m):
    """The member's first name plus its usual variants, folded."""
    f = fold(m["first_name"]).split()
    out = set(f[:1])
    for group in NICKNAMES:
        if out & set(group): out |= set(group)
    return out


def load_aliases():
    """data/aliases.csv: gs_number,alias  (other spellings of a surname used on diocesan pages)."""
    path = DATA / "aliases.csv"
    out = {}
    if path.exists():
        for r in read_csv(path): out.setdefault(r["gs_number"], []).append(fold(r["alias"]))
    return out


ALIASES = load_aliases()


def surname_patterns(m):
    return [fold(m["last_name"])] + ALIASES.get(m["gs_number"], [])


def member_matches(members, ctx, fname):
    """Members whose surname (and first name, when the surname is shared) occur in the text.
    In filenames the surname may run straight into the next word, so only a leading boundary is required."""
    t, f = fold(ctx), fold(fname)
    hits = []
    surnames = [fold(m["last_name"]) for m in members]
    for m in members:
        pats = [p for p in surname_patterns(m) if p]
        if not any(re.search(rf"\b{re.escape(p)}\b", t) or re.search(rf"\b{re.escape(p)}", f) for p in pats): continue
        if surnames.count(fold(m["last_name"])) > 1:
            if not any(re.search(rf"\b{re.escape(n)}\b", t + " " + f) for n in first_names(m)): continue
        hits.append(m)
    return hits


def name_agreement(m, text):
    """+1 when the member's first name (or a variant) is in the text, -1 when a different first name
    directly precedes the surname, else 0. Used to rank links that share a surname."""
    t = fold(text)
    if any(re.search(rf"\b{re.escape(n)}\b", t) for n in first_names(m)): return 1
    for p in surname_patterns(m):
        mm = re.search(rf"\b([a-z]+)\s+{re.escape(p)}\b", t)
        if mm and mm.group(1) not in {"revd", "canon", "dr", "mr", "mrs", "ms", "miss", "ven", "fr", "the", "prof", "professor", "sir", "dame"}:
            return -1
    return 0


def safe_name(m, ext):
    return f'{int(m["gs_number"]):03d}-{fold(m["last_name"]).replace(" ", "-")}-{fold(m["first_name"]).replace(" ", "-")}{ext}'


def download(url, m, diocese):
    st, ct, body = fetch(url, binary=True, timeout=60)
    if st != 200 or not body: return None
    ext = {"application/pdf": ".pdf", "application/msword": ".doc",
           "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"}.get(ct)
    if ext is None:
        if body[:4] == b"%PDF": ext, ct = ".pdf", "application/pdf"
        elif "html" in (ct or ""): ext = ".html"
        else: ext = "." + (DOC_RE.search(url).group(1).lower() if DOC_RE.search(url) else "bin")
    d = STATEMENTS / diocese.replace(" ", "_").replace("&", "and")
    d.mkdir(parents=True, exist_ok=True)
    p = d / safe_name(m, ext)
    p.write_bytes(body)
    return dict(file=str(p.relative_to(ROOT)), content_type=ct, bytes=len(body),
                sha256=hashlib.sha256(body).hexdigest(), note=verify(p, m, ext))


def verify(path, m, ext):
    """Return '' when the file's text names the member, else a note. PDFs via pdftotext."""
    import subprocess
    try:
        if ext == ".pdf":
            txt = subprocess.run(["pdftotext", "-l", "3", str(path), "-"], capture_output=True, text=True, timeout=60).stdout
        elif ext == ".html":
            txt = BeautifulSoup(path.read_text(errors="replace"), "lxml").get_text(" ")
        else:
            return "not verified: " + ext
    except Exception as e:
        return "verify failed: " + e.__class__.__name__
    t = fold(txt)
    if not t.strip(): return "no extractable text (scanned?)"
    if any(re.search(rf"\b{re.escape(p)}\b", t) for p in surname_patterns(m) if p):
        return "" if any(re.search(rf"\b{re.escape(n)}\b", t) for n in first_names(m)) else "first name not found in file text"
    return "surname not found in file text"


def harvest_diocese(diocese, members, pages, domain):
    found, named = {}, {}
    for page in pages:
        st, ct, body = fetch(page)
        if st != 200 or not body: log(f"    {st} {page}"); continue
        soup = BeautifulSoup(body, "lxml")
        text = fold(soup.get_text(" ", strip=True))
        for m in members:
            if re.search(rf"\b{re.escape(fold(m['last_name']))}\b", text): named.setdefault(m["gs_number"], page)
        cands = []  # (priority, member, href, page)
        for href, atext, ctx, fname in anchors(soup, page):
            if SKIP_RE.search(atext) and not DOC_RE.search(href): continue
            if SKIP_RE.search(fname) and not HINT_RE.search(fname): continue
            # the link's own text and filename first; the surrounding text only as a fallback
            hits = member_matches(members, atext, fname) or member_matches(members, ctx, fname)
            if len(hits) > 1:  # e.g. "Hannah Lockwood" when another member's surname is Hannah
                best = [h for h in hits if name_agreement(h, atext + " " + fname) > 0]
                hits = best if len(best) == 1 else hits
            if len(hits) != 1: continue
            m = hits[0]
            isdoc = bool(DOC_RE.search(href))
            same = urllib.parse.urlparse(href).netloc.lower().endswith(domain.lower())
            if not isdoc and not same: continue
            if not isdoc and not (HINT_RE.search(ctx) or fold(m["last_name"]) in fold(href)): continue
            pri = (-name_agreement(m, atext + " " + fname), 0 if isdoc else 1, 0 if HINT_RE.search(ctx + " " + fname) else 1)
            cands.append((pri, m, href))
        cands.sort(key=lambda c: c[0])
        for pri, m, href in cands:
            if m["gs_number"] in found: continue
            if DOC_RE.search(href):
                info = download(href, m, diocese)
                if info: found[m["gs_number"]] = dict(status="downloaded", statement_url=href, source_page=page, **info)
                continue
            # HTML sub-page: look for a document link, else keep the page itself
            st2, ct2, body2 = fetch(href)
            if st2 != 200 or not body2: continue
            sub = BeautifulSoup(body2, "lxml")
            docs = [h for h, a, c, f in anchors(sub, href) if DOC_RE.search(h)]
            docs = [h for h in docs if member_matches([m], "", urllib.parse.unquote(h))] or docs[:1]
            if docs:
                info = download(docs[0], m, diocese)
                if info:
                    found[m["gs_number"]] = dict(status="downloaded", statement_url=docs[0], source_page=href, **info); continue
            subtext = sub.get_text(" ", strip=True)
            if len(subtext) > 800 and re.search(rf"\b{re.escape(fold(m['last_name']))}\b", fold(subtext)):
                info = download(href, m, diocese)
                if info: found[m["gs_number"]] = dict(status="html-page", statement_url=href, source_page=page, **info)
    return found, named


def harvest_urls(diocese, members, found):
    """data/statement-urls.csv: gs_number,url,source_page,note. Statement files found by hand or by web
    search. Downloaded when the site allows; otherwise recorded as 'url-only' so the link is kept."""
    path = DATA / "statement-urls.csv"
    if not path.exists(): return
    by = {m["gs_number"]: m for m in members}
    for row in read_csv(path):
        m = by.get(row["gs_number"])
        if not m or m["gs_number"] in found: continue
        info = download(row["url"], m, diocese)
        if info:
            found[m["gs_number"]] = dict(status="downloaded", statement_url=row["url"], source_page=row.get("source_page", ""), **info)
        elif (kept := existing_file(diocese, m)):
            found[m["gs_number"]] = dict(status="downloaded", statement_url=row["url"], source_page=row.get("source_page", ""), **kept)
        else:
            found[m["gs_number"]] = dict(status="url-only", statement_url=row["url"], source_page=row.get("source_page", ""),
                                         note=row.get("note") or "site refuses scripted download; fetch in a browser")


def existing_file(diocese, m):
    """A file imported by hand earlier (statements/<Diocese>/<gs>-*), kept when the site now refuses scripts."""
    d = STATEMENTS / diocese.replace(" ", "_").replace("&", "and")
    for p in sorted(d.glob(f"{m['gs_number']}-*")) if d.exists() else []:
        body = p.read_bytes()
        ct = "application/pdf" if p.suffix == ".pdf" else "application/octet-stream"
        return dict(file=str(p.relative_to(ROOT)), content_type=ct, bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
                    note="kept from an earlier hand import; site refuses scripted download")
    return None


def harvest_compiled(diocese, members, found):
    """Documents in data/compiled.csv that carry several members' statements in one file.
    Each member of the matching house gets status 'compiled' with the page range naming them.
    A row with kind=answers is a collection of candidates' answers to electors' questions rather than
    election addresses: members named in it get status 'answers', which coverage counts separately."""
    import subprocess
    path = DATA / "compiled.csv"
    if not path.exists(): return
    for row in read_csv(path):
        if row["diocese"] != diocese: continue
        st, ct, body = fetch(row["url"], binary=True, timeout=90)
        if st != 200 or not body: log(f"    {st} compiled {row['url']}"); continue
        d = STATEMENTS / diocese.replace(" ", "_").replace("&", "and"); d.mkdir(parents=True, exist_ok=True)
        tag = fold(Path(row["url"].split("?")[0]).stem).replace(" ", "-")  # several files may share a house
        p = d / f"_compiled-{tag}.pdf"
        p.write_bytes(body)
        pages = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, timeout=120).stdout.split("\f")
        if pages and not pages[-1].strip(): pages.pop()  # pdftotext ends the last page with a form feed
        folded = [fold(pg) for pg in pages]
        def first_pos(m, pg):
            hit = re.search(rf"\b{re.escape(fold(m['last_name']))}\b", pg)
            return hit.start() if hit else None
        answers = (row.get("kind") or "").strip().lower() == "answers"
        names_on = [{m["gs_number"] for m in members if first_pos(m, pg) is not None} for pg in folded]
        # contents, nomination or results pages name several members and are not anyone's statement
        def is_index(i):
            ns = names_on[i]
            if len(ns) >= 3: return True
            if i == 0 and len(ns) >= 2:  # a nomination list opens with its heading; a statement opens with the member's name
                kw = re.search(r"nominat|contents|result", folded[i])
                first = min(first_pos(m, folded[i]) for m in members if m["gs_number"] in ns)
                return bool(kw) and kw.start() < first
            return False
        index_pages = set() if answers else {i for i in range(len(names_on)) if is_index(i)}
        if not answers:
            # a statement page that mentions another member (a proposer, say) belongs to the member named first
            for i, ns in enumerate(names_on):
                if len(ns) >= 2 and i not in index_pages:
                    owner = min(ns, key=lambda g: first_pos(next(m for m in members if m["gs_number"] == g), folded[i]))
                    names_on[i] = {owner}
        image_pages = [i + 1 for i, pg in enumerate(folded) if len(pg.strip()) < 40 and not names_on[i]]  # scanned pages
        for m in members:
            if m["gs_number"] in found: continue
            if row.get("house") and m["house"] != row["house"]: continue
            hits = [i + 1 for i, ns in enumerate(names_on) if m["gs_number"] in ns and i not in index_pages]
            listed = [i + 1 for i in index_pages if m["gs_number"] in names_on[i]]
            if answers and hits: note = f"answers to electors' questions, not an election address; pages {', '.join(map(str, hits))} of compiled file"
            elif hits: note = f"pages {hits[0]}-{hits[-1]} of compiled file"
            elif listed and image_pages:
                note = (f"listed on contents page {listed[0]} of compiled file; statement is probably on an image-only page "
                        f"without extractable text (pages {image_pages[0]}-{image_pages[-1]})")
            elif listed:
                found[m["gs_number"]] = dict(status="named-no-link", statement_url=row["url"], source_page=row.get("note", ""),
                                             note=f"named on page {listed[0]} of the compiled file but has no statement page in it")
                continue
            else: continue
            found[m["gs_number"]] = dict(status="answers" if answers else "compiled", statement_url=row["url"], source_page=row.get("note", ""),
                                         file=str(p.relative_to(ROOT)), content_type="application/pdf", bytes=len(body),
                                         sha256=hashlib.sha256(body).hexdigest(), note=note)


def main():
    args = sys.argv[1:]
    src = DATA / "sources.csv"
    if "--sources" in args:
        i = args.index("--sources"); src = Path(args[i + 1]); del args[i:i + 2]
    want = set(args)
    sources = read_csv(src)
    manual = DATA / "sources-manual.csv"
    if manual.exists():
        sources += [dict(r, method="manual", score="99", surnames_matched="99") for r in read_csv(manual)]
    members = diocesan_members()
    domains = {r["diocese"]: r["domain"] for r in load_dioceses()}
    notes_path = DATA / "notes.csv"  # gs_number,note: why a member has no statement
    notes = {r["gs_number"]: r["note"] for r in read_csv(notes_path)} if notes_path.exists() else {}
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = DATA / "statements.csv"
    rows = [r for r in read_csv(out) if r["diocese"] not in want] if (want and out.exists()) else []
    coverage = []
    for diocese, ms in sorted(members.items()):
        if want and diocese not in want: continue
        pages = choose_pages(sources, diocese)
        log(f"== {diocese}: {len(ms)} members, {len(pages)} pages")
        found = {}
        harvest_urls(diocese, ms, found)  # hand-found statement URLs take precedence over page links
        found2, named = harvest_diocese(diocese, ms, pages, domains.get(diocese, "")) if pages else ({}, {})
        for k, v in found2.items(): found.setdefault(k, v)
        harvest_compiled(diocese, ms, found)
        n_dl = n_html = 0
        for m in ms:
            r = dict(m, diocese=diocese, fetched_at=now, note="")
            if m["gs_number"] in found:
                r.update(found[m["gs_number"]])
                if r["status"] in ("downloaded", "compiled", "answers"): n_dl += 1
                else: n_html += 1
                if r["status"] not in ("downloaded", "compiled", "answers", "html-page") and m["gs_number"] in notes:
                    r["note"] = notes[m["gs_number"]]
            elif m["gs_number"] in named:
                r.update(status="named-no-link", source_page=named[m["gs_number"]])
            else:
                r.update(status="no-page-found" if not pages else "not-found", source_page=pages[0] if pages else "",
                         note=notes.get(m["gs_number"], ""))
            rows.append(r)
        coverage.append((diocese, len(ms), n_dl, n_html, pages))
        log(f"   downloaded {n_dl}, html {n_html}, of {len(ms)}")
    rows.sort(key=lambda r: int(r["gs_number"]))
    write_csv(out, rows, FIELDS)
    write_coverage(rows)
    log(f"wrote {out} ({len(rows)} rows)")


def write_coverage(rows):
    from collections import defaultdict
    by = defaultdict(list)
    for r in rows: by[r["diocese"]].append(r)
    lines = ["# Coverage of General Synod election statements by diocese", "",
             f"Generated {datetime.date.today().isoformat()} by agent/harvest.py from data/statements.csv.", "",
             "Answers = candidates' answers to electors' questions found where no election address is online.", "",
             "| Diocese | Members | Statements | Answers | URL only | Named only | Missing | Source page |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    tot = [0, 0, 0, 0, 0, 0]
    for d, rs in sorted(by.items()):
        got = sum(r["status"] in ("downloaded", "html-page", "compiled") for r in rs)
        ans = sum(r["status"] == "answers" for r in rs)
        uo = sum(r["status"] == "url-only" for r in rs)
        nm = sum(r["status"] == "named-no-link" for r in rs)
        miss = len(rs) - got - ans - uo - nm
        pages = sorted({r["source_page"] for r in rs if r["source_page"]}, key=lambda u: -sum(1 for r in rs if r["source_page"] == u))
        for i, v in enumerate((len(rs), got, ans, uo, nm, miss)): tot[i] += v
        lines.append(f"| {d} | {len(rs)} | {got} | {ans} | {uo} | {nm} | {miss} | {pages[0] if pages else ''} |")
    lines.append(f"| **Total** | {tot[0]} | {tot[1]} | {tot[2]} | {tot[3]} | {tot[4]} | {tot[5]} | |")
    (DATA / "coverage.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
