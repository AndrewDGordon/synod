#!/usr/bin/env python3
"""Write docs/index.html, the GitHub Pages site: the members table with photos from Wikipedia,
links to election statements and Wikipedia articles, search and filters. Self-contained HTML.
Usage: python3 agent/make_site.py"""
import csv, datetime, html, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCE_PDF = "https://www.churchofengland.org/sites/default/files/2026-10/List-of-members-for-website-v2.pdf"
REPO = "https://github.com/AndrewDGordon/synod"
HOUSE_NAMES = {"Bishops": "House of Bishops", "Clergy": "House of Clergy", "Laity": "House of Laity", "Non-voting": "Non-voting"}


def read(name):
    p = DATA / name
    return list(csv.DictReader(open(p, newline="", encoding="utf-8"))) if p.exists() else []


def h(s): return html.escape(s or "", quote=True)


def statement_links(r):
    if not r or not r["statement_url"]: return "", ""
    url, src, note = r["statement_url"], r["source_page"], r["note"]
    if r["status"] == "downloaded": label = "Statement"
    elif r["status"] == "compiled":
        m = re.search(r"pages (\d+)-(\d+)", note); label = f"Compiled PDF, pp. {m.group(1)}–{m.group(2)}" if m else "Compiled PDF"
    elif r["status"] == "answers": label = "Answers to electors' questions"
    else: label = "Statement"
    out = f'<a class="doc" href="{h(url)}">{label}</a>'
    if src and src != url: out += f' <a class="src" href="{h(src)}" title="Page where the statement was found">page</a>'
    return out, label


def note_text(r):
    if not r: return ""
    if r["status"] in ("downloaded", "compiled", "answers"):
        return "On an image-only page of the compiled file" if r["note"].startswith("listed on contents page") else ""
    return r["note"] or "No statement found"


def wplink(w, text, cls):
    """A link to a Wikipedia article carrying the data the hover card needs; plain text if there is none."""
    if not w or not w.get("url"): return h(text)
    thumb = f' data-thumb="{h(w["thumb_url"])}"' if w.get("thumb_url") else ""
    return f'<a class="{cls}" href="{h(w["url"])}" data-title="{h(w["title"])}" data-abstract="{h(w.get("abstract", ""))}"{thumb}>{h(text)}</a>'


def initials(m):
    return "".join(x[0] for x in (m["first_name"], m["last_name"]) if x).upper()[:2]


def main():
    members = read("members.csv")
    statements = {r["gs_number"]: r for r in read("statements.csv")}
    wiki = {r["gs_number"]: r for r in read("wikipedia.csv") if r["status"] in ("confirmed", "likely")}
    extras = {r["gs_number"]: r for r in read("wikipedia-images.csv")}
    images = {k: v for k, v in extras.items() if v["thumb_url"]}
    const_wp = {r["constituency"]: r for r in read("constituency-wikipedia.csv")}  # dioceses, other constituencies, house:<House>
    thumbs = {}
    for r in read("../docs/thumbs/index.csv") if (ROOT / "docs" / "thumbs" / "index.csv").exists() else []:
        thumbs.setdefault(r["gs_number"], []).append(r)
    held = sum(1 for r in statements.values() if r["status"] in ("downloaded", "compiled", "answers"))
    constituencies = sorted({m["constituency"] for m in members})
    today = datetime.date.today().strftime("%-d %B %Y")

    rows = []
    for m in members:
        gs = m["gs_number"]; r = statements.get(gs); w = wiki.get(gs); im = images.get(gs)
        name = h(" ".join(x for x in (m["title"], m["first_name"], m["last_name"]) if x))
        ab = extras.get(gs, {}).get("abstract", "") if w else ""
        name_html = (f'<a class="wp" href="{h(w["url"])}" data-title="{h(w["title"])}" data-abstract="{h(ab)}"'
                     f'{" data-thumb=" + chr(34) + h(im["thumb_url"]) + chr(34) if im else ""}>{name}</a>') if w else name
        const_html = wplink(const_wp.get(m["constituency"]), m["constituency"], "cwp")
        house_html = wplink(const_wp.get("house:" + m["house"]), m["house"], "cwp")
        if im:
            credit = ", ".join(x for x in (im["artist"], im["licence"]) if x)
            photo = (f'<a href="{h(im["file_page"] or im["thumb_url"])}" title="{h(credit)}"><img loading="lazy" src="{h(im["thumb_url"])}" '
                     f'alt="Photograph of {name}" width="44" height="44"></a>')
        else:
            photo = f'<span class="ph" aria-hidden="true">{h(initials(m))}</span>'
        st, label = statement_links(r)
        if r and thumbs.get(gs):
            pages = thumbs[gs]
            imgs = "".join(f'<img loading="lazy" src="thumbs/{gs}-{t["page"]}.webp" width="{int(int(t["width"]) * 50 / int(t["height"]))}" height="50" '
                           f'alt="Page {t["page"]} of the statement of {name}">' for t in pages)
            st = (f'<a class="thumbs" href="{h(r["statement_url"])}" data-pages="{",".join(f"{gs}-{t[chr(112)+chr(97)+chr(103)+chr(101)]}" for t in pages)}" '
                  f'data-title="{name}" aria-label="{label}, {len(pages)} page{"s" if len(pages) > 1 else ""}">{imgs}</a> ' + st)
        note = note_text(r)
        elected = "yes" if r else "no"
        has = "yes" if r and r["status"] in ("downloaded", "compiled", "answers") else "no"
        search = " ".join([name, m["constituency"], m["house"], gs]).lower()
        rows.append(f'<tr data-house="{h(m["house"])}" data-const="{h(m["constituency"])}" data-elected="{elected}" data-statement="{has}" data-search="{h(search)}">'
                    f'<td class="photo">{photo}</td><td class="gs">{gs}</td><td class="name">{name_html}</td>'
                    f'<td>{const_html}</td><td>{house_html}</td><td class="st">{st}</td><td class="note">{h(note)}</td></tr>')

    credits = []
    for gs, im in sorted(images.items(), key=lambda x: int(x[0])):
        who = wiki[gs]["title"]
        lic = f'<a href="{h(im["licence_url"])}">{h(im["licence"])}</a>' if im["licence_url"] else h(im["licence"])
        credits.append(f'<li><a href="{h(im["file_page"] or im["thumb_url"])}">{h(who)}</a>: {h(im["artist"]) or "unknown author"}, {lic}</li>')

    options = "".join(f'<option value="{h(c)}">{h(c)}</option>' for c in constituencies)
    page = f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>General Synod 2026–2031: members and election statements</title>
<meta name="description" content="Every member of the Church of England's General Synod 2026-2031, with their election statements and Wikipedia articles.">
<style>
:root {{ --bg:#faf8f4; --fg:#1f1d1a; --muted:#6b655c; --line:#e2dcd2; --accent:#5b2a86; --accent2:#8a1538; --row:#ffffff; --row2:#f4f0e8; --chip:#ece6da; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#17161a; --fg:#ece8e1; --muted:#a39c92; --line:#34313a; --accent:#c9a6ec; --accent2:#f0a3b6; --row:#1f1e23; --row2:#25232a; --chip:#2e2b34; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:16px/1.5 Georgia, "Times New Roman", serif; background:var(--bg); color:var(--fg); }}
header, main, footer {{ max-width:1180px; margin:0 auto; padding:0 16px; }}
header {{ padding-top:32px; }}
h1 {{ font-size:2rem; margin:0 0 .3rem; font-weight:normal; letter-spacing:.01em; }}
h1 small {{ display:block; font-size:1rem; color:var(--muted); }}
p.lede {{ max-width:70ch; color:var(--fg); }}
.stats {{ display:flex; gap:24px; flex-wrap:wrap; margin:12px 0 20px; font-family:system-ui, sans-serif; }}
.stats div {{ background:var(--chip); border-radius:10px; padding:10px 16px; min-width:120px; }}
.stats b {{ display:block; font-size:1.6rem; line-height:1.1; color:var(--accent); }}
.stats span {{ font-size:.85rem; color:var(--muted); }}
.controls {{ display:flex; gap:12px; flex-wrap:wrap; align-items:center; margin:0 0 14px; font-family:system-ui, sans-serif; font-size:.95rem; }}
.controls input[type=search], .controls select {{ font:inherit; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:var(--row); color:var(--fg); }}
.controls input[type=search] {{ flex:1 1 220px; min-width:180px; }}
.controls label {{ display:flex; align-items:center; gap:6px; }}
.count {{ color:var(--muted); margin-left:auto; }}
.tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:12px; background:var(--row); }}
table {{ border-collapse:collapse; width:100%; font-size:.95rem; }}
th, td {{ padding:8px 10px; text-align:left; vertical-align:middle; border-top:1px solid var(--line); }}
thead th {{ border-top:0; background:var(--row2); font-family:system-ui, sans-serif; font-size:.8rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); position:sticky; top:0; cursor:pointer; user-select:none; }}
thead th.sorted {{ color:var(--accent); }}
tbody tr:nth-child(even) {{ background:var(--row2); }}
td.gs {{ font-family:system-ui, sans-serif; color:var(--muted); text-align:right; }}
td.photo {{ width:56px; }}
td.photo img, .ph {{ width:44px; height:44px; border-radius:50%; object-fit:cover; display:block; }}
.ph {{ background:var(--chip); color:var(--muted); font:600 .85rem system-ui, sans-serif; display:flex; align-items:center; justify-content:center; }}
td.name {{ font-weight:600; min-width:200px; }}
a {{ color:var(--accent); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
a.wp::after {{ content:" W"; font:600 .7rem system-ui, sans-serif; color:var(--muted); vertical-align:super; }}
a.doc {{ display:inline-block; background:var(--chip); color:var(--accent2); border-radius:6px; padding:1px 8px; font-family:system-ui, sans-serif; font-size:.85rem; white-space:nowrap; }}
a.src {{ font-family:system-ui, sans-serif; font-size:.8rem; color:var(--muted); margin-left:4px; }}
td.note {{ color:var(--muted); font-size:.85rem; max-width:34ch; }}
td.st {{ white-space:nowrap; }}
a.thumbs {{ display:inline-flex; gap:3px; vertical-align:middle; margin-right:8px; }}
a.thumbs img {{ height:50px; width:auto; border:1px solid var(--line); border-radius:2px; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.12); }}
#card.pages {{ width:auto; max-width:min(560px, calc(100vw - 32px)); }}
#card .strip {{ display:flex; gap:8px; margin:6px 0 8px; }}
#card .strip img {{ float:none; width:auto; height:auto; max-width:240px; max-height:340px; margin:0; border:1px solid var(--line); border-radius:3px; background:#fff; }}
tbody tr.hide {{ display:none; }}
footer {{ margin:40px auto 60px; color:var(--muted); font-size:.9rem; }}
footer details {{ margin-top:12px; }}
footer summary {{ cursor:pointer; color:var(--accent); }}
footer ul {{ columns:2; column-gap:32px; padding-left:18px; }}
a.cwp {{ color:inherit; border-bottom:1px dotted var(--muted); }}
#card {{ position:absolute; z-index:10; width:340px; max-width:calc(100vw - 32px); background:var(--row); color:var(--fg); border:1px solid var(--line); border-radius:12px; box-shadow:0 8px 28px rgba(0,0,0,.18); padding:14px 16px; font-size:.92rem; line-height:1.45; display:none; }}
#card.show {{ display:block; }}
#card img {{ float:right; width:84px; height:84px; object-fit:cover; border-radius:8px; margin:0 0 8px 12px; }}
#card b {{ display:block; font-size:1.05rem; margin-bottom:4px; }}
#card p {{ margin:0 0 8px; }}
#card a {{ font-family:system-ui, sans-serif; font-size:.85rem; }}
@media (max-width:760px) {{ td.note, th.note {{ display:none; }} footer ul {{ columns:1; }} body {{ font-size:15px; }} }}
</style>
</head>
<body>
<header>
<h1>General Synod 2026–2031<small>Members of the Church of England's General Synod, their election statements, and their Wikipedia articles</small></h1>
<p class="lede">Names, GS numbers, constituencies and houses follow the Church of England's <a href="{SOURCE_PDF}">list of members</a> (October 2026). Where a diocese or the Church of England has published a candidate's election address, the statement link leads to the publisher's own copy. A linked name opens the member's Wikipedia article, and resting on it shows the article's opening lines. Constituency and House names link to their articles in the same way. Photographs come from Wikipedia and are credited below. The small page images beside each statement show its shape, not its text; rest on them for a closer look, and click to open the publisher's PDF.</p>
<div class="stats">
<div><b>{len(members)}</b><span>members</span></div>
<div><b>{len(statements)}</b><span>elected members</span></div>
<div><b>{held}</b><span>statements linked</span></div>
<div><b>{len(wiki)}</b><span>Wikipedia articles</span></div>
<div><b>{len(images)}</b><span>photographs</span></div>
<div><b>{sum(len(v) for v in thumbs.values())}</b><span>statement pages</span></div>
</div>
</header>
<main>
<div class="controls">
<input type="search" id="q" placeholder="Search name, diocese or GS number" aria-label="Search">
<select id="house" aria-label="House"><option value="">All houses</option><option>Bishops</option><option>Clergy</option><option>Laity</option><option>Non-voting</option></select>
<select id="const" aria-label="Constituency"><option value="">All constituencies</option>{options}</select>
<label><input type="checkbox" id="withst"> with a statement</label>
<label><input type="checkbox" id="withwp"> on Wikipedia</label>
<span class="count" id="count"></span>
</div>
<div class="tablewrap">
<table id="t">
<thead><tr><th></th><th data-k="gs" class="sorted">GS</th><th data-k="name">Name</th><th data-k="const">Constituency</th><th data-k="house">House</th><th>Statement</th><th class="note">Note</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</div>
</main>
<footer>
<p>Data and code: <a href="{REPO}">github.com/AndrewDGordon/synod</a>. Generated {today}. The statements belong to their authors and publishers and are linked, not copied. Members who sit by office, appointment or co-option were not elected and have no statements; the note column says why an elected member has none.</p>
<details><summary>Photograph credits ({len(credits)})</summary><ul>
{chr(10).join(credits)}
</ul></details>
</footer>
<div id="card" role="tooltip"></div>
<script>
(function(){{
  const card=document.getElementById('card'); let hideTimer=null, current=null;
  function show(a){{
    clearTimeout(hideTimer); current=a;
    const t=a.dataset.title, ab=a.dataset.abstract, th=a.dataset.thumb;
    if(a.dataset.pages){{
      card.classList.add('pages');
      card.innerHTML='<b>'+t+'</b><div class="strip">'+a.dataset.pages.split(',').map(p=>'<img src="thumbs/m/'+p+'.webp" alt="">').join('')+'</div><a href="'+a.href+'">Open the statement (PDF) →</a>';
    }} else {{
      card.classList.remove('pages');
      card.innerHTML=(th?'<img src="'+th+'" alt="">':'')+'<b>'+t+'</b><p>'+(ab||'No summary available.')+'</p><a href="'+a.href+'">Read on Wikipedia →</a>';
    }}
    card.classList.add('show');
    const r=a.getBoundingClientRect(), cw=card.offsetWidth, ch=card.offsetHeight;
    let x=r.left+window.scrollX, y=r.bottom+window.scrollY+8;
    if(x+cw>window.scrollX+document.documentElement.clientWidth-16) x=window.scrollX+document.documentElement.clientWidth-16-cw;
    if(r.bottom+8+ch>window.innerHeight && r.top-8-ch>0) y=r.top+window.scrollY-8-ch;
    card.style.left=x+'px'; card.style.top=y+'px';
  }}
  function hide(){{ hideTimer=setTimeout(()=>{{card.classList.remove('show'); current=null;}},180); }}
  document.querySelectorAll('a[data-abstract], a[data-pages]').forEach(a=>{{
    a.addEventListener('mouseenter',()=>show(a)); a.addEventListener('mouseleave',hide);
    a.addEventListener('focus',()=>show(a)); a.addEventListener('blur',hide);
  }});
  card.addEventListener('mouseenter',()=>clearTimeout(hideTimer)); card.addEventListener('mouseleave',hide);
  document.addEventListener('keydown',e=>{{ if(e.key==='Escape'){{card.classList.remove('show');}} }});
  const q=document.getElementById('q'), house=document.getElementById('house'), cst=document.getElementById('const'),
        withst=document.getElementById('withst'), withwp=document.getElementById('withwp'), count=document.getElementById('count'),
        tbody=document.querySelector('#t tbody'), rows=[...tbody.rows];
  function apply(){{
    const s=q.value.trim().toLowerCase(), hv=house.value, cv=cst.value; let n=0;
    for(const r of rows){{
      const ok=(!s||r.dataset.search.includes(s))&&(!hv||r.dataset.house===hv)&&(!cv||r.dataset.const===cv)
        &&(!withst.checked||r.dataset.statement==='yes')&&(!withwp.checked||r.querySelector('a.wp'));
      r.classList.toggle('hide',!ok); if(ok)n++;
    }}
    count.textContent=n+' of '+rows.length;
  }}
  [q,house,cst,withst,withwp].forEach(e=>e.addEventListener('input',apply));
  let dir=1, key='gs';
  document.querySelectorAll('thead th[data-k]').forEach(th=>th.addEventListener('click',()=>{{
    const k=th.dataset.k; dir = (k===key)?-dir:1; key=k;
    document.querySelectorAll('thead th').forEach(x=>x.classList.remove('sorted')); th.classList.add('sorted');
    const val=r=>k==='gs'?+r.cells[1].textContent:k==='name'?r.cells[2].textContent.replace(/^(The |Rt |Most |Very |Revd |Ven |Canon |Dr |Prof |Mr |Mrs |Ms |Miss |Sir |Dame |Fr |Br |Sr |Cdr |Maj |Prof Emerita |Archpriest |Rt Worshipful |Fg Off |AVM )+/,'').toLowerCase():r.dataset[k==='const'?'const':'house'].toLowerCase();
    rows.sort((a,b)=>{{const x=val(a),y=val(b); return (x<y?-1:x>y?1:0)*dir;}}); rows.forEach(r=>tbody.appendChild(r));
  }}));
  apply();
}})();
</script>
</body>
</html>
"""
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote docs/index.html: {len(members)} members, {held} statements, {len(wiki)} articles, {len(images)} photos, {sum(len(v) for v in thumbs.values())} thumbnail pages")


if __name__ == "__main__":
    main()
