---
name: find-statements
description: Find and download the General Synod election statements of elected diocesan members. Runs the crawler in agent/, then uses web search and page fetching to fill the dioceses the crawler missed, records hand-found pages in data/sources-manual.csv, re-harvests, and reports coverage. Use when asked to find, refresh, or complete the election statements database, or to chase a particular diocese.
---

# Find election statements

Goal: one statement file per elected clergy or lay member in `data/members.csv` whose
constituency is a diocese, recorded in `data/statements.csv`, with files under `statements/`.

## Steps

1. **Crawl.** `python3 agent/find_pages.py [Diocese ...]` writes `data/sources.csv`:
   candidate pages per diocese scored by elected surnames found, keywords, and PDF count.
   A page scoring 12 or more with 2 or more surnames is used automatically.
2. **Harvest.** `python3 agent/harvest.py [Diocese ...]` downloads statements and writes
   `data/statements.csv` and `data/coverage.md`.
3. **Fill gaps.** For each diocese in `data/coverage.md` with missing members:
   - Search the web (several phrasings, in this order):
     `"<Diocese>" "General Synod" 2026 election addresses`,
     `site:<domain> general synod 2026 candidates`,
     `"<surname>" "General Synod" 2026 "<Diocese>" election address`.
   - Fetch the best hit with WebFetch (use it, not curl, for sites that return 403 to curl).
   - Judge: does the page link to statements, addresses, or profiles of the *elected*
     members? Results sheets and news stories about results do not count unless they link
     statements.
   - Append confirmed pages to `data/sources-manual.csv` as `diocese,url,note`, then rerun
     step 2 for that diocese. If the statements are HTML pages per candidate rather than
     PDFs the harvester saves the HTML.
   - If a diocese never published statements, or removed them after the election, record
     that in the `notes` column of `data/dioceses.csv` so nobody searches again.
4. **Report.** Summarise `data/coverage.md`: dioceses complete, partial, and none, and what
   stopped each incomplete one (blocked site, statements removed, never published).

After any change to `data/statements.csv`, run `python3 agent/make_members_page.py` to
regenerate `members.md`, the public page of links. The PDFs themselves stay out of git.

## Known behaviour of diocesan sites (as of 15 November 2026)

- Most have no sitemap; the crawler relies on navigation links mentioning synod,
  election, or governance. Election material is usually on a page named for the election
  (`general-synod-elections-2026`), not the standing "General Synod" page.
- These sites return 403 to scripted requests, so read their pages with WebFetch and copy
  the statement URLs into `data/statement-urls.csv`: Sheffield, St Albans, Salisbury,
  Peterborough, Manchester, Worcester, Hereford, Bath and Wells, Durham, Oxford, York.
  WebFetch of a PDF saves the file under the session's tool-results folder; file it with
  `python3 agent/import_file.py <gs_number> <path> <url>`.
- Southwark rate-limits (429); `fetch()` backs off and retries.
- Chester publishes one compiled PDF per house (Wix usrfiles host): use `data/compiled.csv`
  with `kind=addresses`. A `kind=answers` row (St Albans's "Responses to Questions submitted
  to Candidates" PDFs) gives members status `answers`, reported in its own coverage column.
- Oxford hosts its PDFs on Mailchimp (`mcusercontent.com`), which is open to scripts.
- Spelling differences between the national list and diocesan pages are handled with
  `data/aliases.csv` (Braithwaite/Brathwaite, Purpurra/Purppura, Bilson/Billson,
  Ilife/Iliffe, Holywell/Hollywell).
- Before crawling, check Peter Owen's tracker (`data/sources-peterowen.csv`, from
  http://peterowen.org.uk/articles/gselection2026.html, plain HTTP only): it links each
  diocese's address page. Derby's addresses are on a candidates page it links but the
  diocese's own General Synod page does not.
- When a page links nothing, query the WordPress media API,
  `https://<site>/wp-json/wp/v2/media?search=election%20address&per_page=100`: Southwell &
  Nottingham uploaded every address without linking them.
- The special constituencies (suffragan bishops, deans, universities and TEIs) are groups
  like dioceses. Their addresses are national PDFs, one per constituency and province, linked
  from https://www.churchofengland.org/national-bodies/general-synod/elections-synod/general-synod-election-results-2026
  and held in `data/compiled.csv`. Armed Forces and religious communities seats are returned
  without a count and have no addresses. Reasons for a missing statement go in `data/notes.csv`.
- No statements exist for Salisbury's three Channel Islands members: those seats are filled
  by the deaneries without a contest, and neither deanery site has anything.
- Sheffield's General Synod page lists members only; the addresses hang off a news post
  (general-synod-election-results). When a governance page is bare, try the site's own
  search page, `https://<site>/?s=general+synod+election`, which the page fetcher can read
  even on sites that return 403 to scripts.
- St Albans keeps each address on a WordPress "resource" page that its General Synod page
  loads through a JavaScript document library invisible to scripts. The site's search API,
  `https://www.stalbansdiocese.org/wp-json/wp/v2/search?search=election%20address&per_page=50`,
  lists every resource page, and each page links its PDF. Try the same `wp-json/wp/v2/search`
  call on any other WordPress diocesan site whose documents hide behind JavaScript.
- Many PDFs fail the surname check for harmless reasons: nicknames (Rich, Kat, Jonny,
  Tiffer, Greg, Gilli, Jenn) or fonts that defeat pdftotext (Truro, Gloucester). Check the
  first line of text before treating a flagged file as wrong.

## Self-improvement

After each run, add to the list above anything learned about a diocesan site that would
save the next run time, and adjust the regexes in `agent/find_pages.py` and
`agent/harvest.py` if a systematic miss was found.
