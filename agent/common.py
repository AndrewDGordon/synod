"""Shared helpers for the Synod election-statement agent."""
import csv, re, time, unicodedata, sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
           "Accept-Language": "en-GB,en;q=0.9"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Constituencies in members.csv that are not dioceses.
NON_DIOCESAN = {"Suffragan Bishop", "Armed Forces", "Deans", "Religious Communities",
                "Universities and TEIs", "Ex Officio", "Archbishops' Council",
                "Deaf Anglicans", "Ecumenical Representatives", "Young Adult"}
# Member-list constituency -> diocese name used in dioceses.csv
CONSTITUENCY_TO_DIOCESE = {"Salisbury - Channel Islands": "Salisbury", "St Eds & Ipswich": "St Eds and Ipswich"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fold(s):
    """Lower-case ASCII with diacritics stripped and punctuation turned to spaces."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def load_members():
    return read_csv(DATA / "members.csv")


SPECIAL = {"Suffragan Bishop", "Deans", "Universities and TEIs", "Armed Forces", "Religious Communities"}


def diocesan_members():
    """Elected members grouped by electing body: clergy and laity by diocese, plus the elected
    special constituencies (suffragan bishops, deans, universities and TEIs, Armed Forces,
    religious communities) each as a group of its own. Ex officio, appointed and co-opted
    members are left out."""
    by = {}
    for m in load_members():
        if not m["last_name"].strip():
            continue
        if m["constituency"] in SPECIAL:
            by.setdefault(m["constituency"], []).append(m)
            continue
        if m["house"] not in ("Clergy", "Laity") or m["constituency"] in NON_DIOCESAN:
            continue
        d = CONSTITUENCY_TO_DIOCESE.get(m["constituency"], m["constituency"])
        by.setdefault(d, []).append(m)
    return by


def load_dioceses():
    return read_csv(DATA / "dioceses.csv")


def fetch(url, timeout=25, binary=False, sleep=0.4):
    """GET with a polite pause. Returns (status, content_type, body) or (None, None, None)."""
    time.sleep(sleep)
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        except requests.RequestException as e:
            log(f"    ! {url}: {e.__class__.__name__}")
            return None, None, None
        if r.status_code != 429: break
        time.sleep(5 * (attempt + 1))  # rate limited: back off and retry
    ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
    return r.status_code, ct, (r.content if binary else r.text)
