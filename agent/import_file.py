"""Import a statement file fetched by hand (browser, WebFetch) for one member.
Usage: python3 agent/import_file.py <gs_number> <path> [<statement_url>]
Copies the file to statements/<Diocese>/, verifies it names the member, and updates the member's
row in data/statements.csv (status 'downloaded', note 'imported by hand')."""
import sys, shutil, hashlib, datetime
from common import *
import harvest

gs, src = sys.argv[1], Path(sys.argv[2])
url = sys.argv[3] if len(sys.argv) > 3 else ""
rows = read_csv(DATA / "statements.csv")
row = next(r for r in rows if r["gs_number"] == gs)
m = row
ext = src.suffix.lower() or ".pdf"
if src.read_bytes()[:4] == b"%PDF": ext = ".pdf"
d = harvest.STATEMENTS / row["diocese"].replace(" ", "_").replace("&", "and"); d.mkdir(parents=True, exist_ok=True)
dst = d / harvest.safe_name(m, ext)
shutil.copyfile(src, dst)
body = dst.read_bytes()
note = harvest.verify(dst, m, ext)
row.update(status="downloaded", statement_url=url or row["statement_url"], file=str(dst.relative_to(ROOT)),
           content_type="application/pdf" if ext == ".pdf" else "", bytes=str(len(body)), sha256=hashlib.sha256(body).hexdigest(),
           fetched_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           note=("imported by hand; " + note).rstrip("; "))
write_csv(DATA / "statements.csv", rows, harvest.FIELDS)
harvest.write_coverage(rows)
log(f"{gs} {m['last_name']}: {dst} {note or 'verified'}")
