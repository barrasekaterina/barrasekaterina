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
4. Optionally looks up each matched attendee's MLO NMLS id in the NMLS
   database and adds their currently Authorized-to-Represent company or
   branch name (see "NMLS enrichment" below).
5. Produces a color-coded Excel export with clickable links back to the CRM
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
  - Both Contacts and Leads authenticate via Windows Integrated Auth
    (`Trusted_Connection`) — no username/password is asked for or sent
    anywhere. This only works when the tool runs on a domain-joined
    Windows machine (or a Linux host configured for Kerberos against that
    domain) as an account with access to the CRM database. (The original
    contacts script also carried a UID/PWD pair, but when
    `Trusted_Connection=yes` is present the ODBC driver ignores UID/PWD
    entirely — that pair was never actually authenticating anything.)
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

## NMLS enrichment

The "NMLS enrichment" checkbox looks up each matched attendee in a
*different* database - the NMLS database on `p-nmls-db01.admortgage.com` -
and adds `NMLS FullName` (that individual's own First/Last Name from
`dbo.Individual`, so you can visually compare it against the attendee's
own Full Name), `NMLS RegulationType` (State-Licensed / Federally
Registered / Dual / None), `NMLS LicensingStatus` (Active/Inactive), `NMLS
LocationNMLSID`, and `NMLS LocationName` (the company or branch that
person is currently authorized to represent, from `dbo.Company.Name` or
`dbo.Branch.Name`), plus `NMLS Match Method` saying how each row was
looked up:

1. **`CRM`** - if the attendee matched a CRM Contact/Lead that has an MLO
   NMLS id on file, that id is used directly. This is the priority path -
   it's an exact, unambiguous id, so it always wins when available.
2. **`Name+Company`** - only for attendees with *no* CRM match at all.
   Falls back to fuzzy-matching their Full Name against `dbo.Individual`
   (blocked on exact `LastName`, Jaro-Winkler on First/Last), then always
   also compares Company Name against each name-candidate's resolved
   company/branch name - a name match alone is never enough to accept a
   result, even when it's the only name candidate. If there's no Company
   Name to compare (blank), a single unambiguous name candidate is still
   accepted; multiple name candidates with no Company Name, or none of the
   candidates' companies matching well enough, leaves the attendee
   unmatched rather than guessing.
3. Blank `NMLS Match Method` - neither path found anything (no CRM match
   and no confident NMLS name match).

A `Company Match` column checks whether the company on file agrees with
what NMLS currently shows for that MLO - useful for spotting people who
have since moved companies. It compares `Company NMLS` (the id already
on the matched CRM Contact/Lead) against NMLS's `OwningCompanyNMLSID`
exactly when both are available; otherwise it falls back to a *fuzzy*
comparison (Jaro-Winkler, same threshold as the name+company matching
above) of the attendee's own Company Name against NMLS's resolved
company/branch name - never a plain string-equality check, since real
company names vary in spelling/suffixes ("Acme Lending" vs "Acme Lending
LLC"). This runs for every attendee with any NMLS match at all, including
ones with no CRM record found only through the name+company fallback -
blank means no NMLS match happened, not that the companies differ.

Like the CRM pull, this authenticates via Windows Integrated Auth, no
credentials needed. Unlike a typical bulk NMLS export (which processes the
*entire* `dbo.Individual` table - hundreds of thousands of rows, meant to
run offline), this is scoped: it only queries the specific ids/names that
are actually relevant to this run, via SQL `IN (...)` filters, batched at
500 at a time to stay under SQL Server's parameter limit. See
`matcher/nmls.py` for the full "Authorized to Represent" derivation logic
(ported from a reporting script, one simplification: it keeps only the
single most recent authorized location per person, not every one they've
ever held). Like the CRM query, this has only been exercised against a
mocked schema (`sample_data/smoke_test_nmls.py`,
`sample_data/smoke_test_nmls_fallback.py`), not a live database - verify
the `Name` column really exists on both `dbo.Company` and `dbo.Branch` in
your instance before relying on it.

## Also used as a backend by the browser extension

`tools/tradeshow-matcher-extension/` is a Chrome/Edge extension version of
this same tool. It runs entirely client-side, but a browser can't open a
direct SQL Server connection, so its "Pull live via local backend" and
"NMLS enrichment" options call this Flask app's `/api/contacts`,
`/api/leads`, and `/api/nmls` JSON endpoints instead, which do the real
`pyodbc` calls and return standardized rows. Keep `python app.py` running
here if you want to use those options from the extension. CORS on those
routes is restricted to `chrome-extension://` origins only (see `app.py`)
— never widen that to `*`.

## Sample data

`sample_data/make_samples.py` generates small synthetic fixtures covering
all four field combinations; `sample_data/smoke_test.py` runs the pipeline
against them without the web server, for quick regression checks after
changing matching logic.
