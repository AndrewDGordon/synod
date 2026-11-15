#!/usr/bin/env python3
"""Write members.md: every member of the General Synod 2026-2031 in the order of the Church of
England's own list, with a link to each elected member's election statement where one exists.
Usage: python3 agent/make_members_page.py"""
import csv, datetime, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOURCE_PDF = "https://www.churchofengland.org/sites/default/files/2026-10/List-of-members-for-website-v2.pdf"
HOUSE_NAMES = {"Bishops": "House of Bishops", "Clergy": "House of Clergy", "Laity": "House of Laity", "Non-voting": "Non-voting members"}


def read(name):
    p = DATA / name
    return list(csv.DictReader(open(p, newline="", encoding="utf-8"))) if p.exists() else []


def esc(s):
    return s.replace("|", "\\|").strip()


def statement_cell(r):
    if not r: return ""
    url, src = r["statement_url"], r["source_page"]
    note = r["note"]
    if r["status"] == "downloaded":
        cell = f"[statement]({url})"
    elif r["status"] == "compiled":
        m = re.search(r"pages (\d+)-(\d+)", note)
        pages = f"pages {m.group(1)}-{m.group(2)} of " if m else ""
        cell = f"[{pages}compiled PDF]({url})"
    elif r["status"] == "answers":
        cell = f"[answers to electors' questions]({url})"
    elif r["status"] in ("url-only", "html-page"):
        cell = f"[statement]({url})"
    else:
        cell = ""
    if src and src != url:
        cell += f" · [source page]({src})" if cell else f"[source page]({src})"
    return cell


def note_cell(r):
    if not r: return ""
    note = r["note"]
    if r["status"] in ("downloaded", "compiled", "answers"):
        # keep only remarks a reader needs; drop verification chatter and page ranges
        if note.startswith("listed on contents page"): return "statement on an image-only page of the compiled file"
        return ""
    return esc(note) if note else "no statement found"


def main():
    members = read("members.csv")
    statements = {r["gs_number"]: r for r in read("statements.csv")}
    wiki = {r["gs_number"]: r for r in read("wikipedia.csv") if r["status"] in ("confirmed", "likely")}
    held = sum(1 for r in statements.values() if r["status"] in ("downloaded", "compiled", "answers"))
    today = datetime.date.today().isoformat()
    out = [
        "# Members of the General Synod 2026-2031: election statements and Wikipedia articles", "",
        f"The names, GS numbers, constituencies and houses follow the Church of England's [list of members]({SOURCE_PDF}) "
        f"(October 2026), in its order. The statement links point to the candidates' election addresses where a diocese or "
        f"the Church of England has published one. The documents themselves are not reproduced here; the links lead to the "
        f"publishers' own copies. Run `python3 download_statements.py` to fetch them all.", "",
        f"Of the {len(statements)} elected members, {held} have a statement linked below. The members without one "
        f"(uncontested seats, or seats held ex officio) carry a note saying why. Members who sit by office, appointment or "
        f"co-option were not elected and have no statements.", "",
        f"A member's name is a link to their English Wikipedia article where one exists ({len(wiki)} members), "
        f"found by `agent/find_wikipedia.py` and checked against the member's role.", "",
        f"Generated {today} by `agent/make_members_page.py` from `data/members.csv`, `data/statements.csv` and `data/wikipedia.csv`.", "",
    ]
    section = None
    for m in members:
        house = m["house"] if int(m["gs_number"]) >= 54 or m["house"] != "Non-voting" else "Bishops"
        if house != section:
            section = house
            out += ["", f"## {HOUSE_NAMES.get(house, house)}", "",
                    "| GS | Name | Constituency | House | Statement | Note |", "|---:|---|---|---|---|---|"]
        r = statements.get(m["gs_number"])
        name = esc(" ".join(x for x in (m["title"], m["first_name"], m["last_name"]) if x))
        w = wiki.get(m["gs_number"])
        if w: name = f"[{name}]({w['url']})"
        out.append(f"| {m['gs_number']} | {name} | {esc(m['constituency'])} | {m['house']} | {statement_cell(r)} | {note_cell(r)} |")
    (ROOT / "members.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote members.md: {len(members)} members, {held} statements linked")


if __name__ == "__main__":
    main()
