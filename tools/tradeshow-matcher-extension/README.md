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

## What's different from the Python/Flask version

- **No live CRM database pull.** A browser can't open a direct SQL Server
  (ODBC) connection, so this version only supports uploading the CRM
  Contacts/Leads CSV exports. Use the Python version's "pull live from CRM
  database" option (`tools/tradeshow-matcher/matcher/db.py`) if you need
  that.
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
- `lib/xlsx.full.min.js` — vendored SheetJS (Apache-2.0), used to parse
  uploaded `.csv`/`.xlsx` files and to build the downloadable export.

## Publishing

This has only been set up and tested as an unpacked/personal extension. If
you want to distribute it via the Chrome Web Store, you'd additionally need
a privacy policy, store listing assets (icons, screenshots), and a
developer account — none of that is included here.
