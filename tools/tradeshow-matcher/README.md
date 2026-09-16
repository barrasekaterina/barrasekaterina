# Tradeshow vs CRM Matcher

A single web tool that replaces the four separate `tradeshow_*` notebook
pipelines (`..._full_name_email`, `..._full_name_company_name_phone`,
`..._full_name_company_name_email`, `..._full_name_company_name_phone_email`)
that used to live as near-duplicate Jupyter notebooks, each hard-coded for
one combination of columns.

Upload one tradeshow attendee list and the tool inspects its columns to see
which of **Company Name**, **Phone**, **Email** are present alongside the
required **Full Name**, then runs the matching logic for exactly that
combination automatically. There is no business-card (BC) input or matching
path anywhere in this tool — that source (`tradeshow_bc_matching.ipynb`,
plus the BC merge cells inside the other notebooks) has been dropped
entirely.

## What it does

1. Cleans and standardizes the tradeshow list and the CRM Contacts / CRM
   Leads exports (name splitting, phone/email normalization).
2. Fuzzy-matches the tradeshow list against CRM Contacts and CRM Leads with
   `recordlinkage` (Jaro-Winkler on name/company, exact-or-fuzzy on email,
   last-10-digit set intersection on phone), weighting each detected field
   equally.
3. Flags each attendee as an existing **Contact**, existing **Lead**,
   **Duplicate**, **New Contact**, or **personal_email**, and buckets job
   titles (Owner/CEO, Loan Officer, Account Executive, ...).
4. Produces a color-coded Excel export with clickable links back to the CRM
   record, plus an in-browser preview.

## Running it

```bash
cd tools/tradeshow-matcher
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5050`.

## CRM data source

For each of Contacts and Leads you can either:

- **Upload a CSV export** — semicolon (`;`) separated, same shape as
  `crm_contacts.csv` / `crm_leads.csv` in the original pipeline, or
- **Pull live from the CRM database** — runs the same SQL against the
  Bitrix CRM database on `bi-02.prod.admortgage.com` that used to be a
  manual export step, so you always match against current data.
  - Contacts uses SQL auth: fill in the DB username/password in the form
    (sent for that request only, never stored, logged, or written to disk).
  - Leads uses Windows Integrated Auth (`Trusted_Connection`), so it only
    works when the tool runs on a domain-joined Windows machine, or a Linux
    host configured for Kerberos against that domain.
  - This path needs `pyodbc` plus the system-level "ODBC Driver 17 for SQL
    Server" installed, and network access to that server — see
    `matcher/db.py` for the exact queries. It has not been exercised
    against a live database in this repo's own dev/test environment, only
    against a mocked DataFrame shaped like the query output
    (`sample_data/smoke_test_db.py`) — verify it against a real connection
    before relying on it.

The tradeshow file can be `.csv` or `.xlsx` and just needs a name column —
common header spellings (Name, Full Name, Company/Organization,
Phone/Phone Number, Email/E-mail) are recognized automatically.

## Also used as a backend by the browser extension

`tools/tradeshow-matcher-extension/` is a Chrome/Edge extension version of
this same tool. It runs entirely client-side, but a browser can't open a
direct SQL Server connection, so its "Pull live via local backend" option
calls this Flask app's `/api/contacts` and `/api/leads` JSON endpoints
instead, which do the real `pyodbc` call and return standardized rows. Keep
`python app.py` running here if you want to use that option from the
extension. CORS on those two routes is restricted to `chrome-extension://`
origins only (see `app.py`) — never widen that to `*`.

## Sample data

`sample_data/make_samples.py` generates small synthetic fixtures covering
all four field combinations; `sample_data/smoke_test.py` runs the pipeline
against them without the web server, for quick regression checks after
changing matching logic.
