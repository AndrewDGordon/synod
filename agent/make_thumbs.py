#!/usr/bin/env python3
"""Render small page thumbnails of every statement for the site.
Usage: python3 agent/make_thumbs.py [--force]
Writes docs/thumbs/<gs>-<page>.webp at 160 px wide (the strip in the table) and
docs/thumbs/m/<gs>-<page>.webp at 240 px (the hover card), plus docs/thumbs/index.csv listing
gs_number, page, width, height, source sha256. Pages are rendered at 40 dpi, so the text is not
legible: the thumbnails show the shape of a statement and link to the publisher's copy. For a
member inside a compiled file only their own pages are rendered. Word files are converted with
LibreOffice when it is installed and skipped otherwise. Needs the local statements/ folder
(download_statements.py rebuilds it), pdftoppm (poppler) and Pillow."""
import csv, hashlib, io, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "thumbs"
SMALL, MEDIUM = 160, 240
MAX_PAGES = 4


def render(pdf, first, last):
    """PIL images of pages first..last (1-based) of a PDF."""
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", "40", "-f", str(first), "-l", str(last), "-png", str(pdf), f"{td}/p"],
                       capture_output=True, timeout=120)
        files = sorted(Path(td).glob("p*.png"), key=lambda p: int(re.search(r"(\d+)\.png$", p.name).group(1)))
        return [Image.open(f).convert("RGB") for f in files]


def to_pdf(path):
    """A PDF copy of a Word file via LibreOffice, or None."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice: return None
    td = Path(tempfile.mkdtemp())
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(td), str(path)], capture_output=True, timeout=180)
    out = list(td.glob("*.pdf"))
    return out[0] if out else None


def save(im, width, path):
    t = im.copy(); t.thumbnail((width, width * 3))
    b = io.BytesIO(); t.save(b, "WEBP", quality=60, method=6)
    path.write_bytes(b.getvalue()); return t.size


def main():
    force = "--force" in sys.argv
    (OUT / "m").mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.csv"
    done = {(r["gs_number"], r["page"]): r for r in csv.DictReader(open(index_path))} if index_path.exists() and not force else {}
    rows = []
    rendered = skipped = missing = 0
    for r in csv.DictReader(open(DATA / "statements.csv", newline="", encoding="utf-8")):
        if r["status"] not in ("downloaded", "compiled") or not r["file"]: continue
        src = ROOT / r["file"]
        if not src.exists(): missing += 1; continue
        sha = r["sha256"] or hashlib.sha256(src.read_bytes()).hexdigest()
        prev = done.get((r["gs_number"], "1"))
        if prev and prev["sha256"] == sha:
            rows += [v for k, v in done.items() if k[0] == r["gs_number"]]; skipped += 1; continue
        first, last = 1, MAX_PAGES
        if r["status"] == "compiled":
            m = re.search(r"pages (\d+)-(\d+)", r["note"])
            if not m: continue
            first, last = int(m.group(1)), min(int(m.group(2)), int(m.group(1)) + MAX_PAGES - 1)
        pdf = src
        if src.suffix.lower() != ".pdf":
            pdf = to_pdf(src)
            if not pdf: print(f"skip {src.name}: no LibreOffice to convert it"); continue
        try: pages = render(pdf, first, last)
        except Exception as e: print(f"fail {src.name}: {e}"); continue
        for i, im in enumerate(pages, 1):
            w, hgt = save(im, SMALL, OUT / f"{r['gs_number']}-{i}.webp")
            save(im, MEDIUM, OUT / "m" / f"{r['gs_number']}-{i}.webp")
            rows.append(dict(gs_number=r["gs_number"], page=str(i), width=str(w), height=str(hgt), sha256=sha))
        rendered += 1
    rows.sort(key=lambda x: (int(x["gs_number"]), int(x["page"])))
    with open(index_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["gs_number", "page", "width", "height", "sha256"]); w.writeheader(); w.writerows(rows)
    total = sum(p.stat().st_size for p in OUT.rglob("*.webp"))
    print(f"rendered {rendered} statements, unchanged {skipped}, source files missing {missing}; {len(rows)} pages, {total/1e6:.1f} MB in docs/thumbs")


if __name__ == "__main__":
    main()
