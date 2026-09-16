# Tradeshow vs CRM Matcher (browser extension)

The same tool as `tools/tradeshow-matcher/` (the Flask/Python version), but
packaged as a Chrome/Edge extension so you don't need to run a local Python
server. Everything runs client-side in the browser tab — files never leave
your machine.

Like the Python version, this auto-detects whether your tradeshow file has
Full Name + Email, + Company Name, + Phone, or all of them, and matches
accordingly. There is no business-card (BC) input or matching path.

## Install (unpacked, for personal/local use)

1. Open `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select this `tradeshow-matcher-extension`
   folder.
4. Click the extension's icon in the toolbar, then **Open matcher**.

## Live CRM database pull

A browser extension still can't open a direct SQL Server (ODBC) connection
itself — that's a hard platform limitation, not a missing feature. Instead,
"Pull live via local backend" on each of the CRM Contacts/Leads fields sends
the request to the Flask app in `tools/tradeshow-matcher/` running on your
machine (`python app.py`, default `http://127.0.0.1:5050`), which does the
real `pyodbc` connection and hands back standardized rows over
`/api/contacts` / `/api/leads`. So the extension is the UI; the local Flask
process is what actually talks to the database. You need that Flask app
running whenever you use the live-DB option — CSV upload doesn't need it.

The DB password (Contacts only; Leads uses Windows Integrated Auth) is only
ever held in the page's memory for the one request, is cleared from the
form right after the run, and is never written to `chrome.storage` or any
log. It does travel over plain HTTP to `127.0.0.1`, which is fine for
localhost but don't repoint the backend URL at a non-local, non-HTTPS host.

CORS on the Flask side (`app.py`) is restricted to `chrome-extension://`
origins specifically — never opened to `*` — because the Leads endpoint
needs no credentials at all; an open CORS policy would let any website you
happen to have open in another tab silently query it while the server runs.

## What's different from the Python/Flask version

- **Excel export has no color-coded Status column.** The vendored
  `lib/xlsx.full.min.js` is the free/community build of SheetJS, which can
  write hyperlinks but not cell fill colors (that's a paid-tier feature of
  that library). CSV export is unaffected since CSV has no styling either
  way. The Python version's Excel export still has the colors.
- Matching uses a from-scratch JavaScript port of the same logic
  (Jaro-Winkler name/company similarity, last-10-digit phone-set
  intersection, exact-or-fuzzy email) — see `js/matching.js`. It's been
  checked against the Python version using the same sample fixtures
  (`tools/tradeshow-matcher/sample_data/`) and produces identical match
  counts, but it's a reimplementation, not the same code.

## Files

- `manifest.json` — Manifest V3 extension definition.
- `popup.html` / `popup.js` — the toolbar popup; just opens `app.html` in a
  new tab (file uploads and result tables need more room than a popup).
- `app.html` / `app.js` / `app.css` — the actual tool.
- `js/cleaning.js`, `js/loaders.js`, `js/matching.js`, `js/enrich.js`,
  `js/pipeline.js`, `js/export.js` — ported matching engine, one module per
  concern, mirroring `tools/tradeshow-matcher/matcher/*.py`.
- `js/db.js` — client for the local Flask backend's `/api/contacts` /
  `/api/leads` endpoints, used only by the "Pull live via local backend"
  option.
- `lib/xlsx.full.min.js` — vendored SheetJS (Apache-2.0), used to parse
  uploaded `.csv`/`.xlsx` files and to build the downloadable export.

## Publishing

This has only been set up and tested as an unpacked/personal extension. If
you want to distribute it via the Chrome Web Store, you'd additionally need
a privacy policy, store listing assets (icons, screenshots), and a
developer account — none of that is included here.
